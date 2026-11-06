"""Command line entry point. No operation overwrites an existing artifact."""
import argparse
import json
import sys

from .fixture import build_fixture
from .io import StudyError, read_json, write_json
from .provenance import resolve_origins
from .report import render_report
from .review import create_review, score_review, compare_reviews
from .runner import run_local
from .study import export_study, load_dataset, verify_export


def parser():
    root = argparse.ArgumentParser(description="Controlled threat evidence study; no paid APIs or submission actions")
    sub = root.add_subparsers(dest="command", required=True)
    p = sub.add_parser("validate", help="Validate source annotations")
    p.add_argument("dataset")
    p = sub.add_parser("export", help="Create immutable prompts and separate reference keys")
    p.add_argument("dataset"); p.add_argument("output")
    p.add_argument("--split", choices=["development", "evaluation_candidate"], default="evaluation_candidate")
    p = sub.add_parser("verify", help="Verify an exported study")
    p.add_argument("export")
    p = sub.add_parser("run", help="Call an already-installed local Ollama model")
    p.add_argument("export"); p.add_argument("output"); p.add_argument("--model", required=True)
    p.add_argument("--endpoint", default="http://127.0.0.1:11434")
    p.add_argument("--timeout", type=int, default=120); p.add_argument("--limit", type=int)
    p.add_argument("--resume", action="store_true")
    p = sub.add_parser("review", help="Create a method-blinded semantic review CSV")
    p.add_argument("export"); p.add_argument("responses"); p.add_argument("output")
    p = sub.add_parser("score", help="Score complete, hash-bound semantic reviews")
    p.add_argument("export"); p.add_argument("responses"); p.add_argument("reviews"); p.add_argument("output")
    p.add_argument("--review-pair", nargs=2, metavar=("FIRST_CSV", "SECOND_CSV"))
    p = sub.add_parser("compare-reviews", help="Compare two completed reviews and prepare explicit adjudication")
    p.add_argument("export"); p.add_argument("responses"); p.add_argument("first"); p.add_argument("second"); p.add_argument("output")
    p = sub.add_parser("fixture", help="Exercise the workflow with explicitly scripted responses")
    p.add_argument("export"); p.add_argument("output")
    p.add_argument("--mode", choices=["correct", "omit_b", "false_corroboration", "abstain"], default="correct")
    p = sub.add_parser("report", help="Render a self-contained HTML report")
    p.add_argument("results"); p.add_argument("output")
    p = sub.add_parser("origins", help="Resolve explicit claim-specific reporting provenance")
    p.add_argument("nodes")
    return root


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        if args.command == "validate":
            data = load_dataset(args.dataset)
            result = {"valid": True, "families": len(data["families"]), "status": data.get("status")}
        elif args.command == "export":
            result = export_study(load_dataset(args.dataset), args.output, args.split)
        elif args.command == "verify":
            result = verify_export(args.export)[0]
        elif args.command == "run":
            _, tasks, _ = verify_export(args.export)
            result = run_local(tasks, args.output, args.model, args.endpoint, args.timeout, args.resume, args.limit)
        elif args.command == "review":
            result = create_review(args.export, args.responses, args.output)
        elif args.command == "score":
            result = score_review(args.export, args.responses, args.reviews, args.review_pair)
            write_json(args.output, result)
        elif args.command == "compare-reviews":
            result = compare_reviews(args.export, args.responses, args.first, args.second, args.output)
        elif args.command == "fixture":
            result = build_fixture(args.export, args.output, args.mode)
        elif args.command == "report":
            result = render_report(read_json(args.results), args.output)
        else:
            result = resolve_origins(read_json(args.nodes))
        print(json.dumps(result, indent=2))
        return 1 if args.command == "run" and result["errors"] else 0
    except (StudyError, OSError, ValueError, KeyError, TypeError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
