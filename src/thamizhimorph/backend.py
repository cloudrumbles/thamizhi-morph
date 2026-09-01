"""Backend abstraction and a safe, batched Foma implementation."""

from __future__ import annotations

import shutil
import subprocess
from collections import defaultdict
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Protocol, TypeAlias

from .errors import BackendError, ConfigurationError
from .models import ModelSpec
from .normalization import normalize_token
from .parsing import parse_flookup_pairs
from .model_resources import default_model_dir, validate_model_files

LookupRecord: TypeAlias = tuple[str, str]
LookupMap: TypeAlias = dict[str, tuple[LookupRecord, ...]]


class LookupBackend(Protocol):
    """Minimal backend contract used by :class:`thamizhimorph.Analyzer`."""

    def lookup_models(
        self,
        inputs: Sequence[str],
        models: Sequence[ModelSpec],
        *,
        inverse: bool = False,
    ) -> LookupMap:
        """Return ``(output, model filename)`` records for each input."""


class FomaBackend:
    """Invoke compiled Foma transducers without shell pipelines.

    One ``flookup`` process is launched per model for an entire input batch. The legacy
    script launched both ``echo`` and ``flookup`` for every token/model pair; batching
    removes the dominant process-startup overhead while retaining the existing FSTs.
    """

    def __init__(
        self,
        *,
        model_dir: str | Path | None = None,
        binary: str = "flookup",
        timeout_seconds: float = 60.0,
        workers: int = 4,
    ) -> None:
        self.model_dir = Path(model_dir) if model_dir is not None else default_model_dir()
        self.binary = binary
        self.timeout_seconds = timeout_seconds
        self.workers = max(1, workers)

    def _resolve_binary(self) -> str:
        candidate = Path(self.binary)
        if candidate.parent != Path(".") or candidate.is_absolute():
            if not candidate.is_file():
                raise ConfigurationError(f"flookup executable does not exist: {candidate}")
            return str(candidate)

        resolved = shutil.which(self.binary)
        if resolved is None:
            raise ConfigurationError(
                "flookup was not found on PATH. Install Foma or pass --flookup /path/to/flookup."
            )
        return resolved

    def _lookup_one_model(
        self,
        binary: str,
        inputs: tuple[str, ...],
        model: ModelSpec,
        *,
        inverse: bool,
    ) -> tuple[ModelSpec, dict[str, tuple[str, ...]]]:
        model_path = self.model_dir / model.filename
        command = [binary]
        if inverse:
            command.append("-i")
        command.append(str(model_path))

        payload = "\n".join(inputs) + "\n"
        try:
            completed = subprocess.run(
                command,
                input=payload,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="strict",
                check=False,
                timeout=self.timeout_seconds,
            )
        except subprocess.TimeoutExpired as error:
            raise BackendError(
                f"flookup timed out after {self.timeout_seconds:g}s for {model.filename}"
            ) from error
        except OSError as error:
            raise BackendError(f"could not execute flookup for {model.filename}: {error}") from error

        if completed.returncode != 0:
            detail = completed.stderr.strip() or "no diagnostic output"
            raise BackendError(
                f"flookup failed for {model.filename} with exit code "
                f"{completed.returncode}: {detail}"
            )

        return model, parse_flookup_pairs(completed.stdout)

    def lookup_models(
        self,
        inputs: Sequence[str],
        models: Sequence[ModelSpec],
        *,
        inverse: bool = False,
    ) -> LookupMap:
        normalized_inputs = tuple(dict.fromkeys(normalize_token(item) for item in inputs if item.strip()))
        if not normalized_inputs:
            return {}
        if any("\n" in item or "\r" in item for item in normalized_inputs):
            raise ValueError("lookup inputs must not contain line breaks")

        active_models = tuple(model for model in models if model.enabled)
        if not active_models:
            return {item: () for item in normalized_inputs}

        validate_model_files(self.model_dir, active_models)
        binary = self._resolve_binary()
        results: dict[str, list[LookupRecord]] = defaultdict(list)

        worker_count = min(self.workers, len(active_models))
        with ThreadPoolExecutor(max_workers=worker_count) as executor:
            futures = {
                model.filename: executor.submit(
                    self._lookup_one_model,
                    binary,
                    normalized_inputs,
                    model,
                    inverse=inverse,
                )
                for model in active_models
            }
            # Consume in manifest order so output is deterministic despite parallel execution.
            for model in active_models:
                _, pairs = futures[model.filename].result()
                for source, outputs in pairs.items():
                    for output in outputs:
                        record = (output, model.filename)
                        if record not in results[source]:
                            results[source].append(record)

        return {
            item: tuple(results.get(item, ()))
            for item in normalized_inputs
        }

    def health(self, models: Sequence[ModelSpec]) -> dict[str, object]:
        """Return diagnostics suitable for a service health endpoint."""

        binary: str | None
        error: str | None = None
        try:
            binary = self._resolve_binary()
            validate_model_files(self.model_dir, tuple(models))
        except ConfigurationError as caught:
            binary = None
            error = str(caught)
        return {
            "ready": error is None,
            "binary": binary,
            "model_dir": str(self.model_dir),
            "model_count": len(tuple(models)),
            "error": error,
        }
