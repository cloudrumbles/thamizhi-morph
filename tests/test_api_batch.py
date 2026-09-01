from __future__ import annotations

from fastapi.testclient import TestClient

from thamizhi_morph.api import create_app
from thamizhi_morph.engine import MorphologyEngine
from thamizhi_morph.models import BackendHealth, MorphAnalysis


class BatchApiBackend:
    name = "batch-api"

    def analyze_many(
        self,
        words: list[str] | tuple[str, ...],
        *,
        guess: bool = False,
    ) -> dict[str, tuple[MorphAnalysis, ...]]:
        del guess
        return {
            word: (MorphAnalysis(word, word, "noun", model="noun"),)
            for word in words
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


def test_batch_endpoint_amortises_document_analysis() -> None:
    client = TestClient(create_app(MorphologyEngine(BatchApiBackend())))

    response = client.post(
        "/v1/analyze/batch",
        json={"texts": ["தமிழ் தமிழ்.", "மரம்"]},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["document_count"] == 2
    assert payload["token_count"] == 4
    assert payload["documents"][1]["tokens"][0]["analyses"][0]["lemma"] == "மரம்"


def test_api_rejects_unknown_fields_empty_items_and_oversized_batches() -> None:
    client = TestClient(create_app(MorphologyEngine(BatchApiBackend())))

    assert (
        client.post("/v1/analyze", json={"text": "தமிழ்", "surprise": True}).status_code
        == 422
    )
    assert client.post("/v1/analyze/batch", json={"texts": [""]}).status_code == 422
    assert (
        client.post(
            "/v1/analyze/batch",
            json={"texts": ["தமிழ்"] * 257},
        ).status_code
        == 413
    )
