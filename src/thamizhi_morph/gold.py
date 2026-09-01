from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .conllu import upos_for_analysis
from .engine import MorphologyEngine
from .models import TokenAnalysis, TokenKind
from .normalization import normalize_text


@dataclass(frozen=True, slots=True)
class GoldToken:
    sentence: int
    token_id: int
    form: str
    lemma: str
    upos: str
    feats: str = "_"


@dataclass(frozen=True, slots=True)
class GoldCorpus:
    tokens: tuple[GoldToken, ...]
    sentences: int
    skipped_lines: int = 0


@dataclass(frozen=True, slots=True)
class GoldEvaluationReport:
    corpus_tokens: int
    evaluated_tamil_tokens: int
    exact_coverage: int
    guesser_coverage: int
    dictionary_only: int
    unknown: int
    ambiguous: int
    candidate_count: int
    lemma_total: int
    lemma_top1_correct: int
    lemma_oracle_correct: int
    pos_total: int
    pos_top1_correct: int
    pos_oracle_correct: int
    by_upos: dict[str, dict[str, int]]
    unknown_words: tuple[str, ...]

    @staticmethod
    def _ratio(numerator: int, denominator: int) -> float:
        return numerator / denominator if denominator else 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "corpus_tokens": self.corpus_tokens,
            "evaluated_tamil_tokens": self.evaluated_tamil_tokens,
            "coverage": {
                "exact": self.exact_coverage,
                "guesser": self.guesser_coverage,
                "dictionary_only": self.dictionary_only,
                "unknown": self.unknown,
                "exact_rate": round(
                    self._ratio(self.exact_coverage, self.evaluated_tamil_tokens), 6
                ),
                "recoverable_rate": round(
                    self._ratio(
                        self.exact_coverage + self.guesser_coverage,
                        self.evaluated_tamil_tokens,
                    ),
                    6,
                ),
            },
            "ambiguity": {
                "ambiguous_tokens": self.ambiguous,
                "ambiguous_rate": round(
                    self._ratio(self.ambiguous, self.evaluated_tamil_tokens), 6
                ),
                "mean_candidates": round(
                    self._ratio(self.candidate_count, self.evaluated_tamil_tokens), 4
                ),
            },
            "lemma": {
                "total": self.lemma_total,
                "top1_correct": self.lemma_top1_correct,
                "oracle_correct": self.lemma_oracle_correct,
                "top1_accuracy": round(
                    self._ratio(self.lemma_top1_correct, self.lemma_total), 6
                ),
                "oracle_recall": round(
                    self._ratio(self.lemma_oracle_correct, self.lemma_total), 6
                ),
            },
            "upos": {
                "total": self.pos_total,
                "top1_correct": self.pos_top1_correct,
                "oracle_correct": self.pos_oracle_correct,
                "top1_accuracy": round(
                    self._ratio(self.pos_top1_correct, self.pos_total), 6
                ),
                "oracle_recall": round(
                    self._ratio(self.pos_oracle_correct, self.pos_total), 6
                ),
            },
            "by_upos": self.by_upos,
            "unknown_words": list(self.unknown_words),
        }


def parse_conllu(lines: Iterable[str]) -> GoldCorpus:
    """Read ordinary CoNLL-U while ignoring comments and multiword/empty nodes."""

    tokens: list[GoldToken] = []
    sentence = 1
    saw_token = False
    skipped = 0

    for raw_line in lines:
        line = raw_line.rstrip("\r\n")
        if not line:
            if saw_token:
                sentence += 1
                saw_token = False
            continue
        if line.startswith("#"):
            continue
        fields = line.split("\t")
        if len(fields) < 6:
            skipped += 1
            continue
        token_id = fields[0]
        if not token_id.isdigit():
            continue
        saw_token = True
        tokens.append(
            GoldToken(
                sentence=sentence,
                token_id=int(token_id),
                form=fields[1],
                lemma=fields[2],
                upos=fields[3],
                feats=fields[5],
            )
        )

    sentence_count = sentence if tokens else 0
    if tokens and not saw_token:
        sentence_count -= 1
    return GoldCorpus(tuple(tokens), sentence_count, skipped)


def read_conllu(path: str | Path) -> GoldCorpus:
    with Path(path).open(encoding="utf-8") as source:
        return parse_conllu(source)


def _chunks(values: Sequence[GoldToken], size: int) -> Iterable[Sequence[GoldToken]]:
    for start in range(0, len(values), size):
        yield values[start : start + size]


def _coverage_class(token: TokenAnalysis) -> str:
    if not token.analyses:
        return "unknown"
    if all(item.model == "dictionary-fallback" for item in token.analyses):
        return "dictionary_only"
    if all(item.guessed for item in token.analyses):
        return "guesser"
    return "exact"


def evaluate_conllu(
    engine: MorphologyEngine,
    corpus: GoldCorpus,
    *,
    use_guessers: bool = True,
    enrich_dictionary: bool = False,
    batch_size: int = 20_000,
    max_unknown_words: int = 100,
) -> GoldEvaluationReport:
    """Measure coverage separately from top-1 accuracy and oracle candidate recall."""

    if batch_size < 1:
        raise ValueError("batch_size must be positive")

    gold_tokens = tuple(
        token
        for token in corpus.tokens
        if engine.analyze_words([token.form], use_guessers=False)[0].kind
        is TokenKind.TAMIL
    )
    results: list[TokenAnalysis] = []
    for chunk in _chunks(gold_tokens, batch_size):
        results.extend(
            engine.analyze_words(
                [token.form for token in chunk],
                use_guessers=use_guessers,
                enrich_dictionary=enrich_dictionary,
            )
        )

    coverage: Counter[str] = Counter()
    by_upos: dict[str, Counter[str]] = defaultdict(Counter)
    unknown_words: list[str] = []
    ambiguous = 0
    candidate_count = 0
    lemma_total = 0
    lemma_top1 = 0
    lemma_oracle = 0
    pos_total = 0
    pos_top1 = 0
    pos_oracle = 0

    for gold, result in zip(gold_tokens, results, strict=True):
        coverage_class = _coverage_class(result)
        coverage[coverage_class] += 1
        if coverage_class == "unknown" and len(unknown_words) < max_unknown_words:
            unknown_words.append(gold.form)

        candidate_count += len(result.analyses)
        if len(result.analyses) > 1:
            ambiguous += 1

        best = result.best
        gold_lemma = normalize_text(gold.lemma).normalized
        if gold_lemma and gold_lemma != "_":
            lemma_total += 1
            candidate_lemmas = {
                normalize_text(item.lemma).normalized for item in result.analyses
            }
            if best is not None and normalize_text(best.lemma).normalized == gold_lemma:
                lemma_top1 += 1
            if gold_lemma in candidate_lemmas:
                lemma_oracle += 1

        gold_upos = gold.upos.upper()
        if gold_upos and gold_upos != "_":
            pos_total += 1
            candidate_upos = {upos_for_analysis(item) for item in result.analyses}
            top1_match = best is not None and upos_for_analysis(best) == gold_upos
            oracle_match = gold_upos in candidate_upos
            pos_top1 += int(top1_match)
            pos_oracle += int(oracle_match)
            by_upos[gold_upos]["total"] += 1
            by_upos[gold_upos]["top1_correct"] += int(top1_match)
            by_upos[gold_upos]["oracle_correct"] += int(oracle_match)

    serialised_by_upos = {
        upos: {
            "total": counts["total"],
            "top1_correct": counts["top1_correct"],
            "oracle_correct": counts["oracle_correct"],
        }
        for upos, counts in sorted(by_upos.items())
    }
    return GoldEvaluationReport(
        corpus_tokens=len(corpus.tokens),
        evaluated_tamil_tokens=len(gold_tokens),
        exact_coverage=coverage["exact"],
        guesser_coverage=coverage["guesser"],
        dictionary_only=coverage["dictionary_only"],
        unknown=coverage["unknown"],
        ambiguous=ambiguous,
        candidate_count=candidate_count,
        lemma_total=lemma_total,
        lemma_top1_correct=lemma_top1,
        lemma_oracle_correct=lemma_oracle,
        pos_total=pos_total,
        pos_top1_correct=pos_top1,
        pos_oracle_correct=pos_oracle,
        by_upos=serialised_by_upos,
        unknown_words=tuple(unknown_words),
    )
