"""CLI entry point for grounding-eval."""

import argparse
import sys
from pathlib import Path

from .openrouter import OpenRouterClient
from .generate import load_all_cases, generate_outputs, save_outputs, load_outputs
from .evaluate import evaluate_all, save_results
from .failure_modes import all_mode_ids, FAILURE_MODES
from .report import generate_report
from .judge_calibration import run_judge_comparison, compare_judges
from .evaluate import load_results


DEFAULT_SUBJECT_MODELS = [
    "anthropic/claude-sonnet-4.6",
    "google/gemini-3-flash-preview",
    "mistralai/mistral-large-2512",
    "openai/gpt-5.4-mini",
    "openai/gpt-4o-2024-11-20",
    "qwen/qwen3.5-122b-a10b",
    "qwen/qwen3.5-397b-a17b",
    "minimax/minimax-m2.7",
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
                source_key=args.source_key,
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

    source_key = args.source_key
    concurrency = args.concurrency

    with OpenRouterClient() as client:
        results = evaluate_all(
            client, cases_dir, outputs, judge_model, mode_ids,
            concurrency=concurrency, source_key=source_key,
        )
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


def cmd_calibrate(args):
    opus_results_dir = Path(args.opus_results)
    outputs_dir = Path(args.outputs)
    cases_dir = Path(args.cases)
    candidate_judges = args.judges.split(",")
    source_key = args.source_key
    concurrency = args.concurrency

    print(f"Calibrating {len(candidate_judges)} judge(s) against Opus baseline")
    print(f"Opus results: {opus_results_dir}")

    with OpenRouterClient() as client:
        candidate_results = run_judge_comparison(
            client, opus_results_dir, outputs_dir, cases_dir,
            candidate_judges, source_key=source_key, concurrency=concurrency,
        )

    opus_results = load_results(opus_results_dir)
    report = compare_judges(opus_results, candidate_results)
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
    gen.add_argument("--source-key", type=str, default="text_en", help="Source text key (text_en or text_fi)")
    gen.set_defaults(func=cmd_generate)

    # evaluate
    ev = subparsers.add_parser("evaluate", help="Evaluate generated outputs")
    ev.add_argument("--outputs", type=str, default="outputs", help="Generated outputs directory")
    ev.add_argument("--cases", type=str, default="eval_data", help="Eval cases directory")
    ev.add_argument("--results", type=str, default="results", help="Results directory")
    ev.add_argument("--judge", type=str, default=DEFAULT_JUDGE_MODEL, help="Judge model ID")
    ev.add_argument("--modes", type=str, default=None, help="Comma-separated failure mode IDs")
    ev.add_argument("--concurrency", type=int, default=10, help="Max concurrent judge calls")
    ev.add_argument("--source-key", type=str, default="text_en", help="Source text key (text_en or text_fi)")
    ev.set_defaults(func=cmd_evaluate)

    # report
    rep = subparsers.add_parser("report", help="Generate comparison report")
    rep.add_argument("--results", type=str, default="results", help="Results directory")
    rep.add_argument("--output", type=str, default=None, help="Save report to file")
    rep.set_defaults(func=cmd_report)

    # calibrate
    cal = subparsers.add_parser("calibrate", help="Compare candidate judges against Opus baseline")
    cal.add_argument("--opus-results", type=str, required=True, help="Opus results directory (ground truth)")
    cal.add_argument("--outputs", type=str, required=True, help="Generated outputs directory")
    cal.add_argument("--cases", type=str, default="eval_data", help="Eval cases directory")
    cal.add_argument("--judges", type=str, required=True, help="Comma-separated candidate judge model IDs")
    cal.add_argument("--concurrency", type=int, default=10, help="Max concurrent judge calls")
    cal.add_argument("--source-key", type=str, default="text_en", help="Source text key")
    cal.add_argument("--output", type=str, default=None, help="Save report to file")
    cal.set_defaults(func=cmd_calibrate)

    # list-modes
    lm = subparsers.add_parser("list-modes", help="List available failure modes")
    lm.set_defaults(func=cmd_list_modes)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
