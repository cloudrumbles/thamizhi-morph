from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from ..models import BackendHealth, MorphAnalysis
from ..overlay import OverlayEntry, OverlayMode, OverlayStore
from .base import MorphologyBackend


class OverlayBackend:
    """Apply reviewed lexical corrections without mutating the underlying FST assets.

    Replace entries suppress exact FST output. Augment entries accompany exact output and
    become authoritative when no exact output exists. Fallback entries are introduced only
    during the guesser stage, where they outrank guesses because they are curated analyses.
    """

    def __init__(self, backend: MorphologyBackend, store: OverlayStore) -> None:
        self.backend = backend
        self.store = store
        self.name = f"{backend.name}+overlay"

    @staticmethod
    def _analyses(
        entries: Sequence[OverlayEntry],
        *modes: OverlayMode,
    ) -> tuple[MorphAnalysis, ...]:
        selected = frozenset(modes)
        return tuple(
            entry.to_analysis() for entry in entries if entry.mode in selected
        )

    @staticmethod
    def _deduplicate(
        analyses: Sequence[MorphAnalysis],
    ) -> tuple[MorphAnalysis, ...]:
        seen: set[tuple[object, ...]] = set()
        output: list[MorphAnalysis] = []
        for analysis in analyses:
            signature: tuple[object, ...] = analysis.signature
            if signature not in seen:
                seen.add(signature)
                output.append(analysis)
        return tuple(output)

    def analyze_many(
        self,
        words: Sequence[str],
        *,
        guess: bool = False,
    ) -> Mapping[str, tuple[MorphAnalysis, ...]]:
        values = tuple(dict.fromkeys(words))
        if not values:
            return {}
        entries_by_word = self.store.lookup_many(values)
        replace_words = {
            word
            for word, entries in entries_by_word.items()
            if any(entry.mode is OverlayMode.REPLACE for entry in entries)
        }
        delegated = tuple(word for word in values if word not in replace_words)
        base = self.backend.analyze_many(delegated, guess=guess) if delegated else {}
        output: dict[str, tuple[MorphAnalysis, ...]] = {}

        for word in values:
            entries = entries_by_word.get(word, ())
            replacements = self._analyses(entries, OverlayMode.REPLACE)
            augmentations = self._analyses(entries, OverlayMode.AUGMENT)
            if replacements:
                candidates = replacements + augmentations
            elif guess:
                fallbacks = self._analyses(entries, OverlayMode.FALLBACK)
                candidates = fallbacks + tuple(base.get(word, ())) + augmentations
            else:
                candidates = tuple(base.get(word, ())) + augmentations
            output[word] = self._deduplicate(candidates)
        return output

    def generate_many(
        self,
        lexical_forms: Sequence[str],
        *,
        model: str | None = None,
    ) -> Mapping[str, tuple[str, ...]]:
        if model is not None and model.startswith("overlay:"):
            return {value: () for value in lexical_forms}
        return self.backend.generate_many(lexical_forms, model=model)

    def health(self) -> BackendHealth:
        inner = self.backend.health()
        details: dict[str, Any] = {
            "backend": inner.to_dict(),
            "overlay": {
                "path": str(self.store.path),
                "writable": self.store.writable,
                **self.store.statistics(),
            },
        }
        return BackendHealth(
            name=self.name,
            ready=inner.ready,
            details=details,
        )

    def close(self) -> None:
        close = getattr(self.backend, "close", None)
        if callable(close):
            close()
        self.store.close()
