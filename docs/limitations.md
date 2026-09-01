# Known linguistic limitations

The runtime overhaul fixes engineering constraints; it does not pretend that unresolved linguistic coverage has disappeared.

## Derivational morphology

The published analyser primarily models inflection. Derivational formations can remain unresolved or reach only a guesser. New derivational rules need linguistic review, gold examples, and regression tests before they are added.

## Complex predicates and compounds

The published implementation handles joined complex verbs only up to two verbal roots and identifies noun–verb, noun–noun, and verb–verb compounds incompletely. The runtime can return and rank more candidates, but it cannot infer missing finite-state rules.

## Free case-marking morphemes

Words that function contextually as free locative, sociative, ablative, or instrumental markers are generally analysed under their lexical category. A syntax-aware layer is needed to label the contextual case function.

## Dialect, named entities, spelling variation, and loanwords

Indian Tamil, Sri Lankan Tamil, Singapore Tamil, proper names, acronyms, code-switching, and noisy orthography create out-of-vocabulary cases. The staged guesser and optional dictionary fallback improve usefulness while keeping provenance explicit. They are not substitutes for balanced lexicon work.

## Contextual disambiguation

A POS hint often resolves noun/verb/particle ambiguity but is insufficient for every surface form. Syntax, semantic selection, multiword expressions, and sentence-level agreement may be required. The API therefore ranks but retains all candidates.

## Annotation interoperability

Tamil distinctions such as rationality, euphonic increments, internal/external Sandhi, and some combined person-number-gender markers do not have simple universal mappings. CoNLL-U export maps only conservative correspondences and preserves native labels in `MISC`.

## Evaluation

Coverage is not accuracy. The `benchmark` command reports exact-model, guesser, dictionary-only, and unknown outcomes separately. A trustworthy accuracy claim still requires a versioned gold corpus with lemma, segmentation, feature, ambiguity, dialect, and provenance annotations.
