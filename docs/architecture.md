# Architecture

## Principle

ThamizhiMorph has two assets with different rates of change. The linguistic core—lexicons, paradigms, orthographical rules, guessers, and compiled FSTs—should remain explicit and reviewable. The software shell—process management, APIs, caching, serialization, testing, and deployment—should follow current engineering practice. Version 2 separates those layers.

## Request path

```text
text
  -> Unicode normalization and offset-preserving tokenization
  -> exact analysis across the lexical FSTs
  -> guesser FSTs only for unresolved Tamil tokens
  -> optional dictionary enrichment
  -> POS-aware deterministic ranking
  -> JSON / JSONL / CoNLL-U / Python objects
```

Generation follows the inverse Foma direction and can be restricted to a named transducer.

## Components

`normalization.py` performs NFC normalization and token classification. It removes only BOM, zero-width space, word joiner, and soft hyphen. ZWJ and ZWNJ are retained because they may be intentional rendering controls.

`parser.py` owns the `flookup` wire format. It preserves all analyses, parses `label=surface` morphs, de-duplicates exact outputs, and records malformed lines instead of silently corrupting them.

`backends/foma.py` is the only layer that starts `flookup`. A complete batch is sent to each independent model in one process. Model tasks may run concurrently; their results are merged in declared priority order, so output is reproducible.

`engine.py` runs the staged exact-then-guesser pipeline, provides a bounded thread-safe LRU cache, attaches optional dictionary glosses, and ranks candidates. Ranking never discards ambiguity. A POS hint strongly prefers compatible candidates, known lexical analyses outrank guesses, and dictionary-only fallbacks remain low confidence.

`dictionary.py` supports the schema:

```sql
words(id INTEGER PRIMARY KEY, headword TEXT UNIQUE)
entries(word_id INTEGER, source TEXT, pos TEXT, ta TEXT, en TEXT)
```

Connections use SQLite read-only URI mode and `PRAGMA query_only`.

`context.py` defines a small tagger protocol. The optional Stanza adapter is lazy and uses installed Tamil models instead of repository-specific model paths.

`conllu.py` emits ten columns. Only labels with a safe, well-defined UD correspondence are mapped into `FEATS`. Every original ThamizhiMorph label remains available in `MISC=TMorphTags=...`, including language-specific distinctions that UD may not represent.

## Extension points

A different finite-state runtime can implement `MorphologyBackend`; a different contextual tagger can implement `PosTagger`; dictionary sources can be adapted to the `Gloss` model. None of these require changes to the morphology engine.

The next structural step is to unpack and version the source Meta-Morph/Foma specifications currently stored as archives, then compile every `.fst` reproducibly in CI. Compiled models should be treated as build artifacts derived from reviewed linguistic sources rather than as the only executable representation.
