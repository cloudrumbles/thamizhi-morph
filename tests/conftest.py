from __future__ import annotations

import sqlite3
from collections.abc import Sequence
from pathlib import Path

import pytest

from thamizhimorph.backend import LookupMap
from thamizhimorph.models import ModelSpec


class FakeBackend:
    def __init__(self, data: dict[tuple[str, str, bool], tuple[str, ...]]) -> None:
        self.data = data
        self.calls: list[tuple[tuple[str, ...], tuple[str, ...], bool]] = []

    def lookup_models(
        self,
        inputs: Sequence[str],
        models: Sequence[ModelSpec],
        *,
        inverse: bool = False,
    ) -> LookupMap:
        self.calls.append(
            (tuple(inputs), tuple(model.filename for model in models), inverse)
        )
        output: dict[str, list[tuple[str, str]]] = {item: [] for item in inputs}
        for item in inputs:
            for model in models:
                for value in self.data.get((model.filename, item, inverse), ()):
                    output[item].append((value, model.filename))
        return {item: tuple(records) for item, records in output.items()}


@pytest.fixture
def model_specs() -> tuple[tuple[ModelSpec, ...], tuple[ModelSpec, ...]]:
    exact = (
        ModelSpec("verb.fst", "exact", ("VERB", "AUX"), 10),
        ModelSpec("noun.fst", "exact", ("NOUN", "PROPN"), 20),
    )
    guessers = (
        ModelSpec("verb-guess.fst", "guesser", ("VERB", "AUX"), 110),
        ModelSpec("noun-guess.fst", "guesser", ("NOUN", "PROPN"), 120),
    )
    return exact, guessers


@pytest.fixture
def dictionary_path(tmp_path: Path) -> Path:
    path = tmp_path / "dictionary.db"
    connection = sqlite3.connect(path)
    connection.executescript(
        """
        CREATE TABLE words (
            id INTEGER PRIMARY KEY,
            headword TEXT NOT NULL UNIQUE
        );
        CREATE TABLE entries (
            word_id INTEGER NOT NULL REFERENCES words(id),
            source TEXT NOT NULL,
            pos TEXT NOT NULL DEFAULT '',
            ta TEXT NOT NULL DEFAULT '',
            en TEXT NOT NULL DEFAULT '',
            PRIMARY KEY (word_id, source)
        );
        INSERT INTO words(id, headword) VALUES
            (1, 'தமிழ்'),
            (2, 'புதுச்சொல்');
        INSERT INTO entries(word_id, source, pos, ta, en) VALUES
            (1, 'test', 'பெயர்ச்சொல்', 'தமிழ் மொழி', 'Tamil language'),
            (2, 'test', 'பெயர்ச்சொல்', 'புதிய சொல்', 'new word');
        """
    )
    connection.commit()
    connection.close()
    return path
