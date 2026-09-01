from __future__ import annotations

import threading
import time
from collections import OrderedDict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from .backends.base import MorphologyBackend
from .context import PosTagger, TaggedToken
from .dictionary import AvvaiDictionary
from .models import (
    BackendHealth,
    DocumentAnalysis,
    Gloss,
    MorphAnalysis,
    TokenAnalysis,
    TokenKind,
)
from .normalization import classify_token, normalize_text, tokenize

_POS_COMPATIBILITY: dict[str, frozenset[str]] = {
    "NOUN": frozenset({"noun"}),
    "PROPN": frozenset({"noun", "propernoun"}),
    "PRON": frozenset({"pronoun", "noun"}),
    "VERB": frozenset({"verb"}),
    "AUX": frozenset({"verb", "auxiliary"}),
    "ADJ": frozenset({"adjective", "adj"}),
    "ADV": frozenset({"adverb", "adv"}),
    "NUM": frozenset({"number", "numeral", "cardinal", "ordinal"}),
    "DET": frozenset({"particle", "demonstrative", "dem"}),
    "ADP": frozenset({"particle", "casemarker", "postposition", "nmod"}),
    "CCONJ": frozenset({"particle", "conjunction"}),
    "SCONJ": frozenset({"particle", "conjunction", "complementizer"}),
    "PART": frozenset({"particle"}),
}


@dataclass(frozen=True, slots=True)
class _CachedCandidates:
    analyses: tuple[MorphAnalysis, ...]
    warnings: tuple[str, ...]


class _LruCache:
    def __init__(self, max_size: int) -> None:
        self.max_size = max(0, max_size)
        self._items: OrderedDict[tuple[object, ...], _CachedCandidates] = OrderedDict()
        self._lock = threading.RLock()

    def get(self, key: tuple[object, ...]) -> _CachedCandidates | None:
        if self.max_size == 0:
            return None
        with self._lock:
            value = self._items.get(key)
            if value is not None:
                self._items.move_to_end(key)
            return value

    def put(self, key: tuple[object, ...], value: _CachedCandidates) -> None:
        if self.max_size == 0:
            return
        with self._lock:
            self._items[key] = value
            self._items.move_to_end(key)
            while len(self._items) > self.max_size:
                self._items.popitem(last=False)

    def clear(self) -> None:
        with self._lock:
            self._items.clear()


class MorphologyEngine:
    def __init__(
        self,
        backend: MorphologyBackend,
        *,
        dictionary: AvvaiDictionary | None = None,
        cache_size: int = 4096,
    ) -> None:
        self.backend = backend
        self.dictionary = dictionary
        self._cache = _LruCache(cache_size)

    @staticmethod
    def _synthetic(token: str, kind: TokenKind) -> tuple[MorphAnalysis, ...]:
        pos = {
            TokenKind.PUNCTUATION: "punct",
            TokenKind.NUMBER: "number",
            TokenKind.FOREIGN: "foreign",
            TokenKind.SYMBOL: "symbol",
        }.get(kind, "unknown")
        return (
            MorphAnalysis(
                surface=token,
                lemma=token,
                pos=pos,
                model="builtin",
                raw=token,
                score=100.0,
            ),
        )

    @staticmethod
    def _score(analysis: MorphAnalysis, pos_hint: str | None, order: int) -> float:
        if analysis.model == "dictionary-fallback":
            score = 8.0
        else:
            score = 100.0 if not analysis.guessed else 35.0
        if pos_hint:
            compatible = _POS_COMPATIBILITY.get(pos_hint.upper(), frozenset())
            if analysis.pos in compatible or analysis.pos == pos_hint.lower():
                score += 50.0
            else:
                score -= 15.0
        if analysis.glosses:
            score += 2.0
        score -= min(len(analysis.morphemes), 100) * 0.001
        score -= order * 0.0001
        return score

    @classmethod
    def _rank(
        cls,
        analyses: Sequence[MorphAnalysis],
        pos_hint: str | None,
    ) -> tuple[MorphAnalysis, ...]:
        scored = [
            analysis.with_score(cls._score(analysis, pos_hint, index))
            for index, analysis in enumerate(analyses)
        ]
        return tuple(sorted(scored, key=lambda item: item.score, reverse=True))

    @staticmethod
    def _dictionary_fallback(
        surface: str,
        glosses: tuple[Gloss, ...],
    ) -> MorphAnalysis:
        first_pos = glosses[0].pos if glosses else ""
        return MorphAnalysis(
            surface=surface,
            lemma=surface,
            pos=AvvaiDictionary.map_pos(first_pos),
            model="dictionary-fallback",
            guessed=True,
            raw=surface,
            glosses=glosses,
        )

    def analyze_words(
        self,
        words: Sequence[str],
        *,
        pos_hints: Sequence[str | None] | None = None,
        use_guessers: bool = True,
        enrich_dictionary: bool = False,
    ) -> tuple[TokenAnalysis, ...]:
        if pos_hints is not None and len(pos_hints) != len(words):
            raise ValueError("pos_hints must have the same length as words")

        records: list[tuple[str, str, TokenKind, str | None, tuple[str, ...]]] = []
        for index, word in enumerate(words):
            normalized = normalize_text(word)
            warnings: list[str] = []
            if normalized.changed:
                warnings.append("input was Unicode-normalized")
            if normalized.removed_codepoints:
                warnings.append(
                    "removed invisible formatting characters: "
                    + ", ".join(normalized.removed_codepoints)
                )
            records.append(
                (
                    word,
                    normalized.normalized,
                    classify_token(normalized.normalized),
                    pos_hints[index] if pos_hints is not None else None,
                    tuple(warnings),
                )
            )

        candidate_by_key: dict[tuple[object, ...], _CachedCandidates] = {}
        pending_keys: list[tuple[object, ...]] = []
        for _word, normalized, kind, pos_hint, _warnings in records:
            key = (normalized, kind.value, pos_hint, use_guessers, enrich_dictionary)
            if key in candidate_by_key:
                continue
            cached = self._cache.get(key)
            if cached is None:
                pending_keys.append(key)
            else:
                candidate_by_key[key] = cached

        tamil_words = tuple(
            dict.fromkeys(str(key[0]) for key in pending_keys if key[1] == TokenKind.TAMIL.value)
        )
        known = self.backend.analyze_many(tamil_words, guess=False) if tamil_words else {}
        unknown_words = tuple(word for word in tamil_words if not known.get(word))
        guessed = (
            self.backend.analyze_many(unknown_words, guess=True)
            if use_guessers and unknown_words
            else {}
        )

        dictionary_terms: list[str] = []
        if enrich_dictionary and self.dictionary is not None:
            for word in tamil_words:
                dictionary_terms.append(word)
                for analysis in known.get(word, ()) or guessed.get(word, ()):
                    dictionary_terms.append(analysis.lemma)
            dictionary_matches = self.dictionary.lookup_many(dictionary_terms)
        else:
            dictionary_matches = {}

        for key in pending_keys:
            normalized = str(key[0])
            kind = TokenKind(str(key[1]))
            pos_hint = key[2] if isinstance(key[2], str) else None
            base_warnings: list[str] = []

            if kind is not TokenKind.TAMIL:
                analyses = self._synthetic(normalized, kind)
            else:
                source = known.get(normalized, ())
                if not source:
                    source = guessed.get(normalized, ())
                    if source:
                        base_warnings.append("analysis produced by an out-of-vocabulary guesser")
                enriched: list[MorphAnalysis] = []
                for analysis in source:
                    glosses = tuple(dictionary_matches.get(analysis.lemma, ()))
                    enriched.append(analysis.with_glosses(glosses) if glosses else analysis)
                analyses = tuple(enriched)

                if not analyses:
                    glosses = tuple(dictionary_matches.get(normalized, ()))
                    if glosses:
                        analyses = (self._dictionary_fallback(normalized, glosses),)
                        base_warnings.append(
                            "dictionary-only fallback; no inflectional morphology was recovered"
                        )
                    else:
                        base_warnings.append("no morphological analysis found")

            ranked = self._rank(analyses, pos_hint)
            value = _CachedCandidates(ranked, tuple(base_warnings))
            candidate_by_key[key] = value
            self._cache.put(key, value)

        output: list[TokenAnalysis] = []
        for word, normalized, kind, pos_hint, normalization_warnings in records:
            key = (normalized, kind.value, pos_hint, use_guessers, enrich_dictionary)
            candidates = candidate_by_key[key]
            output.append(
                TokenAnalysis(
                    token=word,
                    normalized=normalized,
                    kind=kind,
                    analyses=candidates.analyses,
                    selected=0 if candidates.analyses else None,
                    pos_hint=pos_hint,
                    warnings=normalization_warnings + candidates.warnings,
                )
            )
        return tuple(output)

    def analyze_text(
        self,
        text: str,
        *,
        use_guessers: bool = True,
        enrich_dictionary: bool = False,
    ) -> DocumentAnalysis:
        started = time.perf_counter()
        text_tokens = tokenize(text)
        analyses = self.analyze_words(
            [token.text for token in text_tokens],
            use_guessers=use_guessers,
            enrich_dictionary=enrich_dictionary,
        )
        tokens = tuple(
            analysis.with_offsets(token.start, token.end)
            for token, analysis in zip(text_tokens, analyses, strict=True)
        )
        return DocumentAnalysis(
            text=text,
            tokens=tokens,
            elapsed_ms=(time.perf_counter() - started) * 1000,
            backend=self.backend.name,
        )

    def analyze_contextual(
        self,
        text: str,
        tagger: PosTagger,
        *,
        use_guessers: bool = True,
        enrich_dictionary: bool = False,
    ) -> DocumentAnalysis:
        started = time.perf_counter()
        tagged = tuple(tagger.tag(text))
        analyses = self.analyze_words(
            [token.text for token in tagged],
            pos_hints=[token.upos for token in tagged],
            use_guessers=use_guessers,
            enrich_dictionary=enrich_dictionary,
        )
        tokens = self._align_contextual_offsets(text, tagged, analyses)
        return DocumentAnalysis(
            text=text,
            tokens=tokens,
            elapsed_ms=(time.perf_counter() - started) * 1000,
            backend=self.backend.name,
            metadata={"context_tagger": tagger.name},
        )

    @staticmethod
    def _align_contextual_offsets(
        text: str,
        tagged: Sequence[TaggedToken],
        analyses: Sequence[TokenAnalysis],
    ) -> tuple[TokenAnalysis, ...]:
        output: list[TokenAnalysis] = []
        cursor = 0
        for tag, analysis in zip(tagged, analyses, strict=True):
            start = tag.start
            end = tag.end
            if start is None or end is None:
                start = text.find(tag.text, cursor)
                if start < 0:
                    start = cursor
                end = start + len(tag.text)
            cursor = max(cursor, end)
            output.append(analysis.with_offsets(start, end))
        return tuple(output)

    def generate_many(
        self,
        lexical_forms: Sequence[str],
        *,
        model: str | None = None,
    ) -> Mapping[str, tuple[str, ...]]:
        normalized = [normalize_text(value).normalized for value in lexical_forms]
        return self.backend.generate_many(normalized, model=model)

    def health(self) -> dict[str, Any]:
        backend: BackendHealth = self.backend.health()
        dictionary: dict[str, Any] | None = None
        if self.dictionary is not None:
            dictionary = {
                "path": str(self.dictionary.path),
                "ready": True,
                **self.dictionary.statistics(),
            }
        return {
            "ready": backend.ready,
            "backend": backend.to_dict(),
            "dictionary": dictionary,
        }

    def clear_cache(self) -> None:
        self._cache.clear()

    def close(self) -> None:
        if self.dictionary is not None:
            self.dictionary.close()

    def __enter__(self) -> MorphologyEngine:
        return self

    def __exit__(self, _exc_type: object, _exc: object, _traceback: object) -> None:
        self.close()
