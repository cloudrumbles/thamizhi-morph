"""Optional contextual analysis adapters."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from .analyzer import Analyzer
from .errors import OptionalDependencyError
from .models import SentenceResult, TokenContext


class StanzaContextProvider:
    """Supply UPOS and dependency evidence using a normal Stanza Tamil pipeline.

    Unlike the 2020 script, model paths are not hard-coded and the statistical parser
    remains an optional layer. All finite-state candidates are preserved after ranking.
    """

    def __init__(
        self,
        pipeline: Any | None = None,
        *,
        use_gpu: bool = False,
        processors: str = "tokenize,pos,depparse",
        **pipeline_options: Any,
    ) -> None:
        if pipeline is not None:
            self.pipeline = pipeline
            return
        try:
            import stanza
        except ImportError as error:
            raise OptionalDependencyError(
                "Stanza support is not installed. Install thamizhimorph[nlp]."
            ) from error

        self.pipeline = stanza.Pipeline(
            lang="ta",
            processors=processors,
            use_gpu=use_gpu,
            **pipeline_options,
        )

    def analyze(
        self,
        analyzer: Analyzer,
        text: str,
        *,
        use_guessers: bool = True,
        include_dictionary: bool = False,
    ) -> tuple[SentenceResult, ...]:
        document = self.pipeline(text)
        sentences: list[SentenceResult] = []
        for index, sentence in enumerate(document.sentences, 1):
            tokens = tuple(word.text for word in sentence.words)
            contexts = tuple(
                TokenContext(
                    upos=getattr(word, "upos", None),
                    xpos=getattr(word, "xpos", None),
                    head=getattr(word, "head", None),
                    deprel=getattr(word, "deprel", None),
                )
                for word in sentence.words
            )
            sentences.append(
                SentenceResult(
                    sent_id=str(index),
                    text=getattr(sentence, "text", " ".join(tokens)),
                    tokens=analyzer.analyze_tokens(
                        tokens,
                        contexts=contexts,
                        use_guessers=use_guessers,
                        include_dictionary=include_dictionary,
                    ),
                )
            )
        return tuple(sentences)


def download_stanza_models(*, processors: Iterable[str] = ("tokenize", "pos", "depparse")) -> None:
    """Explicitly download optional Tamil models; never runs during package import."""

    try:
        import stanza
    except ImportError as error:
        raise OptionalDependencyError(
            "Stanza support is not installed. Install thamizhimorph[nlp]."
        ) from error
    stanza.download("ta", processors=",".join(processors))
