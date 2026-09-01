from __future__ import annotations

from thamizhi_morph.conllu import to_conllu, ud_features
from thamizhi_morph.models import (
    DocumentAnalysis,
    MorphAnalysis,
    Morpheme,
    TokenAnalysis,
    TokenKind,
)


def test_ud_feature_mapping_is_conservative() -> None:
    analysis = MorphAnalysis(
        surface="வந்தான்",
        lemma="வா",
        pos="verb",
        morphemes=(
            Morpheme("fin"),
            Morpheme("past", "த்"),
            Morpheme("3sgm", "ஆன்"),
            Morpheme("strong"),
        ),
    )

    assert ud_features(analysis) == {
        "VerbForm": "Fin",
        "Tense": "Past",
        "Person": "3",
        "Number": "Sing",
        "Gender": "Masc",
    }


def test_conllu_has_ten_columns_and_retains_native_labels() -> None:
    analysis = MorphAnalysis(
        surface="மரங்கள்",
        lemma="மரம்",
        pos="noun",
        morphemes=(Morpheme("pl", "கள்"), Morpheme("nom"), Morpheme("rat")),
        model="noun",
    )
    token = TokenAnalysis(
        token="மரங்கள்",
        normalized="மரங்கள்",
        kind=TokenKind.TAMIL,
        analyses=(analysis,),
        selected=0,
    )
    document = DocumentAnalysis("மரங்கள்", (token,), 1.0, "foma")

    output = to_conllu(document)
    columns = output.splitlines()[1].split("\t")

    assert len(columns) == 10
    assert columns[2] == "மரம்"
    assert columns[3] == "NOUN"
    assert "Case=Nom" in columns[5]
    assert "Number=Plur" in columns[5]
    assert "TMorphModel=noun" in columns[9]
    assert "TMorphTags=" in columns[9]
