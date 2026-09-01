from __future__ import annotations

import unicodedata

from thamizhi_morph.models import TokenKind
from thamizhi_morph.normalization import classify_token, normalize_text, tokenize


def test_normalize_tamil_to_nfc_and_remove_invisible_separator() -> None:
    decomposed = unicodedata.normalize("NFD", "கொ")
    result = normalize_text("\ufeff" + decomposed + "\u200b")

    assert result.normalized == "கொ"
    assert result.changed
    assert result.removed_codepoints == ("U+FEFF", "U+200B")


def test_tokenize_preserves_offsets_and_types() -> None:
    text = "தமிழ் 2026, hello!"
    tokens = tokenize(text)

    assert [(item.text, item.start, item.end) for item in tokens] == [
        ("தமிழ்", 0, 5),
        ("2026", 6, 10),
        (",", 10, 11),
        ("hello", 12, 17),
        ("!", 17, 18),
    ]
    assert [item.kind for item in tokens] == [
        TokenKind.TAMIL,
        TokenKind.NUMBER,
        TokenKind.PUNCTUATION,
        TokenKind.FOREIGN,
        TokenKind.PUNCTUATION,
    ]


def test_tamil_digits_are_numbers_before_script_classification() -> None:
    assert classify_token("௨௦௨௬") is TokenKind.NUMBER
