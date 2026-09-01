from __future__ import annotations

import os
from pathlib import Path

import pytest

from thamizhi_morph.backends.foma import FomaBackend, FomaModel


@pytest.fixture
def fake_foma(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path, Path]:
    executable = tmp_path / "flookup"
    executable.write_text(
        """#!/usr/bin/env python3
import os
import sys
from pathlib import Path

inverse = '-i' in sys.argv[1:]
model = Path(sys.argv[-1]).name
values = [line.rstrip('\\n') for line in sys.stdin if line.rstrip('\\n')]
log = os.environ.get('FAKE_FLOOKUP_LOG')
if log:
    with open(log, 'a', encoding='utf-8') as handle:
        handle.write(f'{model}:{len(values)}:{inverse}\\n')
for value in values:
    if inverse:
        if model == 'noun.fst' and value == 'மரம்+noun+nom':
            print(f'{value}\\tமரம்')
        else:
            print(f'{value}\\t+?')
    elif model == 'noun.fst' and value == 'தமிழ்':
        print(f'{value}\\tதமிழ்+noun+nom')
    elif model == 'noun.fst' and value == 'மரங்கள்':
        print(f'{value}\\tமரம்+noun+pl=கள்+nom')
    elif model == 'noun-guess.fst' and value == 'புதுச்சொல்':
        print(f'{value}\\tபுதுச்சொல்+noun+guess+nom')
    else:
        print(f'{value}\\t+?')
""",
        encoding="utf-8",
    )
    executable.chmod(0o755)
    model_dir = tmp_path / "models"
    model_dir.mkdir()
    (model_dir / "noun.fst").touch()
    (model_dir / "noun-guess.fst").touch()
    log = tmp_path / "calls.log"
    monkeypatch.setenv("FAKE_FLOOKUP_LOG", str(log))
    return executable, model_dir, log


def backend(executable: Path, model_dir: Path) -> FomaBackend:
    return FomaBackend(
        model_dir,
        flookup=executable,
        models=(
            FomaModel("noun", "noun.fst", "noun", priority=0),
            FomaModel("noun-guesser", "noun-guess.fst", "noun", guesser=True, priority=10),
        ),
        max_workers=2,
    )


def test_backend_batches_each_model_once(fake_foma: tuple[Path, Path, Path]) -> None:
    executable, model_dir, log = fake_foma
    runtime = backend(executable, model_dir)

    result = runtime.analyze_many(["தமிழ்", "மரங்கள்"])

    assert result["தமிழ்"][0].lemma == "தமிழ்"
    assert result["மரங்கள்"][0].lemma == "மரம்"
    assert log.read_text(encoding="utf-8").splitlines() == ["noun.fst:2:False"]


def test_backend_runs_guessers_as_a_separate_stage(fake_foma: tuple[Path, Path, Path]) -> None:
    executable, model_dir, _log = fake_foma
    runtime = backend(executable, model_dir)

    result = runtime.analyze_many(["புதுச்சொல்"], guess=True)

    assert result["புதுச்சொல்"][0].guessed
    assert result["புதுச்சொல்"][0].model == "noun-guesser"


def test_backend_inverse_generation(fake_foma: tuple[Path, Path, Path]) -> None:
    executable, model_dir, _log = fake_foma
    runtime = backend(executable, model_dir)

    result = runtime.generate_many(["மரம்+noun+nom"], model="noun")

    assert result == {"மரம்+noun+nom": ("மரம்",)}


def test_backend_health_and_protocol_injection(fake_foma: tuple[Path, Path, Path]) -> None:
    executable, model_dir, _log = fake_foma
    runtime = backend(executable, model_dir)

    assert runtime.health().ready
    with pytest.raises(ValueError, match="newlines"):
        runtime.analyze_many(["தமிழ்\nமரம்"])


def test_backend_resolves_executable_from_path(
    fake_foma: tuple[Path, Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    executable, model_dir, _log = fake_foma
    monkeypatch.setenv("PATH", str(executable.parent) + os.pathsep + os.environ.get("PATH", ""))
    runtime = FomaBackend(
        model_dir,
        flookup="flookup",
        models=(FomaModel("noun", "noun.fst", "noun"),),
    )

    assert runtime.health().ready


def test_empty_batches_do_not_start_processes(fake_foma: tuple[Path, Path, Path]) -> None:
    executable, model_dir, log = fake_foma
    runtime = backend(executable, model_dir)

    assert runtime.analyze_many([]) == {}
    assert runtime.generate_many([]) == {}
    assert not log.exists()


def test_unknown_model_and_missing_model_are_reported(fake_foma: tuple[Path, Path, Path]) -> None:
    executable, model_dir, _log = fake_foma
    runtime = backend(executable, model_dir)

    with pytest.raises(ValueError, match="unknown model"):
        runtime.generate_many(["மரம்+noun+nom"], model="missing")

    (model_dir / "noun.fst").unlink()
    assert not runtime.health().ready
    with pytest.raises(RuntimeError, match="missing FST model"):
        runtime.analyze_many(["தமிழ்"])


def test_nonzero_exit_timeout_and_strict_malformed_output(tmp_path: Path) -> None:
    model_dir = tmp_path / "models"
    model_dir.mkdir()
    (model_dir / "noun.fst").touch()

    failing = tmp_path / "failing"
    failing.write_text("#!/bin/sh\necho broken >&2\nexit 7\n", encoding="utf-8")
    failing.chmod(0o755)
    runtime = FomaBackend(
        model_dir,
        flookup=failing,
        models=(FomaModel("noun", "noun.fst", "noun"),),
    )
    with pytest.raises(RuntimeError, match="exit code 7"):
        runtime.analyze_many(["தமிழ்"])

    sleepy = tmp_path / "sleepy"
    sleepy.write_text("#!/bin/sh\nsleep 1\n", encoding="utf-8")
    sleepy.chmod(0o755)
    runtime = FomaBackend(
        model_dir,
        flookup=sleepy,
        models=(FomaModel("noun", "noun.fst", "noun"),),
        timeout=0.01,
    )
    with pytest.raises(RuntimeError, match="timed out"):
        runtime.analyze_many(["தமிழ்"])

    malformed = tmp_path / "malformed"
    malformed.write_text("#!/bin/sh\ncat >/dev/null\necho malformed\n", encoding="utf-8")
    malformed.chmod(0o755)
    runtime = FomaBackend(
        model_dir,
        flookup=malformed,
        models=(FomaModel("noun", "noun.fst", "noun"),),
        strict_output=True,
    )
    with pytest.raises(RuntimeError, match="malformed output"):
        runtime.analyze_many(["தமிழ்"])


def test_missing_executable_is_reported(tmp_path: Path) -> None:
    model_dir = tmp_path / "models"
    model_dir.mkdir()
    (model_dir / "noun.fst").touch()
    runtime = FomaBackend(
        model_dir,
        flookup=tmp_path / "does-not-exist",
        models=(FomaModel("noun", "noun.fst", "noun"),),
    )

    assert not runtime.health().ready
    with pytest.raises(RuntimeError, match="could not find"):
        runtime.analyze_many(["தமிழ்"])
