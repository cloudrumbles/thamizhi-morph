from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import StrEnum
from typing import Any


class TokenKind(StrEnum):
    TAMIL = "tamil"
    PUNCTUATION = "punctuation"
    NUMBER = "number"
    FOREIGN = "foreign"
    SYMBOL = "symbol"


@dataclass(frozen=True, slots=True)
class Morpheme:
    """One analyser label and, where available, its realised surface morph."""

    label: str
    surface: str | None = None

    @classmethod
    def parse(cls, segment: str) -> Morpheme:
        label, separator, surface = segment.partition("=")
        return cls(label=label.strip(), surface=surface if separator else None)

    def to_dict(self) -> dict[str, str | None]:
        return {"label": self.label, "surface": self.surface}


@dataclass(frozen=True, slots=True)
class Gloss:
    source: str
    pos: str
    tamil: str
    english: str

    def to_dict(self) -> dict[str, str]:
        return {
            "source": self.source,
            "pos": self.pos,
            "ta": self.tamil,
            "en": self.english,
        }


@dataclass(frozen=True, slots=True)
class MorphAnalysis:
    surface: str
    lemma: str
    pos: str
    morphemes: tuple[Morpheme, ...] = ()
    model: str = ""
    guessed: bool = False
    raw: str = ""
    score: float = 0.0
    glosses: tuple[Gloss, ...] = ()

    @property
    def signature(self) -> tuple[str, str, tuple[tuple[str, str | None], ...], bool]:
        return (
            self.lemma,
            self.pos,
            tuple((item.label, item.surface) for item in self.morphemes),
            self.guessed,
        )

    @property
    def labels(self) -> tuple[str, ...]:
        return tuple(item.label for item in self.morphemes)

    def with_score(self, score: float) -> MorphAnalysis:
        return replace(self, score=score)

    def with_glosses(self, glosses: tuple[Gloss, ...]) -> MorphAnalysis:
        return replace(self, glosses=glosses)

    def to_dict(self) -> dict[str, Any]:
        return {
            "surface": self.surface,
            "lemma": self.lemma,
            "pos": self.pos,
            "morphemes": [item.to_dict() for item in self.morphemes],
            "model": self.model,
            "guessed": self.guessed,
            "score": round(self.score, 4),
            "glosses": [item.to_dict() for item in self.glosses],
        }


@dataclass(frozen=True, slots=True)
class TextToken:
    text: str
    start: int
    end: int
    kind: TokenKind


@dataclass(frozen=True, slots=True)
class TokenAnalysis:
    token: str
    normalized: str
    kind: TokenKind
    analyses: tuple[MorphAnalysis, ...] = ()
    selected: int | None = None
    start: int | None = None
    end: int | None = None
    pos_hint: str | None = None
    warnings: tuple[str, ...] = ()

    @property
    def best(self) -> MorphAnalysis | None:
        if self.selected is None or self.selected >= len(self.analyses):
            return None
        return self.analyses[self.selected]

    def with_offsets(self, start: int, end: int) -> TokenAnalysis:
        return replace(self, start=start, end=end)

    def to_dict(self) -> dict[str, Any]:
        return {
            "token": self.token,
            "normalized": self.normalized,
            "kind": self.kind.value,
            "start": self.start,
            "end": self.end,
            "pos_hint": self.pos_hint,
            "selected": self.selected,
            "warnings": list(self.warnings),
            "analyses": [item.to_dict() for item in self.analyses],
        }


@dataclass(frozen=True, slots=True)
class DocumentAnalysis:
    text: str
    tokens: tuple[TokenAnalysis, ...]
    elapsed_ms: float
    backend: str
    warnings: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "backend": self.backend,
            "elapsed_ms": round(self.elapsed_ms, 3),
            "warnings": list(self.warnings),
            "metadata": self.metadata,
            "tokens": [item.to_dict() for item in self.tokens],
        }


@dataclass(frozen=True, slots=True)
class BackendHealth:
    name: str
    ready: bool
    details: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "ready": self.ready, "details": self.details}
