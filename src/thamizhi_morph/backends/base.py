from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Protocol

from ..models import BackendHealth, MorphAnalysis


class BackendError(RuntimeError):
    """Base exception for analyser backends."""


class MorphologyBackend(Protocol):
    name: str

    def analyze_many(
        self,
        words: Sequence[str],
        *,
        guess: bool = False,
    ) -> Mapping[str, tuple[MorphAnalysis, ...]]: ...

    def generate_many(
        self,
        lexical_forms: Sequence[str],
        *,
        model: str | None = None,
    ) -> Mapping[str, tuple[str, ...]]: ...

    def health(self) -> BackendHealth: ...
