"""Reproducible coverage evaluation utilities."""

from __future__ import annotations

from collections.abc import Iterable, Iterator, Sequence
from pathlib import Path
from time import perf_counter

from .analyzer import Analyzer
from .models import CoverageReport, TokenResult


def read_wordlist(path: str | Path) -> list[str]:
    """Read one surface form per non-empty, non-comment line."""

    words: list[str] = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            words.append(stripped.split("\t", 1)[0])
    return words


def read_conllu_tokens(path: str | Path) -> list[str]:
    """Read FORM values from ordinary integer-token rows in a CoNLL-U file."""

    words: list[str] = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if not line or line.startswith("#"):
            continue
        columns = line.split("\t")
        if len(columns) != 10 or "-" in columns[0] or "." in columns[0]:
            continue
        words.append(columns[1])
    return words


def batched(values: Sequence[str], size: int) -> Iterator[Sequence[str]]:
    if size <= 0:
        raise ValueError("batch size must be positive")
    for offset in range(0, len(values), size):
        yield values[offset : offset + size]


def evaluate_coverage(
    analyzer: Analyzer,
    words: Iterable[str],
    *,
    use_guessers: bool = True,
    include_dictionary: bool = False,
    batch_size: int = 512,
) -> CoverageReport:
    """Measure analysability without conflating coverage with correctness."""

    materialized = tuple(words)
    started = perf_counter()
    results: list[TokenResult] = []
    for batch in batched(materialized, batch_size):
        results.extend(
            analyzer.analyze_tokens(
                batch,
                use_guessers=use_guessers,
                include_dictionary=include_dictionary,
            )
        )

    counts = {status: 0 for status in ("exact", "guessed", "lexical_only", "unknown", "skipped")}
    ambiguous = 0
    lemmas: set[str] = set()
    unknown_tokens: list[str] = []

    for result in results:
        counts[result.status] += 1
        if len(result.analyses) > 1:
            ambiguous += 1
        lemmas.update(analysis.lemma for analysis in result.analyses)
        if result.status == "unknown":
            unknown_tokens.append(result.normalized)

    return CoverageReport(
        total=len(results),
        exact=counts["exact"],
        guessed=counts["guessed"],
        lexical_only=counts["lexical_only"],
        unknown=counts["unknown"],
        skipped=counts["skipped"],
        ambiguous=ambiguous,
        unique_lemmas=len(lemmas),
        elapsed_seconds=perf_counter() - started,
        unknown_tokens=tuple(dict.fromkeys(unknown_tokens)),
    )
