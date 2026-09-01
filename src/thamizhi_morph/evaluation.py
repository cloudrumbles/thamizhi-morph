from __future__ import annotations

import time
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from .engine import MorphologyEngine
from .models import TokenAnalysis, TokenKind


@dataclass(frozen=True, slots=True)
class CoverageReport:
    total: int
    known: int
    guessed: int
    dictionary_only: int
    unknown: int
    elapsed_ms: float
    tokens_per_second: float
    by_kind: dict[str, int]
    unknown_words: tuple[str, ...]

    @property
    def known_coverage(self) -> float:
        return self.known / self.total if self.total else 0.0

    @property
    def recoverable_coverage(self) -> float:
        return (self.known + self.guessed) / self.total if self.total else 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "total": self.total,
            "known": self.known,
            "guessed": self.guessed,
            "dictionary_only": self.dictionary_only,
            "unknown": self.unknown,
            "known_coverage": round(self.known_coverage, 6),
            "recoverable_coverage": round(self.recoverable_coverage, 6),
            "elapsed_ms": round(self.elapsed_ms, 3),
            "tokens_per_second": round(self.tokens_per_second, 2),
            "by_kind": self.by_kind,
            "unknown_words": list(self.unknown_words),
        }


def _classification(token: TokenAnalysis) -> str:
    if token.kind is not TokenKind.TAMIL:
        return "known"
    if not token.analyses:
        return "unknown"
    if all(analysis.model == "dictionary-fallback" for analysis in token.analyses):
        return "dictionary_only"
    if all(analysis.guessed for analysis in token.analyses):
        return "guessed"
    return "known"


def evaluate_words(
    engine: MorphologyEngine,
    words: Sequence[str],
    *,
    use_guessers: bool = True,
    enrich_dictionary: bool = False,
    max_unknown_words: int = 100,
) -> CoverageReport:
    started = time.perf_counter()
    results = engine.analyze_words(
        words,
        use_guessers=use_guessers,
        enrich_dictionary=enrich_dictionary,
    )
    elapsed = time.perf_counter() - started
    classes = Counter(_classification(token) for token in results)
    kinds = Counter(token.kind.value for token in results)
    unknown = tuple(
        token.token
        for token in results
        if _classification(token) == "unknown"
    )[:max_unknown_words]
    total = len(results)
    return CoverageReport(
        total=total,
        known=classes["known"],
        guessed=classes["guessed"],
        dictionary_only=classes["dictionary_only"],
        unknown=classes["unknown"],
        elapsed_ms=elapsed * 1000,
        tokens_per_second=total / elapsed if elapsed else 0.0,
        by_kind=dict(sorted(kinds.items())),
        unknown_words=unknown,
    )
