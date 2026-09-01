from __future__ import annotations

from pathlib import Path

import pytest

from thamizhi_morph.backends.factory import build_foma_backend
from thamizhi_morph.backends.foma import FomaBackend, FomaModel
from thamizhi_morph.backends.native import NativeFomaUnavailable


def test_factory_rejects_unknown_backend() -> None:
    with pytest.raises(ValueError, match="auto, native, subprocess"):
        build_foma_backend("magic")


def test_factory_builds_subprocess_backend(tmp_path: Path) -> None:
    backend = build_foma_backend(
        "subprocess",
        tmp_path,
        flookup="custom-flookup",
        models=(FomaModel("noun", "noun.fst", "noun"),),
    )

    assert isinstance(backend, FomaBackend)
    assert backend.flookup == "custom-flookup"


def test_auto_falls_back_when_native_library_is_unavailable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def unavailable(*_args: object, **_kwargs: object) -> object:
        raise NativeFomaUnavailable("missing")

    monkeypatch.setattr(
        "thamizhi_morph.backends.factory.NativeFomaBackend",
        unavailable,
    )
    backend = build_foma_backend(
        "auto",
        tmp_path,
        flookup="flookup",
        models=(FomaModel("noun", "noun.fst", "noun"),),
    )

    assert isinstance(backend, FomaBackend)


def test_native_mode_does_not_hide_loader_failures(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def unavailable(*_args: object, **_kwargs: object) -> object:
        raise NativeFomaUnavailable("missing")

    monkeypatch.setattr(
        "thamizhi_morph.backends.factory.NativeFomaBackend",
        unavailable,
    )
    with pytest.raises(NativeFomaUnavailable, match="missing"):
        build_foma_backend("native", tmp_path)
