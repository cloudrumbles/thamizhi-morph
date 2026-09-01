# Architecture

## Design goals

The original project made a strong architectural choice: linguistic knowledge lives
in finite-state lexicons, orthographic rules, and Meta-Morph data rather than being
entangled with one application language. The modern application layer keeps that
choice and adds four constraints:

1. **Lossless at the boundary.** Native ThamizhiMorph analyses are always retained.
   UD mappings, dictionary evidence, and statistical predictions are secondary views.
2. **Explicit provenance.** Every candidate names the FST model that produced it and
   whether it came from an exact model or a guesser.
3. **No false disambiguation.** A candidate is selected only when it is the sole result
   or external evidence gives it a strictly higher score. Ties remain unresolved.
4. **Replaceable infrastructure.** The public analyser depends on a backend protocol,
   not directly on subprocesses or Foma-specific implementation details.

## Layers

### Linguistic resources

The existing compiled transducers remain the reference implementation. A versioned
`manifest.json` defines model order, exact-versus-guesser status, and compatible UPOS
hints. It replaces undocumented filename lists and lets packaging, CI, the CLI, and
the service use the same configuration.

### Backend

`LookupBackend` accepts a batch of inputs and model specifications. `FomaBackend`
implements the protocol by launching one `flookup` process per model for the whole
batch. It does not invoke a shell, does not construct an `echo` pipeline, validates
model paths, applies a timeout, decodes strict UTF-8, and reports model-specific
errors. Independent model calls run concurrently but are consumed in manifest order,
so output remains deterministic.

The protocol permits an in-process `libfoma`, HFST, WebAssembly, or remote backend in
the future without changing `Analyzer` or downstream applications.

### Analysis orchestration

`Analyzer` performs the following steps:

1. normalise input to Unicode NFC;
2. skip non-Tamil tokens unless explicitly asked to analyse them;
3. query all exact models;
4. query guessers only for tokens with no exact output;
5. parse and deduplicate analyses while retaining model provenance;
6. optionally collect read-only dictionary evidence;
7. rank candidates using available UPOS, dependency, and dictionary POS evidence;
8. return typed `TokenResult` objects with all candidates.

For a repeated surface token, backend results are reused within the batch. Ranking is
still performed per occurrence, so two instances may select different candidates
when their syntactic contexts differ.

### Contextual evidence

The core API accepts `TokenContext` from any parser. The optional Stanza adapter
supplies UPOS, XPOS, head, and dependency relation without hard-coded model paths.
The ranker rewards POS agreement and a deliberately small set of morphosyntactic
compatibilities. It records its score and reasons in each candidate.

This is not a learned contextual morphological analyser. It is an auditable bridge
between the FST candidate generator and an external parser. A future trained ranker
can implement the same interface.

### Dictionary evidence

`SQLiteDictionary` supports the schema used by the supplied Avvai database. It opens
the file in SQLite read-only mode, validates its schema, batches queries, and returns
lexical entries separately from FST analyses. A dictionary hit can support candidate
ranking or produce `lexical_only` status, but it cannot fabricate inflectional
segmentation or a paradigm class.

The database is intentionally not vendored. Its size, release cadence, and licensing
must remain independent of the analyser package.

### Output adapters

The JSON representation is the canonical application format. TSV is intended for
inspection. CoNLL-U output always contains ten columns; conservative UD features are
mapped where possible, while the native analysis and model provenance are encoded in
`MISC`. An unresolved ambiguous token has no selected lemma and exposes its candidate
count rather than choosing arbitrarily.

## Failure model

Configuration failures, missing Foma binaries, timeouts, malformed model output, and
invalid dictionary schemas raise package-specific exceptions. The CLI prints a short
error and returns status 2. The HTTP service converts runtime failures to structured
503 responses. Unknown words are ordinary analysis results, not exceptions.

## Compatibility

The root-level `thamizhi-morph-parsing.py` is retained unchanged as a historical
reference. New code should import `thamizhimorph` or call its CLI. The compiled models
also remain in `FST-Models/`; the package contains an additional copy so installed
applications do not depend on the repository layout.
