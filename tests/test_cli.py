from __future__ import annotations

import json
from pathlib import Path

from thamizhimorph.cli import main


def test_dictionary_stats_command(dictionary_path: Path, capsys) -> None:
    assert main(("dictionary", "stats", str(dictionary_path))) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["words"] == 2
    assert payload["entries"] == 2


def test_models_command_does_not_require_foma(capsys) -> None:
    assert main(("models",)) == 0
    payload = json.loads(capsys.readouterr().out)
    assert any(model["file"] == "noun.fst" for model in payload)
