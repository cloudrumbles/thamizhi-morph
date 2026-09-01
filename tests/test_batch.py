from __future__ import annotations

import pytest

from thamizhi_morph.engine import MorphologyEngine
from thamizhi_morph.models import BackendHealth, MorphAnalysis


class BatchBackend:
    name = "batch"

    def __init__(self) -> None:
        self.calls: list[tuple[tuple[str, ...], bool]] = []

    def analyze_many(
        self,
        words: list[str] | tuple[str, ...],
        *,
        guess: bool = False,
    ) -> dict[str, tuple[MorphAnalysis, ...]]:
        values = tuple(words)
        self.calls.append((values, guess))
        return {
            word: (MorphAnalysis(word, word, "noun", model="noun"),)
            for word in values
        }

    def generate_many(
        self,
        lexical_forms: list[str] | tuple[str, ...],
        *,
        model: str | None = None,
    ) -> dict[str, tuple[str, ...]]:
        del model
        return {item: () for item in lexical_forms}

    def health(self) -> BackendHealth:
        return BackendHealth(self.name, True, {})


def test_documents_share_one_morphology_batch() -> None:
    backend = BatchBackend()
    engine = MorphologyEngine(backend)

    result = engine.analyze_texts(["தமிழ் தமிழ்.", "மரம்"], token_batch_size=100)

    assert result.token_count == 4
    assert len(result.documents) == 2
    assert [token.token for token in result.documents[0].tokens] == ["தமிழ்", "தமிழ்", "."]
    assert result.documents[1].tokens[0].best is not None
    assert result.documents[1].tokens[0].best.lemma == "மரம்"
    assert backend.calls == [(('தமிழ்', 'மரம்'), False)]


def test_empty_batch_and_invalid_token_batch_size() -> None:
    backend = BatchBackend()
    engine = MorphologyEngine(backend)

    result = engine.analyze_texts([])

    assert result.documents == ()
    assert result.token_count == 0
    assert backend.calls == []
    with pytest.raises(ValueError, match="positive"):
        engine.analyze_texts(["தமிழ்"], token_batch_size=0)
