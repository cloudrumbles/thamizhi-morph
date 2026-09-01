from __future__ import annotations

from thamizhi_morph.engine import MorphologyEngine
from thamizhi_morph.evaluation import evaluate_words
from thamizhi_morph.models import BackendHealth, MorphAnalysis


class CoverageBackend:
    name = "coverage"

    def analyze_many(
        self,
        words: list[str] | tuple[str, ...],
        *,
        guess: bool = False,
    ) -> dict[str, tuple[MorphAnalysis, ...]]:
        output: dict[str, tuple[MorphAnalysis, ...]] = {}
        for word in words:
            if word == "known" and not guess:
                output[word] = (MorphAnalysis(word, word, "noun", model="noun"),)
            elif word == "guessed" and guess:
                output[word] = (
                    MorphAnalysis(word, word, "noun", model="noun-guesser", guessed=True),
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
        return {item: () for item in lexical_forms}

    def health(self) -> BackendHealth:
        return BackendHealth(self.name, True, {})


def test_coverage_report_separates_known_guessed_and_unknown() -> None:
    # Latin words are classified as foreign, so use Tamil-shaped test keys.
    backend = CoverageBackend()
    original = backend.analyze_many

    def tamil_backend(
        words: list[str] | tuple[str, ...],
        *,
        guess: bool = False,
    ) -> dict[str, tuple[MorphAnalysis, ...]]:
        translation = {"அறிந்தது": "known", "ஊகம்": "guessed", "அறியாது": "unknown"}
        reverse = {value: key for key, value in translation.items()}
        result = original([translation[word] for word in words], guess=guess)
        return {reverse[key]: value for key, value in result.items()}

    backend.analyze_many = tamil_backend  # type: ignore[method-assign]
    report = evaluate_words(
        MorphologyEngine(backend),
        ["அறிந்தது", "ஊகம்", "அறியாது"],
    )

    assert report.total == 3
    assert report.known == 1
    assert report.guessed == 1
    assert report.unknown == 1
    assert report.recoverable_coverage == 2 / 3
    assert report.unknown_words == ("அறியாது",)
