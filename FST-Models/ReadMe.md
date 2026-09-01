# Compiled FST models

These are the original compiled Foma transducers used by ThamizhiMorph. New
applications should normally install the Python package, which includes the same
binaries and reads their order from
`src/thamizhimorph/resources/models/manifest.json`.

## Exact models

| File | Function |
| --- | --- |
| `pronoun.fst` | pronouns |
| `noun.fst` | nouns |
| `adj.fst` | adjectives |
| `adv.fst` | adverbs |
| `part.fst` | particles and other closed classes |
| `verb-c3.fst` | verb class 3 |
| `verb-c4.fst` | verb class 4 |
| `verb-c62.fst` | verb class 6.2 |
| `verb-c11.fst` | verb class 11 |
| `verb-c12.fst` | verb class 12 |
| `verb-c-rest.fst` | remaining verb classes |

The verb classes remain separate because some orthographic rules conflict when the
transducers are compiled together. Query every exact model and retain every valid
analysis.

## Guessers

- `noun-guess.fst`
- `verb-guess.fst`
- `adj-guess.fst`
- `adv-guess.fst`
- `adverb-guesser.fst` (legacy duplicate, disabled in the default manifest)

A guesser must run only after every relevant exact model has failed. Its output is a
hypothesis based on suffix patterns, not evidence that the guessed lemma is present in
the lexicon.

## Direct use

```bash
printf 'தமிழ்\n' | flookup noun.fst
printf 'மரம்+noun+nom\n' | flookup -i noun.fst
```

For batching, error handling, Unicode normalisation, provenance, and structured
output, use `thamizhimorph` instead of invoking these files directly.
