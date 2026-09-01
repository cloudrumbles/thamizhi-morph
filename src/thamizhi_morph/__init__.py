"""Modern runtime for the ThamizhiMorph Tamil morphological transducers."""

from .engine import MorphologyEngine
from .models import DocumentAnalysis, MorphAnalysis, Morpheme, TokenAnalysis

__all__ = [
    "DocumentAnalysis",
    "MorphAnalysis",
    "Morpheme",
    "MorphologyEngine",
    "TokenAnalysis",
]

__version__ = "2.0.0a1"
