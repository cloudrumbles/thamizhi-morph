from __future__ import annotations

import sqlite3
import threading
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path

from .models import Gloss
from .normalization import normalize_text

_TAMIL_POS_TO_ANALYSER = {
    "பெயர்ச்சொல்": "noun",
    "வினைச்சொல்": "verb",
    "பெயரடை": "adjective",
    "வினையடை": "adverb",
    "இடைச்சொல்": "particle",
    "வியப்பிடைச்சொல்": "particle",
    "இணைப்புச்சொல்": "particle",
    "பிரதிப்பெயர்": "pronoun",
}


class DictionaryError(RuntimeError):
    pass


class AvvaiDictionary:
    """Read-only adapter for the Avvai SQLite dictionary database.

    The database remains an optional external resource. This adapter does not redistribute it.
    """

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path).expanduser().resolve()
        if not self.path.is_file():
            raise DictionaryError(f"dictionary database does not exist: {self.path}")
        self._lock = threading.RLock()
        self._connection: sqlite3.Connection | None = None
        try:
            self._validate_schema()
        except Exception:
            self.close()
            raise

    def _connect(self) -> sqlite3.Connection:
        with self._lock:
            if self._connection is None:
                uri = self.path.as_uri() + "?mode=ro"
                connection = sqlite3.connect(uri, uri=True, check_same_thread=False)
                connection.row_factory = sqlite3.Row
                connection.execute("PRAGMA query_only = ON")
                self._connection = connection
            return self._connection

    def _validate_schema(self) -> None:
        with self._lock:
            connection = self._connect()
            words = {row[1] for row in connection.execute("PRAGMA table_info(words)")}
            entries = {row[1] for row in connection.execute("PRAGMA table_info(entries)")}
        if not {"id", "headword"}.issubset(words):
            raise DictionaryError("Avvai database is missing words(id, headword)")
        if not {"word_id", "source", "pos", "ta", "en"}.issubset(entries):
            raise DictionaryError("Avvai database is missing entries(word_id, source, pos, ta, en)")

    @staticmethod
    def map_pos(pos: str) -> str:
        return _TAMIL_POS_TO_ANALYSER.get(pos.strip(), pos.strip().lower() or "unknown")

    @staticmethod
    def _to_gloss(row: sqlite3.Row) -> Gloss:
        return Gloss(
            source=str(row["source"]),
            pos=str(row["pos"]),
            tamil=str(row["ta"]),
            english=str(row["en"]),
        )

    def lookup(self, headword: str, *, limit: int = 16) -> tuple[Gloss, ...]:
        normalized = normalize_text(headword).normalized
        with self._lock:
            rows = tuple(
                self._connect().execute(
                    """
                    SELECT e.source, e.pos, e.ta, e.en
                    FROM words AS w
                    JOIN entries AS e ON e.word_id = w.id
                    WHERE w.headword = ?
                    ORDER BY
                      CASE e.source
                        WHEN 'agarathi' THEN 0
                        WHEN 'lexicon2' THEN 1
                        WHEN 'wiktionary' THEN 2
                        ELSE 3
                      END,
                      e.source
                    LIMIT ?
                    """,
                    (normalized, max(1, limit)),
                )
            )
        return tuple(self._to_gloss(row) for row in rows)

    def lookup_many(
        self,
        headwords: Sequence[str],
        *,
        limit_per_word: int = 16,
    ) -> Mapping[str, tuple[Gloss, ...]]:
        normalized = tuple(dict.fromkeys(normalize_text(word).normalized for word in headwords if word))
        output: dict[str, list[Gloss]] = {word: [] for word in normalized}
        if not normalized:
            return {}

        with self._lock:
            for chunk in _chunks(normalized, 500):
                placeholders = ",".join("?" for _ in chunk)
                rows = self._connect().execute(
                    f"""
                    SELECT w.headword, e.source, e.pos, e.ta, e.en
                    FROM words AS w
                    JOIN entries AS e ON e.word_id = w.id
                    WHERE w.headword IN ({placeholders})
                    ORDER BY w.headword,
                      CASE e.source
                        WHEN 'agarathi' THEN 0
                        WHEN 'lexicon2' THEN 1
                        WHEN 'wiktionary' THEN 2
                        ELSE 3
                      END,
                      e.source
                    """,
                    chunk,
                )
                for row in rows:
                    headword = str(row["headword"])
                    if len(output[headword]) < limit_per_word:
                        output[headword].append(self._to_gloss(row))
        return {word: tuple(output[word]) for word in normalized}

    def search_prefix(self, prefix: str, *, limit: int = 20) -> dict[str, tuple[Gloss, ...]]:
        normalized = normalize_text(prefix).normalized
        escaped = normalized.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        with self._lock:
            headwords = tuple(
                str(row[0])
                for row in self._connect().execute(
                    """
                    SELECT headword
                    FROM words
                    WHERE headword LIKE ? ESCAPE '\\'
                    ORDER BY length(headword), headword
                    LIMIT ?
                    """,
                    (escaped + "%", max(1, limit)),
                )
            )
        return dict(self.lookup_many(headwords))

    def statistics(self) -> dict[str, int]:
        with self._lock:
            connection = self._connect()
            headwords = connection.execute("SELECT count(*) FROM words").fetchone()
            entries = connection.execute("SELECT count(*) FROM entries").fetchone()
        if headwords is None or entries is None:
            raise DictionaryError("could not read dictionary statistics")
        return {"headwords": int(headwords[0]), "entries": int(entries[0])}

    def close(self) -> None:
        with self._lock:
            if self._connection is not None:
                self._connection.close()
                self._connection = None

    def __enter__(self) -> AvvaiDictionary:
        return self

    def __exit__(self, _exc_type: object, _exc: object, _traceback: object) -> None:
        self.close()


def _chunks(values: Sequence[str], size: int) -> Iterable[tuple[str, ...]]:
    for start in range(0, len(values), size):
        yield tuple(values[start : start + size])
