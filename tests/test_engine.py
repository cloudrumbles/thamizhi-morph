from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from thamizhi_morph.context import TaggedToken
from thamizhi_morph.dictionary import AvvaiDictionary
from thamizhi_morph.engine import MorphologyEngine
from thamizhi_morph.models import BackendHealth, MorphAnalysis, Morpheme, TokenKind


class FakeBackend:
    name = "fake"

    def __init__(self) -> None:
        self.calls: list[tuple[tuple[str, ...], bool]] = []

    def analyze_many(
        self,
        words: list[str] | tuple[str, ...],
        *,
        guess: bool = False,
    ) -> dict[str, tuple[MorphAnalysis, ...]]:
        values = tuple(words)
        self.calls.append((values, guess))
        output: dict[str, tuple[MorphAnalysis, ...]] = {}
        for word in values:
            if not guess and word == "செய்யும்":
                output[word] = (
                    MorphAnalysis(
                        word,
                        "செய்",
                        "adjective",
                        (Morpheme("futANDadjpart", "உம்"),),
                        "verb-rest",
                    ),
                    MorphAnalysis(
                        word,
                        "செய்",
                        "verb",
                        (Morpheme("fin"), Morpheme("fut", "உம்"), Morpheme("3sgn", "உம்")),
                        "verb-rest",
                    ),
                )
            elif not guess and word == "மரங்கள்":
                output[word] = (
                    MorphAnalysis(
                        word,
                        "மரம்",
                        "noun",
                        (Morpheme("pl", "கள்"), Morpheme("nom")),
                        "noun",
                    ),
                )
            elif guess and word == "புதுச்சொல்":
                output[word] = (
                    MorphAnalysis(
                        word,
                        word,
                        "noun",
                        (Morpheme("guess"), Morpheme("nom")),
                        "noun-guesser",
                        guessed=True,
                    ),
                )
            else:
                output[word] = ()
        return output

    def generate_many(
        self,
        lexical_forms: list[str] | tuple[str, ...],
        *,
        model: str | None = None,
    ) -> dict[str, tuple[str, ...]]:
        del model
        return {value: ("மரம்",) if value == "மரம்+noun+nom" else () for value in lexical_forms}

    def health(self) -> BackendHealth:
        return BackendHealth("fake", True, {"ok": True})


class FakeTagger:
    name = "fake-pos"

    def tag(self, text: str) -> tuple[TaggedToken, ...]:
        assert text == "செய்யும் மரங்கள்"
        return (
            TaggedToken("செய்யும்", "VERB", 0, 7),
            TaggedToken("மரங்கள்", "NOUN", 8, 16),
        )


def make_dictionary(tmp_path: Path) -> AvvaiDictionary:
    path = tmp_path / "dictionary.db"
    connection = sqlite3.connect(path)
    connection.executescript(
        """
        CREATE TABLE words (id INTEGER PRIMARY KEY, headword TEXT NOT NULL UNIQUE);
        CREATE TABLE entries (
          word_id INTEGER NOT NULL,
          source TEXT NOT NULL,
          pos TEXT NOT NULL DEFAULT '',
          ta TEXT NOT NULL DEFAULT '',
          en TEXT NOT NULL DEFAULT '',
          PRIMARY KEY (word_id, source)
        );
        INSERT INTO words(id, headword) VALUES (1, 'மரம்'), (2, 'அகராதி');
        INSERT INTO entries(word_id, source, pos, ta, en) VALUES
          (1, 'agarathi', 'பெயர்ச்சொல்', 'மரம்', 'tree'),
          (2, 'agarathi', 'பெயர்ச்சொல்', 'சொற்களஞ்சியம்', 'dictionary');
        """
    )
    connection.commit()
    connection.close()
    return AvvaiDictionary(path)


def test_exact_analysis_precedes_guesser_and_batches_unknowns() -> None:
    backend = FakeBackend()
    engine = MorphologyEngine(backend)

    results = engine.analyze_words(["மரங்கள்", "புதுச்சொல்"])

    assert results[0].best is not None and not results[0].best.guessed
    assert results[1].best is not None and results[1].best.guessed
    assert backend.calls == [(("மரங்கள்", "புதுச்சொல்"), False), (("புதுச்சொல்",), True)]


def test_pos_hint_ranks_compatible_analysis_without_deleting_ambiguity() -> None:
    engine = MorphologyEngine(FakeBackend())

    token = engine.analyze_words(["செய்யும்"], pos_hints=["VERB"])[0]

    assert len(token.analyses) == 2
    assert token.best is not None and token.best.pos == "verb"
    assert {analysis.pos for analysis in token.analyses} == {"verb", "adjective"}


def test_dictionary_enrichment_and_honest_dictionary_fallback(tmp_path: Path) -> None:
    engine = MorphologyEngine(FakeBackend(), dictionary=make_dictionary(tmp_path))

    noun, fallback = engine.analyze_words(
        ["மரங்கள்", "அகராதி"],
        enrich_dictionary=True,
    )

    assert noun.best is not None and noun.best.glosses[0].english == "tree"
    assert fallback.best is not None and fallback.best.model == "dictionary-fallback"
    assert "no inflectional morphology" in fallback.warnings[0]
    engine.close()


def test_text_analysis_offsets_synthetic_tokens_and_cache() -> None:
    backend = FakeBackend()
    engine = MorphologyEngine(backend)

    first = engine.analyze_text("மரங்கள், 2 hello")
    second = engine.analyze_text("மரங்கள், 2 hello")

    assert [(token.token, token.start, token.end) for token in first.tokens] == [
        ("மரங்கள்", 0, 7),
        (",", 7, 8),
        ("2", 9, 10),
        ("hello", 11, 16),
    ]
    assert [token.kind for token in first.tokens] == [
        TokenKind.TAMIL,
        TokenKind.PUNCTUATION,
        TokenKind.NUMBER,
        TokenKind.FOREIGN,
    ]
    assert first.tokens[1].best is not None and first.tokens[1].best.pos == "punct"
    assert second.tokens[0].best == first.tokens[0].best
    assert backend.calls == [(("மரங்கள்",), False)]


def test_contextual_analysis_and_generation() -> None:
    engine = MorphologyEngine(FakeBackend())

    document = engine.analyze_contextual("செய்யும் மரங்கள்", FakeTagger())
    generated = engine.generate_many(["மரம்+noun+nom"])

    assert document.tokens[0].best is not None and document.tokens[0].best.pos == "verb"
    assert document.metadata == {"context_tagger": "fake-pos"}
    assert generated == {"மரம்+noun+nom": ("மரம்",)}
    assert engine.health()["ready"]


def test_pos_hint_length_must_match() -> None:
    engine = MorphologyEngine(FakeBackend())

    with pytest.raises(ValueError, match="same length"):
        engine.analyze_words(["தமிழ்"], pos_hints=[])
