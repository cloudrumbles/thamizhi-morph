from __future__ import annotations

from io import StringIO

from thamizhi_morph.engine import MorphologyEngine
from thamizhi_morph.gold import evaluate_conllu, parse_conllu
from thamizhi_morph.models import BackendHealth, MorphAnalysis


class GoldBackend:
    name = "gold"

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
                    MorphAnalysis(word, "மர", "noun", model="noun"),
                    MorphAnalysis(word, "மரம்", "noun", model="noun"),
                )
            elif word == "வரும்" and guess:
                output[word] = (
                    MorphAnalysis(
                        word,
                        "வா",
                        "verb",
                        model="verb-guesser",
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
        return {item: () for item in lexical_forms}

    def health(self) -> BackendHealth:
        return BackendHealth(self.name, True, {})


def test_parse_conllu_ignores_comments_and_multiword_nodes() -> None:
    corpus = parse_conllu(
        StringIO(
            "# text = மரங்கள் வரும்.\n"
            "1-2\tமரங்கள் வரும்\t_\t_\t_\t_\t_\t_\t_\t_\n"
            "1\tமரங்கள்\tமரம்\tNOUN\t_\tNumber=Plur\t_\t_\t_\t_\n"
            "2\tவரும்\tவா\tVERB\t_\tTense=Fut\t_\t_\t_\t_\n"
            "3\t.\t.\tPUNCT\t_\t_\t_\t_\t_\t_\n\n"
            "malformed\n"
        )
    )

    assert corpus.sentences == 1
    assert len(corpus.tokens) == 3
    assert corpus.skipped_lines == 1
    assert corpus.tokens[0].form == "மரங்கள்"


def test_gold_evaluation_keeps_coverage_separate_from_accuracy() -> None:
    corpus = parse_conllu(
        StringIO(
            "1\tமரங்கள்\tமரம்\tNOUN\t_\tNumber=Plur\t_\t_\t_\t_\n"
            "2\tவரும்\tவா\tVERB\t_\tTense=Fut\t_\t_\t_\t_\n"
            "3\tஅறியாது\tஅறி\tVERB\t_\t_\t_\t_\t_\t_\n"
            "4\t.\t.\tPUNCT\t_\t_\t_\t_\t_\t_\n"
        )
    )

    report = evaluate_conllu(MorphologyEngine(GoldBackend()), corpus)
    serialised = report.to_dict()

    assert report.evaluated_tamil_tokens == 3
    assert report.exact_coverage == 1
    assert report.guesser_coverage == 1
    assert report.unknown == 1
    assert report.ambiguous == 1
    assert report.lemma_top1_correct == 1
    assert report.lemma_oracle_correct == 2
    assert report.pos_top1_correct == 2
    assert report.pos_oracle_correct == 2
    assert serialised["coverage"]["recoverable_rate"] == 2 / 3
    assert report.unknown_words == ("அறியாது",)
