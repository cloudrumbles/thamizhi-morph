from __future__ import annotations

import os
from importlib import import_module
from typing import Any

from .backends.foma import FomaBackend
from .dictionary import AvvaiDictionary
from .engine import MorphologyEngine

_MAX_TEXT_LENGTH = 100_000


def default_engine() -> MorphologyEngine:
    dictionary_path = os.environ.get("THAMIZHI_DICTIONARY")
    dictionary = AvvaiDictionary(dictionary_path) if dictionary_path else None
    return MorphologyEngine(FomaBackend(), dictionary=dictionary)


def create_app(engine: MorphologyEngine | None = None) -> Any:
    """Create a FastAPI app without making FastAPI a core dependency."""

    try:
        fastapi = import_module("fastapi")
    except ImportError as error:
        raise RuntimeError("install the API extra: pip install 'thamizhi-morph[api]'") from error

    app = fastapi.FastAPI(
        title="ThamizhiMorph API",
        version="2.0.0a1",
        description="Tamil morphological analysis and generation backed by finite-state models.",
    )
    runtime = engine or default_engine()

    @app.get("/healthz")
    def health() -> dict[str, Any]:
        return runtime.health()

    @app.post("/v1/analyze")
    def analyze(payload: dict[str, Any]) -> dict[str, Any]:
        text = payload.get("text")
        if not isinstance(text, str) or not text:
            raise fastapi.HTTPException(status_code=422, detail="text must be a non-empty string")
        if len(text) > _MAX_TEXT_LENGTH:
            raise fastapi.HTTPException(status_code=413, detail="text is too large")
        contextual = bool(payload.get("contextual", False))
        use_guessers = bool(payload.get("use_guessers", True))
        enrich = bool(payload.get("enrich_dictionary", False))
        if contextual:
            from .context import StanzaPosTagger

            result = runtime.analyze_contextual(
                text,
                StanzaPosTagger(),
                use_guessers=use_guessers,
                enrich_dictionary=enrich,
            )
        else:
            result = runtime.analyze_text(
                text,
                use_guessers=use_guessers,
                enrich_dictionary=enrich,
            )
        return result.to_dict()

    @app.post("/v1/generate")
    def generate(payload: dict[str, Any]) -> dict[str, Any]:
        forms = payload.get("lexical_forms")
        if not isinstance(forms, list) or not all(isinstance(item, str) for item in forms):
            raise fastapi.HTTPException(
                status_code=422,
                detail="lexical_forms must be a list of strings",
            )
        if len(forms) > 10_000:
            raise fastapi.HTTPException(status_code=413, detail="too many lexical forms")
        model = payload.get("model")
        if model is not None and not isinstance(model, str):
            raise fastapi.HTTPException(status_code=422, detail="model must be a string")
        return {"forms": runtime.generate_many(forms, model=model)}

    @app.get("/v1/dictionary/{headword}")
    def dictionary(headword: str, limit: int = 16) -> dict[str, Any]:
        if runtime.dictionary is None:
            raise fastapi.HTTPException(status_code=404, detail="dictionary is not configured")
        entries = runtime.dictionary.lookup(headword, limit=min(max(limit, 1), 100))
        return {"headword": headword, "entries": [entry.to_dict() for entry in entries]}

    return app
