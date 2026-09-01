from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from .models import TextToken, TokenKind

_TAMIL_START = 0x0B80
_TAMIL_END = 0x0BFF
_INVISIBLE_FORMATTING = frozenset({"\ufeff", "\u200b", "\u2060", "\u00ad"})
_TOKEN_PATTERN = re.compile(r"[\u0B80-\u0BFF]+|[^\W_]+(?:['’][^\W_]+)*|[^\s]", re.UNICODE)


@dataclass(frozen=True, slots=True)
class NormalizationResult:
    original: str
    normalized: str
    changed: bool
    removed_codepoints: tuple[str, ...]


def is_tamil_character(character: str) -> bool:
    return len(character) == 1 and _TAMIL_START <= ord(character) <= _TAMIL_END


def contains_tamil(text: str) -> bool:
    return any(is_tamil_character(character) for character in text)


def normalize_text(text: str) -> NormalizationResult:
    """Return a stable NFC representation while removing harmless invisible separators.

    ZWJ and ZWNJ are deliberately retained: they can be intentional rendering controls.
    """

    removed = tuple(character for character in text if character in _INVISIBLE_FORMATTING)
    cleaned = "".join(character for character in text if character not in _INVISIBLE_FORMATTING)
    normalized = unicodedata.normalize("NFC", cleaned)
    return NormalizationResult(
        original=text,
        normalized=normalized,
        changed=normalized != text,
        removed_codepoints=tuple(f"U+{ord(character):04X}" for character in removed),
    )


def classify_token(text: str) -> TokenKind:
    if text and all(unicodedata.category(character).startswith("P") for character in text):
        return TokenKind.PUNCTUATION
    if text and all(character.isnumeric() for character in text):
        return TokenKind.NUMBER
    if contains_tamil(text):
        return TokenKind.TAMIL
    if any(character.isalpha() or character.isnumeric() for character in text):
        return TokenKind.FOREIGN
    return TokenKind.SYMBOL


def tokenize(text: str) -> tuple[TextToken, ...]:
    """Unicode-aware, dependency-free tokenisation with exact character offsets."""

    return tuple(
        TextToken(
            text=match.group(0),
            start=match.start(),
            end=match.end(),
            kind=classify_token(match.group(0)),
        )
        for match in _TOKEN_PATTERN.finditer(text)
    )
