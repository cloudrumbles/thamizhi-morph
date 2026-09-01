# Roadmap

Modern packaging removes operational barriers, but the remaining limits are mostly
linguistic and empirical. Work should be accepted against explicit evidence rather
than a growing pile of ad hoc exceptions.

## P0: establish a trustworthy benchmark

Create a versioned, licence-clear gold set sampled across Sri Lankan Tamil, Indian
Tamil, Singapore Tamil, formal prose, conversation, educational text, and named
entities. Each token should include all valid analyses, a contextually preferred
analysis where determinable, provenance, and an adjudication record.

**Acceptance criteria**

- train, development, and held-out test partitions;
- separate metrics for coverage, candidate recall, lemma accuracy, feature accuracy,
  and contextual top-1 accuracy;
- exact-model and guesser results reported separately;
- CI regression thresholds and a documented error taxonomy.

Until this exists, `thamizhimorph evaluate` intentionally reports coverage only.

## P0: lexicon governance and OOV review

Use corpus frequency, regional metadata, and dictionary evidence to construct a
review queue. The included `tools/avvai_oov.py` is the first stage: it finds words
with lexical evidence that exact FSTs do not recognise. Human review must assign the
correct lemma, lexical category, dialect/register, and inflectional class before a
lexicon patch is accepted.

**Acceptance criteria**

- provenance and licence recorded for every imported lemma;
- NFC-normalised, duplicate-free source tables;
- regional and named-entity coverage measured separately;
- generated regression cases for every accepted lemma.

## P1: derivational morphology

The current FSTs primarily model inflection. Add productive nominalisation,
adjectival, adverbial, causative, and other derivational processes as explicit rules,
with blocking and lexicalised exceptions where necessary. Do not treat dictionary
headword lookup as derivational analysis.

**Acceptance criteria**

- linguistically documented rule inventory;
- positive and negative examples for every rule;
- ambiguity retained where a surface form has both inflectional and derivational
  analyses;
- benchmark improvement without a material precision regression.

## P1: compounds and complex predicates

Move from manually listed two-root cases toward compositional handling of noun–noun,
noun–verb, and multi-verb predicates. Tokenisation, orthographic joining, light-verb
function, auxiliary order, and inflection on the final verb need separate tests.

**Acceptance criteria**

- supports both joined and space-separated spellings;
- identifies every verbal root rather than returning only a final stem;
- handles sequences longer than two roots where licensed;
- rejects unattested combinations through morphotactic constraints.

## P1: contextual morphological disambiguation

Replace the transparent heuristic ranker with a trained candidate ranker that scores
only analyses licensed by the FST. Useful inputs include the sentence, UPOS,
dependency structure, neighbouring lemmas, agreement, and candidate features. The
rule-based ranker should remain available as a deterministic baseline.

**Acceptance criteria**

- no candidate hallucination outside FST output;
- calibrated confidence and abstention on ties or distribution shift;
- regional test slices;
- model card, training-data statement, and reproducible training command.

## P1: free case markers and multi-token morphology

The initial application layer recognises `மூலம்` and `கொண்டு` only when an external
parser licenses them as case markers. Expand this from a documented inventory and
model the distinction between lexical and grammatical uses.

**Acceptance criteria**

- multi-token annotation schema that does not overwrite lexical analyses;
- context-sensitive positive and negative cases;
- mapping to UD `case` relations and suitable language-specific features.

## P2: interoperable annotation

Publish explicit mappings from native labels to UD and UniMorph while preserving
Tamil-specific distinctions such as rationality, euphonic material, Sandhi, and
strong/weak verb classes.

**Acceptance criteria**

- machine-readable mapping table with coverage statistics;
- no lossy conversion presented as reversible;
- round-trip tests for native JSON output;
- proposed Tamil-specific UD extensions discussed with the treebank community.

## P2: in-process and portable runtimes

Benchmark the reference subprocess backend against `libfoma` bindings, HFST, and a
portable WebAssembly path. Runtime migration is worthwhile only if it can consume or
reproducibly rebuild the same transducers and passes the gold regression suite.

**Acceptance criteria**

- cold-start, throughput, memory, and binary-size measurements;
- byte-for-byte or analysis-set equivalence on the benchmark;
- Linux, macOS, and Windows release artifacts;
- no change to the public `Analyzer` interface.
