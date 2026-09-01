from __future__ import annotations

import re
from urllib.parse import quote

from .models import DocumentAnalysis, MorphAnalysis, TokenAnalysis

_UPOS = {
    "noun": "NOUN",
    "propernoun": "PROPN",
    "pronoun": "PRON",
    "verb": "VERB",
    "auxiliary": "AUX",
    "adjective": "ADJ",
    "adj": "ADJ",
    "adverb": "ADV",
    "adv": "ADV",
    "particle": "PART",
    "conjunction": "CCONJ",
    "casemarker": "ADP",
    "postposition": "ADP",
    "number": "NUM",
    "numeral": "NUM",
    "cardinal": "NUM",
    "ordinal": "NUM",
    "punct": "PUNCT",
    "foreign": "X",
    "symbol": "SYM",
    "unknown": "X",
}

_CASE = {
    "nom": "Nom",
    "acc": "Acc",
    "dat": "Dat",
    "gen": "Gen",
    "abl": "Abl",
    "inst": "Ins",
    "ins": "Ins",
    "soc": "Com",
    "loc": "Loc",
    "voc": "Voc",
}
_TENSE = {"past": "Past", "pres": "Pres", "present": "Pres", "fut": "Fut", "future": "Fut"}
_SIMPLE = {
    "fin": ("VerbForm", "Fin"),
    "nonfin": ("VerbForm", "NonFin"),
    "inf": ("VerbForm", "Inf"),
    "vpart": ("VerbForm", "Part"),
    "adjpart": ("VerbForm", "Part"),
    "imp": ("Mood", "Imp"),
    "pass": ("Voice", "Pass"),
    "caus": ("Voice", "Cau"),
    "sg": ("Number", "Sing"),
    "pl": ("Number", "Plur"),
}
_PERSON_NUMBER = re.compile(r"^(?P<person>[123])(?P<number>sg|pl|s|p)(?P<gender>[mfne])?.*$")


def _encode_misc(value: str) -> str:
    return quote(value, safe="._:-,")


def _native_tags(analysis: MorphAnalysis) -> str:
    return ",".join(
        item.label if item.surface is None else f"{item.label}={item.surface}"
        for item in analysis.morphemes
    )


def ud_features(analysis: MorphAnalysis) -> dict[str, str]:
    """Conservatively map well-defined labels; preserve every native label in MISC."""

    features: dict[str, str] = {}
    for morpheme in analysis.morphemes:
        label = morpheme.label.lower()
        if label in _CASE:
            features["Case"] = _CASE[label]
        elif label in _TENSE:
            features["Tense"] = _TENSE[label]
        elif label in _SIMPLE:
            key, value = _SIMPLE[label]
            features[key] = value
        else:
            match = _PERSON_NUMBER.match(label)
            if match:
                features["Person"] = match.group("person")
                number = match.group("number")
                features["Number"] = "Sing" if number in {"s", "sg"} else "Plur"
                gender = match.group("gender")
                if gender in {"m", "f", "n"}:
                    features["Gender"] = {"m": "Masc", "f": "Fem", "n": "Neut"}[gender]
    return features


def _misc(token: TokenAnalysis, analysis: MorphAnalysis | None) -> str:
    values: list[str] = []
    if token.normalized != token.token:
        values.append(f"NormalizedForm={_encode_misc(token.normalized)}")
    if token.pos_hint:
        values.append(f"PosHint={_encode_misc(token.pos_hint)}")
    if analysis is not None:
        if analysis.model:
            values.append(f"TMorphModel={_encode_misc(analysis.model)}")
        if analysis.guessed:
            values.append("TMorphGuess=Yes")
        native = _native_tags(analysis)
        if native:
            values.append(f"TMorphTags={_encode_misc(native)}")
    if token.warnings:
        values.append(f"TMorphWarnings={_encode_misc('; '.join(token.warnings))}")
    return "|".join(values) or "_"


def token_to_conllu(token: TokenAnalysis, index: int) -> str:
    analysis = token.best
    lemma = analysis.lemma if analysis is not None else "_"
    upos = _UPOS.get(analysis.pos.lower(), "X") if analysis is not None else "X"
    xpos = analysis.pos if analysis is not None and analysis.pos else "_"
    features = ud_features(analysis) if analysis is not None else {}
    feats = "|".join(f"{key}={value}" for key, value in sorted(features.items())) or "_"
    columns = [
        str(index),
        token.token,
        lemma,
        upos,
        xpos,
        feats,
        "_",
        "_",
        "_",
        _misc(token, analysis),
    ]
    return "\t".join(columns)


def to_conllu(document: DocumentAnalysis) -> str:
    lines = [f"# text = {document.text}"]
    lines.extend(token_to_conllu(token, index) for index, token in enumerate(document.tokens, 1))
    return "\n".join(lines) + "\n"
