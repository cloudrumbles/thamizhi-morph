from __future__ import annotations

import json
from pathlib import Path

import pytest

from thamizhi_morph.backends.foma import DEFAULT_MODELS
from thamizhi_morph.cli import main


@pytest.fixture
def roundtrip_runtime(tmp_path: Path) -> tuple[Path, Path]:
    executable = tmp_path / "flookup"
    executable.write_text(
        """#!/usr/bin/env python3
import sys
from pathlib import Path
inverse = '-i' in sys.argv[1:]
model = Path(sys.argv[-1]).name
for raw in sys.stdin:
    value = raw.rstrip('\\n')
    if not value:
        continue
    if not inverse and model == 'noun.fst' and value in {'தமிழ்', 'பிழை'}:
        print(f'{value}\\t{value}+noun+nom')
    elif inverse and model == 'noun.fst' and value == 'தமிழ்+noun+nom':
        print(f'{value}\\tதமிழ்')
    elif inverse and model == 'noun.fst' and value == 'பிழை+noun+nom':
        print(f'{value}\\tவேறு')
    else:
        print(f'{value}\\t+?')
""",
        encoding="utf-8",
    )
    executable.chmod(0o755)
    model_dir = tmp_path / "models"
    model_dir.mkdir()
    for model in DEFAULT_MODELS:
        (model_dir / model.filename).touch()
    return executable, model_dir


def global_args(executable: Path, model_dir: Path) -> list[str]:
    return ["--flookup", str(executable), "--model-dir", str(model_dir)]


def test_cli_roundtrip_reports_and_can_fail_ci(
    roundtrip_runtime: tuple[Path, Path],
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    executable, model_dir = roundtrip_runtime
    wordlist = tmp_path / "words.txt"
    wordlist.write_text("தமிழ்\nபிழை\n", encoding="utf-8")

    code = main(
        [
            *global_args(executable, model_dir),
            "roundtrip",
            str(wordlist),
            "--fail-on-error",
        ]
    )

    assert code == 1
    report = json.loads(capsys.readouterr().out)
    assert report["checked_analyses"] == 2
    assert report["passed"] == 1
    assert report["failed"] == 1
