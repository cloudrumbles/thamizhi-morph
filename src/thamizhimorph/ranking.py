"""Transparent candidate ranking without discarding ambiguity."""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping

from .models import Analysis, ContextFeature, TokenContext

_INTERNAL_TO_UPOS: dict[str, tuple[str, ...]] = {
    "noun": ("NOUN", "PROPN"),
    "pronoun": ("PRON",),
    "verb": ("VERB", "AUX"),
    "adj": ("ADJ",),
    "adjective": ("ADJ",),
    "adv": ("ADV",),
    "adverb": ("ADV",),
    "part": ("PART", "ADP", "DET", "CCONJ", "SCONJ"),
    "dem": ("DET", "PRON"),
    "cardinal": ("NUM",),
    "ordinal": ("NUM", "ADJ"),
    "conjunction": ("CCONJ", "SCONJ"),
    "conjuction": ("CCONJ", "SCONJ"),  # historical spelling in model output
    "nmod": ("ADP",),
    "casemarker": ("ADP",),
    "cop": ("AUX",),
}

_TAMIL_DICTIONARY_POS: dict[str, tuple[str, ...]] = {
    "பெயர்ச்சொல்": ("NOUN", "PROPN"),
    "வினைச்சொல்": ("VERB", "AUX"),
    "வினையடை": ("ADV",),
    "பெயரடை": ("ADJ",),
    "இடைச்சொல்": ("PART", "ADP"),
    "பிரதிப்பெயர்": ("PRON",),
    "இணைப்புச்சொல்": ("CCONJ", "SCONJ"),
    "வியப்பிடைச்சொல்": ("INTJ",),
}

_CASE_BY_LABEL = {
    "nom": "Nom",
    "acc": "Acc",
    "dat": "Dat",
    "gen": "Gen",
    "loc": "Loc",
    "abl": "Abl",
    "inst": "Ins",
    "ins": "Ins",
    "soc": "Com",
    "voc": "Voc",
}

_FREE_CASE_MARKERS = {
    "மூலம்": ("Case", "Ins"),
    "கொண்டு": ("Case", "Ins"),
}


def upos_for_internal_pos(pos: str) -> tuple[str, ...]:
    return _INTERNAL_TO_UPOS.get(pos.strip().lower(), ())


def upos_for_dictionary_pos(pos: str) -> tuple[str, ...]:
    return _TAMIL_DICTIONARY_POS.get(pos.strip(), ())


def dictionary_upos_values(positions: Iterable[str]) -> frozenset[str]:
    values: set[str] = set()
    for position in positions:
        values.update(upos_for_dictionary_pos(position))
    return frozenset(values)


def _normalised_labels(analysis: Analysis) -> set[str]:
    labels: set[str] = set()
    for label in analysis.labels:
        lower = label.lower()
        labels.add(lower)
        labels.update(part for part in re.split(r"and|[-_]", lower) if part)
    return labels


def _case_value(labels: set[str]) -> str | None:
    for label, value in _CASE_BY_LABEL.items():
        if label in labels:
            return value
    return None


def _context_score(analysis: Analysis, context: TokenContext | None) -> tuple[float, list[str]]:
    if context is None:
        return 0.0, []

    score = 0.0
    reasons: list[str] = []
    upos = context.upos.upper() if context.upos else None
    compatible = upos_for_internal_pos(analysis.pos)
    if upos and upos in compatible:
        score += 100.0
        reasons.append(f"POS agrees with {upos}")
    elif upos and compatible:
        score -= 20.0
        reasons.append(f"POS conflicts with {upos}")

    labels = _normalised_labels(analysis)
    relation = (context.deprel or "").lower()

    if relation in {"root", "conj", "ccomp"} and "fin" in labels:
        score += 12.0
        reasons.append(f"finite form fits {relation}")
    if relation in {"acl", "advcl", "xcomp"} and "nonfin" in labels:
        score += 12.0
        reasons.append(f"non-finite form fits {relation}")

    case = _case_value(labels)
    expected_cases: dict[str, set[str]] = {
        "obj": {"Acc"},
        "iobj": {"Dat"},
        "nmod": {"Gen"},
        "obl": {"Dat", "Loc", "Abl", "Ins", "Com"},
    }
    if case and relation in expected_cases:
        if case in expected_cases[relation]:
            score += 8.0
            reasons.append(f"{case} case fits {relation}")
        else:
            score -= 3.0

    return score, reasons


def rank_analyses(
    analyses: Iterable[Analysis],
    *,
    context: TokenContext | None = None,
    dictionary_upos: frozenset[str] = frozenset(),
    model_priorities: Mapping[str, int] | None = None,
) -> tuple[Analysis, ...]:
    """Rank candidates using explicit POS, dependency, and lexical evidence.

    This is a selector, not a destructive disambiguator: every candidate is returned.
    Scores and human-readable reasons make the ranking auditable.
    """

    priorities = model_priorities or {}
    ranked: list[tuple[Analysis, int]] = []

    for index, analysis in enumerate(analyses):
        score, reasons = _context_score(analysis, context)
        compatible = set(upos_for_internal_pos(analysis.pos))
        if dictionary_upos and compatible.intersection(dictionary_upos):
            score += 15.0
            reasons.append("POS supported by dictionary evidence")

        ranked.append((analysis.ranked(score=score, reasons=tuple(reasons)), index))

    ranked.sort(
        key=lambda item: (
            -item[0].score,
            min(
                (priorities.get(model, 1000) for model in item[0].source_models),
                default=1000,
            ),
            item[1],
        )
    )
    return tuple(item[0] for item in ranked)


def infer_context_features(token: str, context: TokenContext | None) -> tuple[ContextFeature, ...]:
    """Recognise a small, high-precision set of free case markers.

    The lexical form alone is ambiguous, so a marker is emitted only when an external
    parser labels the token as ADP or gives it the dependency relation ``case``.
    """

    marker = _FREE_CASE_MARKERS.get(token)
    if marker is None or context is None:
        return ()
    if (context.upos or "").upper() != "ADP" and (context.deprel or "").lower() != "case":
        return ()
    name, value = marker
    return (
        ContextFeature(
            name=name,
            value=value,
            evidence="free case marker licensed by external syntactic context",
        ),
    )
