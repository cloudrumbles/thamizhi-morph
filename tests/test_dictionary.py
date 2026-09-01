from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from thamizhi_morph.dictionary import AvvaiDictionary, DictionaryError


@pytest.fixture
def dictionary_db(tmp_path: Path) -> Path:
    path = tmp_path / "avvai.db"
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
        INSERT INTO words(id, headword) VALUES
          (1, 'தமிழ்'),
          (2, 'தமிழன்'),
          (3, 'மரம்');
        INSERT INTO entries(word_id, source, pos, ta, en) VALUES
          (1, 'wiktionary', 'பெயர்ச்சொல்', 'தமிழ் மொழி', 'Tamil language'),
          (1, 'agarathi', 'பெயர்ச்சொல்', 'இனிமை', ''),
          (2, 'wiktionary', 'பெயர்ச்சொல்', 'தமிழர்', 'Tamil man'),
          (3, 'agarathi', 'பெயர்ச்சொல்', 'மரம்', 'tree');
        """
    )
    connection.commit()
    connection.close()
    return path


def test_exact_lookup_orders_primary_source_first(dictionary_db: Path) -> None:
    with AvvaiDictionary(dictionary_db) as dictionary:
        entries = dictionary.lookup("தமிழ்")
        statistics = dictionary.statistics()

    assert [entry.source for entry in entries] == ["agarathi", "wiktionary"]
    assert entries[1].english == "Tamil language"
    assert statistics == {"headwords": 3, "entries": 4}


def test_lookup_many_and_prefix_search(dictionary_db: Path) -> None:
    with AvvaiDictionary(dictionary_db) as dictionary:
        many = dictionary.lookup_many(["தமிழ்", "மரம்"])
        prefix = dictionary.search_prefix("தமிழ", limit=5)

    assert many["மரம்"][0].english == "tree"
    assert list(prefix) == ["தமிழ்", "தமிழன்"]


def test_dictionary_is_read_only(dictionary_db: Path) -> None:
    with AvvaiDictionary(dictionary_db) as dictionary:
        with pytest.raises(sqlite3.OperationalError):
            dictionary._connect().execute("DELETE FROM words")  # noqa: SLF001


def test_invalid_schema_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "bad.db"
    connection = sqlite3.connect(path)
    connection.execute("CREATE TABLE words (value TEXT)")
    connection.commit()
    connection.close()

    with pytest.raises(DictionaryError, match="missing words"):
        AvvaiDictionary(path)
