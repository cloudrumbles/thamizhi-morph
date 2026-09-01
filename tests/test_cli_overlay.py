from __future__ import annotations

import json
from pathlib import Path

import pytest

from thamizhi_morph.backends.foma import DEFAULT_MODELS
from thamizhi_morph.cli import main


@pytest.fixture
def overlay_runtime(tmp_path: Path) -> tuple[Path, Path, Path]:
    executable = tmp_path / "flookup"
    executable.write_text(
        """#!/usr/bin/env python3
import sys
for raw in sys.stdin:
    value = raw.rstrip('\\n')
    if value:
        print(f'{value}\\t+?')
""",
        encoding="utf-8",
    )
    executable.chmod(0o755)
    model_dir = tmp_path / "models"
    model_dir.mkdir()
    for model in DEFAULT_MODELS:
        (model_dir / model.filename).touch()
    return executable, model_dir, tmp_path / "overlay.db"


def global_args(executable: Path, model_dir: Path, overlay: Path) -> list[str]:
    return [
        "--flookup",
        str(executable),
        "--model-dir",
        str(model_dir),
        "--overlay",
        str(overlay),
    ]


def test_cli_creates_adds_lists_and_applies_overlay(
    overlay_runtime: tuple[Path, Path, Path],
    capsys: pytest.CaptureFixture[str],
) -> None:
    executable, model_dir, overlay = overlay_runtime
    arguments = global_args(executable, model_dir, overlay)

    assert main([*arguments, "overlay", "init"]) == 0
    assert json.loads(capsys.readouterr().out)["entries"] == 0

    assert (
        main(
            [
                *arguments,
                "overlay",
                "add",
                "சிங்கப்பூர்ல",
                "--lemma",
                "சிங்கப்பூர்",
                "--pos",
                "noun",
                "--morpheme",
                "loc=ல",
                "--mode",
                "fallback",
                "--source",
                "sg-tamil",
            ]
        )
        == 0
    )
    entry = json.loads(capsys.readouterr().out)
    assert entry["lemma"] == "சிங்கப்பூர்"

    assert main([*arguments, "overlay", "list", "--enabled-only"]) == 0
    assert len(json.loads(capsys.readouterr().out)) == 1

    assert (
        main(
            [
                *arguments,
                "analyze",
                "சிங்கப்பூர்ல",
                "--format",
                "json",
            ]
        )
        == 0
    )
    analysis = json.loads(capsys.readouterr().out)["tokens"][0]["analyses"][0]
    assert analysis["lemma"] == "சிங்கப்பூர்"
    assert analysis["provenance"] == "overlay"

    assert main([*arguments, "overlay", "disable", str(entry["id"])]) == 0
    assert json.loads(capsys.readouterr().out)["enabled"] is False
    assert main([*arguments, "overlay", "enable", str(entry["id"])]) == 0
    assert json.loads(capsys.readouterr().out)["enabled"] is True

    assert main([*arguments, "overlay", "delete", str(entry["id"])]) == 0
    assert main([*arguments, "overlay", "list"]) == 0
    assert json.loads(capsys.readouterr().out) == []


def test_cli_overlay_export_and_import(
    overlay_runtime: tuple[Path, Path, Path],
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    executable, model_dir, overlay = overlay_runtime
    arguments = global_args(executable, model_dir, overlay)
    assert (
        main(
            [
                *arguments,
                "overlay",
                "add",
                "கம்ப்யூட்டர்",
                "--lemma",
                "கம்ப்யூட்டர்",
                "--pos",
                "noun",
            ]
        )
        == 0
    )
    capsys.readouterr()

    export_path = tmp_path / "overlay.jsonl"
    assert main([*arguments, "overlay", "export", str(export_path)]) == 0
    assert "கம்ப்யூட்டர்" in export_path.read_text(encoding="utf-8")

    imported_overlay = tmp_path / "imported.db"
    imported_args = global_args(executable, model_dir, imported_overlay)
    assert main([*imported_args, "overlay", "import", str(export_path)]) == 0
    assert json.loads(capsys.readouterr().out)["imported"] == 1


def test_cli_requires_overlay_path(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["overlay", "init"]) == 2
    assert "require --overlay" in capsys.readouterr().err
