"""Loss-conscious conversion to the ten-column CoNLL-U format."""

from __future__ import annotations

import re
from urllib.parse import quote

from .models import Analysis, SentenceResult, TokenResult
from .normalization import is_punctuation
from .ranking import upos_for_internal_pos

_CASES = {
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
_TENSES = {"past": "Past", "pres": "Pres", "present": "Pres", "fut": "Fut", "future": "Fut"}


def _labels(analysis: Analysis) -> set[str]:
    values: set[str] = set()
    for morpheme in analysis.morphemes:
        lower = morpheme.label.lower()
        values.add(lower)
        values.update(piece for piece in re.split(r"and|[-_]", lower) if piece)
    return values


def _features(analysis: Analysis | None, token: TokenResult) -> str:
    features: dict[str, str] = {
        feature.name: feature.value for feature in token.context_features
    }
    if analysis is None:
        return "|".join(f"{key}={value}" for key, value in sorted(features.items())) or "_"

    labels = _labels(analysis)
    for label, value in _CASES.items():
        if label in labels:
            features["Case"] = value
            break
    for label, value in _TENSES.items():
        if label in labels:
            features["Tense"] = value
            break

    compact = " ".join(labels)
    person_match = re.search(r"(?<!\d)([123])(?:s|sg|p|pl|e)", compact)
    if person_match:
        features["Person"] = person_match.group(1)
    if re.search(r"(?:^|\W)(?:sg|[123]s)(?:\W|$)", compact) or re.search(
        r"[123](?:sg|s)[a-z]*", compact
    ):
        features["Number"] = "Sing"
    if re.search(r"(?:^|\W)(?:pl|[123]p)(?:\W|$)", compact) or re.search(
        r"[123](?:pl|p)[a-z]*", compact
    ):
        features["Number"] = "Plur"

    if any(re.search(pattern, compact) for pattern in (r"3(?:sg|s)m", r"masc")):
        features["Gender"] = "Masc"
    elif any(re.search(pattern, compact) for pattern in (r"3(?:sg|s)f", r"fem")):
        features["Gender"] = "Fem"
    elif any(re.search(pattern, compact) for pattern in (r"3(?:sg|s|pl|p)n", r"neut")):
        features["Gender"] = "Neut"

    if "fin" in labels:
        features["VerbForm"] = "Fin"
    if "inf" in labels or "infinitive" in labels:
        features["VerbForm"] = "Inf"
    if "vpart" in labels or "participle" in labels:
        features["VerbForm"] = "Part"
    if "imp" in labels or "imperative" in labels:
        features["Mood"] = "Imp"
    if "neg" in labels or "negative" in labels:
        features["Polarity"] = "Neg"
    if "pass" in labels or "passive" in labels:
        features["Voice"] = "Pass"
    if "caus" in labels or "causative" in labels:
        features["Voice"] = "Cau"

    return "|".join(f"{key}={value}" for key, value in sorted(features.items())) or "_"


def _misc(token: TokenResult, analysis: Analysis | None) -> str:
    values = [f"TMStatus={token.status.title().replace('_', '')}"]
    if len(token.analyses) > 1:
        values.append(f"TMCandidates={len(token.analyses)}")
    if analysis is not None:
        values.append(f"TMAnalysis={quote(analysis.raw, safe=':+_./-')}")
        values.append(
            f"TMModels={quote(','.join(analysis.source_models), safe='._,-')}"
        )
        if analysis.guessed:
            values.append("TMGuessed=Yes")
        if analysis.reasons:
            values.append(
                f"TMSelection={quote('; '.join(analysis.reasons), safe='._,-')}"
            )
    if token.dictionary_entries:
        sources = sorted({entry.source for entry in token.dictionary_entries})
        values.append(f"TMDictSources={quote(','.join(sources), safe='._,-')}")
    return "|".join(values)


def token_to_conllu(token: TokenResult, token_id: int) -> str:
    """Serialise one token as a valid ten-column CoNLL-U row."""

    analysis = token.selected_analysis
    context = token.context
    if context and context.upos:
        upos = context.upos.upper()
    elif analysis:
        compatible = upos_for_internal_pos(analysis.pos)
        upos = compatible[0] if compatible else "X"
    elif is_punctuation(token.normalized):
        upos = "PUNCT"
    else:
        upos = "X"

    lemma = analysis.lemma if analysis else "_"
    xpos = context.xpos if context and context.xpos else (analysis.pos if analysis else "_")
    head = str(context.head) if context and context.head is not None else "_"
    deprel = context.deprel if context and context.deprel else "_"

    columns = (
        str(token_id),
        token.normalized or token.token,
        lemma,
        upos,
        xpos,
        _features(analysis, token),
        head,
        deprel,
        "_",
        _misc(token, analysis),
    )
    return "\t".join(columns)


def sentence_to_conllu(sentence: SentenceResult) -> str:
    """Serialise a sentence and retain the original text as metadata."""

    comments: list[str] = []
    if sentence.sent_id:
        comments.append(f"# sent_id = {sentence.sent_id}")
    comments.append(f"# text = {sentence.text.replace(chr(10), ' ')}")
    rows = [token_to_conllu(token, index) for index, token in enumerate(sentence.tokens, 1)]
    return "\n".join((*comments, *rows, ""))
