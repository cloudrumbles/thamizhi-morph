from __future__ import annotations

from pathlib import Path

from .base import MorphologyBackend
from .foma import FomaBackend, FomaModel
from .native import NativeFomaBackend, NativeFomaUnavailable


def build_foma_backend(
    kind: str = "auto",
    model_dir: str | Path | None = None,
    *,
    flookup: str | Path | None = None,
    library_path: str | Path | None = None,
    models: tuple[FomaModel, ...] | None = None,
    timeout: float = 30.0,
    max_workers: int = 4,
    strict_output: bool = False,
) -> MorphologyBackend:
    """Build a backend, preferring persistent libfoma when `kind` is `auto`."""

    selected = kind.strip().lower()
    if selected not in {"auto", "native", "subprocess"}:
        raise ValueError("backend must be one of: auto, native, subprocess")

    keyword_models = {} if models is None else {"models": models}
    if selected in {"auto", "native"}:
        try:
            return NativeFomaBackend(
                model_dir,
                library_path=library_path,
                max_workers=max_workers,
                **keyword_models,
            )
        except NativeFomaUnavailable:
            if selected == "native":
                raise

    return FomaBackend(
        model_dir,
        flookup=flookup,
        timeout=timeout,
        max_workers=max_workers,
        strict_output=strict_output,
        **keyword_models,
    )
