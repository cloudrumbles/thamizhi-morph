# Changelog

## 0.2.0 — unreleased

### Added

- installable, typed Python package with no mandatory Python dependencies;
- packaged FST manifest and resource discovery;
- safe batched Foma backend with timeouts and deterministic output;
- CLI for analysis, generation, coverage evaluation, dictionary inspection, and API serving;
- optional Stanza contextual ranking and optional FastAPI service;
- read-only Avvai-style SQLite dictionary adapter and OOV review exporter;
- valid ten-column CoNLL-U output retaining native analysis provenance;
- unit, integration, API, and packaging tests;
- GitHub Actions CI and a production container image;
- architecture, roadmap, and contribution documentation.

### Changed

- Unicode is normalised to NFC at every public input boundary;
- guessers run only after exact model lookup fails;
- unresolved ambiguity is represented explicitly instead of arbitrarily collapsed;
- coverage and correctness are reported as separate concepts.

### Preserved

- original Foma transducers, lexicons, generated data, research attribution, and Apache-2.0 licence;
- the historical 2020 parser script for compatibility and reference.
