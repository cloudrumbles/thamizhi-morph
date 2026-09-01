"""Typed public data models for morphological analysis and generation."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any, Literal

AnalysisStatus = Literal["exact", "guessed", "lexical_only", "unknown", "skipped"]
ModelKind = Literal["exact", "guesser"]


@dataclass(frozen=True, slots=True)
class Morpheme:
    """One labelled morph emitted by a finite-state model."""

    label: str
    surface: str | None = None

    def to_dict(self) -> dict[str, str | None]:
        return {"label": self.label, "surface": self.surface}


@dataclass(frozen=True, slots=True)
class Analysis:
    """A single candidate analysis for a surface token.

    ``raw`` is retained losslessly because the historical ThamizhiMorph labels carry
    distinctions that cannot always be mapped to UD or UniMorph without information loss.
    """

    lemma: str
    pos: str
    morphemes: tuple[Morpheme, ...]
    raw: str
    source_models: tuple[str, ...]
    guessed: bool = False
    score: float = 0.0
    reasons: tuple[str, ...] = ()

    @property
    def labels(self) -> tuple[str, ...]:
        return tuple(morpheme.label for morpheme in self.morphemes)

    def ranked(self, *, score: float, reasons: tuple[str, ...]) -> Analysis:
        return replace(self, score=score, reasons=reasons)

    def with_sources(self, sources: tuple[str, ...]) -> Analysis:
        return replace(self, source_models=sources)

    def to_dict(self) -> dict[str, Any]:
        return {
            "lemma": self.lemma,
            "pos": self.pos,
            "morphemes": [morpheme.to_dict() for morpheme in self.morphemes],
            "raw": self.raw,
            "source_models": list(self.source_models),
            "guessed": self.guessed,
            "score": self.score,
            "reasons": list(self.reasons),
        }


@dataclass(frozen=True, slots=True)
class DictionaryEntry:
    """A lexical entry from an optional external SQLite dictionary."""

    source: str
    pos: str
    tamil: str
    english: str

    def to_dict(self) -> dict[str, str]:
        return {
            "source": self.source,
            "pos": self.pos,
            "tamil": self.tamil,
            "english": self.english,
        }


@dataclass(frozen=True, slots=True)
class TokenContext:
    """Optional syntactic evidence supplied by a tokenizer/parser."""

    upos: str | None = None
    xpos: str | None = None
    head: int | None = None
    deprel: str | None = None

    def to_dict(self) -> dict[str, str | int | None]:
        return {
            "upos": self.upos,
            "xpos": self.xpos,
            "head": self.head,
            "deprel": self.deprel,
        }


@dataclass(frozen=True, slots=True)
class ContextFeature:
    """A conservative multi-token annotation inferred from syntactic context."""

    name: str
    value: str
    evidence: str

    def to_dict(self) -> dict[str, str]:
        return {"name": self.name, "value": self.value, "evidence": self.evidence}


@dataclass(frozen=True, slots=True)
class TokenResult:
    """All evidence retained for one input token."""

    token: str
    normalized: str
    status: AnalysisStatus
    analyses: tuple[Analysis, ...] = ()
    selected: int | None = None
    dictionary_entries: tuple[DictionaryEntry, ...] = ()
    context: TokenContext | None = None
    context_features: tuple[ContextFeature, ...] = ()

    @property
    def selected_analysis(self) -> Analysis | None:
        if self.selected is None or self.selected >= len(self.analyses):
            return None
        return self.analyses[self.selected]

    def to_dict(self) -> dict[str, Any]:
        return {
            "token": self.token,
            "normalized": self.normalized,
            "status": self.status,
            "analyses": [analysis.to_dict() for analysis in self.analyses],
            "selected": self.selected,
            "dictionary_entries": [entry.to_dict() for entry in self.dictionary_entries],
            "context": self.context.to_dict() if self.context else None,
            "context_features": [feature.to_dict() for feature in self.context_features],
        }


@dataclass(frozen=True, slots=True)
class SentenceResult:
    """Morphological results and metadata for one sentence."""

    text: str
    tokens: tuple[TokenResult, ...]
    sent_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "sent_id": self.sent_id,
            "text": self.text,
            "tokens": [token.to_dict() for token in self.tokens],
        }


@dataclass(frozen=True, slots=True)
class GenerationResult:
    """Surface forms generated from one lexical analysis string."""

    lexical_form: str
    forms: tuple[str, ...]
    source_models: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "lexical_form": self.lexical_form,
            "forms": list(self.forms),
            "source_models": list(self.source_models),
        }


@dataclass(frozen=True, slots=True)
class ModelSpec:
    """Configuration for one compiled Foma transducer."""

    filename: str
    kind: ModelKind
    pos_hints: tuple[str, ...] = ()
    priority: int = 100
    enabled: bool = True

    @classmethod
    def from_dict(cls, value: dict[str, Any], *, kind: ModelKind) -> ModelSpec:
        return cls(
            filename=str(value["file"]),
            kind=kind,
            pos_hints=tuple(str(item).upper() for item in value.get("pos", ())),
            priority=int(value.get("priority", 100)),
            enabled=bool(value.get("enabled", True)),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "file": self.filename,
            "kind": self.kind,
            "pos": list(self.pos_hints),
            "priority": self.priority,
            "enabled": self.enabled,
        }


@dataclass(frozen=True, slots=True)
class CoverageReport:
    """Coverage-only evaluation; it does not claim linguistic correctness."""

    total: int
    exact: int
    guessed: int
    lexical_only: int
    unknown: int
    skipped: int
    ambiguous: int
    unique_lemmas: int
    elapsed_seconds: float
    unknown_tokens: tuple[str, ...] = field(default_factory=tuple)

    @property
    def analysable(self) -> int:
        return self.total - self.skipped

    @property
    def morphological_coverage(self) -> float:
        return (self.exact + self.guessed) / self.analysable if self.analysable else 0.0

    @property
    def exact_coverage(self) -> float:
        return self.exact / self.analysable if self.analysable else 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "total": self.total,
            "exact": self.exact,
            "guessed": self.guessed,
            "lexical_only": self.lexical_only,
            "unknown": self.unknown,
            "skipped": self.skipped,
            "ambiguous": self.ambiguous,
            "unique_lemmas": self.unique_lemmas,
            "elapsed_seconds": self.elapsed_seconds,
            "analysable": self.analysable,
            "morphological_coverage": self.morphological_coverage,
            "exact_coverage": self.exact_coverage,
            "unknown_tokens": list(self.unknown_tokens),
        }
