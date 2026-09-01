from __future__ import annotations

from types import SimpleNamespace

from thamizhimorph import Analyzer
from thamizhimorph.context import StanzaContextProvider

from conftest import FakeBackend


def test_stanza_adapter_is_injectable_and_preserves_dependencies(model_specs) -> None:
    exact, guessers = model_specs
    backend = FakeBackend(
        {
            ("noun.fst", "செய்", False): ("செய்+noun+nom",),
            ("verb.fst", "செய்", False): ("செய்+verb+fin",),
        }
    )
    analyzer = Analyzer(backend=backend, exact_models=exact, guesser_models=guessers)
    word = SimpleNamespace(text="செய்", upos="VERB", xpos="V", head=0, deprel="root")
    sentence = SimpleNamespace(text="செய்", words=[word])

    def pipeline(_text: str) -> SimpleNamespace:
        return SimpleNamespace(sentences=[sentence])

    result = StanzaContextProvider(pipeline=pipeline).analyze(analyzer, "செய்")[0]
    token = result.tokens[0]
    assert token.selected_analysis is not None
    assert token.selected_analysis.pos == "verb"
    assert token.context is not None
    assert token.context.deprel == "root"
