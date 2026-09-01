"""Optional adapter for the Avvai-style SQLite dictionary schema."""

from __future__ import annotations

import sqlite3
from collections import defaultdict
from collections.abc import Iterable, Iterator, Sequence
from pathlib import Path
from urllib.parse import quote

from .errors import DictionaryError
from .models import DictionaryEntry
from .normalization import normalize_token

_REQUIRED_COLUMNS = {
    "words": {"id", "headword"},
    "entries": {"word_id", "source", "pos", "ta", "en"},
}


class SQLiteDictionary:
    """Read lexical evidence from a user-supplied SQLite database.

    The expected schema is intentionally tiny: ``words(id, headword)`` and
    ``entries(word_id, source, pos, ta, en)``. The database is always opened read-only
    and is never bundled into the Python package.
    """

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path).expanduser().resolve()
        if not self.path.is_file():
            raise DictionaryError(f"dictionary database does not exist: {self.path}")
        self._validate_schema()

    def _connect(self) -> sqlite3.Connection:
        uri = f"file:{quote(str(self.path), safe='/')}?mode=ro"
        try:
            connection = sqlite3.connect(uri, uri=True, timeout=10.0)
        except sqlite3.Error as error:
            raise DictionaryError(f"cannot open dictionary {self.path}: {error}") from error
        connection.row_factory = sqlite3.Row
        return connection

    def _validate_schema(self) -> None:
        try:
            with self._connect() as connection:
                for table, required in _REQUIRED_COLUMNS.items():
                    columns = {
                        row["name"]
                        for row in connection.execute(f"PRAGMA table_info({table})")
                    }
                    missing = required.difference(columns)
                    if missing:
                        raise DictionaryError(
                            f"dictionary table {table!r} is missing columns: "
                            f"{', '.join(sorted(missing))}"
                        )
        except sqlite3.Error as error:
            raise DictionaryError(f"cannot inspect dictionary {self.path}: {error}") from error

    def lookup(self, headword: str) -> tuple[DictionaryEntry, ...]:
        return self.lookup_many((headword,)).get(normalize_token(headword), ())

    def lookup_many(
        self,
        headwords: Sequence[str],
        *,
        chunk_size: int = 800,
    ) -> dict[str, tuple[DictionaryEntry, ...]]:
        normalized = tuple(dict.fromkeys(normalize_token(word) for word in headwords if word.strip()))
        collected: dict[str, list[DictionaryEntry]] = defaultdict(list)
        if not normalized:
            return {}

        try:
            with self._connect() as connection:
                for offset in range(0, len(normalized), chunk_size):
                    chunk = normalized[offset : offset + chunk_size]
                    placeholders = ",".join("?" for _ in chunk)
                    query = f"""
                        SELECT w.headword, e.source, e.pos, e.ta, e.en
                        FROM words AS w
                        JOIN entries AS e ON e.word_id = w.id
                        WHERE w.headword IN ({placeholders})
                        ORDER BY w.headword, e.source
                    """
                    for row in connection.execute(query, chunk):
                        collected[row["headword"]].append(
                            DictionaryEntry(
                                source=row["source"],
                                pos=row["pos"],
                                tamil=row["ta"],
                                english=row["en"],
                            )
                        )
        except sqlite3.Error as error:
            raise DictionaryError(f"dictionary lookup failed: {error}") from error

        return {word: tuple(collected.get(word, ())) for word in normalized}

    def iter_headwords(self) -> Iterator[str]:
        try:
            with self._connect() as connection:
                cursor = connection.execute("SELECT headword FROM words ORDER BY headword")
                for row in cursor:
                    yield row["headword"]
        except sqlite3.Error as error:
            raise DictionaryError(f"could not iterate dictionary headwords: {error}") from error

    def contains_many(self, headwords: Iterable[str]) -> frozenset[str]:
        words = tuple(headwords)
        return frozenset(
            word for word, entries in self.lookup_many(words).items() if entries
        )

    def stats(self) -> dict[str, object]:
        try:
            with self._connect() as connection:
                word_count = connection.execute("SELECT COUNT(*) FROM words").fetchone()[0]
                entry_count = connection.execute("SELECT COUNT(*) FROM entries").fetchone()[0]
                sources = {
                    row[0]: row[1]
                    for row in connection.execute(
                        "SELECT source, COUNT(*) FROM entries GROUP BY source ORDER BY source"
                    )
                }
        except sqlite3.Error as error:
            raise DictionaryError(f"could not read dictionary statistics: {error}") from error
        return {
            "path": str(self.path),
            "words": word_count,
            "entries": entry_count,
            "sources": sources,
        }
