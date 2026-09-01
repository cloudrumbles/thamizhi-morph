from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from thamizhimorph import SQLiteDictionary
from thamizhimorph.errors import DictionaryError


def test_dictionary_lookup_and_statistics(dictionary_path: Path) -> None:
    dictionary = SQLiteDictionary(dictionary_path)
    entries = dictionary.lookup(" தமிழ் ")
    assert len(entries) == 1
    assert entries[0].pos == "பெயர்ச்சொல்"
    assert dictionary.stats()["words"] == 2
    assert dictionary.contains_many(("தமிழ்", "இல்லை")) == frozenset({"தமிழ்"})


def test_dictionary_batch_lookup_retains_requested_empty_keys(dictionary_path: Path) -> None:
    dictionary = SQLiteDictionary(dictionary_path)
    values = dictionary.lookup_many(("தமிழ்", "இல்லை"))
    assert values["தமிழ்"]
    assert values["இல்லை"] == ()


def test_dictionary_requires_documented_schema(tmp_path: Path) -> None:
    path = tmp_path / "bad.db"
    connection = sqlite3.connect(path)
    connection.execute("CREATE TABLE words(id INTEGER PRIMARY KEY)")
    connection.commit()
    connection.close()

    with pytest.raises(DictionaryError, match="missing columns"):
        SQLiteDictionary(path)
