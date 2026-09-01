# Changelog

## 2.0.0a1

- Introduced a typed, dependency-free Python core.
- Replaced token-by-token shell pipelines with concurrent batched `flookup` execution.
- Added analysis, inverse generation, Unicode diagnostics, candidate ranking, and caching.
- Added optional Stanza POS contextualization and Avvai SQLite dictionary enrichment.
- Added JSON, JSONL, pretty, and valid ten-column CoNLL-U output.
- Added CLI commands for analysis, generation, dictionary lookup, benchmarking, runtime diagnosis, and serving.
- Added a FastAPI service, Docker image, automated tests, linting, typing, coverage, and CI.
- Documented the distinction between engineering improvements and remaining linguistic limitations.
