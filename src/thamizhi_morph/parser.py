from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from .models import MorphAnalysis, Morpheme

_UNKNOWN_MARKERS = frozenset({"?", "+?", "?+"})


@dataclass(frozen=True, slots=True)
class LookupParseResult:
    analyses: dict[str, tuple[MorphAnalysis, ...]]
    diagnostics: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class GenerationParseResult:
    forms: dict[str, tuple[str, ...]]
    diagnostics: tuple[str, ...]


def _parse_analysis(surface: str, lexical: str, model: str, guessed: bool) -> MorphAnalysis:
    parts = lexical.split("+")
    if len(parts) < 2 or not parts[0] or not parts[1]:
        raise ValueError(f"invalid lexical analysis: {lexical!r}")
    return MorphAnalysis(
        surface=surface,
        lemma=parts[0],
        pos=parts[1].strip().lower(),
        morphemes=tuple(Morpheme.parse(part) for part in parts[2:] if part),
        model=model,
        guessed=guessed,
        raw=lexical,
    )


def parse_lookup_output(output: str, *, model: str, guessed: bool = False) -> LookupParseResult:
    """Parse flookup's echoed, tab-separated output without losing ambiguity."""

    grouped: dict[str, list[MorphAnalysis]] = defaultdict(list)
    seen: dict[str, set[tuple[object, ...]]] = defaultdict(set)
    diagnostics: list[str] = []

    for line_number, raw_line in enumerate(output.splitlines(), start=1):
        line = raw_line.rstrip("\r")
        if not line:
            continue
        surface, separator, lexical = line.partition("\t")
        if not separator:
            diagnostics.append(f"line {line_number}: missing tab separator")
            continue
        lexical = lexical.strip()
        if lexical in _UNKNOWN_MARKERS or not lexical:
            grouped.setdefault(surface, [])
            continue
        try:
            analysis = _parse_analysis(surface, lexical, model, guessed)
        except ValueError as error:
            diagnostics.append(f"line {line_number}: {error}")
            continue
        signature: tuple[object, ...] = analysis.signature
        if signature not in seen[surface]:
            seen[surface].add(signature)
            grouped[surface].append(analysis)

    return LookupParseResult(
        analyses={surface: tuple(items) for surface, items in grouped.items()},
        diagnostics=tuple(diagnostics),
    )


def parse_generation_output(output: str) -> GenerationParseResult:
    grouped: dict[str, list[str]] = defaultdict(list)
    seen: dict[str, set[str]] = defaultdict(set)
    diagnostics: list[str] = []

    for line_number, raw_line in enumerate(output.splitlines(), start=1):
        line = raw_line.rstrip("\r")
        if not line:
            continue
        lexical, separator, surface = line.partition("\t")
        if not separator:
            diagnostics.append(f"line {line_number}: missing tab separator")
            continue
        surface = surface.strip()
        if surface in _UNKNOWN_MARKERS or not surface:
            grouped.setdefault(lexical, [])
            continue
        if surface not in seen[lexical]:
            seen[lexical].add(surface)
            grouped[lexical].append(surface)

    return GenerationParseResult(
        forms={lexical: tuple(items) for lexical, items in grouped.items()},
        diagnostics=tuple(diagnostics),
    )
