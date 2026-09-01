from __future__ import annotations

from pathlib import Path

from thamizhimorph.backend import FomaBackend
from thamizhimorph.models import ModelSpec


def _fake_flookup(tmp_path: Path) -> Path:
    executable = tmp_path / "fake-flookup"
    executable.write_text(
        """#!/usr/bin/env python3
import os
import pathlib
import sys

inverse = '-i' in sys.argv[1:]
model = pathlib.Path(sys.argv[-1]).name
log = os.environ.get('FAKE_FLOOKUP_LOG')
if log:
    with open(log, 'a', encoding='utf-8') as handle:
        handle.write(model + '\\n')
for line in sys.stdin:
    token = line.strip()
    if not token:
        continue
    if token == 'தெரியாது':
        print(f'{token}\\t+?')
    elif inverse:
        print(f'{token}\\t{token}-surface-{model}')
    else:
        print(f'{token}\\t{token}+noun+nom')
""",
        encoding="utf-8",
    )
    executable.chmod(0o755)
    return executable


def test_backend_batches_each_model_once(tmp_path: Path, monkeypatch) -> None:
    executable = _fake_flookup(tmp_path)
    log = tmp_path / "calls.log"
    monkeypatch.setenv("FAKE_FLOOKUP_LOG", str(log))
    for name in ("one.fst", "two.fst"):
        (tmp_path / name).write_bytes(b"model")

    models = (
        ModelSpec("one.fst", "exact"),
        ModelSpec("two.fst", "exact"),
    )
    backend = FomaBackend(model_dir=tmp_path, binary=str(executable), workers=2)
    results = backend.lookup_models(("தமிழ்", "மரம்"), models)

    assert len(results["தமிழ்"]) == 2
    assert sorted(log.read_text(encoding="utf-8").splitlines()) == ["one.fst", "two.fst"]


def test_backend_supports_inverse_generation(tmp_path: Path) -> None:
    executable = _fake_flookup(tmp_path)
    (tmp_path / "noun.fst").write_bytes(b"model")
    model = ModelSpec("noun.fst", "exact")
    backend = FomaBackend(model_dir=tmp_path, binary=str(executable))

    result = backend.lookup_models(("மரம்+noun+nom",), (model,), inverse=True)
    assert result["மரம்+noun+nom"][0][0].endswith("surface-noun.fst")


def test_backend_discards_only_explicit_unknown_marker(tmp_path: Path) -> None:
    executable = _fake_flookup(tmp_path)
    (tmp_path / "noun.fst").write_bytes(b"model")
    backend = FomaBackend(model_dir=tmp_path, binary=str(executable))

    result = backend.lookup_models(
        ("தெரியாது",),
        (ModelSpec("noun.fst", "exact"),),
    )
    assert result["தெரியாது"] == ()
