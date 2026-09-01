"""Parsers for Foma's textual lookup protocol."""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Iterable

from .models import Analysis, Morpheme
from .normalization import normalize_token

_BOUNDARY_RE = re.compile(r"(?:\|\+|\+|\|)")
_UNKNOWN_OUTPUTS = {"?", "+?"}


def parse_flookup_pairs(output: str) -> dict[str, tuple[str, ...]]:
    """Parse ``flookup`` output into input-to-output pairs.

    Foma repeats the input in the first tab-separated field for every possible output.
    Unknown markers are discarded, while malformed diagnostic lines are ignored.
    """

    values: dict[str, list[str]] = defaultdict(list)
    for raw_line in output.splitlines():
        line = raw_line.rstrip("\r")
        if not line or "\t" not in line:
            continue
        source, target = line.split("\t", 1)
        source = normalize_token(source)
        target = target.strip()
        if not source or not target or target in _UNKNOWN_OUTPUTS:
            continue
        if target not in values[source]:
            values[source].append(target)
    return {key: tuple(items) for key, items in values.items()}


def parse_analysis(raw: str, *, source_model: str, guessed: bool = False) -> Analysis:
    """Convert a ThamizhiMorph lexical string into a structured candidate.

    Both the plus-only format shown in the repository README and the pipe-delimited
    format described in the paper are accepted.
    """

    fields = [part.strip() for part in _BOUNDARY_RE.split(raw.strip()) if part.strip()]
    if not fields:
        raise ValueError("cannot parse an empty morphological analysis")

    lemma = normalize_token(fields[0])
    pos = fields[1].lower() if len(fields) > 1 else "unknown"
    morphemes: list[Morpheme] = []

    for field in fields[2:]:
        if "=" in field:
            label, surface = field.split("=", 1)
            morphemes.append(Morpheme(label=label.strip(), surface=surface.strip() or None))
        else:
            morphemes.append(Morpheme(label=field, surface=None))

    return Analysis(
        lemma=lemma,
        pos=pos,
        morphemes=tuple(morphemes),
        raw=raw.strip(),
        source_models=(source_model,),
        guessed=guessed,
    )


def merge_analyses(analyses: Iterable[Analysis]) -> tuple[Analysis, ...]:
    """Deduplicate identical lexical strings while retaining model provenance."""

    merged: dict[tuple[str, bool], Analysis] = {}
    source_sets: dict[tuple[str, bool], list[str]] = {}

    for analysis in analyses:
        key = (analysis.raw, analysis.guessed)
        if key not in merged:
            merged[key] = analysis
            source_sets[key] = list(analysis.source_models)
            continue
        for source in analysis.source_models:
            if source not in source_sets[key]:
                source_sets[key].append(source)

    return tuple(
        merged[key].with_sources(tuple(source_sets[key]))
        for key in merged
    )
