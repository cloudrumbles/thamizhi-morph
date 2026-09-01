# Contributing

Contributions are welcome, especially reviewed lexical additions, regression cases,
regional Tamil data, documentation, and improvements to the finite-state rules.

## Development setup

```bash
sudo apt-get install foma
python -m pip install -e '.[dev,api]'
ruff check .
pytest
python -m build
```

## Linguistic changes

A linguistic patch should include:

1. the source and licence of any new lexical data;
2. the intended dialect, register, and paradigm class;
3. positive examples that must analyse or generate;
4. negative examples guarding against overgeneration;
5. a short explanation of the rule or lexical exception;
6. updated coverage/accuracy results where a gold set exists.

Do not import a dictionary wholesale into an FST lexicon. Dictionary POS categories,
headwords, inflectional classes, and morphological analyses are different kinds of
evidence. Use `tools/avvai_oov.py` to create a human review queue.

## Application changes

Keep the core package dependency-free. Integrations with statistical NLP or web
frameworks belong in optional extras. Preserve the native FST output, expose model
provenance, and do not silently select one candidate when evidence is tied.

The public `LookupBackend` protocol is the boundary for new runtimes. A backend must
support batched forward and inverse lookup and must pass the same regression corpus as
the Foma backend.

## Repository hygiene

- Store source rules and reproducible build instructions whenever adding binaries.
- Avoid new ZIP archives or generated word lists in normal commits.
- Normalise Tamil text to NFC.
- Keep test fixtures small and licence-clear.
- Run Ruff and the full test suite before opening a pull request.
