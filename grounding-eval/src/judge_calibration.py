"""Compare alternative judges against Opus baseline."""

import asyncio
import json
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from collections import defaultdict

from .openrouter import OpenRouterClient
from .evaluate import EvalResult, load_results, parse_judge_response, save_results
from .failure_modes import FAILURE_MODES, get_judge_prompt, all_mode_ids


def build_judge_requests(
    opus_results: list[EvalResult],
    candidate_judge: str,
    source_key: str = "text_en",
    cases_dir: Path = Path("eval_data"),
) -> list[dict]:
    """Build requests to re-run all Opus judgements with a candidate judge."""
    # Load source texts
    cases = {}
    for p in cases_dir.glob("*.json"):
        with open(p) as f:
            case = json.load(f)
        cases[case["id"]] = case

    # Load subject model outputs
    outputs = {}
    for r in opus_results:
        key = (r.case_id, r.subject_model, r.run_index)
        if key not in outputs:
            outputs[key] = r  # we'll get the output content from the original eval

    requests = []
    for r in opus_results:
        case = cases[r.case_id]
        source_text = case["source"].get(source_key) or case["source"]["text_fi"]

        # We need the original model output — reconstruct from the judge prompt
        # Actually, we need to load the output files
        requests.append({
            "opus_result": r,
            "mode_id": r.failure_mode,
        })

    return requests


def run_judge_comparison(
    client: OpenRouterClient,
    opus_results_dir: Path,
    outputs_dir: Path,
    cases_dir: Path,
    candidate_judges: list[str],
    source_key: str = "text_en",
    concurrency: int = 10,
) -> dict[str, list[EvalResult]]:
    """Run candidate judges on the same inputs Opus judged, return results per judge."""
    opus_results = load_results(opus_results_dir)

    # Load source texts
    cases = {}
    for p in cases_dir.glob("*.json"):
        with open(p) as f:
            case = json.load(f)
        cases[case["id"]] = case

    # Load model outputs
    model_outputs = {}
    for p in outputs_dir.glob("*.json"):
        with open(p) as f:
            data = json.load(f)
        key = (data["case_id"], data["model"], data["run_index"])
        model_outputs[key] = data["content"]

    # Build work items: one per (opus_result, candidate_judge)
    all_candidate_results = {}

    for judge_model in candidate_judges:
        print(f"\n=== Judge: {judge_model} ===", flush=True)

        requests = []
        opus_refs = []
        for r in opus_results:
            case = cases[r.case_id]
            source_text = case["source"].get(source_key) or case["source"]["text_fi"]
            output_key = (r.case_id, r.subject_model, r.run_index)
            output_content = model_outputs.get(output_key, "")

            if not output_content:
                continue

            judge_prompt = get_judge_prompt(r.failure_mode, source_text, output_content)
            requests.append({
                "model": judge_model,
                "messages": [{"role": "user", "content": judge_prompt}],
                "temperature": 0.0,
                "max_tokens": 4096,
            })
            opus_refs.append(r)

        print(f"  Running {len(requests)} judge calls with concurrency={concurrency}", flush=True)
        completion_results = asyncio.run(
            client.batch_complete(requests, concurrency=concurrency)
        )

        candidate_results = []
        for opus_r, comp_result in zip(opus_refs, completion_results):
            verdict = parse_judge_response(opus_r.failure_mode, comp_result.content)
            candidate_results.append(EvalResult(
                case_id=opus_r.case_id,
                subject_model=opus_r.subject_model,
                run_index=opus_r.run_index,
                judge_model=judge_model,
                failure_mode=opus_r.failure_mode,
                verdict=verdict,
                raw_judge_response=comp_result.content,
                judge_prompt_tokens=comp_result.prompt_tokens,
                judge_completion_tokens=comp_result.completion_tokens,
                judge_cost_usd=comp_result.cost_usd,
                timestamp=time.time(),
            ))

        all_candidate_results[judge_model] = candidate_results
        detected = sum(1 for r in candidate_results if r.verdict.detected)
        cost = sum(r.judge_cost_usd or 0 for r in candidate_results)
        print(f"  Done: {detected}/{len(candidate_results)} detected, cost: ${cost:.2f}", flush=True)

    return all_candidate_results


def compare_judges(
    opus_results: list[EvalResult],
    candidate_results: dict[str, list[EvalResult]],
) -> str:
    """Compare candidate judges against Opus baseline."""
    # Index Opus results
    opus_lookup = {}
    for r in opus_results:
        key = (r.case_id, r.subject_model, r.run_index, r.failure_mode)
        opus_lookup[key] = r.verdict.detected

    lines = ["# Judge Calibration Report\n"]
    lines.append(f"**Baseline:** anthropic/claude-opus-4.6 ({len(opus_results)} judgements)\n")

    for judge_model, results in candidate_results.items():
        agree = 0
        disagree = 0
        false_pos = 0  # candidate says detected, opus says no
        false_neg = 0  # candidate says no, opus says detected
        total_cost = 0.0

        per_mode_stats = defaultdict(lambda: {"agree": 0, "disagree": 0, "fp": 0, "fn": 0, "total": 0})

        for r in results:
            key = (r.case_id, r.subject_model, r.run_index, r.failure_mode)
            opus_detected = opus_lookup.get(key)
            if opus_detected is None:
                continue

            cand_detected = r.verdict.detected
            total_cost += r.judge_cost_usd or 0

            mode_stats = per_mode_stats[r.failure_mode]
            mode_stats["total"] += 1

            if cand_detected == opus_detected:
                agree += 1
                mode_stats["agree"] += 1
            else:
                disagree += 1
                mode_stats["disagree"] += 1
                if cand_detected and not opus_detected:
                    false_pos += 1
                    mode_stats["fp"] += 1
                else:
                    false_neg += 1
                    mode_stats["fn"] += 1

        total = agree + disagree
        agreement_rate = agree / total if total else 0

        lines.append(f"\n## {judge_model}")
        lines.append(f"  Agreement with Opus: **{agreement_rate:.1%}** ({agree}/{total})")
        lines.append(f"  False positives (candidate flags, Opus doesn't): {false_pos}")
        lines.append(f"  False negatives (candidate misses, Opus catches): {false_neg}")
        lines.append(f"  Total cost: **${total_cost:.2f}**")

        # Per-mode breakdown
        lines.append(f"\n  Per failure mode:")
        for mode_id in all_mode_ids():
            s = per_mode_stats[mode_id]
            if s["total"] == 0:
                continue
            mode_agreement = s["agree"] / s["total"] if s["total"] else 0
            fm = FAILURE_MODES[mode_id]
            flag = ""
            if mode_agreement < 0.7:
                flag = " ⚠️"
            lines.append(
                f"    {fm.name:40} {mode_agreement:5.0%} agree  "
                f"(FP:{s['fp']} FN:{s['fn']}){flag}"
            )

    return "\n".join(lines)
