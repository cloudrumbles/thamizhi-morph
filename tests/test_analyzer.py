from __future__ import annotations

from thamizhimorph import Analyzer, SQLiteDictionary, TokenContext

from conftest import FakeBackend


def test_exact_analysis_prevents_guesser_lookup(model_specs) -> None:
    exact, guessers = model_specs
    backend = FakeBackend(
        {
            ("noun.fst", "தமிழ்", False): ("தமிழ்+noun+nom",),
            ("noun-guess.fst", "தமிழ்", False): ("தமிழ்+noun+guess+nom",),
        }
    )
    analyzer = Analyzer(
        backend=backend,
        exact_models=exact,
        guesser_models=guessers,
    )

    result = analyzer.analyze_word("தமிழ்")
    assert result.status == "exact"
    assert result.analyses[0].guessed is False
    assert len(backend.calls) == 1


def test_pos_hint_limits_guesser_candidates(model_specs) -> None:
    exact, guessers = model_specs
    backend = FakeBackend(
        {
            ("noun-guess.fst", "புதுச்சொல்", False): ("புதுச்சொல்+noun+guess+nom",),
            ("verb-guess.fst", "புதுச்சொல்", False): ("புதுச்சொல்+verb+guess+fin",),
        }
    )
    analyzer = Analyzer(
        backend=backend,
        exact_models=exact,
        guesser_models=guessers,
    )

    result = analyzer.analyze_word("புதுச்சொல்", pos_hint="NOUN")
    assert result.status == "guessed"
    assert [analysis.pos for analysis in result.analyses] == ["noun"]


def test_unresolved_ambiguity_is_not_silently_collapsed(model_specs) -> None:
    exact, guessers = model_specs
    backend = FakeBackend(
        {
            ("noun.fst", "செய்", False): ("செய்+noun+nom",),
            ("verb.fst", "செய்", False): ("செய்+verb+imp",),
        }
    )
    analyzer = Analyzer(backend=backend, exact_models=exact, guesser_models=guessers)

    result = analyzer.analyze_word("செய்")
    assert len(result.analyses) == 2
    assert result.selected is None


def test_context_ranks_but_preserves_all_candidates(model_specs) -> None:
    exact, guessers = model_specs
    backend = FakeBackend(
        {
            ("noun.fst", "செய்", False): ("செய்+noun+nom",),
            ("verb.fst", "செய்", False): ("செய்+verb+fin+imp",),
        }
    )
    analyzer = Analyzer(backend=backend, exact_models=exact, guesser_models=guessers)

    result = analyzer.analyze_tokens(("செய்",), contexts=(TokenContext(upos="VERB"),))[0]
    assert result.selected == 0
    assert result.selected_analysis is not None
    assert result.selected_analysis.pos == "verb"
    assert {analysis.pos for analysis in result.analyses} == {"verb", "noun"}
    assert "POS agrees with VERB" in result.selected_analysis.reasons


def test_dictionary_can_supply_lexical_evidence_without_fake_morphology(
    model_specs, dictionary_path
) -> None:
    exact, guessers = model_specs
    analyzer = Analyzer(
        backend=FakeBackend({}),
        exact_models=exact,
        guesser_models=guessers,
        dictionary=SQLiteDictionary(dictionary_path),
    )

    result = analyzer.analyze_word(
        "புதுச்சொல்",
        use_guessers=False,
        include_dictionary=True,
    )
    assert result.status == "lexical_only"
    assert result.analyses == ()
    assert result.dictionary_entries[0].english == "new word"


def test_dictionary_evidence_can_break_a_pos_tie(model_specs, dictionary_path) -> None:
    exact, guessers = model_specs
    backend = FakeBackend(
        {
            ("noun.fst", "தமிழ்", False): ("தமிழ்+noun+nom",),
            ("verb.fst", "தமிழ்", False): ("தமிழ்+verb+fin",),
        }
    )
    analyzer = Analyzer(
        backend=backend,
        exact_models=exact,
        guesser_models=guessers,
        dictionary=SQLiteDictionary(dictionary_path),
    )

    result = analyzer.analyze_word("தமிழ்", include_dictionary=True)
    assert result.selected_analysis is not None
    assert result.selected_analysis.pos == "noun"
    assert "dictionary evidence" in " ".join(result.selected_analysis.reasons)


def test_generation_preserves_model_provenance(model_specs) -> None:
    exact, guessers = model_specs
    backend = FakeBackend(
        {
            ("noun.fst", "மரம்+noun+nom", True): ("மரம்",),
            ("verb.fst", "மரம்+noun+nom", True): (),
        }
    )
    analyzer = Analyzer(backend=backend, exact_models=exact, guesser_models=guessers)

    result = analyzer.generate("மரம்+noun+nom")
    assert result.forms == ("மரம்",)
    assert result.source_models == ("noun.fst",)


def test_non_tamil_tokens_are_explicitly_skipped(model_specs) -> None:
    exact, guessers = model_specs
    analyzer = Analyzer(
        backend=FakeBackend({}),
        exact_models=exact,
        guesser_models=guessers,
    )
    assert analyzer.analyze_word("Tamil").status == "skipped"
