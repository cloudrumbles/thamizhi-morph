from __future__ import annotations

import shutil

import pytest

from thamizhimorph import Analyzer
from thamizhimorph.model_resources import default_model_dir, load_model_specs


def test_manifest_references_packaged_models() -> None:
    exact, guessers = load_model_specs()
    assert exact
    assert guessers
    for model in (*exact, *guessers):
        assert (default_model_dir() / model.filename).is_file()
    assert "adverb-guesser.fst" not in {model.filename for model in guessers}


@pytest.mark.integration
def test_packaged_fst_smoke_analysis() -> None:
    if shutil.which("flookup") is None:
        pytest.skip("Foma is not installed")
    # Local development may intentionally use zero-byte placeholders; release/CI trees
    # package the existing compiled blobs.
    if (default_model_dir() / "noun.fst").stat().st_size == 0:
        pytest.skip("compiled model blobs are not materialised in this workspace")

    result = Analyzer().analyze_word("தமிழ்", use_guessers=False)
    assert result.status == "exact"
    assert any(analysis.lemma == "தமிழ்" for analysis in result.analyses)
