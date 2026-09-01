from __future__ import annotations

from io import StringIO
from pathlib import Path

import pytest

from thamizhi_morph.models import Morpheme
from thamizhi_morph.overlay import OverlayError, OverlayMode, OverlayStore


def test_overlay_crud_lookup_and_statistics(tmp_path: Path) -> None:
    path = tmp_path / "overlay.db"
    with OverlayStore(path, writable=True) as store:
        entry = store.add(
            "சிங்கப்பூர்ல",
            "சிங்கப்பூர்",
            "noun",
            morphemes=(Morpheme("loc", "ல"),),
            mode=OverlayMode.AUGMENT,
            source="sg-tamil",
            note="colloquial locative",
        )

        assert entry.id > 0
        assert entry.to_analysis().provenance == "overlay"
        assert store.lookup_many(["சிங்கப்பூர்ல"])["சிங்கப்பூர்ல"] == (entry,)
        assert store.statistics() == {"entries": 1, "enabled": 1}

        assert store.set_enabled(entry.id, False)
        assert store.lookup_many(["சிங்கப்பூர்ல"])["சிங்கப்பூர்ல"] == ()
        assert store.statistics() == {"entries": 1, "enabled": 0}

        assert store.set_enabled(entry.id, True)
        assert store.delete(entry.id)
        assert store.get(entry.id) is None
        assert not store.delete(entry.id)


def test_overlay_upsert_and_read_only_mode(tmp_path: Path) -> None:
    path = tmp_path / "overlay.db"
    with OverlayStore(path, writable=True) as store:
        first = store.add("தமிழ்", "தமிழ்", "noun", note="first")
        second = store.add("தமிழ்", "தமிழ்", "noun", note="updated")
        assert first.id == second.id
        assert second.note == "updated"

    with OverlayStore(path) as store:
        assert store.list_entries()[0].note == "updated"
        with pytest.raises(OverlayError, match="read-only"):
            store.add("மரம்", "மரம்", "noun")


def test_overlay_jsonl_round_trip(tmp_path: Path) -> None:
    source_path = tmp_path / "source.db"
    destination_path = tmp_path / "destination.db"
    with OverlayStore(source_path, writable=True) as source:
        entry = source.add(
            "கம்ப்யூட்டர்",
            "கம்ப்யூட்டர்",
            "noun",
            mode="fallback",
            source="loanwords",
        )
        source.set_enabled(entry.id, False)
        portable = StringIO()
        assert source.export_jsonl(portable) == 1

    portable.seek(0)
    with OverlayStore(destination_path, writable=True) as destination:
        assert destination.import_jsonl(portable) == 1
        imported = destination.list_entries()[0]
        assert imported.surface == "கம்ப்யூட்டர்"
        assert imported.mode is OverlayMode.FALLBACK
        assert not imported.enabled


def test_overlay_rejects_missing_or_invalid_schema(tmp_path: Path) -> None:
    with pytest.raises(OverlayError, match="does not exist"):
        OverlayStore(tmp_path / "missing.db")

    path = tmp_path / "invalid.db"
    path.touch()
    with pytest.raises(OverlayError, match="unsupported overlay schema"):
        OverlayStore(path)


def test_overlay_import_validates_json(tmp_path: Path) -> None:
    with OverlayStore(tmp_path / "overlay.db", writable=True) as store:
        with pytest.raises(OverlayError, match="invalid overlay JSON"):
            store.import_jsonl(["{bad json}"])
        with pytest.raises(OverlayError, match="must be an object"):
            store.import_jsonl(["[]"])
