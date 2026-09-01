# ThamizhiMorph

ThamizhiMorph is an open Tamil morphological analyser and generator built from
finite-state transducers (FSTs). Its linguistic core covers Tamil nouns, pronouns,
verbs, adjectives, adverbs, particles, morphophonological alternations, and Sandhi.
The project was created by K. Sarveswaran with Gihan Dias and Miriam Butt.

This repository now provides a maintained application layer around the original Foma
models: a typed Python package, batch-safe runtime, command-line interface, optional
contextual ranking, valid CoNLL-U export, an HTTP API, reproducible evaluation tools,
tests, CI, and a container image.

## What changed in 0.2

- The compiled FSTs are packaged with the Python library and described by one
  versioned manifest.
- Unicode input is normalised to NFC before every lookup.
- Lookup is batched: one `flookup` process per model and input batch, rather than an
  `echo` and `flookup` process for every token/model pair.
- Exact analyses always run before guessers. Results identify whether an analysis was
  exact, guessed, lexical-only, unknown, or skipped.
- Every candidate and its source model are retained. Ambiguous forms are not silently
  collapsed when the available evidence cannot distinguish them.
- Optional UPOS/dependency evidence ranks candidates transparently and records the
  reason for a selection.
- A read-only adapter can use an external Avvai-style SQLite dictionary as lexical
  evidence and as a source of reviewed OOV candidates. Dictionary entries never
  masquerade as morphological analyses.
- The exporter writes all ten CoNLL-U columns and preserves native ThamizhiMorph
  labels in `MISC` when a safe UD mapping is unavailable.
- The old 2020 script remains in the repository for reference, but new applications
  should use the package API or CLI.

## Requirements

- Python 3.10 or later
- [Foma](https://fomafst.github.io/) (`flookup` must be available on `PATH`)

On Debian or Ubuntu:

```bash
sudo apt-get install foma
python -m pip install -e .
```

Optional integrations:

```bash
python -m pip install -e '.[api]'     # FastAPI and Uvicorn
python -m pip install -e '.[nlp]'     # Stanza contextual analysis
python -m pip install -e '.[dev,api]' # tests, lint, and build tools
```

## Command line

Analyse one or more tokens:

```bash
thamizhimorph analyze தமிழ் மரங்களில்
thamizhimorph analyze செய்தான் --pos VERB --format tsv
```

Analyse stdin and emit CoNLL-U:

```bash
echo 'அவன் மரத்தைப் பார்த்தான்.' | thamizhimorph analyze --format conllu
```

Use Stanza POS and dependency predictions as ranking evidence:

```bash
thamizhimorph stanza-download
printf 'அவன் மரத்தைப் பார்த்தான்.\n' | \
  thamizhimorph analyze --context stanza --format conllu
```

Generate surface forms by inverse lookup:

```bash
thamizhimorph generate 'மரம்+noun+nom'
thamizhimorph generate 'செய்+verb+fin+past+3sgm' --format json
```

Measure coverage without presenting it as linguistic accuracy:

```bash
thamizhimorph evaluate test-data/Grade1-Unique-Wordlist
thamizhimorph evaluate corpus.conllu --input-format conllu \
  --unknown-output unknown.txt
```

## Python API

```python
from thamizhimorph import Analyzer, TokenContext

analyzer = Analyzer()
result = analyzer.analyze_word("செய்யும்", pos_hint="VERB")

for candidate in result.analyses:
    print(candidate.lemma, candidate.pos, candidate.labels)

contextual = analyzer.analyze_tokens(
    ["செய்யும்"],
    contexts=[TokenContext(upos="VERB", deprel="root")],
)
print(contextual[0].selected_analysis)
```

`selected_analysis` is `None` when candidates remain tied. The full candidate list is
always available in `analyses`.

## Optional dictionary evidence

The package supports a read-only SQLite database with this schema:

```sql
CREATE TABLE words (
  id INTEGER PRIMARY KEY,
  headword TEXT NOT NULL UNIQUE
);
CREATE TABLE entries (
  word_id INTEGER NOT NULL REFERENCES words(id),
  source TEXT NOT NULL,
  pos TEXT NOT NULL DEFAULT '',
  ta TEXT NOT NULL DEFAULT '',
  en TEXT NOT NULL DEFAULT '',
  PRIMARY KEY (word_id, source)
);
```

Pass the database explicitly; it is not distributed with this repository:

```bash
thamizhimorph dictionary stats /path/to/avvai-dict.db
thamizhimorph analyze புதுச்சொல் --dictionary /path/to/avvai-dict.db
python tools/avvai_oov.py /path/to/avvai-dict.db words.txt candidates.tsv
```

The OOV exporter produces a review queue. It does not modify lexicons automatically,
because dictionary POS labels and FST paradigm classes are not interchangeable.

## HTTP API

```bash
thamizhimorph serve --host 0.0.0.0 --port 8000
```

Or run the container:

```bash
docker build -t thamizhimorph .
docker run --rm -p 8000:8000 thamizhimorph
```

Endpoints:

- `GET /health`
- `POST /v1/analyze`
- `POST /v1/generate`
- interactive OpenAPI documentation at `/docs`

Example request:

```json
{
  "tokens": ["தமிழ்", "மரங்களில்"],
  "pos_hints": ["NOUN", "NOUN"],
  "use_guessers": true
}
```

## Architecture

```text
text / tokens
    │
    ├── NFC normalisation
    │
    ├── exact FST lookup (batched, all analyses retained)
    │       └── guesser lookup only when exact lookup is empty
    │
    ├── optional dictionary evidence
    ├── optional POS/dependency ranking
    │
    └── typed JSON / TSV / CoNLL-U / Python objects
```

The backend is defined by a small protocol. Foma is the reference backend, but a
future in-process `libfoma`, HFST, or other runtime can be added without changing the
public analyser interface or the linguistic resources.

See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md),
[`docs/ROADMAP.md`](docs/ROADMAP.md), and [`docs/LEGACY.md`](docs/LEGACY.md)
for design details, open linguistic work, and the migration status of historical artifacts.

## Current linguistic limits

The application layer makes the existing analyser easier to use and safer to extend;
it does not pretend that software packaging solves unfinished linguistic analysis.
The main unresolved areas are derivational morphology, broad coverage of compounds
and complex predicates, contextual disambiguation that requires syntax or semantics,
regional and named-entity OOV coverage, and a manually verified public benchmark.
Guesser output is therefore marked explicitly, all ambiguity is retained, and coverage
reports are not called accuracy reports.

## Research and citation

Please cite the linguistic work when using the models or derived resources:

> Sarveswaran, K., Dias, G., & Butt, M. (2021). ThamizhiMorph: A morphological
> parser for the Tamil language. *Machine Translation, 35*, 37–70.
> https://doi.org/10.1007/s10590-021-09261-5

> Sarveswaran, K., Dias, G., & Butt, M. (2019). Using Meta-Morph Rules to develop
> morphological analysers: A case study concerning Tamil. In *Proceedings of the
> 14th International Conference on Finite-State Methods and Natural Language
> Processing* (pp. 76–86).

The original research was supported by the AHEAD Operation of Sri Lanka's Ministry
of Higher Education, funded by the World Bank, and by the DAAD.

## License

Apache License 2.0. See [`LICENSE`](LICENSE).
