from __future__ import annotations

from pathlib import Path

from thamizhimorph import Analyzer
from thamizhimorph.evaluation import evaluate_coverage, read_conllu_tokens, read_wordlist

from conftest import FakeBackend


def test_coverage_report_keeps_exact_and_guessed_separate(model_specs) -> None:
    exact, guessers = model_specs
    backend = FakeBackend(
        {
            ("noun.fst", "தமிழ்", False): ("தமிழ்+noun+nom",),
            ("noun-guess.fst", "புதுச்சொல்", False): ("புதுச்சொல்+noun+guess",),
        }
    )
    analyzer = Analyzer(backend=backend, exact_models=exact, guesser_models=guessers)

    report = evaluate_coverage(analyzer, ("தமிழ்", "புதுச்சொல்", "அறியாதது"), batch_size=3)
    assert report.exact == 1
    assert report.guessed == 1
    assert report.unknown == 1
    assert report.morphological_coverage == 2 / 3
    assert report.unknown_tokens == ("அறியாதது",)


def test_corpus_readers(tmp_path: Path) -> None:
    wordlist = tmp_path / "words.txt"
    wordlist.write_text("# comment\nதமிழ்\nமரம்\textra\n", encoding="utf-8")
    assert read_wordlist(wordlist) == ["தமிழ்", "மரம்"]

    conllu = tmp_path / "sample.conllu"
    conllu.write_text(
        "# text = தமிழ்\n1\tதமிழ்\t_\tNOUN\t_\t_\t0\troot\t_\t_\n"
        "1-2\tபலசொல்\t_\t_\t_\t_\t_\t_\t_\t_\n",
        encoding="utf-8",
    )
    assert read_conllu_tokens(conllu) == ["தமிழ்"]
