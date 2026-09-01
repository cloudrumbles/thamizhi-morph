from __future__ import annotations

from pathlib import Path

from thamizhi_morph.backends.overlay import OverlayBackend
from thamizhi_morph.models import BackendHealth, MorphAnalysis
from thamizhi_morph.overlay import OverlayStore


class BaseBackend:
    name = "base"

    def analyze_many(
        self,
        words: list[str] | tuple[str, ...],
        *,
        guess: bool = False,
    ) -> dict[str, tuple[MorphAnalysis, ...]]:
        output: dict[str, tuple[MorphAnalysis, ...]] = {}
        for word in words:
            if not guess and word in {"மரம்", "திருத்தம்"}:
                output[word] = (
                    MorphAnalysis(word, word, "noun", model="noun", raw=f"{word}+noun+nom"),
                )
            elif guess:
                output[word] = (
                    MorphAnalysis(
                        word,
                        word,
                        "noun",
                        model="noun-guesser",
                        raw=f"{word}+noun+guess+nom",
                        guessed=True,
                    ),
                )
            else:
                output[word] = ()
        return output

    def generate_many(
        self,
        lexical_forms: list[str] | tuple[str, ...],
        *,
        model: str | None = None,
    ) -> dict[str, tuple[str, ...]]:
        del model
        return {value: (value,) for value in lexical_forms}

    def health(self) -> BackendHealth:
        return BackendHealth(self.name, True, {"base": True})


def make_backend(tmp_path: Path) -> OverlayBackend:
    store = OverlayStore(tmp_path / "overlay.db", writable=True)
    store.add("மரம்", "மரம்", "noun", mode="augment", source="curated")
    store.add("திருத்தம்", "திருத்து", "verb", mode="replace", source="correction")
    store.add("சிங்கப்பூர்ல", "சிங்கப்பூர்", "noun", mode="fallback", source="sg")
    return OverlayBackend(BaseBackend(), store)


def test_augment_keeps_fst_and_deduplicates_equivalent_overlay(tmp_path: Path) -> None:
    backend = make_backend(tmp_path)

    result = backend.analyze_many(["மரம்"])["மரம்"]

    assert len(result) == 1
    assert result[0].model == "noun"
    backend.close()


def test_replace_suppresses_fst_output(tmp_path: Path) -> None:
    backend = make_backend(tmp_path)

    result = backend.analyze_many(["திருத்தம்"])["திருத்தம்"]

    assert len(result) == 1
    assert result[0].lemma == "திருத்து"
    assert result[0].pos == "verb"
    assert result[0].model.startswith("overlay:replace:")
    backend.close()


def test_fallback_appears_with_and_outranks_guesser(tmp_path: Path) -> None:
    backend = make_backend(tmp_path)

    exact = backend.analyze_many(["சிங்கப்பூர்ல"], guess=False)["சிங்கப்பூர்ல"]
    guessed = backend.analyze_many(["சிங்கப்பூர்ல"], guess=True)["சிங்கப்பூர்ல"]

    assert exact == ()
    assert len(guessed) == 2
    assert guessed[0].model.startswith("overlay:fallback:")
    assert guessed[1].guessed
    backend.close()


def test_overlay_health_and_generation_delegation(tmp_path: Path) -> None:
    backend = make_backend(tmp_path)

    health = backend.health()

    assert health.ready
    assert health.name == "base+overlay"
    assert health.details["overlay"]["entries"] == 3
    assert backend.generate_many(["x"], model="noun") == {"x": ("x",)}
    assert backend.generate_many(["x"], model="overlay:fallback:sg") == {"x": ()}
    backend.close()
