"""Command-line interface for analysis, generation, evaluation, and serving."""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from .analyzer import Analyzer
from .backend import FomaBackend
from .conllu import sentence_to_conllu
from .context import StanzaContextProvider, download_stanza_models
from .dictionary import SQLiteDictionary
from .errors import OptionalDependencyError, ThamizhiMorphError
from .evaluation import evaluate_coverage, read_conllu_tokens, read_wordlist
from .models import SentenceResult, TokenResult
from .normalization import simple_tokenize

_VERSION = "0.2.0"


def _add_runtime_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--model-dir",
        type=Path,
        default=os.getenv("THAMIZHIMORPH_MODEL_DIR"),
        help="directory containing manifest-listed .fst files",
    )
    parser.add_argument(
        "--flookup",
        default=os.getenv("THAMIZHIMORPH_FLOOKUP", "flookup"),
        help="flookup executable name or path",
    )
    parser.add_argument("--workers", type=int, default=4, help="parallel FST lookups")
    parser.add_argument(
        "--dictionary",
        type=Path,
        default=os.getenv("THAMIZHIMORPH_DICTIONARY"),
        help="optional Avvai-style SQLite dictionary",
    )


def _build_analyzer(arguments: argparse.Namespace) -> Analyzer:
    dictionary = SQLiteDictionary(arguments.dictionary) if arguments.dictionary else None
    return Analyzer(
        backend=FomaBackend(
            model_dir=arguments.model_dir,
            binary=arguments.flookup,
            workers=arguments.workers,
        ),
        dictionary=dictionary,
    )


def _read_text(arguments: argparse.Namespace) -> str:
    if getattr(arguments, "file", None):
        return arguments.file.read_text(encoding="utf-8")
    if getattr(arguments, "input", None):
        return " ".join(arguments.input)
    if sys.stdin.isatty():
        raise ValueError("provide text as arguments, with --file, or through stdin")
    return sys.stdin.read()


def _print_token_tsv(results: Sequence[TokenResult]) -> None:
    print("token\tstatus\tlemma\tpos\tanalysis\tmodels")
    for result in results:
        if not result.analyses:
            print(f"{result.normalized}\t{result.status}\t_\t_\t_\t_")
            continue
        for analysis in result.analyses:
            print(
                "\t".join(
                    (
                        result.normalized,
                        result.status,
                        analysis.lemma,
                        analysis.pos,
                        analysis.raw,
                        ",".join(analysis.source_models),
                    )
                )
            )


def _command_analyze(arguments: argparse.Namespace) -> int:
    text = _read_text(arguments)
    analyzer = _build_analyzer(arguments)
    include_dictionary = bool(arguments.dictionary)

    if arguments.context == "stanza":
        provider = StanzaContextProvider(use_gpu=arguments.gpu)
        sentences = provider.analyze(
            analyzer,
            text,
            use_guessers=not arguments.no_guessers,
            include_dictionary=include_dictionary,
        )
    else:
        tokens = tuple(arguments.input) if arguments.input else tuple(simple_tokenize(text))
        if arguments.pos and len(arguments.pos) != len(tokens):
            raise ValueError("--pos must be repeated once per input token")
        results = analyzer.analyze_tokens(
            tokens,
            pos_hints=arguments.pos,
            use_guessers=not arguments.no_guessers,
            include_dictionary=include_dictionary,
        )
        sentences = (SentenceResult(text=text.strip(), tokens=results),)

    if arguments.format == "conllu":
        print("\n".join(sentence_to_conllu(sentence) for sentence in sentences), end="")
    elif arguments.format == "jsonl":
        for sentence in sentences:
            for token in sentence.tokens:
                print(json.dumps(token.to_dict(), ensure_ascii=False))
    elif arguments.format == "tsv":
        _print_token_tsv(tuple(token for sentence in sentences for token in sentence.tokens))
    else:
        payload: dict[str, Any]
        if len(sentences) == 1 and arguments.context == "none":
            payload = {"tokens": [token.to_dict() for token in sentences[0].tokens]}
        else:
            payload = {"sentences": [sentence.to_dict() for sentence in sentences]}
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def _command_generate(arguments: argparse.Namespace) -> int:
    analyzer = _build_analyzer(arguments)
    result = analyzer.generate(arguments.lexical_form, model_names=arguments.model)
    if arguments.format == "json":
        print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
    else:
        for form in result.forms:
            print(form)
    return 0


def _command_evaluate(arguments: argparse.Namespace) -> int:
    analyzer = _build_analyzer(arguments)
    input_format = arguments.input_format
    if input_format == "auto":
        input_format = "conllu" if arguments.file.suffix in {".conllu", ".conll", ".cupt"} else "wordlist"
    words = read_conllu_tokens(arguments.file) if input_format == "conllu" else read_wordlist(arguments.file)
    report = evaluate_coverage(
        analyzer,
        words,
        use_guessers=not arguments.no_guessers,
        include_dictionary=bool(arguments.dictionary),
        batch_size=arguments.batch_size,
    )
    print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
    if arguments.unknown_output:
        arguments.unknown_output.write_text(
            "\n".join(report.unknown_tokens) + ("\n" if report.unknown_tokens else ""),
            encoding="utf-8",
        )
    return 0


def _command_dictionary(arguments: argparse.Namespace) -> int:
    dictionary = SQLiteDictionary(arguments.database)
    if arguments.dictionary_command == "stats":
        print(json.dumps(dictionary.stats(), ensure_ascii=False, indent=2))
    else:
        payload = {
            word: [entry.to_dict() for entry in dictionary.lookup(word)]
            for word in arguments.words
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def _command_models(arguments: argparse.Namespace) -> int:
    analyzer = _build_analyzer(arguments)
    print(json.dumps([model.to_dict() for model in analyzer.models], indent=2))
    return 0


def _command_stanza_download(_arguments: argparse.Namespace) -> int:
    download_stanza_models()
    return 0


def _command_serve(arguments: argparse.Namespace) -> int:
    try:
        import uvicorn
    except ImportError as error:
        raise OptionalDependencyError(
            "HTTP API support is not installed. Install thamizhimorph[api]."
        ) from error

    if arguments.model_dir:
        os.environ["THAMIZHIMORPH_MODEL_DIR"] = str(arguments.model_dir)
    os.environ["THAMIZHIMORPH_FLOOKUP"] = arguments.flookup
    if arguments.dictionary:
        os.environ["THAMIZHIMORPH_DICTIONARY"] = str(arguments.dictionary)
    uvicorn.run(
        "thamizhimorph.api:app",
        host=arguments.host,
        port=arguments.port,
        workers=arguments.processes,
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="thamizhimorph",
        description="Tamil finite-state morphological analysis and generation",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {_VERSION}")
    subparsers = parser.add_subparsers(dest="command", required=True)

    analyze = subparsers.add_parser("analyze", help="analyse tokens or text")
    analyze.add_argument("input", nargs="*", help="tokens; stdin is tokenised when omitted")
    analyze.add_argument("--file", type=Path, help="read UTF-8 text from a file")
    analyze.add_argument("--pos", action="append", help="UPOS hint, repeated per token")
    analyze.add_argument(
        "--format",
        choices=("json", "jsonl", "tsv", "conllu"),
        default="json",
    )
    analyze.add_argument("--no-guessers", action="store_true")
    analyze.add_argument("--context", choices=("none", "stanza"), default="none")
    analyze.add_argument("--gpu", action="store_true", help="allow Stanza to use a GPU")
    _add_runtime_options(analyze)
    analyze.set_defaults(handler=_command_analyze)

    generate = subparsers.add_parser("generate", help="generate surface forms")
    generate.add_argument("lexical_form")
    generate.add_argument("--model", action="append", help="restrict to an exact model filename")
    generate.add_argument("--format", choices=("lines", "json"), default="lines")
    _add_runtime_options(generate)
    generate.set_defaults(handler=_command_generate)

    evaluate = subparsers.add_parser("evaluate", help="measure coverage on a corpus")
    evaluate.add_argument("file", type=Path)
    evaluate.add_argument(
        "--input-format",
        choices=("auto", "wordlist", "conllu"),
        default="auto",
    )
    evaluate.add_argument("--batch-size", type=int, default=512)
    evaluate.add_argument("--no-guessers", action="store_true")
    evaluate.add_argument("--unknown-output", type=Path)
    _add_runtime_options(evaluate)
    evaluate.set_defaults(handler=_command_evaluate)

    dictionary = subparsers.add_parser("dictionary", help="inspect an external dictionary")
    dictionary_subcommands = dictionary.add_subparsers(dest="dictionary_command", required=True)
    dictionary_stats = dictionary_subcommands.add_parser("stats")
    dictionary_stats.add_argument("database", type=Path)
    dictionary_stats.set_defaults(handler=_command_dictionary)
    dictionary_lookup = dictionary_subcommands.add_parser("lookup")
    dictionary_lookup.add_argument("database", type=Path)
    dictionary_lookup.add_argument("words", nargs="+")
    dictionary_lookup.set_defaults(handler=_command_dictionary)

    models = subparsers.add_parser("models", help="show configured finite-state models")
    _add_runtime_options(models)
    models.set_defaults(handler=_command_models)

    stanza_download = subparsers.add_parser(
        "stanza-download", help="download optional Tamil Stanza models"
    )
    stanza_download.set_defaults(handler=_command_stanza_download)

    serve = subparsers.add_parser("serve", help="run the optional HTTP API")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)
    serve.add_argument("--processes", type=int, default=1)
    _add_runtime_options(serve)
    serve.set_defaults(handler=_command_serve)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    arguments = parser.parse_args(argv)
    try:
        return int(arguments.handler(arguments))
    except (ThamizhiMorphError, OSError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
