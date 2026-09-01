from __future__ import annotations

import json
from pathlib import Path

import pytest

from thamizhi_morph.backends.foma import DEFAULT_MODELS
from thamizhi_morph.cli import main


@pytest.fixture
def corpus_runtime(tmp_path: Path) -> tuple[Path, Path]:
    executable = tmp_path / "flookup"
    executable.write_text(
        """#!/usr/bin/env python3
import sys
from pathlib import Path
model = Path(sys.argv[-1]).name
for raw in sys.stdin:
    value = raw.rstrip('\\n')
    if not value:
        continue
    if model == 'noun.fst' and value in {'தமிழ்', 'மரம்'}:
        print(f'{value}\\t{value}+noun+nom')
    else:
        print(f'{value}\\t+?')
""",
        encoding="utf-8",
    )
    executable.chmod(0o755)
    model_dir = tmp_path / "models"
    model_dir.mkdir()
    for model in DEFAULT_MODELS:
        (model_dir / model.filename).touch()
    return executable, model_dir


def global_args(executable: Path, model_dir: Path) -> list[str]:
    return ["--flookup", str(executable), "--model-dir", str(model_dir)]


def test_cli_annotates_plain_text_corpus_as_jsonl(
    corpus_runtime: tuple[Path, Path],
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    executable, model_dir = corpus_runtime
    source = tmp_path / "corpus.txt"
    source.write_text("தமிழ்.\nமரம்\n", encoding="utf-8")

    code = main(
        [
            *global_args(executable, model_dir),
            "corpus",
            str(source),
            "--document-batch-size",
            "2",
        ]
    )

    assert code == 0
    documents = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert [document["id"] for document in documents] == [1, 2]
    assert documents[0]["tokens"][0]["analyses"][0]["lemma"] == "தமிழ்"
    assert documents[1]["tokens"][0]["analyses"][0]["lemma"] == "மரம்"


def test_cli_annotates_jsonl_and_preserves_ids(
    corpus_runtime: tuple[Path, Path],
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    executable, model_dir = corpus_runtime
    source = tmp_path / "corpus.jsonl"
    source.write_text(
        '{"document_id":"a","body":"தமிழ்"}\n'
        '{"document_id":"b","body":"மரம்"}\n',
        encoding="utf-8",
    )

    code = main(
        [
            *global_args(executable, model_dir),
            "corpus",
            str(source),
            "--input-format",
            "jsonl",
            "--text-field",
            "body",
            "--id-field",
            "document_id",
        ]
    )

    assert code == 0
    documents = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert [document["id"] for document in documents] == ["a", "b"]


def test_cli_evaluates_conllu_accuracy(
    corpus_runtime: tuple[Path, Path],
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    executable, model_dir = corpus_runtime
    corpus = tmp_path / "gold.conllu"
    corpus.write_text(
        "1\tதமிழ்\tதமிழ்\tNOUN\t_\tCase=Nom\t_\t_\t_\t_\n"
        "2\t.\t.\tPUNCT\t_\t_\t_\t_\t_\t_\n",
        encoding="utf-8",
    )

    code = main(
        [
            *global_args(executable, model_dir),
            "evaluate",
            str(corpus),
            "--no-guessers",
        ]
    )

    assert code == 0
    report = json.loads(capsys.readouterr().out)
    assert report["evaluated_tamil_tokens"] == 1
    assert report["coverage"]["exact_rate"] == 1.0
    assert report["lemma"]["top1_accuracy"] == 1.0
    assert report["upos"]["top1_accuracy"] == 1.0
