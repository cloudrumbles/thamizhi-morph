from thamizhimorph.normalization import (
    contains_tamil,
    is_punctuation,
    normalize_token,
    simple_tokenize,
)


def test_tamil_unicode_is_normalized_to_nfc() -> None:
    decomposed = "கொ"  # U+0BC6 + U+0BBE
    assert normalize_token(decomposed) == "கொ"


def test_tamil_detection_does_not_reject_mixed_tokens() -> None:
    assert contains_tamil("தமிழ்")
    assert contains_tamil("தமிழ்NLP")
    assert not contains_tamil("Tamil")


def test_simple_tokenizer_keeps_combining_marks_and_splits_punctuation() -> None:
    assert simple_tokenize("தமிழ், NLP நல்லது.") == ["தமிழ்", ",", "NLP", "நல்லது", "."]


def test_punctuation_detection() -> None:
    assert is_punctuation("—")
    assert not is_punctuation("தமிழ்")
