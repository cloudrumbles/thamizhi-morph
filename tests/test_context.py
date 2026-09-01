from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from thamizhi_morph.context import StanzaPosTagger


class FakePipeline:
    def __call__(self, text: str) -> Any:
        assert text == "தமிழ் வரும்"
        return SimpleNamespace(
            sentences=[
                SimpleNamespace(
                    tokens=[
                        SimpleNamespace(
                            start_char=0,
                            end_char=5,
                            words=[SimpleNamespace(text="தமிழ்", upos="NOUN")],
                        ),
                        SimpleNamespace(
                            start_char=6,
                            end_char=11,
                            words=[SimpleNamespace(text="வரும்", upos="VERB")],
                        ),
                    ]
                )
            ]
        )


def test_stanza_adapter_accepts_an_injected_pipeline() -> None:
    tagger = StanzaPosTagger(pipeline=FakePipeline())

    tagged = tagger.tag("தமிழ் வரும்")

    assert [(item.text, item.upos, item.start, item.end) for item in tagged] == [
        ("தமிழ்", "NOUN", 0, 5),
        ("வரும்", "VERB", 6, 11),
    ]


def test_stanza_adapter_has_a_clear_optional_dependency_error() -> None:
    with pytest.raises(RuntimeError, match="optional dependency"):
        StanzaPosTagger()
