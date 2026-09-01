# Packaged models

These files mirror the compiled transducers in the repository's historical
`FST-Models/` directory so an installed wheel is self-contained. `manifest.json` is
the source of truth for lookup order, exact/guesser classification, and compatible
UPOS hints.

Do not edit compiled `.fst` files directly. Linguistic changes should be made in the
source lexicons, Meta-Morph rules, and orthographic rules, then rebuilt and checked
against the regression suite.
