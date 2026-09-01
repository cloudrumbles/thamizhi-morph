"""Discovery and validation of packaged finite-state resources."""

from __future__ import annotations

import json
from pathlib import Path

from .errors import ConfigurationError
from .models import ModelSpec


def default_model_dir() -> Path:
    """Return the directory containing the packaged FST binaries."""

    return Path(__file__).resolve().parent / "resources" / "models"


def default_manifest_path() -> Path:
    return default_model_dir() / "manifest.json"


def load_model_specs(
    manifest_path: str | Path | None = None,
) -> tuple[tuple[ModelSpec, ...], tuple[ModelSpec, ...]]:
    """Load exact and guesser model specifications from a JSON manifest."""

    path = Path(manifest_path) if manifest_path is not None else default_manifest_path()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise ConfigurationError(f"model manifest does not exist: {path}") from error
    except json.JSONDecodeError as error:
        raise ConfigurationError(f"invalid model manifest {path}: {error}") from error

    if payload.get("schema_version") != 1:
        raise ConfigurationError(
            f"unsupported model manifest schema: {payload.get('schema_version')!r}"
        )

    try:
        exact = tuple(
            sorted(
                (
                    ModelSpec.from_dict(item, kind="exact")
                    for item in payload.get("exact", ())
                ),
                key=lambda model: model.priority,
            )
        )
        guessers = tuple(
            sorted(
                (
                    ModelSpec.from_dict(item, kind="guesser")
                    for item in payload.get("guessers", ())
                ),
                key=lambda model: model.priority,
            )
        )
    except (KeyError, TypeError, ValueError) as error:
        raise ConfigurationError(f"invalid model entry in {path}: {error}") from error

    enabled = tuple(model for model in (*exact, *guessers) if model.enabled)
    names = [model.filename for model in enabled]
    duplicates = sorted({name for name in names if names.count(name) > 1})
    if duplicates:
        raise ConfigurationError(f"duplicate model entries: {', '.join(duplicates)}")
    if not exact:
        raise ConfigurationError("the manifest contains no exact models")

    return (
        tuple(model for model in exact if model.enabled),
        tuple(model for model in guessers if model.enabled),
    )


def validate_model_files(
    model_dir: str | Path,
    models: tuple[ModelSpec, ...],
) -> tuple[Path, ...]:
    """Resolve model files and fail with one actionable error for missing resources."""

    directory = Path(model_dir)
    paths = tuple(directory / model.filename for model in models)
    missing = [path.name for path in paths if not path.is_file()]
    if missing:
        raise ConfigurationError(
            f"missing FST model files in {directory}: {', '.join(sorted(missing))}"
        )
    return paths
