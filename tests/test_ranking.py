from thamizhimorph.models import TokenContext
from thamizhimorph.ranking import infer_context_features


def test_free_case_marker_requires_syntactic_licensing() -> None:
    assert infer_context_features("மூலம்", None) == ()
    assert infer_context_features("மூலம்", TokenContext(upos="NOUN")) == ()
    features = infer_context_features("மூலம்", TokenContext(deprel="case"))
    assert features[0].name == "Case"
    assert features[0].value == "Ins"
