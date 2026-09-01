from __future__ import annotations

from pathlib import Path

import pytest

from thamizhi_morph.backends.foma import FomaModel
from thamizhi_morph.backends.native import NativeFomaBackend, NativeFomaError


class FakeTransducer:
    def __init__(
        self,
        analyses: dict[str, tuple[str, ...]],
        generations: dict[str, tuple[str, ...]],
    ) -> None:
        self.analyses = analyses
        self.generations = generations
        self.calls: list[tuple[str, bool]] = []
        self.closed = False

    def apply(self, value: str, *, inverse: bool = False) -> tuple[str, ...]:
        self.calls.append((value, inverse))
        return (self.generations if inverse else self.analyses).get(value, ())

    def close(self) -> None:
        self.closed = True


class FakeLoader:
    version = "fake-1.0"
    library_path = "fake-libfoma"

    def __init__(self, transducers: dict[str, FakeTransducer]) -> None:
        self.transducers = transducers
        self.loaded: list[str] = []
        self.closed = False

    def load(self, path: Path) -> FakeTransducer:
        self.loaded.append(path.name)
        return self.transducers[path.name]

    def close(self) -> None:
        self.closed = True


def make_backend(tmp_path: Path) -> tuple[NativeFomaBackend, FakeLoader]:
    model_dir = tmp_path / "models"
    model_dir.mkdir()
    (model_dir / "noun.fst").touch()
    (model_dir / "noun-guess.fst").touch()
    loader = FakeLoader(
        {
            "noun.fst": FakeTransducer(
                {
                    "தமிழ்": ("தமிழ்+noun+nom",),
                    "மரங்கள்": ("மரம்+noun+pl=கள்+nom",),
                },
                {"மரம்+noun+nom": ("மரம்",)},
            ),
            "noun-guess.fst": FakeTransducer(
                {"புதுச்சொல்": ("புதுச்சொல்+noun+guess+nom",)},
                {},
            ),
        }
    )
    backend = NativeFomaBackend(
        model_dir,
        loader=loader,
        models=(
            FomaModel("noun", "noun.fst", "noun", priority=0),
            FomaModel(
                "noun-guesser",
                "noun-guess.fst",
                "noun",
                guesser=True,
                priority=10,
            ),
        ),
        max_workers=2,
    )
    return backend, loader


def test_native_backend_loads_lazily_and_reuses_transducers(tmp_path: Path) -> None:
    backend, loader = make_backend(tmp_path)

    first = backend.analyze_many(["தமிழ்", "மரங்கள்"])
    second = backend.analyze_many(["தமிழ்"])

    assert first["தமிழ்"][0].lemma == "தமிழ்"
    assert first["மரங்கள்"][0].morphemes[0].surface == "கள்"
    assert second["தமிழ்"][0].model == "noun"
    assert loader.loaded == ["noun.fst"]
    assert backend.health().details["loaded_models"] == 1
    backend.close()


def test_native_backend_keeps_guesser_stage_separate(tmp_path: Path) -> None:
    backend, _loader = make_backend(tmp_path)

    exact = backend.analyze_many(["புதுச்சொல்"])
    guessed = backend.analyze_many(["புதுச்சொல்"], guess=True)

    assert exact["புதுச்சொல்"] == ()
    assert guessed["புதுச்சொல்"][0].guessed
    assert guessed["புதுச்சொல்"][0].model == "noun-guesser"
    backend.close()


def test_native_backend_generates_inversely(tmp_path: Path) -> None:
    backend, _loader = make_backend(tmp_path)

    generated = backend.generate_many(["மரம்+noun+nom"], model="noun")

    assert generated == {"மரம்+noun+nom": ("மரம்",)}
    backend.close()


def test_native_backend_validates_input_models_and_lifecycle(tmp_path: Path) -> None:
    backend, loader = make_backend(tmp_path)

    with pytest.raises(ValueError, match="NUL"):
        backend.analyze_many(["தமிழ்\x00மரம்"])
    with pytest.raises(ValueError, match="unknown model"):
        backend.generate_many(["x"], model="missing")

    backend.close()
    assert loader.closed
    assert not backend.health().ready
    with pytest.raises(NativeFomaError, match="closed"):
        backend.analyze_many(["தமிழ்"])


def test_native_backend_rejects_malformed_lexical_output(tmp_path: Path) -> None:
    backend, loader = make_backend(tmp_path)
    loader.transducers["noun.fst"].analyses["பிழை"] = ("malformed",)

    with pytest.raises(NativeFomaError, match="invalid lexical analysis"):
        backend.analyze_many(["பிழை"])
    backend.close()
