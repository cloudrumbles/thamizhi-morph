#!/usr/bin/env python3
"""Export dictionary-backed candidates missing from the exact FST lexicons."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

from thamizhimorph import Analyzer, SQLiteDictionary
from thamizhimorph.evaluation import batched, read_conllu_tokens, read_wordlist


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Find words supported by an Avvai-style dictionary but absent from the exact "
            "ThamizhiMorph models. Output is review data, not an automatic lexicon patch."
        )
    )
    parser.add_argument("database", type=Path)
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--input-format", choices=("wordlist", "conllu"), default="wordlist")
    parser.add_argument("--batch-size", type=int, default=512)
    arguments = parser.parse_args()

    words = (
        read_conllu_tokens(arguments.input)
        if arguments.input_format == "conllu"
        else read_wordlist(arguments.input)
    )
    analyzer = Analyzer(dictionary=SQLiteDictionary(arguments.database))

    rows: list[dict[str, str]] = []
    for batch in batched(tuple(words), arguments.batch_size):
        for result in analyzer.analyze_tokens(batch, include_dictionary=True):
            if result.status == "exact" or not result.dictionary_entries:
                continue
            rows.append(
                {
                    "word": result.normalized,
                    "morphology_status": result.status,
                    "dictionary_pos": ";".join(
                        sorted({entry.pos for entry in result.dictionary_entries if entry.pos})
                    ),
                    "dictionary_sources": ";".join(
                        sorted({entry.source for entry in result.dictionary_entries})
                    ),
                }
            )

    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    with arguments.output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=(
                "word",
                "morphology_status",
                "dictionary_pos",
                "dictionary_sources",
            ),
            delimiter="\t",
        )
        writer.writeheader()
        writer.writerows(rows)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
