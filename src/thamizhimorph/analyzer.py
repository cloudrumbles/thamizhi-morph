"""High-level morphological analyser and generator."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import cast

from .backend import FomaBackend, LookupBackend, LookupMap
from .dictionary import SQLiteDictionary
from .errors import BackendError, ConfigurationError
from .models import (
    Analysis,
    AnalysisStatus,
    DictionaryEntry,
    GenerationResult,
    ModelSpec,
    SentenceResult,
    TokenContext,
    TokenResult,
)
from .normalization import contains_tamil, normalize_token, simple_tokenize
from .parsing import merge_analyses, parse_analysis
from .ranking import dictionary_upos_values, infer_context_features, rank_analyses
from .model_resources import load_model_specs


class Analyzer:
    """Compose the existing FSTs into a typed, auditable application interface."""

    def __init__(
        self,
        *,
        backend: LookupBackend | None = None,
        model_dir: str | Path | None = None,
        manifest_path: str | Path | None = None,
        exact_models: Sequence[ModelSpec] | None = None,
        guesser_models: Sequence[ModelSpec] | None = None,
        dictionary: SQLiteDictionary | None = None,
        strict_guesser_pos: bool = True,
    ) -> None:
        if exact_models is None or guesser_models is None:
            loaded_exact, loaded_guessers = load_model_specs(manifest_path)
            exact_models = loaded_exact if exact_models is None else exact_models
            guesser_models = loaded_guessers if guesser_models is None else guesser_models

        self.exact_models = tuple(exact_models)
        self.guesser_models = tuple(guesser_models)
        if not self.exact_models:
            raise ConfigurationError("at least one exact model is required")
        self.backend = backend if backend is not None else FomaBackend(model_dir=model_dir)
        self.dictionary = dictionary
        self.strict_guesser_pos = strict_guesser_pos
        self._model_priorities = {
            model.filename: model.priority
            for model in (*self.exact_models, *self.guesser_models)
        }

    @property
    def models(self) -> tuple[ModelSpec, ...]:
        return (*self.exact_models, *self.guesser_models)

    def _parse_lookup(
        self,
        lookup: LookupMap,
        *,
        guessed: bool,
    ) -> dict[str, tuple[Analysis, ...]]:
        parsed: dict[str, tuple[Analysis, ...]] = {}
        for token, records in lookup.items():
            candidates: list[Analysis] = []
            for raw, model in records:
                try:
                    candidates.append(
                        parse_analysis(raw, source_model=model, guessed=guessed)
                    )
                except ValueError as error:
                    raise BackendError(
                        f"model {model} returned an invalid analysis for {token!r}: {raw!r}"
                    ) from error
            parsed[token] = merge_analyses(candidates)
        return parsed

    def _allowed_guesser_models(self, context: TokenContext | None) -> frozenset[str] | None:
        if not self.strict_guesser_pos or context is None or not context.upos:
            return None
        upos = context.upos.upper()
        return frozenset(
            model.filename
            for model in self.guesser_models
            if not model.pos_hints or upos in model.pos_hints
        )

    def analyze_tokens(
        self,
        tokens: Sequence[str],
        *,
        contexts: Sequence[TokenContext | None] | None = None,
        pos_hints: Sequence[str | None] | None = None,
        use_guessers: bool = True,
        include_dictionary: bool = False,
        analyze_non_tamil: bool = False,
    ) -> tuple[TokenResult, ...]:
        """Analyse a sequence while preserving every candidate and its provenance."""

        if contexts is not None and pos_hints is not None:
            raise ValueError("pass contexts or pos_hints, not both")
        if pos_hints is not None:
            contexts = tuple(
                TokenContext(upos=hint.upper()) if hint else None for hint in pos_hints
            )
        if contexts is None:
            contexts = tuple(None for _ in tokens)
        if len(contexts) != len(tokens):
            raise ValueError("contexts/pos_hints must have the same length as tokens")

        normalized = tuple(normalize_token(token) for token in tokens)
        analysable = tuple(
            dict.fromkeys(
                token
                for token in normalized
                if token and (analyze_non_tamil or contains_tamil(token))
            )
        )

        exact_lookup = self.backend.lookup_models(analysable, self.exact_models)
        exact = self._parse_lookup(exact_lookup, guessed=False)
        unknown = tuple(token for token in analysable if not exact.get(token))

        guessed: dict[str, tuple[Analysis, ...]] = {}
        if use_guessers and unknown and self.guesser_models:
            guess_lookup = self.backend.lookup_models(unknown, self.guesser_models)
            guessed = self._parse_lookup(guess_lookup, guessed=True)

        dictionary_results: dict[str, tuple[DictionaryEntry, ...]] = {}
        if include_dictionary:
            if self.dictionary is None:
                raise ConfigurationError(
                    "dictionary lookup was requested but no SQLiteDictionary was configured"
                )
            dictionary_results = self.dictionary.lookup_many(analysable)

        results: list[TokenResult] = []
        for original, token, context in zip(tokens, normalized, contexts, strict=True):
            if not token or (not analyze_non_tamil and not contains_tamil(token)):
                results.append(
                    TokenResult(
                        token=original,
                        normalized=token,
                        status="skipped",
                        context=context,
                    )
                )
                continue

            candidates = exact.get(token, ())
            status = "exact"
            if not candidates:
                candidates = guessed.get(token, ())
                status = "guessed"
                allowed = self._allowed_guesser_models(context)
                if allowed is not None:
                    candidates = tuple(
                        candidate
                        for candidate in candidates
                        if allowed.intersection(candidate.source_models)
                    )

            entries = dictionary_results.get(token, ())
            if candidates:
                dictionary_upos = dictionary_upos_values(entry.pos for entry in entries)
                ranked = rank_analyses(
                    candidates,
                    context=context,
                    dictionary_upos=dictionary_upos,
                    model_priorities=self._model_priorities,
                )
                selected = (
                    0
                    if len(ranked) == 1
                    or (len(ranked) > 1 and ranked[0].score > ranked[1].score)
                    else None
                )
            else:
                ranked = ()
                selected = None
                status = "lexical_only" if entries else "unknown"

            results.append(
                TokenResult(
                    token=original,
                    normalized=token,
                    status=cast(AnalysisStatus, status),
                    analyses=ranked,
                    selected=selected,
                    dictionary_entries=entries,
                    context=context,
                    context_features=infer_context_features(token, context),
                )
            )

        return tuple(results)

    def analyze_word(
        self,
        word: str,
        *,
        pos_hint: str | None = None,
        use_guessers: bool = True,
        include_dictionary: bool = False,
    ) -> TokenResult:
        result = self.analyze_tokens(
            (word,),
            pos_hints=(pos_hint,),
            use_guessers=use_guessers,
            include_dictionary=include_dictionary,
        )
        return result[0]

    def analyze_text(
        self,
        text: str,
        *,
        use_guessers: bool = True,
        include_dictionary: bool = False,
        sent_id: str | None = None,
    ) -> SentenceResult:
        tokens = simple_tokenize(text)
        return SentenceResult(
            text=text,
            sent_id=sent_id,
            tokens=self.analyze_tokens(
                tokens,
                use_guessers=use_guessers,
                include_dictionary=include_dictionary,
            ),
        )

    def generate(
        self,
        lexical_form: str,
        *,
        model_names: Sequence[str] | None = None,
    ) -> GenerationResult:
        """Generate all surface forms accepted by selected exact transducers."""

        normalized = normalize_token(lexical_form)
        selected_models = self.exact_models
        if model_names:
            requested = set(model_names)
            selected_models = tuple(
                model for model in self.exact_models if model.filename in requested
            )
            missing = requested.difference(model.filename for model in selected_models)
            if missing:
                raise ConfigurationError(
                    f"unknown exact model(s): {', '.join(sorted(missing))}"
                )

        lookup = self.backend.lookup_models((normalized,), selected_models, inverse=True)
        records = lookup.get(normalized, ())
        forms: list[str] = []
        sources: list[str] = []
        for surface, model in records:
            surface = normalize_token(surface)
            if surface not in forms:
                forms.append(surface)
            if model not in sources:
                sources.append(model)
        return GenerationResult(
            lexical_form=normalized,
            forms=tuple(forms),
            source_models=tuple(sources),
        )

    def health(self) -> dict[str, object]:
        checker = getattr(self.backend, "health", None)
        if checker is None:
            return {"ready": True, "backend": type(self.backend).__name__}
        return cast(dict[str, object], checker(self.models))
