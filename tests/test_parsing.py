from thamizhimorph.parsing import merge_analyses, parse_analysis, parse_flookup_pairs


def test_parse_flookup_pairs_preserves_multiple_outputs_and_skips_unknowns() -> None:
    output = (
        "செய்யும்\tசெய்+verb+nonfin+futANDadjpart=உம்\n"
        "செய்யும்\tசெய்+verb+fin+fut=உம்+3sgn=அது\n"
        "அறியாதது\t+?\n"
        "diagnostic without a tab\n"
    )
    assert parse_flookup_pairs(output) == {
        "செய்யும்": (
            "செய்+verb+nonfin+futANDadjpart=உம்",
            "செய்+verb+fin+fut=உம்+3sgn=அது",
        )
    }


def test_parse_analysis_accepts_pipe_and_plus_boundaries() -> None:
    analysis = parse_analysis(
        "மரம்|+noun|+pl=கள்|+loc=இல்",
        source_model="noun.fst",
    )
    assert analysis.lemma == "மரம்"
    assert analysis.pos == "noun"
    assert analysis.labels == ("pl", "loc")
    assert analysis.morphemes[0].surface == "கள்"


def test_merge_analyses_retains_all_model_sources() -> None:
    first = parse_analysis("செய்+verb+fin", source_model="verb-a.fst")
    second = parse_analysis("செய்+verb+fin", source_model="verb-b.fst")
    merged = merge_analyses((first, second))
    assert len(merged) == 1
    assert merged[0].source_models == ("verb-a.fst", "verb-b.fst")
