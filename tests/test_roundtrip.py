from __future__ import annotations

import pytest

from thamizhi_morph.engine import MorphologyEngine
from thamizhi_morph.models import BackendHealth, MorphAnalysis
from thamizhi_morph.roundtrip import validate_round_trips


class RoundTripBackend:
    name = "roundtrip"

    def analyze_many(
        self,
        words: list[str] | tuple[str, ...],
        *,
        guess: bool = False,
    ) -> dict[str, tuple[MorphAnalysis, ...]]:
        output: dict[str, tuple[MorphAnalysis, ...]] = {}
        for word in words:
            if word == "மரங்கள்" and not guess:
                output[word] = (
                    MorphAnalysis(
                        word,
                        "மரம்",
                        "noun",
                        model="noun",
                        raw="மரம்+noun+pl+nom",
                    ),
                )
            elif word == "பிழை" and not guess:
                output[word] = (
                    MorphAnalysis(
                        word,
                        "பிழை",
                        "noun",
                        model="noun",
                        raw="பிழை+noun+nom",
                    ),
                )
            elif word == "புதுச்சொல்" and guess:
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
        assert model is not None
        return {
            lexical: {
                "மரம்+noun+pl+nom": ("மரங்கள்",),
                "பிழை+noun+nom": ("வேறுசொல்",),
                "புதுச்சொல்+noun+guess+nom": ("புதுச்சொல்",),
            }.get(lexical, ())
            for lexical in lexical_forms
        }

    def health(self) -> BackendHealth:
        return BackendHealth(self.name, True, {})


def test_roundtrip_report_finds_model_level_failures() -> None:
    report = validate_round_trips(
        MorphologyEngine(RoundTripBackend()),
        ["மரங்கள்", "பிழை", "unknown"],
    )

    assert report.checked_analyses == 2
    assert report.passed == 1
    assert report.failed == 1
    assert report.pass_rate == 0.5
    assert report.by_model["noun"].failed == 1
    assert report.failures[0].surface == "பிழை"
    assert report.failures[0].generated == ("வேறுசொல்",)


def test_roundtrip_can_include_guesser_models() -> None:
    report = validate_round_trips(
        MorphologyEngine(RoundTripBackend()),
        ["புதுச்சொல்"],
        include_guessers=True,
    )

    assert report.checked_analyses == 1
    assert report.passed == 1
    assert report.by_model["noun-guesser"].pass_rate == 1.0


def test_roundtrip_validates_failure_limit() -> None:
    with pytest.raises(ValueError, match="negative"):
        validate_round_trips(
            MorphologyEngine(RoundTripBackend()),
            ["மரங்கள்"],
            max_failures=-1,
        )
