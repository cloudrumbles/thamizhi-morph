from __future__ import annotations

import asyncio
from typing import Any

import httpx

from thamizhimorph import Analyzer
from thamizhimorph.api import create_app

from conftest import FakeBackend


def request(app: Any, method: str, path: str, **kwargs: Any) -> httpx.Response:
    async def send() -> httpx.Response:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            return await client.request(method, path, **kwargs)

    return asyncio.run(send())


def test_api_analyze_and_health(model_specs) -> None:
    exact, guessers = model_specs
    analyzer = Analyzer(
        backend=FakeBackend({("noun.fst", "தமிழ்", False): ("தமிழ்+noun+nom",)}),
        exact_models=exact,
        guesser_models=guessers,
    )
    app = create_app(analyzer)

    assert request(app, "GET", "/health").json()["ready"] is True
    response = request(app, "POST", "/v1/analyze", json={"tokens": ["தமிழ்"]})
    assert response.status_code == 200
    assert response.json()["tokens"][0]["status"] == "exact"


def test_api_rejects_ambiguous_input_shape(model_specs) -> None:
    exact, guessers = model_specs
    analyzer = Analyzer(
        backend=FakeBackend({}),
        exact_models=exact,
        guesser_models=guessers,
    )
    response = request(
        create_app(analyzer),
        "POST",
        "/v1/analyze",
        json={"tokens": [], "text": "தமிழ்"},
    )
    assert response.status_code == 422
