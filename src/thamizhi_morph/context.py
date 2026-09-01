from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True, slots=True)
class TaggedToken:
    text: str
    upos: str
    start: int | None = None
    end: int | None = None


class PosTagger(Protocol):
    name: str

    def tag(self, text: str) -> Sequence[TaggedToken]: ...


class StanzaPosTagger:
    """Lazy, optional Stanza adapter with no hard-coded model paths."""

    name = "stanza"

    def __init__(
        self,
        *,
        language: str = "ta",
        use_gpu: bool = False,
        pipeline: Any | None = None,
    ) -> None:
        if pipeline is not None:
            self._pipeline = pipeline
            return
        try:
            import stanza  # type: ignore[import-not-found]
        except ImportError as error:
            raise RuntimeError(
                "contextual analysis needs the optional dependency: "
                "pip install 'thamizhi-morph[context]'"
            ) from error
        self._pipeline = stanza.Pipeline(
            lang=language,
            processors="tokenize,pos",
            use_gpu=use_gpu,
            verbose=False,
        )

    def tag(self, text: str) -> tuple[TaggedToken, ...]:
        document = self._pipeline(text)
        output: list[TaggedToken] = []
        for sentence in document.sentences:
            for token in sentence.tokens:
                for word in token.words:
                    output.append(
                        TaggedToken(
                            text=str(word.text),
                            upos=str(word.upos or "X"),
                            start=getattr(token, "start_char", None),
                            end=getattr(token, "end_char", None),
                        )
                    )
        return tuple(output)
