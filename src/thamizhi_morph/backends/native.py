from __future__ import annotations

import ctypes
import ctypes.util
import os
import threading
from collections import defaultdict
from collections.abc import Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from ..models import BackendHealth, MorphAnalysis, Morpheme
from .base import BackendError
from .foma import DEFAULT_MODELS, FomaModel


class NativeFomaUnavailable(BackendError):
    pass


class NativeFomaError(BackendError):
    pass


class NativeTransducer(Protocol):
    def apply(self, value: str, *, inverse: bool = False) -> tuple[str, ...]: ...

    def close(self) -> None: ...


class NativeLoader(Protocol):
    @property
    def version(self) -> str: ...

    @property
    def library_path(self) -> str: ...

    def load(self, path: Path) -> NativeTransducer: ...

    def close(self) -> None: ...


class _CtypesTransducer:
    def __init__(
        self,
        library: Any,
        network: Any,
        *,
        max_results: int,
    ) -> None:
        self._library = library
        self._network = network
        self._max_results = max_results
        self._up_handle = library.apply_init(network)
        self._down_handle = library.apply_init(network)
        if not self._up_handle or not self._down_handle:
            if self._up_handle:
                library.apply_handle_destroy(self._up_handle)
            if self._down_handle:
                library.apply_handle_destroy(self._down_handle)
            library.fsm_destroy(network)
            raise NativeFomaError("libfoma could not allocate an apply handle")
        self._up_lock = threading.Lock()
        self._down_lock = threading.Lock()
        self._closed = False

    @staticmethod
    def _decode(value: Any) -> str:
        if isinstance(value, bytes):
            return value.decode("utf-8", errors="strict")
        return ctypes.string_at(value).decode("utf-8", errors="strict")

    def apply(self, value: str, *, inverse: bool = False) -> tuple[str, ...]:
        if self._closed:
            raise NativeFomaError("native transducer is closed")
        if "\x00" in value:
            raise ValueError("native lookup inputs must not contain NUL bytes")
        function = self._library.apply_down if inverse else self._library.apply_up
        handle = self._down_handle if inverse else self._up_handle
        lock = self._down_lock if inverse else self._up_lock
        output: list[str] = []
        with lock:
            result = function(handle, value.encode("utf-8"))
            while result:
                output.append(self._decode(result))
                if len(output) >= self._max_results:
                    raise NativeFomaError(
                        f"libfoma exceeded the per-input result limit ({self._max_results})"
                    )
                result = function(handle, None)
        return tuple(output)

    def close(self) -> None:
        if self._closed:
            return
        with self._up_lock, self._down_lock:
            self._library.apply_handle_destroy(self._up_handle)
            self._library.apply_handle_destroy(self._down_handle)
            self._library.fsm_destroy(self._network)
            self._closed = True


class CtypesFomaLoader:
    """Small ctypes binding for the stable apply API exposed by libfoma."""

    def __init__(
        self,
        library_path: str | Path | None = None,
        *,
        max_results: int = 10_000,
    ) -> None:
        candidate = (
            str(library_path)
            if library_path is not None
            else os.environ.get("THAMIZHI_LIBFOMA") or ctypes.util.find_library("foma")
        )
        if not candidate:
            raise NativeFomaUnavailable(
                "libfoma was not found; install the Foma runtime or use --backend subprocess"
            )
        try:
            library = ctypes.CDLL(candidate)
        except OSError as error:
            raise NativeFomaUnavailable(f"could not load libfoma from {candidate!r}: {error}") from error
        self._library = library
        self._library_path = candidate
        self._max_results = max(1, max_results)
        self._closed = False
        self._bind()

    def _bind(self) -> None:
        required = (
            "fsm_read_binary_file",
            "fsm_destroy",
            "apply_init",
            "apply_up",
            "apply_down",
            "apply_handle_destroy",
            "fsm_get_library_version_string",
        )
        missing = [name for name in required if not hasattr(self._library, name)]
        if missing:
            raise NativeFomaUnavailable(
                "libfoma is missing required symbols: " + ", ".join(missing)
            )

        self._library.fsm_read_binary_file.argtypes = [ctypes.c_char_p]
        self._library.fsm_read_binary_file.restype = ctypes.c_void_p
        self._library.fsm_destroy.argtypes = [ctypes.c_void_p]
        self._library.fsm_destroy.restype = None
        self._library.apply_init.argtypes = [ctypes.c_void_p]
        self._library.apply_init.restype = ctypes.c_void_p
        self._library.apply_up.argtypes = [ctypes.c_void_p, ctypes.c_char_p]
        self._library.apply_up.restype = ctypes.c_char_p
        self._library.apply_down.argtypes = [ctypes.c_void_p, ctypes.c_char_p]
        self._library.apply_down.restype = ctypes.c_char_p
        self._library.apply_handle_destroy.argtypes = [ctypes.c_void_p]
        self._library.apply_handle_destroy.restype = None
        self._library.fsm_get_library_version_string.argtypes = []
        self._library.fsm_get_library_version_string.restype = ctypes.c_char_p

    @property
    def version(self) -> str:
        raw = self._library.fsm_get_library_version_string()
        return raw.decode("utf-8") if raw else "unknown"

    @property
    def library_path(self) -> str:
        return self._library_path

    def load(self, path: Path) -> NativeTransducer:
        if self._closed:
            raise NativeFomaError("libfoma loader is closed")
        network = self._library.fsm_read_binary_file(os.fsencode(path))
        if not network:
            raise NativeFomaError(f"libfoma could not load FST model: {path}")
        return _CtypesTransducer(
            self._library,
            network,
            max_results=self._max_results,
        )

    def close(self) -> None:
        self._closed = True


@dataclass(frozen=True, slots=True)
class _ModelResult:
    model: FomaModel
    analyses: Mapping[str, tuple[MorphAnalysis, ...]]


class NativeFomaBackend:
    """Persistent libfoma runtime with one loaded transducer per model."""

    name = "foma-native"

    def __init__(
        self,
        model_dir: str | Path | None = None,
        *,
        library_path: str | Path | None = None,
        loader: NativeLoader | None = None,
        models: Sequence[FomaModel] = DEFAULT_MODELS,
        max_workers: int = 4,
        max_results: int = 10_000,
    ) -> None:
        self.model_dir = self._resolve_model_dir(model_dir)
        self.models = tuple(sorted(models, key=lambda item: (item.priority, item.name)))
        self.max_workers = max(1, max_workers)
        self.loader = loader or CtypesFomaLoader(
            library_path,
            max_results=max_results,
        )
        self._by_name = {model.name: model for model in self.models}
        self._transducers: dict[str, NativeTransducer] = {}
        self._load_lock = threading.RLock()
        self._closed = False

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
    def _validate_inputs(values: Sequence[str]) -> tuple[str, ...]:
        unique = tuple(dict.fromkeys(values))
        for value in unique:
            if not value:
                raise ValueError("lookup inputs must not be empty")
            if "\x00" in value:
                raise ValueError("lookup inputs must not contain NUL bytes")
        return unique

    def _model_path(self, model: FomaModel) -> Path:
        return self.model_dir / model.filename

    def _select_models(
        self,
        *,
        guess: bool,
        model: str | None = None,
    ) -> tuple[FomaModel, ...]:
        if model is not None:
            try:
                return (self._by_name[model],)
            except KeyError as error:
                available = ", ".join(sorted(self._by_name))
                raise ValueError(f"unknown model {model!r}; available: {available}") from error
        return tuple(item for item in self.models if item.guesser is guess)

    def _transducer(self, model: FomaModel) -> NativeTransducer:
        if self._closed:
            raise NativeFomaError("native backend is closed")
        with self._load_lock:
            transducer = self._transducers.get(model.name)
            if transducer is None:
                path = self._model_path(model)
                if not path.is_file():
                    raise NativeFomaError(f"missing FST model: {path}")
                transducer = self.loader.load(path)
                self._transducers[model.name] = transducer
            return transducer

    @staticmethod
    def _analysis(
        surface: str,
        lexical: str,
        model: FomaModel,
    ) -> MorphAnalysis:
        parts = lexical.split("+")
        if len(parts) < 2 or not parts[0] or not parts[1]:
            raise NativeFomaError(
                f"invalid lexical analysis from {model.name}: {lexical!r}"
            )
        return MorphAnalysis(
            surface=surface,
            lemma=parts[0],
            pos=parts[1].strip().lower(),
            morphemes=tuple(Morpheme.parse(part) for part in parts[2:] if part),
            model=model.name,
            guessed=model.guesser,
            raw=lexical,
        )

    def _analyze_model(
        self,
        model: FomaModel,
        values: tuple[str, ...],
    ) -> _ModelResult:
        transducer = self._transducer(model)
        output: dict[str, tuple[MorphAnalysis, ...]] = {}
        for value in values:
            seen: set[tuple[object, ...]] = set()
            analyses: list[MorphAnalysis] = []
            for lexical in transducer.apply(value):
                analysis = self._analysis(value, lexical, model)
                signature: tuple[object, ...] = analysis.signature
                if signature not in seen:
                    seen.add(signature)
                    analyses.append(analysis)
            output[value] = tuple(analyses)
        return _ModelResult(model, output)

    def analyze_many(
        self,
        words: Sequence[str],
        *,
        guess: bool = False,
    ) -> Mapping[str, tuple[MorphAnalysis, ...]]:
        values = self._validate_inputs(words)
        if not values:
            return {}
        models = self._select_models(guess=guess)
        completed: dict[str, Mapping[str, tuple[MorphAnalysis, ...]]] = {}
        workers = min(self.max_workers, len(models))
        with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="thamizhi-native") as pool:
            futures = {
                pool.submit(self._analyze_model, model, values): model
                for model in models
            }
            for future in as_completed(futures):
                result = future.result()
                completed[result.model.name] = result.analyses

        merged: dict[str, list[MorphAnalysis]] = {value: [] for value in values}
        seen: dict[str, set[tuple[object, ...]]] = defaultdict(set)
        for model in models:
            for value, analyses in completed[model.name].items():
                for analysis in analyses:
                    signature: tuple[object, ...] = analysis.signature
                    if signature not in seen[value]:
                        seen[value].add(signature)
                        merged[value].append(analysis)
        return {value: tuple(merged[value]) for value in values}

    def _generate_model(
        self,
        model: FomaModel,
        values: tuple[str, ...],
    ) -> tuple[FomaModel, Mapping[str, tuple[str, ...]]]:
        transducer = self._transducer(model)
        return model, {
            value: tuple(dict.fromkeys(transducer.apply(value, inverse=True)))
            for value in values
        }

    def generate_many(
        self,
        lexical_forms: Sequence[str],
        *,
        model: str | None = None,
    ) -> Mapping[str, tuple[str, ...]]:
        values = self._validate_inputs(lexical_forms)
        if not values:
            return {}
        models = self._select_models(guess=False, model=model)
        completed: dict[str, Mapping[str, tuple[str, ...]]] = {}
        workers = min(self.max_workers, len(models))
        with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="thamizhi-native") as pool:
            futures = {
                pool.submit(self._generate_model, item, values): item
                for item in models
            }
            for future in as_completed(futures):
                item, generated = future.result()
                completed[item.name] = generated

        merged: dict[str, list[str]] = {value: [] for value in values}
        seen: dict[str, set[str]] = defaultdict(set)
        for item in models:
            for value, forms in completed[item.name].items():
                for form in forms:
                    if form not in seen[value]:
                        seen[value].add(form)
                        merged[value].append(form)
        return {value: tuple(merged[value]) for value in values}

    def health(self) -> BackendHealth:
        missing = [
            model.filename for model in self.models if not self._model_path(model).is_file()
        ]
        return BackendHealth(
            name=self.name,
            ready=not self._closed and not missing,
            details={
                "library": self.loader.library_path,
                "library_version": self.loader.version,
                "model_dir": str(self.model_dir),
                "models": len(self.models),
                "loaded_models": len(self._transducers),
                "missing_models": missing,
                "batch_workers": self.max_workers,
                "persistent": True,
            },
        )

    def close(self) -> None:
        if self._closed:
            return
        with self._load_lock:
            for transducer in self._transducers.values():
                transducer.close()
            self._transducers.clear()
            self.loader.close()
            self._closed = True
