from __future__ import annotations

import sqlite3
from pathlib import Path

from fastapi.testclient import TestClient

from thamizhi_morph.api import create_app
from thamizhi_morph.dictionary import AvvaiDictionary
from thamizhi_morph.engine import MorphologyEngine
from thamizhi_morph.models import BackendHealth, MorphAnalysis


class DictionaryBackend:
    name = "dictionary-api"

    def analyze_many(
        self,
        words: list[str] | tuple[str, ...],
        *,
        guess: bool = False,
    ) -> dict[str, tuple[MorphAnalysis, ...]]:
        del guess
        return {word: () for word in words}

    def generate_many(
        self,
        lexical_forms: list[str] | tuple[str, ...],
        *,
        model: str | None = None,
    ) -> dict[str, tuple[str, ...]]:
        del model
        return {item: () for item in lexical_forms}

    def health(self) -> BackendHealth:
        return BackendHealth(self.name, True, {})


def test_dictionary_prefix_endpoint(tmp_path: Path) -> None:
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
        INSERT INTO words VALUES (1, 'தமிழ்'), (2, 'தமிழன்');
        INSERT INTO entries VALUES
          (1, 'agarathi', 'பெயர்ச்சொல்', 'மொழி', 'Tamil'),
          (2, 'agarathi', 'பெயர்ச்சொல்', 'மனிதர்', 'Tamil man');
        """
    )
    connection.commit()
    connection.close()
    dictionary = AvvaiDictionary(path)
    client = TestClient(
        create_app(MorphologyEngine(DictionaryBackend(), dictionary=dictionary))
    )

    response = client.get("/v1/dictionary?prefix=தமிழ&limit=2")

    assert response.status_code == 200
    assert list(response.json()["matches"]) == ["தமிழ்", "தமிழன்"]
    dictionary.close()
