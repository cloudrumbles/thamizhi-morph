from thamizhimorph.conllu import sentence_to_conllu, token_to_conllu
from thamizhimorph.models import (
    Analysis,
    ContextFeature,
    Morpheme,
    SentenceResult,
    TokenContext,
    TokenResult,
)


def _verb_analysis() -> Analysis:
    return Analysis(
        lemma="செய்",
        pos="verb",
        morphemes=(
            Morpheme("fin"),
            Morpheme("past", "த்"),
            Morpheme("3sgm", "ஆன்"),
        ),
        raw="செய்+verb+fin+past=த்+3sgm=ஆன்",
        source_models=("verb.fst",),
    )


def test_conllu_has_ten_columns_and_conservative_feature_mapping() -> None:
    token = TokenResult(
        token="செய்தான்",
        normalized="செய்தான்",
        status="exact",
        analyses=(_verb_analysis(),),
        selected=0,
        context=TokenContext(upos="VERB", head=0, deprel="root"),
    )
    columns = token_to_conllu(token, 1).split("\t")
    assert len(columns) == 10
    assert columns[2] == "செய்"
    assert columns[3] == "VERB"
    assert "Gender=Masc" in columns[5]
    assert "Tense=Past" in columns[5]
    assert columns[6:8] == ["0", "root"]


def test_unresolved_ambiguity_is_visible_in_misc() -> None:
    analysis = _verb_analysis()
    token = TokenResult(
        token="செய்",
        normalized="செய்",
        status="exact",
        analyses=(analysis, analysis),
        selected=None,
    )
    columns = token_to_conllu(token, 1).split("\t")
    assert columns[2] == "_"
    assert "TMCandidates=2" in columns[9]


def test_context_features_are_written_without_claiming_a_lexical_analysis() -> None:
    token = TokenResult(
        token="மூலம்",
        normalized="மூலம்",
        status="unknown",
        context_features=(
            ContextFeature("Case", "Ins", "external syntactic context"),
        ),
    )
    assert token_to_conllu(token, 1).split("\t")[5] == "Case=Ins"


def test_sentence_metadata_is_retained() -> None:
    sentence = SentenceResult(
        text="செய்தான்.",
        sent_id="example-1",
        tokens=(
            TokenResult(token=".", normalized=".", status="skipped"),
        ),
    )
    output = sentence_to_conllu(sentence)
    assert "# sent_id = example-1" in output
    assert "# text = செய்தான்." in output
