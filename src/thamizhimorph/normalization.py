"""Unicode handling and dependency-free tokenisation helpers."""

from __future__ import annotations

import unicodedata

_TAMIL_START = 0x0B80
_TAMIL_END = 0x0BFF
_JOINERS = {"\u200c", "\u200d"}
_WORD_PUNCTUATION = {"'", "’"}


def normalize_token(token: str) -> str:
    """Return a stripped, canonically composed representation of ``token``."""

    return unicodedata.normalize("NFC", token.strip())


def normalize_text(text: str) -> str:
    """Canonicalise Unicode without changing whitespace or punctuation."""

    return unicodedata.normalize("NFC", text)


def contains_tamil(text: str) -> bool:
    """Whether ``text`` contains at least one character in the Tamil block."""

    return any(_TAMIL_START <= ord(character) <= _TAMIL_END for character in text)


def is_punctuation(token: str) -> bool:
    """Whether every non-space code point in ``token`` is punctuation or a symbol."""

    normalized = normalize_token(token)
    if not normalized:
        return False
    return all(unicodedata.category(character)[0] in {"P", "S"} for character in normalized)


def simple_tokenize(text: str) -> list[str]:
    """Tokenise text without a statistical model.

    Letters, combining marks, and numbers remain in the same token. Punctuation is
    emitted separately. This deliberately modest tokenizer is suitable for CLI and API
    plumbing; callers that need sentence boundaries or syntactic context can use the
    optional Stanza adapter.
    """

    tokens: list[str] = []
    buffer: list[str] = []

    def flush() -> None:
        if buffer:
            tokens.append("".join(buffer))
            buffer.clear()

    for character in normalize_text(text):
        if character.isspace():
            flush()
            continue

        category = unicodedata.category(character)
        if category[0] in {"L", "M", "N"} or character in _JOINERS:
            buffer.append(character)
            continue

        if character in _WORD_PUNCTUATION and buffer:
            buffer.append(character)
            continue

        flush()
        tokens.append(character)

    flush()
    return tokens
