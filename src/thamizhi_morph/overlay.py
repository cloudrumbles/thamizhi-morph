from __future__ import annotations

import json
import sqlite3
import threading
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any, TextIO

from .models import MorphAnalysis, Morpheme
from .normalization import normalize_text

_SCHEMA_VERSION = 1


class OverlayError(RuntimeError):
    pass


class OverlayMode(StrEnum):
    AUGMENT = "augment"
    REPLACE = "replace"
    FALLBACK = "fallback"


@dataclass(frozen=True, slots=True)
class OverlayEntry:
    id: int
    surface: str
    lemma: str
    pos: str
    morphemes: tuple[Morpheme, ...]
    mode: OverlayMode
    source: str
    note: str
    enabled: bool
    created_at: str
    updated_at: str

    @property
    def model_name(self) -> str:
        return f"overlay:{self.mode.value}:{self.source}"

    def to_analysis(self) -> MorphAnalysis:
        lexical = "+".join(
            [
                self.lemma,
                self.pos,
                *(
                    item.label if item.surface is None else f"{item.label}={item.surface}"
                    for item in self.morphemes
                ),
            ]
        )
        return MorphAnalysis(
            surface=self.surface,
            lemma=self.lemma,
            pos=self.pos,
            morphemes=self.morphemes,
            model=self.model_name,
            raw=lexical,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "surface": self.surface,
            "lemma": self.lemma,
            "pos": self.pos,
            "morphemes": [item.to_dict() for item in self.morphemes],
            "mode": self.mode.value,
            "source": self.source,
            "note": self.note,
            "enabled": self.enabled,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


class OverlayStore:
    """SQLite-backed curated analyses layered over immutable finite-state models."""

    def __init__(self, path: str | Path, *, writable: bool = False) -> None:
        self.path = Path(path).expanduser().resolve()
        self.writable = writable
        self._lock = threading.RLock()
        self._connection: sqlite3.Connection | None = None
        if writable:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self._connect()
            self._initialize_schema()
        elif not self.path.is_file():
            raise OverlayError(f"overlay database does not exist: {self.path}")
        self._validate_schema()

    def _connect(self) -> sqlite3.Connection:
        with self._lock:
            if self._connection is None:
                if self.writable:
                    connection = sqlite3.connect(self.path, check_same_thread=False)
                    connection.execute("PRAGMA journal_mode = WAL")
                    connection.execute("PRAGMA synchronous = NORMAL")
                else:
                    connection = sqlite3.connect(
                        self.path.as_uri() + "?mode=ro",
                        uri=True,
                        check_same_thread=False,
                    )
                    connection.execute("PRAGMA query_only = ON")
                connection.row_factory = sqlite3.Row
                connection.execute("PRAGMA foreign_keys = ON")
                self._connection = connection
            return self._connection

    def _initialize_schema(self) -> None:
        if not self.writable:
            raise OverlayError("overlay is read-only")
        with self._lock:
            connection = self._connect()
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS analyses (
                  id INTEGER PRIMARY KEY,
                  surface TEXT NOT NULL,
                  lemma TEXT NOT NULL,
                  pos TEXT NOT NULL,
                  morphemes TEXT NOT NULL DEFAULT '[]',
                  mode TEXT NOT NULL CHECK (mode IN ('augment', 'replace', 'fallback')),
                  source TEXT NOT NULL DEFAULT 'user',
                  note TEXT NOT NULL DEFAULT '',
                  enabled INTEGER NOT NULL DEFAULT 1 CHECK (enabled IN (0, 1)),
                  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                  UNIQUE(surface, lemma, pos, morphemes, mode, source)
                );
                CREATE INDEX IF NOT EXISTS analyses_surface_enabled
                  ON analyses(surface, enabled, mode);
                """
            )
            connection.execute(f"PRAGMA user_version = {_SCHEMA_VERSION}")
            connection.commit()

    def _validate_schema(self) -> None:
        with self._lock:
            connection = self._connect()
            version_row = connection.execute("PRAGMA user_version").fetchone()
            version = int(version_row[0]) if version_row is not None else 0
            columns = {
                str(row[1]) for row in connection.execute("PRAGMA table_info(analyses)")
            }
        required = {
            "id",
            "surface",
            "lemma",
            "pos",
            "morphemes",
            "mode",
            "source",
            "note",
            "enabled",
            "created_at",
            "updated_at",
        }
        if version != _SCHEMA_VERSION or not required.issubset(columns):
            raise OverlayError(
                f"unsupported overlay schema version {version}; expected {_SCHEMA_VERSION}"
            )

    @staticmethod
    def _encode_morphemes(morphemes: Sequence[Morpheme]) -> str:
        return json.dumps(
            [item.to_dict() for item in morphemes],
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )

    @staticmethod
    def _decode_morphemes(value: str) -> tuple[Morpheme, ...]:
        try:
            payload = json.loads(value)
        except json.JSONDecodeError as error:
            raise OverlayError("overlay contains invalid morpheme JSON") from error
        if not isinstance(payload, list):
            raise OverlayError("overlay morphemes must be a JSON list")
        output: list[Morpheme] = []
        for item in payload:
            if not isinstance(item, dict) or not isinstance(item.get("label"), str):
                raise OverlayError("overlay contains an invalid morpheme object")
            surface = item.get("surface")
            if surface is not None and not isinstance(surface, str):
                raise OverlayError("morpheme surface must be a string or null")
            output.append(Morpheme(label=item["label"], surface=surface))
        return tuple(output)

    @classmethod
    def _row_to_entry(cls, row: sqlite3.Row) -> OverlayEntry:
        return OverlayEntry(
            id=int(row["id"]),
            surface=str(row["surface"]),
            lemma=str(row["lemma"]),
            pos=str(row["pos"]),
            morphemes=cls._decode_morphemes(str(row["morphemes"])),
            mode=OverlayMode(str(row["mode"])),
            source=str(row["source"]),
            note=str(row["note"]),
            enabled=bool(row["enabled"]),
            created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
        )

    def _require_writable(self) -> None:
        if not self.writable:
            raise OverlayError("overlay database was opened read-only")

    def add(
        self,
        surface: str,
        lemma: str,
        pos: str,
        *,
        morphemes: Sequence[Morpheme] = (),
        mode: OverlayMode | str = OverlayMode.AUGMENT,
        source: str = "user",
        note: str = "",
    ) -> OverlayEntry:
        self._require_writable()
        normalized_surface = normalize_text(surface).normalized.strip()
        normalized_lemma = normalize_text(lemma).normalized.strip()
        normalized_pos = pos.strip().lower()
        normalized_source = source.strip()
        selected_mode = OverlayMode(mode)
        if not normalized_surface or not normalized_lemma or not normalized_pos:
            raise ValueError("surface, lemma, and pos must not be empty")
        if not normalized_source:
            raise ValueError("source must not be empty")
        encoded = self._encode_morphemes(morphemes)
        with self._lock:
            connection = self._connect()
            connection.execute(
                """
                INSERT INTO analyses(
                  surface, lemma, pos, morphemes, mode, source, note, enabled
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 1)
                ON CONFLICT(surface, lemma, pos, morphemes, mode, source)
                DO UPDATE SET
                  note = excluded.note,
                  enabled = 1,
                  updated_at = CURRENT_TIMESTAMP
                """,
                (
                    normalized_surface,
                    normalized_lemma,
                    normalized_pos,
                    encoded,
                    selected_mode.value,
                    normalized_source,
                    note,
                ),
            )
            connection.commit()
            row = connection.execute(
                """
                SELECT * FROM analyses
                WHERE surface = ? AND lemma = ? AND pos = ?
                  AND morphemes = ? AND mode = ? AND source = ?
                """,
                (
                    normalized_surface,
                    normalized_lemma,
                    normalized_pos,
                    encoded,
                    selected_mode.value,
                    normalized_source,
                ),
            ).fetchone()
        if row is None:
            raise OverlayError("could not read the inserted overlay entry")
        return self._row_to_entry(row)

    def delete(self, entry_id: int) -> bool:
        self._require_writable()
        with self._lock:
            cursor = self._connect().execute(
                "DELETE FROM analyses WHERE id = ?",
                (entry_id,),
            )
            self._connect().commit()
            return cursor.rowcount > 0

    def set_enabled(self, entry_id: int, enabled: bool) -> bool:
        self._require_writable()
        with self._lock:
            cursor = self._connect().execute(
                """
                UPDATE analyses
                SET enabled = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (int(enabled), entry_id),
            )
            self._connect().commit()
            return cursor.rowcount > 0

    def get(self, entry_id: int) -> OverlayEntry | None:
        with self._lock:
            row = self._connect().execute(
                "SELECT * FROM analyses WHERE id = ?",
                (entry_id,),
            ).fetchone()
        return self._row_to_entry(row) if row is not None else None

    def list_entries(
        self,
        *,
        surface: str | None = None,
        enabled_only: bool = False,
        limit: int = 1000,
        offset: int = 0,
    ) -> tuple[OverlayEntry, ...]:
        conditions: list[str] = []
        parameters: list[object] = []
        if surface is not None:
            conditions.append("surface = ?")
            parameters.append(normalize_text(surface).normalized)
        if enabled_only:
            conditions.append("enabled = 1")
        where = " WHERE " + " AND ".join(conditions) if conditions else ""
        parameters.extend((max(1, limit), max(0, offset)))
        with self._lock:
            rows = tuple(
                self._connect().execute(
                    f"""
                    SELECT * FROM analyses{where}
                    ORDER BY surface, mode, source, id
                    LIMIT ? OFFSET ?
                    """,
                    parameters,
                )
            )
        return tuple(self._row_to_entry(row) for row in rows)

    def lookup_many(
        self,
        surfaces: Sequence[str],
    ) -> Mapping[str, tuple[OverlayEntry, ...]]:
        normalized = tuple(
            dict.fromkeys(normalize_text(surface).normalized for surface in surfaces if surface)
        )
        output: dict[str, list[OverlayEntry]] = {surface: [] for surface in normalized}
        if not normalized:
            return {}
        with self._lock:
            for chunk in _chunks(normalized, 500):
                placeholders = ",".join("?" for _ in chunk)
                rows = self._connect().execute(
                    f"""
                    SELECT * FROM analyses
                    WHERE enabled = 1 AND surface IN ({placeholders})
                    ORDER BY surface,
                      CASE mode
                        WHEN 'replace' THEN 0
                        WHEN 'augment' THEN 1
                        WHEN 'fallback' THEN 2
                      END,
                      source,
                      id
                    """,
                    chunk,
                )
                for row in rows:
                    entry = self._row_to_entry(row)
                    output[entry.surface].append(entry)
        return {surface: tuple(entries) for surface, entries in output.items()}

    def statistics(self) -> dict[str, int]:
        with self._lock:
            connection = self._connect()
            total_row = connection.execute("SELECT count(*) FROM analyses").fetchone()
            enabled_row = connection.execute(
                "SELECT count(*) FROM analyses WHERE enabled = 1"
            ).fetchone()
        if total_row is None or enabled_row is None:
            raise OverlayError("could not read overlay statistics")
        return {"entries": int(total_row[0]), "enabled": int(enabled_row[0])}

    def data_version(self) -> int:
        with self._lock:
            row = self._connect().execute("PRAGMA data_version").fetchone()
        return int(row[0]) if row is not None else 0

    def export_jsonl(self, destination: TextIO) -> int:
        entries = self.list_entries(limit=2_147_483_647)
        for entry in entries:
            payload = entry.to_dict()
            payload.pop("id", None)
            payload.pop("created_at", None)
            payload.pop("updated_at", None)
            destination.write(json.dumps(payload, ensure_ascii=False) + "\n")
        return len(entries)

    def import_jsonl(self, source: Iterable[str]) -> int:
        self._require_writable()
        imported = 0
        for line_number, raw_line in enumerate(source, 1):
            line = raw_line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError as error:
                raise OverlayError(
                    f"invalid overlay JSON on line {line_number}: {error.msg}"
                ) from error
            if not isinstance(payload, dict):
                raise OverlayError(f"overlay line {line_number} must be an object")
            raw_morphemes = payload.get("morphemes", [])
            if not isinstance(raw_morphemes, list):
                raise OverlayError(f"morphemes on line {line_number} must be a list")
            morphemes: list[Morpheme] = []
            for item in raw_morphemes:
                if not isinstance(item, dict) or not isinstance(item.get("label"), str):
                    raise OverlayError(
                        f"invalid morpheme object on line {line_number}"
                    )
                surface = item.get("surface")
                if surface is not None and not isinstance(surface, str):
                    raise OverlayError(
                        f"invalid morpheme surface on line {line_number}"
                    )
                morphemes.append(Morpheme(item["label"], surface))
            try:
                entry = self.add(
                    str(payload["surface"]),
                    str(payload["lemma"]),
                    str(payload["pos"]),
                    morphemes=morphemes,
                    mode=str(payload.get("mode", OverlayMode.AUGMENT.value)),
                    source=str(payload.get("source", "import")),
                    note=str(payload.get("note", "")),
                )
            except KeyError as error:
                raise OverlayError(
                    f"overlay line {line_number} is missing {error.args[0]!r}"
                ) from error
            if not bool(payload.get("enabled", True)):
                self.set_enabled(entry.id, False)
            imported += 1
        return imported

    def close(self) -> None:
        with self._lock:
            if self._connection is not None:
                self._connection.close()
                self._connection = None

    def __enter__(self) -> OverlayStore:
        return self

    def __exit__(self, _exc_type: object, _exc: object, _traceback: object) -> None:
        self.close()


def _chunks(values: Sequence[str], size: int) -> Iterable[tuple[str, ...]]:
    for start in range(0, len(values), size):
        yield tuple(values[start : start + size])
