from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, cast

from . import __version__
from .backends.base import BackendError
from .backends.foma import FomaBackend
from .conllu import to_conllu
from .context import StanzaPosTagger
from .dictionary import AvvaiDictionary, DictionaryError
from .engine import MorphologyEngine
from .evaluation import evaluate_words
from .models import DocumentAnalysis, TokenAnalysis


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="thamizhi-morph",
        description="Analyse and generate Tamil word forms with ThamizhiMorph.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("--model-dir", default=os.environ.get("THAMIZHI_MODELS"))
    parser.add_argument("--flookup", default=os.environ.get("THAMIZHI_FLOOKUP", "flookup"))
    parser.add_argument("--dictionary", default=os.environ.get("THAMIZHI_DICTIONARY"))
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--strict-output", action="store_true")

    commands = parser.add_subparsers(dest="command", required=True)

    analyze = commands.add_parser("analyze", help="analyse text from arguments, a file, or stdin")
    analyze.add_argument("text", nargs="*")
    analyze.add_argument("--file", type=Path)
    analyze.add_argument(
        "--format", choices=("pretty", "json", "jsonl", "conllu"), default="pretty"
    )
    analyze.add_argument("--pos", help="UPOS hint for a single input word, such as NOUN or VERB")
    analyze.add_argument(
        "--contextual", action="store_true", help="rank analyses with optional Stanza POS tags"
    )
    analyze.add_argument("--no-guessers", action="store_true")
    analyze.add_argument("--enrich-dictionary", action="store_true")
    analyze.add_argument("--all", action="store_true", help="show every candidate in pretty output")

    generate = commands.add_parser("generate", help="generate surface forms from lexical analyses")
    generate.add_argument("forms", nargs="*")
    generate.add_argument("--model", help="restrict generation to one model name")
    generate.add_argument("--format", choices=("pretty", "json"), default="pretty")

    lookup = commands.add_parser("lookup", help="look up entries in an external Avvai database")
    lookup.add_argument("headword")
    lookup.add_argument("--prefix", action="store_true")
    lookup.add_argument("--limit", type=int, default=20)

    benchmark = commands.add_parser(
        "benchmark", help="measure coverage and throughput on a word list"
    )
    benchmark.add_argument("wordlist", type=Path)
    benchmark.add_argument("--limit", type=int)
    benchmark.add_argument("--no-guessers", action="store_true")
    benchmark.add_argument("--enrich-dictionary", action="store_true")
    benchmark.add_argument("--max-unknown", type=int, default=100)

    doctor = commands.add_parser("doctor", help="validate flookup, models, and optional dictionary")
    doctor.add_argument("--json", action="store_true")

    serve = commands.add_parser("serve", help="start the optional HTTP API")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)

    return parser


def _engine(args: argparse.Namespace) -> MorphologyEngine:
    backend = FomaBackend(
        args.model_dir,
        flookup=args.flookup,
        timeout=args.timeout,
        max_workers=args.workers,
        strict_output=args.strict_output,
    )
    dictionary = AvvaiDictionary(args.dictionary) if args.dictionary else None
    return MorphologyEngine(backend, dictionary=dictionary)


def _read_text(args: argparse.Namespace) -> str:
    file_path = cast(Path | None, args.file)
    text_parts = cast(list[str], args.text)
    if file_path is not None and text_parts:
        raise ValueError("provide either positional text or --file, not both")
    if file_path is not None:
        return file_path.read_text(encoding="utf-8")
    if text_parts:
        return " ".join(text_parts)
    return sys.stdin.read()


def _pretty_token(token: TokenAnalysis, *, show_all: bool) -> str:
    lines = [token.token]
    candidates = token.analyses if show_all else token.analyses[:1]
    for index, analysis in enumerate(candidates):
        marker = "*" if index == token.selected else "-"
        morphology = (
            ", ".join(
                item.label if item.surface is None else f"{item.label}={item.surface}"
                for item in analysis.morphemes
            )
            or "—"
        )
        source = analysis.model + ("; guessed" if analysis.guessed else "")
        lines.append(
            f"  {marker} {analysis.lemma} [{analysis.pos}] {morphology} "
            f"(score={analysis.score:.2f}; {source})"
        )
        for gloss in analysis.glosses[:3]:
            definition = gloss.english or gloss.tamil
            if definition:
                lines.append(f"      {gloss.source}: {definition}")
    if not candidates:
        lines.append("  - no analysis")
    lines.extend(f"  ! {warning}" for warning in token.warnings)
    return "\n".join(lines)


def _print_document(document: DocumentAnalysis, output_format: str, *, show_all: bool) -> None:
    if output_format == "json":
        print(json.dumps(document.to_dict(), ensure_ascii=False, indent=2))
    elif output_format == "jsonl":
        for token in document.tokens:
            print(json.dumps(token.to_dict(), ensure_ascii=False))
    elif output_format == "conllu":
        print(to_conllu(document), end="")
    else:
        print("\n".join(_pretty_token(token, show_all=show_all) for token in document.tokens))


def _input_forms(values: Sequence[str]) -> tuple[str, ...]:
    if values:
        return tuple(values)
    return tuple(line.strip() for line in sys.stdin if line.strip())


def _print_generated(forms: Mapping[str, tuple[str, ...]], output_format: str) -> None:
    if output_format == "json":
        print(json.dumps(forms, ensure_ascii=False, indent=2))
        return
    for lexical, surfaces in forms.items():
        print(f"{lexical}\t{', '.join(surfaces) if surfaces else 'no generated form'}")


def _run(args: argparse.Namespace) -> int:
    if args.command == "lookup":
        if not args.dictionary:
            raise ValueError("lookup requires --dictionary or THAMIZHI_DICTIONARY")
        with AvvaiDictionary(args.dictionary) as dictionary:
            if args.prefix:
                result: Any = {
                    word: [item.to_dict() for item in entries]
                    for word, entries in dictionary.search_prefix(
                        args.headword, limit=args.limit
                    ).items()
                }
            else:
                result = [
                    item.to_dict() for item in dictionary.lookup(args.headword, limit=args.limit)
                ]
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    with _engine(args) as engine:
        if args.command == "doctor":
            status = engine.health()
            if args.json:
                print(json.dumps(status, ensure_ascii=False, indent=2))
            else:
                backend = status["backend"]
                print(f"backend: {backend['name']}")
                print(f"ready: {status['ready']}")
                for key, value in backend["details"].items():
                    print(f"{key}: {value}")
                if status["dictionary"]:
                    print(f"dictionary: {status['dictionary']}")
            return 0 if status["ready"] else 1

        if args.command == "analyze":
            text = _read_text(args)
            if args.pos:
                tokens = engine.analyze_words(
                    [text.strip()],
                    pos_hints=[args.pos],
                    use_guessers=not args.no_guessers,
                    enrich_dictionary=args.enrich_dictionary,
                )
                document = DocumentAnalysis(
                    text=text,
                    tokens=tokens,
                    elapsed_ms=0.0,
                    backend=engine.backend.name,
                )
            elif args.contextual:
                document = engine.analyze_contextual(
                    text,
                    StanzaPosTagger(),
                    use_guessers=not args.no_guessers,
                    enrich_dictionary=args.enrich_dictionary,
                )
            else:
                document = engine.analyze_text(
                    text,
                    use_guessers=not args.no_guessers,
                    enrich_dictionary=args.enrich_dictionary,
                )
            _print_document(document, args.format, show_all=args.all)
            return 0

        if args.command == "generate":
            forms = _input_forms(args.forms)
            _print_generated(engine.generate_many(forms, model=args.model), args.format)
            return 0

        if args.command == "benchmark":
            words = [
                line.strip()
                for line in args.wordlist.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            if args.limit is not None:
                words = words[: args.limit]
            report = evaluate_words(
                engine,
                words,
                use_guessers=not args.no_guessers,
                enrich_dictionary=args.enrich_dictionary,
                max_unknown_words=args.max_unknown,
            )
            print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
            return 0

        if args.command == "serve":
            try:
                import uvicorn
            except ImportError as error:
                raise RuntimeError(
                    "the API server needs: pip install 'thamizhi-morph[api]'"
                ) from error
            from .api import create_app

            uvicorn.run(create_app(engine), host=args.host, port=args.port)
            return 0

        raise AssertionError(f"unhandled command: {args.command}")


def main(argv: Sequence[str] | None = None) -> int:
    parser = _parser()
    try:
        return _run(parser.parse_args(argv))
    except (BackendError, DictionaryError, OSError, RuntimeError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
