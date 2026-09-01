from __future__ import annotations

import json
from pathlib import Path

import pytest

from thamizhi_morph.backends.foma import DEFAULT_MODELS
from thamizhi_morph.cli import main


@pytest.fixture
def cli_runtime(tmp_path: Path) -> tuple[Path, Path]:
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
    if inverse and model == 'noun.fst' and value == 'தமிழ்+noun+nom':
        print(f'{value}\\tதமிழ்')
    elif not inverse and model == 'noun.fst' and value == 'தமிழ்':
        print(f'{value}\\tதமிழ்+noun+nom')
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


def test_cli_doctor_and_analysis(
    cli_runtime: tuple[Path, Path], capsys: pytest.CaptureFixture[str]
) -> None:
    executable, model_dir = cli_runtime

    assert main([*global_args(executable, model_dir), "doctor", "--json"]) == 0
    health = json.loads(capsys.readouterr().out)
    assert health["ready"] is True

    assert (
        main(
            [
                *global_args(executable, model_dir),
                "analyze",
                "தமிழ்",
                "--format",
                "json",
                "--no-guessers",
            ]
        )
        == 0
    )
    output = json.loads(capsys.readouterr().out)
    assert output["tokens"][0]["analyses"][0]["lemma"] == "தமிழ்"


def test_cli_generation_and_error_path(
    cli_runtime: tuple[Path, Path], capsys: pytest.CaptureFixture[str]
) -> None:
    executable, model_dir = cli_runtime

    code = main(
        [
            *global_args(executable, model_dir),
            "generate",
            "தமிழ்+noun+nom",
            "--model",
            "noun",
            "--format",
            "json",
        ]
    )
    assert code == 0
    assert json.loads(capsys.readouterr().out)["தமிழ்+noun+nom"] == ["தமிழ்"]

    assert main([*global_args(executable, model_dir), "lookup", "தமிழ்"]) == 2
    assert "requires --dictionary" in capsys.readouterr().err


def test_cli_output_formats_file_input_and_benchmark(
    cli_runtime: tuple[Path, Path],
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    executable, model_dir = cli_runtime
    text_file = tmp_path / "input.txt"
    text_file.write_text("தமிழ், 2", encoding="utf-8")

    assert (
        main(
            [
                *global_args(executable, model_dir),
                "analyze",
                "--file",
                str(text_file),
                "--format",
                "conllu",
                "--no-guessers",
            ]
        )
        == 0
    )
    conllu = capsys.readouterr().out
    assert len(conllu.splitlines()[1].split("\t")) == 10

    assert (
        main(
            [
                *global_args(executable, model_dir),
                "analyze",
                "தமிழ்",
                "--format",
                "jsonl",
                "--no-guessers",
            ]
        )
        == 0
    )
    assert json.loads(capsys.readouterr().out)["token"] == "தமிழ்"

    wordlist = tmp_path / "words.txt"
    wordlist.write_text("தமிழ்\nஅறியாது\n", encoding="utf-8")
    assert (
        main(
            [
                *global_args(executable, model_dir),
                "benchmark",
                str(wordlist),
                "--limit",
                "2",
                "--max-unknown",
                "1",
            ]
        )
        == 0
    )
    report = json.loads(capsys.readouterr().out)
    assert report["total"] == 2
    assert report["known"] == 1


def test_cli_pretty_pos_and_conflicting_input_error(
    cli_runtime: tuple[Path, Path],
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    executable, model_dir = cli_runtime

    assert (
        main(
            [
                *global_args(executable, model_dir),
                "analyze",
                "தமிழ்",
                "--pos",
                "NOUN",
                "--all",
            ]
        )
        == 0
    )
    assert "தமிழ் [noun]" in capsys.readouterr().out

    text_file = tmp_path / "input.txt"
    text_file.write_text("தமிழ்", encoding="utf-8")
    assert (
        main(
            [
                *global_args(executable, model_dir),
                "analyze",
                "தமிழ்",
                "--file",
                str(text_file),
            ]
        )
        == 2
    )
    assert "either positional text or --file" in capsys.readouterr().err


def test_cli_dictionary_exact_and_prefix(
    cli_runtime: tuple[Path, Path],
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    import sqlite3

    executable, model_dir = cli_runtime
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
    base = [*global_args(executable, model_dir), "--dictionary", str(path)]

    assert main([*base, "lookup", "தமிழ்", "--limit", "1"]) == 0
    assert json.loads(capsys.readouterr().out)[0]["en"] == "Tamil"

    assert main([*base, "lookup", "தமிழ", "--prefix", "--limit", "2"]) == 0
    assert list(json.loads(capsys.readouterr().out)) == ["தமிழ்", "தமிழன்"]


def test_cli_pretty_generation_from_stdin(
    cli_runtime: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    import io

    executable, model_dir = cli_runtime
    monkeypatch.setattr("sys.stdin", io.StringIO("தமிழ்+noun+nom\n"))

    assert (
        main(
            [
                *global_args(executable, model_dir),
                "generate",
                "--model",
                "noun",
            ]
        )
        == 0
    )
    assert "தமிழ்+noun+nom\tதமிழ்" in capsys.readouterr().out
