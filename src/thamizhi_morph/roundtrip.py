from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from .engine import MorphologyEngine
from .models import MorphAnalysis, TokenKind
from .normalization import normalize_text


@dataclass(frozen=True, slots=True)
class RoundTripFailure:
    surface: str
    lexical: str
    model: str
    generated: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "surface": self.surface,
            "lexical": self.lexical,
            "model": self.model,
            "generated": list(self.generated),
        }


@dataclass(frozen=True, slots=True)
class ModelRoundTripStats:
    checked: int
    passed: int
    failed: int

    def to_dict(self) -> dict[str, int | float]:
        return {
            "checked": self.checked,
            "passed": self.passed,
            "failed": self.failed,
            "pass_rate": round(self.passed / self.checked, 6) if self.checked else 0.0,
        }


@dataclass(frozen=True, slots=True)
class RoundTripReport:
    input_tokens: int
    analysed_tokens: int
    checked_analyses: int
    passed: int
    failed: int
    skipped: int
    by_model: dict[str, ModelRoundTripStats]
    failures: tuple[RoundTripFailure, ...]

    @property
    def pass_rate(self) -> float:
        return self.passed / self.checked_analyses if self.checked_analyses else 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "input_tokens": self.input_tokens,
            "analysed_tokens": self.analysed_tokens,
            "checked_analyses": self.checked_analyses,
            "passed": self.passed,
            "failed": self.failed,
            "skipped": self.skipped,
            "pass_rate": round(self.pass_rate, 6),
            "by_model": {
                model: stats.to_dict() for model, stats in sorted(self.by_model.items())
            },
            "failures": [failure.to_dict() for failure in self.failures],
        }


def _is_checkable(analysis: MorphAnalysis, *, include_guessers: bool) -> bool:
    if not analysis.raw or not analysis.model:
        return False
    if analysis.model == "builtin" or analysis.model == "dictionary-fallback":
        return False
    if analysis.model.startswith("overlay:"):
        return False
    return include_guessers or not analysis.guessed


def validate_round_trips(
    engine: MorphologyEngine,
    words: Sequence[str],
    *,
    include_guessers: bool = False,
    max_failures: int = 100,
) -> RoundTripReport:
    """Check that analyses regenerate their original surface through the same FST."""

    if max_failures < 0:
        raise ValueError("max_failures must not be negative")

    tokens = engine.analyze_words(words, use_guessers=include_guessers)
    grouped: dict[str, list[tuple[str, MorphAnalysis]]] = defaultdict(list)
    skipped = 0
    analysed_tokens = 0

    for token in tokens:
        if token.kind is not TokenKind.TAMIL or not token.analyses:
            continue
        analysed_tokens += 1
        for analysis in token.analyses:
            if _is_checkable(analysis, include_guessers=include_guessers):
                grouped[analysis.model].append((token.normalized, analysis))
            else:
                skipped += 1

    counters: dict[str, Counter[str]] = defaultdict(Counter)
    failures: list[RoundTripFailure] = []

    for model, candidates in sorted(grouped.items()):
        lexical_forms = tuple(dict.fromkeys(analysis.raw for _surface, analysis in candidates))
        generated_by_lexical = engine.generate_many(lexical_forms, model=model)
        for surface, analysis in candidates:
            generated = tuple(generated_by_lexical.get(analysis.raw, ()))
            normalized_generated = {
                normalize_text(form).normalized for form in generated
            }
            counters[model]["checked"] += 1
            if surface in normalized_generated:
                counters[model]["passed"] += 1
            else:
                counters[model]["failed"] += 1
                if len(failures) < max_failures:
                    failures.append(
                        RoundTripFailure(
                            surface=surface,
                            lexical=analysis.raw,
                            model=model,
                            generated=generated,
                        )
                    )

    by_model = {
        model: ModelRoundTripStats(
            checked=counts["checked"],
            passed=counts["passed"],
            failed=counts["failed"],
        )
        for model, counts in counters.items()
    }
    checked = sum(stats.checked for stats in by_model.values())
    passed = sum(stats.passed for stats in by_model.values())
    failed = sum(stats.failed for stats in by_model.values())
    return RoundTripReport(
        input_tokens=len(tokens),
        analysed_tokens=analysed_tokens,
        checked_analyses=checked,
        passed=passed,
        failed=failed,
        skipped=skipped,
        by_model=by_model,
        failures=tuple(failures),
    )
