# Contributing

Changes to runtime code and changes to linguistic behaviour require different evidence.

For runtime changes, add unit tests and run `make check`. Performance work should include a reproducible `thamizhi-morph benchmark` comparison. Do not change output order accidentally: ambiguity is part of the public API.

For lexicon, paradigm, orthographical, or Meta-Morph changes, include positive examples, negative examples, the affected class or rule, the variety/register of Tamil, and a source or corpus justification. Add regression fixtures before recompiling an FST. Avoid fixing an isolated word by broadening a rule that creates false analyses elsewhere.

Keep external corpora and dictionaries out of the repository unless their licence and provenance are documented. Generated files should be reproducible from reviewed source files.
