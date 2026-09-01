from __future__ import annotations

from fastapi.testclient import TestClient

from thamizhi_morph.api import create_app
from thamizhi_morph.engine import MorphologyEngine
from thamizhi_morph.models import BackendHealth, MorphAnalysis


class ApiBackend:
    name = "api-test"

    def analyze_many(
        self,
        words: list[str] | tuple[str, ...],
        *,
        guess: bool = False,
    ) -> dict[str, tuple[MorphAnalysis, ...]]:
        return {
            word: (MorphAnalysis(word, "தமிழ்", "noun", model="noun", guessed=guess),)
            if word == "தமிழ்"
            else ()
            for word in words
        }

    def generate_many(
        self,
        lexical_forms: list[str] | tuple[str, ...],
        *,
        model: str | None = None,
    ) -> dict[str, tuple[str, ...]]:
        del model
        return {item: ("தமிழ்",) for item in lexical_forms}

    def health(self) -> BackendHealth:
        return BackendHealth(self.name, True, {})


def test_api_health_analysis_and_generation() -> None:
    client = TestClient(create_app(MorphologyEngine(ApiBackend())))

    health = client.get("/healthz")
    analysis = client.post("/v1/analyze", json={"text": "தமிழ்"})
    generation = client.post("/v1/generate", json={"lexical_forms": ["தமிழ்+noun+nom"]})

    assert health.status_code == 200
    assert health.json()["ready"] is True
    assert analysis.status_code == 200
    assert analysis.json()["tokens"][0]["analyses"][0]["lemma"] == "தமிழ்"
    assert generation.json()["forms"]["தமிழ்+noun+nom"] == ["தமிழ்"]


def test_api_validates_requests_and_dictionary_configuration() -> None:
    client = TestClient(create_app(MorphologyEngine(ApiBackend())))

    assert client.post("/v1/analyze", json={"text": ""}).status_code == 422
    assert client.post("/v1/generate", json={"lexical_forms": "bad"}).status_code == 422
    assert client.get("/v1/dictionary/தமிழ்").status_code == 404


def test_api_size_and_type_limits() -> None:
    client = TestClient(create_app(MorphologyEngine(ApiBackend())))

    assert client.post("/v1/analyze", json={"text": "அ" * 100_001}).status_code == 413
    assert client.post("/v1/generate", json={"lexical_forms": [], "model": 3}).status_code == 422
    assert client.post("/v1/generate", json={"lexical_forms": ["x"] * 10_001}).status_code == 413
