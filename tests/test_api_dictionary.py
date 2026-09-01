from __future__ import annotations

import sqlite3
from pathlib import Path

from fastapi.testclient import TestClient

from thamizhi_morph.api import create_app
from thamizhi_morph.dictionary import AvvaiDictionary
from thamizhi_morph.engine import MorphologyEngine
from thamizhi_morph.models import BackendHealth, MorphAnalysis


class Backend:
    name = "api-dictionary"

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


def test_api_dictionary_endpoint(tmp_path: Path) -> None:
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
        INSERT INTO words VALUES (1, 'தமிழ்');
        INSERT INTO entries VALUES (1, 'agarathi', 'பெயர்ச்சொல்', 'தமிழ் மொழி', 'Tamil');
        """
    )
    connection.commit()
    connection.close()
    dictionary = AvvaiDictionary(path)
    client = TestClient(create_app(MorphologyEngine(Backend(), dictionary=dictionary)))

    response = client.get("/v1/dictionary/தமிழ்?limit=1")

    assert response.status_code == 200
    assert response.json()["entries"][0]["en"] == "Tamil"
    dictionary.close()
