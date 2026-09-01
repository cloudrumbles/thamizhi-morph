from __future__ import annotations

from thamizhi_morph.parser import parse_generation_output, parse_lookup_output


def test_parse_lookup_preserves_ambiguity_and_morph_surfaces() -> None:
    output = (
        "செய்யும்\tசெய்+verb+fin+fut=உம்+3sgn=உம்\n"
        "செய்யும்\tசெய்+verb+nonfin+futANDadjpart=உம்\n"
        "செய்யும்\tசெய்+verb+fin+fut=உம்+3sgn=உம்\n"
    )
    result = parse_lookup_output(output, model="verb-rest")

    analyses = result.analyses["செய்யும்"]
    assert len(analyses) == 2
    assert analyses[0].lemma == "செய்"
    assert analyses[0].morphemes[-1].label == "3sgn"
    assert analyses[0].morphemes[-1].surface == "உம்"
    assert result.diagnostics == ()


def test_parse_lookup_handles_unknown_and_malformed_lines() -> None:
    result = parse_lookup_output("புதியது\t+?\nbroken\n", model="noun")

    assert result.analyses["புதியது"] == ()
    assert result.diagnostics == ("line 2: missing tab separator",)


def test_parse_generation_deduplicates_forms() -> None:
    output = "மரம்+noun+nom\tமரம்\nமரம்+noun+nom\tமரம்\n"
    result = parse_generation_output(output)

    assert result.forms == {"மரம்+noun+nom": ("மரம்",)}
