"""Modern application interface for the ThamizhiMorph Tamil FST resources."""

from .analyzer import Analyzer
from .backend import FomaBackend, LookupBackend
from .dictionary import SQLiteDictionary
from .models import (
    Analysis,
    ContextFeature,
    CoverageReport,
    DictionaryEntry,
    GenerationResult,
    ModelSpec,
    Morpheme,
    SentenceResult,
    TokenContext,
    TokenResult,
)
from .normalization import contains_tamil, normalize_text, normalize_token, simple_tokenize

__all__ = [
    "Analysis",
    "Analyzer",
    "ContextFeature",
    "CoverageReport",
    "DictionaryEntry",
    "FomaBackend",
    "GenerationResult",
    "LookupBackend",
    "ModelSpec",
    "Morpheme",
    "SQLiteDictionary",
    "SentenceResult",
    "TokenContext",
    "TokenResult",
    "contains_tamil",
    "normalize_text",
    "normalize_token",
    "simple_tokenize",
]

__version__ = "0.2.0"
