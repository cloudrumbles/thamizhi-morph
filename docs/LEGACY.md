# Legacy repository layout

Several historical artifacts remain at the repository root so existing citations and
download links do not break during the first modernisation release.

- `thamizhi-morph-parsing.py` is the 2020 Stanza/Foma orchestration script. It uses
  fixed filenames and model paths and is not the supported package entry point.
- `FST-Models/` contains the canonical compiled transducers. The same blobs are also
  packaged under `src/thamizhimorph/resources/models/` for installed applications.
- `foma/*.zip` contains historical Foma bundles.
- `Archive.zip` is an opaque application snapshot and is not used by the package,
  tests, container, or CI.
- `Generated-Verbs/`, `Lexicons/`, and `test-data/` remain research/data resources,
  not Python source packages.

A later housekeeping release can remove or relocate archives only after their source,
licence, reproducible build path, and any external consumers have been identified.
Keeping them outside the runtime now prevents accidental imports and package bloat.
