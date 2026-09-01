from __future__ import annotations

from fastapi.testclient import TestClient

from thamizhi_morph.api import create_app
from thamizhi_morph.engine import MorphologyEngine
from thamizhi_morph.models import BackendHealth, MorphAnalysis
from thamizhi_morph.web import playground_html


class WebBackend:
    name = "web-test"

    def analyze_many(
        self,
        words: list[str] | tuple[str, ...],
        *,
        guess: bool = False,
    ) -> dict[str, tuple[MorphAnalysis, ...]]:
        del guess
        return {word: () for word in words}

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


def test_packaged_playground_contains_all_workbench_modes() -> None:
    html = playground_html()

    assert "ThamizhiMorph Workbench" in html
    assert 'id="analyse"' in html
    assert 'id="generate"' in html
    assert 'id="dictionary"' in html
    assert 'id="batch"' in html
    assert "/v1/analyze/batch" in html


def test_root_serves_playground_without_entering_api_schema() -> None:
    client = TestClient(create_app(MorphologyEngine(WebBackend())))

    response = client.get("/")
    schema = client.get("/openapi.json").json()

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "ThamizhiMorph" in response.text
    assert "/" not in schema["paths"]
