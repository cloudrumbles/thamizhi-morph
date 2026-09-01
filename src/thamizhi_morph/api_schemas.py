from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class _StrictRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AnalyzeRequest(_StrictRequest):
    text: str = Field(min_length=1, max_length=100_000)
    contextual: bool = False
    use_guessers: bool = True
    enrich_dictionary: bool = False


class BatchAnalyzeRequest(_StrictRequest):
    texts: list[str] = Field(min_length=1, max_length=256)
    use_guessers: bool = True
    enrich_dictionary: bool = False
    token_batch_size: int = Field(default=20_000, ge=1, le=100_000)


class GenerateRequest(_StrictRequest):
    lexical_forms: list[str] = Field(min_length=1, max_length=10_000)
    model: str | None = None
