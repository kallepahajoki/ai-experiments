"""CLI entry point for grounding-eval."""

import argparse
import sys
from pathlib import Path

from .openrouter import OpenRouterClient
from .generate import load_all_cases, generate_outputs, save_outputs, load_outputs
from .evaluate import evaluate_all, save_results
from .failure_modes import all_mode_ids, FAILURE_MODES
from .report import generate_report


DEFAULT_SUBJECT_MODELS = [
    "anthropic/claude-sonnet-4.6",
    "google/gemini-2.5-flash",
    "nvidia/nemotron-3-super-120b-a12b:free",
    "mistralai/mistral-small-2603",
    "openai/gpt-5.4-mini",
    "qwen/qwen3.5-122b-a10b",
    "qwen/qwen3.5-9b",
]

DEFAULT_JUDGE_MODEL = "anthropic/claude-opus-4.6"


def cmd_generate(args):
    models = args.models.split(",") if args.models else DEFAULT_SUBJECT_MODELS
    cases_dir = Path(args.cases)
    output_dir = Path(args.output)
    cases = load_all_cases(cases_dir)

    if not cases:
        print(f"No eval cases found in {cases_dir}", file=sys.stderr)
        sys.exit(1)

    print(f"Generating outputs for {len(cases)} case(s) × {len(models)} model(s) × {args.runs} run(s)")

    with OpenRouterClient() as client:
        for case in cases:
            print(f"\n--- Case: {case['id']} ---")
            outputs = generate_outputs(
                client, case, models,
                runs_per_model=args.runs,
                temperature=args.temperature,
            )
            save_outputs(outputs, output_dir)
            for o in outputs:
                cost_str = f"${o.cost_usd:.4f}" if o.cost_usd else "N/A"
                print(f"  {o.model} run {o.run_index}: {o.completion_tokens} tokens, {o.latency_ms:.0f}ms, {cost_str}")

    print(f"\nOutputs saved to {output_dir}")


def cmd_evaluate(args):
    outputs_dir = Path(args.outputs)
    cases_dir = Path(args.cases)
    results_dir = Path(args.results)
    judge_model = args.judge
    mode_ids = args.modes.split(",") if args.modes else None

    outputs = load_outputs(outputs_dir)
    if not outputs:
        print(f"No generated outputs found in {outputs_dir}", file=sys.stderr)
        sys.exit(1)

    modes_desc = ", ".join(mode_ids) if mode_ids else "all"
    print(f"Evaluating {len(outputs)} output(s) with judge {judge_model}")
    print(f"Failure modes: {modes_desc}")

    with OpenRouterClient() as client:
        results = evaluate_all(client, cases_dir, outputs, judge_model, mode_ids)
        save_results(results, results_dir)

    detected_count = sum(1 for r in results if r.verdict.detected)
    print(f"\nDone. {detected_count}/{len(results)} failure mode instances detected.")
    print(f"Results saved to {results_dir}")


def cmd_report(args):
    results_dir = Path(args.results)
    report = generate_report(results_dir)
    print(report)

    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(report)
        print(f"\nReport saved to {output_path}")


def cmd_list_modes(args):
    print("Available failure modes:\n")
    for mode_id, fm in FAILURE_MODES.items():
        print(f"  {mode_id:<25} [{fm.severity:<8}] [{fm.detection_difficulty:<6}] {fm.name}")


def main():
    parser = argparse.ArgumentParser(
        prog="grounding-eval",
        description="Source-grounded LLM output evaluation benchmark",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # generate
    gen = subparsers.add_parser("generate", help="Generate LLM outputs from eval cases")
    gen.add_argument("--models", type=str, default=None, help="Comma-separated model IDs")
    gen.add_argument("--cases", type=str, default="eval_data", help="Eval cases directory")
    gen.add_argument("--output", type=str, default="outputs", help="Output directory")
    gen.add_argument("--runs", type=int, default=3, help="Runs per model")
    gen.add_argument("--temperature", type=float, default=0.3, help="Sampling temperature")
    gen.set_defaults(func=cmd_generate)

    # evaluate
    ev = subparsers.add_parser("evaluate", help="Evaluate generated outputs")
    ev.add_argument("--outputs", type=str, default="outputs", help="Generated outputs directory")
    ev.add_argument("--cases", type=str, default="eval_data", help="Eval cases directory")
    ev.add_argument("--results", type=str, default="results", help="Results directory")
    ev.add_argument("--judge", type=str, default=DEFAULT_JUDGE_MODEL, help="Judge model ID")
    ev.add_argument("--modes", type=str, default=None, help="Comma-separated failure mode IDs")
    ev.set_defaults(func=cmd_evaluate)

    # report
    rep = subparsers.add_parser("report", help="Generate comparison report")
    rep.add_argument("--results", type=str, default="results", help="Results directory")
    rep.add_argument("--output", type=str, default=None, help="Save report to file")
    rep.set_defaults(func=cmd_report)

    # list-modes
    lm = subparsers.add_parser("list-modes", help="List available failure modes")
    lm.set_defaults(func=cmd_list_modes)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
