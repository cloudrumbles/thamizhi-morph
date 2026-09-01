"""Optional FastAPI service for ThamizhiMorph."""

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

from .analyzer import Analyzer
from .backend import FomaBackend
from .dictionary import SQLiteDictionary
from .errors import OptionalDependencyError, ThamizhiMorphError
from .normalization import simple_tokenize


def _environment_analyzer() -> Analyzer:
    model_dir = os.getenv("THAMIZHIMORPH_MODEL_DIR")
    binary = os.getenv("THAMIZHIMORPH_FLOOKUP", "flookup")
    dictionary_path = os.getenv("THAMIZHIMORPH_DICTIONARY")
    dictionary = SQLiteDictionary(Path(dictionary_path)) if dictionary_path else None
    return Analyzer(
        backend=FomaBackend(model_dir=model_dir, binary=binary),
        dictionary=dictionary,
    )


def create_app(analyzer: Analyzer | None = None) -> Any:
    """Create the HTTP application, optionally with an injected analyser for tests."""

    try:
        from fastapi import FastAPI, HTTPException
        from pydantic import BaseModel, Field
    except ImportError as error:
        raise OptionalDependencyError(
            "HTTP API support is not installed. Install thamizhimorph[api]."
        ) from error

    class AnalyzeRequest(BaseModel):
        tokens: list[str] | None = Field(default=None, max_length=4096)
        text: str | None = Field(default=None, max_length=200_000)
        pos_hints: list[str | None] | None = None
        use_guessers: bool = True
        include_dictionary: bool = False

    class GenerateRequest(BaseModel):
        lexical_form: str = Field(min_length=1, max_length=1024)
        models: list[str] | None = None

    application = FastAPI(
        title="ThamizhiMorph",
        version="0.2.0",
        description="Tamil finite-state morphological analysis and generation",
    )

    @lru_cache(maxsize=1)
    def get_analyzer() -> Analyzer:
        return analyzer or _environment_analyzer()

    @application.exception_handler(ThamizhiMorphError)
    async def handle_thamizhimorph_error(_request: Any, error: ThamizhiMorphError) -> Any:
        from fastapi.responses import JSONResponse

        return JSONResponse(status_code=503, content={"detail": str(error)})

    @application.get("/health")
    def health() -> dict[str, object]:
        return get_analyzer().health()

    @application.post("/v1/analyze")
    def analyze(request: AnalyzeRequest) -> dict[str, object]:
        if (request.tokens is None) == (request.text is None):
            raise HTTPException(status_code=422, detail="pass exactly one of tokens or text")
        tokens = request.tokens if request.tokens is not None else simple_tokenize(request.text or "")
        if any(len(token) > 1024 for token in tokens):
            raise HTTPException(status_code=422, detail="a token exceeds 1024 characters")
        try:
            results = get_analyzer().analyze_tokens(
                tokens,
                pos_hints=request.pos_hints,
                use_guessers=request.use_guessers,
                include_dictionary=request.include_dictionary,
            )
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        return {"tokens": [result.to_dict() for result in results]}

    @application.post("/v1/generate")
    def generate(request: GenerateRequest) -> dict[str, object]:
        return get_analyzer().generate(
            request.lexical_form,
            model_names=request.models,
        ).to_dict()

    return application


app = create_app()
