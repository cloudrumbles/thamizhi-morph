from __future__ import annotations

import logging
import os
import shutil
import subprocess
from collections import defaultdict
from collections.abc import Iterable, Sequence
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path

from ..models import BackendHealth, MorphAnalysis
from ..parser import parse_generation_output, parse_lookup_output
from .base import BackendError

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class FomaModel:
    name: str
    filename: str
    pos: str
    guesser: bool = False
    priority: int = 100


DEFAULT_MODELS: tuple[FomaModel, ...] = (
    FomaModel("pronoun", "pronoun.fst", "pronoun", priority=0),
    FomaModel("noun", "noun.fst", "noun", priority=10),
    FomaModel("verb-c3", "verb-c3.fst", "verb", priority=20),
    FomaModel("verb-c4", "verb-c4.fst", "verb", priority=21),
    FomaModel("verb-c62", "verb-c62.fst", "verb", priority=22),
    FomaModel("verb-c11", "verb-c11.fst", "verb", priority=23),
    FomaModel("verb-c12", "verb-c12.fst", "verb", priority=24),
    FomaModel("verb-rest", "verb-c-rest.fst", "verb", priority=25),
    FomaModel("adjective", "adj.fst", "adjective", priority=30),
    FomaModel("adverb", "adv.fst", "adverb", priority=31),
    FomaModel("particle", "part.fst", "particle", priority=40),
    FomaModel("noun-guesser", "noun-guess.fst", "noun", guesser=True, priority=110),
    FomaModel("verb-guesser", "verb-guess.fst", "verb", guesser=True, priority=120),
    FomaModel("adjective-guesser", "adj-guess.fst", "adjective", guesser=True, priority=130),
    FomaModel("adverb-guesser", "adv-guess.fst", "adverb", guesser=True, priority=131),
)


class FomaExecutionError(BackendError):
    pass


class FomaBackend:
    """Fast batch bridge to the existing binary Foma transducers.

    One flookup process is started per model and batch, rather than per token. Models are
    independent, so lookups may run concurrently while results remain deterministically ordered.
    """

    name = "foma"

    def __init__(
        self,
        model_dir: str | Path | None = None,
        *,
        flookup: str | Path | None = None,
        models: Sequence[FomaModel] = DEFAULT_MODELS,
        timeout: float = 30.0,
        max_workers: int = 4,
        strict_output: bool = False,
    ) -> None:
        self.model_dir = self._resolve_model_dir(model_dir)
        self.flookup = str(flookup or os.environ.get("THAMIZHI_FLOOKUP") or "flookup")
        self.models = tuple(sorted(models, key=lambda item: (item.priority, item.name)))
        self.timeout = timeout
        self.max_workers = max(1, max_workers)
        self.strict_output = strict_output
        self._by_name = {model.name: model for model in self.models}

    @staticmethod
    def _resolve_model_dir(model_dir: str | Path | None) -> Path:
        if model_dir is not None:
            return Path(model_dir).expanduser().resolve()
        configured = os.environ.get("THAMIZHI_MODELS")
        candidates = [
            Path(configured).expanduser() if configured else None,
            Path.cwd() / "FST-Models",
            Path(__file__).resolve().parents[3] / "FST-Models",
        ]
        for candidate in candidates:
            if candidate is not None and candidate.is_dir():
                return candidate.resolve()
        return (Path.cwd() / "FST-Models").resolve()

    @staticmethod
    def _unique(values: Iterable[str]) -> tuple[str, ...]:
        return tuple(dict.fromkeys(values))

    @staticmethod
    def _validate_inputs(values: Sequence[str]) -> tuple[str, ...]:
        unique = FomaBackend._unique(values)
        for value in unique:
            if not value:
                raise ValueError("lookup inputs must not be empty")
            if "\n" in value or "\r" in value or "\x00" in value:
                raise ValueError("lookup inputs must not contain newlines or NUL bytes")
        return unique

    def _executable(self) -> str | None:
        candidate = Path(self.flookup)
        if candidate.parent != Path(".") or candidate.is_absolute():
            return str(candidate) if candidate.is_file() else None
        return shutil.which(self.flookup)

    def _model_path(self, model: FomaModel) -> Path:
        return self.model_dir / model.filename

    def _select_models(self, *, guess: bool, model: str | None = None) -> tuple[FomaModel, ...]:
        if model is not None:
            try:
                selected = self._by_name[model]
            except KeyError as error:
                available = ", ".join(sorted(self._by_name))
                raise ValueError(f"unknown model {model!r}; available: {available}") from error
            return (selected,)
        return tuple(item for item in self.models if item.guesser is guess)

    def _run(self, model: FomaModel, values: tuple[str, ...], *, inverse: bool) -> str:
        executable = self._executable()
        if executable is None:
            raise FomaExecutionError(
                f"could not find {self.flookup!r}; install foma-bin or set THAMIZHI_FLOOKUP"
            )
        model_path = self._model_path(model)
        if not model_path.is_file():
            raise FomaExecutionError(f"missing FST model: {model_path}")

        command = [executable]
        if inverse:
            command.append("-i")
        command.append(str(model_path))
        environment = os.environ.copy()
        environment.setdefault("LC_ALL", "C.UTF-8")
        try:
            completed = subprocess.run(
                command,
                input="\n".join(values) + "\n",
                text=True,
                encoding="utf-8",
                errors="strict",
                capture_output=True,
                check=False,
                timeout=self.timeout,
                env=environment,
            )
        except subprocess.TimeoutExpired as error:
            raise FomaExecutionError(
                f"flookup timed out after {self.timeout:g}s for model {model.name}"
            ) from error
        except OSError as error:
            raise FomaExecutionError(f"failed to start flookup: {error}") from error

        if completed.returncode != 0:
            message = completed.stderr.strip() or "no error output"
            raise FomaExecutionError(
                f"flookup failed for {model.name} with exit code {completed.returncode}: {message}"
            )
        return completed.stdout

    def _run_analyses(
        self,
        model: FomaModel,
        values: tuple[str, ...],
    ) -> dict[str, tuple[MorphAnalysis, ...]]:
        parsed = parse_lookup_output(
            self._run(model, values, inverse=False),
            model=model.name,
            guessed=model.guesser,
        )
        if parsed.diagnostics:
            message = "; ".join(parsed.diagnostics)
            if self.strict_output:
                raise FomaExecutionError(f"malformed output from {model.name}: {message}")
            LOGGER.warning("malformed output from %s: %s", model.name, message)
        return parsed.analyses

    def analyze_many(
        self,
        words: Sequence[str],
        *,
        guess: bool = False,
    ) -> dict[str, tuple[MorphAnalysis, ...]]:
        values = self._validate_inputs(words)
        if not values:
            return {}
        models = self._select_models(guess=guess)
        merged: dict[str, list[MorphAnalysis]] = {word: [] for word in values}
        seen: dict[str, set[tuple[object, ...]]] = defaultdict(set)

        workers = min(self.max_workers, len(models))
        with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="thamizhi-foma") as pool:
            futures = {pool.submit(self._run_analyses, model, values): model for model in models}
            completed_by_model: dict[str, dict[str, tuple[MorphAnalysis, ...]]] = {}
            for future in as_completed(futures):
                model = futures[future]
                completed_by_model[model.name] = future.result()

        for model in models:
            for word, analyses in completed_by_model[model.name].items():
                for analysis in analyses:
                    signature: tuple[object, ...] = analysis.signature
                    if signature not in seen[word]:
                        seen[word].add(signature)
                        merged[word].append(analysis)
        return {word: tuple(merged[word]) for word in values}

    def _run_generation(
        self, model: FomaModel, values: tuple[str, ...]
    ) -> dict[str, tuple[str, ...]]:
        parsed = parse_generation_output(self._run(model, values, inverse=True))
        if parsed.diagnostics:
            message = "; ".join(parsed.diagnostics)
            if self.strict_output:
                raise FomaExecutionError(f"malformed output from {model.name}: {message}")
            LOGGER.warning("malformed generation output from %s: %s", model.name, message)
        return parsed.forms

    def generate_many(
        self,
        lexical_forms: Sequence[str],
        *,
        model: str | None = None,
    ) -> dict[str, tuple[str, ...]]:
        values = self._validate_inputs(lexical_forms)
        if not values:
            return {}
        models = self._select_models(guess=False, model=model)
        merged: dict[str, list[str]] = {value: [] for value in values}
        seen: dict[str, set[str]] = defaultdict(set)

        workers = min(self.max_workers, len(models))
        with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="thamizhi-foma") as pool:
            futures = {pool.submit(self._run_generation, item, values): item for item in models}
            completed_by_model: dict[str, dict[str, tuple[str, ...]]] = {}
            for future in as_completed(futures):
                item = futures[future]
                completed_by_model[item.name] = future.result()

        for item in models:
            for lexical, forms in completed_by_model[item.name].items():
                for form in forms:
                    if form not in seen[lexical]:
                        seen[lexical].add(form)
                        merged[lexical].append(form)
        return {value: tuple(merged[value]) for value in values}

    def health(self) -> BackendHealth:
        executable = self._executable()
        missing = [item.filename for item in self.models if not self._model_path(item).is_file()]
        return BackendHealth(
            name=self.name,
            ready=executable is not None and not missing,
            details={
                "flookup": executable,
                "model_dir": str(self.model_dir),
                "models": len(self.models),
                "missing_models": missing,
                "batch_workers": self.max_workers,
            },
        )
