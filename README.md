# ThamizhiMorph

ThamizhiMorph is an open Tamil morphological analyser and generator built from finite-state transducers. This repository preserves the original linguistic assets while adding a maintainable Python runtime, command-line interface, HTTP API, evaluation tools, and optional contextual and dictionary integrations.

The FST remains the source of morphological truth. The new runtime does not replace the carefully encoded paradigms with an opaque model; it makes them fast, testable, composable, and easier to use from modern software.

## What changed in 2.0

- A typed Python package instead of one monolithic, fixed-path script.
- Batched `flookup`: one process per FST and batch, not two subprocesses per token and model.
- Analysis and inverse generation through the same API.
- Deterministic ambiguity preservation and candidate ranking.
- NFC Unicode normalization, token offsets, and explicit diagnostics.
- POS-hint and optional Stanza contextual ranking without hard-coded model files.
- Optional read-only integration with an Avvai-format SQLite dictionary.
- Valid ten-column CoNLL-U export while retaining Tamil-specific labels in `MISC`.
- Coverage/throughput benchmarking, a runtime doctor, FastAPI service, Docker image, tests, linting, typing, and CI.

## Quick start

Install Foma and the package from the repository root:

```bash
sudo apt-get install foma-bin
python -m pip install -e .
thamizhi-morph doctor
```

The runtime discovers `FST-Models/` in the repository automatically. Other deployments can set `THAMIZHI_MODELS=/path/to/FST-Models` and `THAMIZHI_FLOOKUP=/path/to/flookup`.

Analyse a word or sentence:

```bash
thamizhi-morph analyze தமிழ்
thamizhi-morph analyze "அவர் மரத்தைப் பார்த்தார்." --format json --all
thamizhi-morph analyze செய்யும் --pos VERB --format conllu
```

Generate surface forms by applying a transducer in the inverse direction:

```bash
thamizhi-morph generate 'மரம்+noun+nom' --model noun
```

Measure coverage on the bundled word lists:

```bash
thamizhi-morph benchmark test-data/Grade1-Unique-Wordlist
```

## Python

```python
from thamizhi_morph.backends import FomaBackend
from thamizhi_morph.engine import MorphologyEngine

engine = MorphologyEngine(FomaBackend(model_dir="FST-Models"))
result = engine.analyze_text("தமிழ் ஒரு செம்மொழி.")

for token in result.tokens:
    if token.best:
        print(token.token, token.best.lemma, token.best.labels)
```

## Optional contextual analysis

```bash
python -m pip install -e '.[context]'
thamizhi-morph analyze "அவர் நாளை வருவார்." --contextual --all
```

Stanza supplies UPOS hints. ThamizhiMorph still returns every FST analysis; the hint changes ranking rather than deleting ambiguity. External taggers can implement the small `PosTagger` protocol in `thamizhi_morph.context`.

## Optional Avvai dictionary integration

The dictionary database is not bundled or redistributed. Point the runtime at a compatible read-only SQLite file:

```bash
export THAMIZHI_DICTIONARY=/data/avvai-dict-master.db
thamizhi-morph lookup தமிழ்
thamizhi-morph analyze தமிழ் --enrich-dictionary --format json
```

Exact lemma matches add Tamil and English glosses. When an inflectional analysis fails but the surface form is a dictionary headword, the result is explicitly marked `dictionary-fallback`; it is not presented as a recovered morphological parse.

## HTTP API

```bash
python -m pip install -e '.[api]'
thamizhi-morph serve --host 0.0.0.0 --port 8000
```

Endpoints:

- `GET /healthz`
- `POST /v1/analyze`
- `POST /v1/generate`
- `GET /v1/dictionary/{headword}`

Example request:

```json
{
  "text": "மரங்களில்",
  "use_guessers": true,
  "enrich_dictionary": false
}
```

## Design guarantees

The core package has no required Python dependencies. It never invokes a shell, validates the line-based Foma protocol, preserves duplicate-free output in model-priority order, and rejects newline or NUL injection in lookup inputs. Dictionary access is query-only. Optional services are isolated behind extras.

See [`docs/architecture.md`](docs/architecture.md) for the component model and [`docs/limitations.md`](docs/limitations.md) for the linguistic gaps that remain.

## Tests and development

```bash
python -m pip install -e '.[dev,api]'
make check
```

Unit tests use a fake `flookup` executable and therefore run without Foma. CI also performs a smoke test against the real bundled `.fst` models.

## Research and attribution

The analyser, lexicons, Meta-Morph rules, paradigms, and FST models were developed by K. Sarveswaran, Gihan Dias, and Miriam Butt. Please cite:

Sarveswaran, K., Dias, G., & Butt, M. (2021). ThamizhiMorph: A morphological parser for the Tamil language. *Machine Translation, 35*, 37–70. https://doi.org/10.1007/s10590-021-09261-5

Sarveswaran, K., Dias, G., & Butt, M. (2019). Using Meta-Morph Rules to develop morphological analysers: A case study concerning Tamil. In *Proceedings of FSMNLP 2019* (pp. 76–86).

The project is licensed under Apache-2.0. The optional external dictionary may have separate licensing terms.
