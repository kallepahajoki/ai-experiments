"""Evaluate LLM outputs against source documents for failure modes."""

import asyncio
import json
import time
from dataclasses import dataclass, asdict
from pathlib import Path

from .openrouter import OpenRouterClient
from .failure_modes import FAILURE_MODES, get_judge_prompt, JudgeVerdict, all_mode_ids
from .generate import GeneratedOutput, load_eval_case


@dataclass
class EvalResult:
    case_id: str
    subject_model: str
    run_index: int
    judge_model: str
    failure_mode: str
    verdict: JudgeVerdict
    raw_judge_response: str
    judge_prompt_tokens: int
    judge_completion_tokens: int
    judge_cost_usd: float | None
    timestamp: float


def parse_judge_response(mode_id: str, raw: str) -> JudgeVerdict:
    """Parse judge JSON response into a JudgeVerdict."""
    # Strip markdown code fences if present
    if raw is None:
        return JudgeVerdict(
            failure_mode=mode_id,
            detected=False,
            confidence=0.0,
            evidence="[ERROR] Judge returned null response",
            severity="unknown",
        )
    text = raw.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        lines = lines[1:]  # remove opening fence
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines)

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return JudgeVerdict(
            failure_mode=mode_id,
            detected=False,
            confidence=0.0,
            evidence=f"[PARSE ERROR] Could not parse judge response: {raw[:200]}",
            severity="unknown",
        )

    fm = FAILURE_MODES[mode_id]

    # Each mode uses a different key for the detected boolean
    detected_keys = {
        "fabricated_addition": "fabricated_additions_found",
        "contradiction": "contradiction_found",
        "entity_substitution": "substitution_found",
        "numerical_distortion": "distortion_found",
        "temporal_drift": "drift_found",
        "hedging_removal": "hedging_removal_found",
        "hedging_addition": "hedging_addition_found",
        "framing_shift": "framing_shift_found",
        "scope_creep": "scope_creep_found",
        "omission": "critical_omission_found",
        "composite_conflation": "conflation_found",
        "instruction_leakage": "leakage_found",
    }

    detected_key = detected_keys.get(mode_id, "detected")
    detected = data.get(detected_key, False)
    confidence = data.get("confidence", 0.5)
    evidence = data.get("evidence", "")

    return JudgeVerdict(
        failure_mode=mode_id,
        detected=bool(detected),
        confidence=float(confidence),
        evidence=str(evidence),
        severity=fm.severity,
    )


def evaluate_output(
    client: OpenRouterClient,
    case: dict,
    output: GeneratedOutput,
    judge_model: str,
    mode_ids: list[str] | None = None,
    source_key: str = "text_en",
) -> list[EvalResult]:
    """Evaluate a single generated output for all (or specified) failure modes."""
    source_text = case["source"].get(source_key) or case["source"]["text_fi"]
    modes = mode_ids or all_mode_ids()
    results = []

    for mode_id in modes:
        judge_prompt = get_judge_prompt(mode_id, source_text, output.content)
        messages = [{"role": "user", "content": judge_prompt}]

        result = client.complete(
            model=judge_model,
            messages=messages,
            temperature=0.0,
            max_tokens=4096,
        )

        verdict = parse_judge_response(mode_id, result.content)
        results.append(EvalResult(
            case_id=output.case_id,
            subject_model=output.model,
            run_index=output.run_index,
            judge_model=judge_model,
            failure_mode=mode_id,
            verdict=verdict,
            raw_judge_response=result.content,
            judge_prompt_tokens=result.prompt_tokens,
            judge_completion_tokens=result.completion_tokens,
            judge_cost_usd=result.cost_usd,
            timestamp=time.time(),
        ))

    return results


def evaluate_all(
    client: OpenRouterClient,
    cases_dir: Path,
    outputs: list[GeneratedOutput],
    judge_model: str,
    mode_ids: list[str] | None = None,
    concurrency: int = 10,
    source_key: str = "text_en",
) -> list[EvalResult]:
    """Evaluate all generated outputs concurrently."""
    cases = {}
    for p in cases_dir.glob("*.json"):
        case = load_eval_case(p)
        cases[case["id"]] = case

    modes = mode_ids or all_mode_ids()

    # Build all (output, mode) pairs as batch requests
    work_items = []
    for output in outputs:
        case = cases[output.case_id]
        source_text = case["source"].get(source_key) or case["source"]["text_fi"]
        for mode_id in modes:
            judge_prompt = get_judge_prompt(mode_id, source_text, output.content)
            work_items.append({
                "request": {
                    "model": judge_model,
                    "messages": [{"role": "user", "content": judge_prompt}],
                    "temperature": 0.0,
                    "max_tokens": 4096,
                },
                "output": output,
                "mode_id": mode_id,
            })

    total = len(work_items)
    print(f"  Running {total} judge calls with concurrency={concurrency}", flush=True)

    # Run all requests concurrently
    requests = [w["request"] for w in work_items]
    completion_results = asyncio.run(
        client.batch_complete(requests, concurrency=concurrency)
    )

    # Parse results
    all_results = []
    detected_count = 0
    for item, comp_result in zip(work_items, completion_results):
        output = item["output"]
        mode_id = item["mode_id"]
        verdict = parse_judge_response(mode_id, comp_result.content)
        if verdict.detected:
            detected_count += 1

        all_results.append(EvalResult(
            case_id=output.case_id,
            subject_model=output.model,
            run_index=output.run_index,
            judge_model=judge_model,
            failure_mode=mode_id,
            verdict=verdict,
            raw_judge_response=comp_result.content,
            judge_prompt_tokens=comp_result.prompt_tokens,
            judge_completion_tokens=comp_result.completion_tokens,
            judge_cost_usd=comp_result.cost_usd,
            timestamp=time.time(),
        ))

    print(f"  Done: {detected_count}/{total} failures detected", flush=True)
    return all_results


def save_results(results: list[EvalResult], output_dir: Path):
    output_dir.mkdir(parents=True, exist_ok=True)
    for r in results:
        filename = (
            f"{r.case_id}__{r.subject_model.replace('/', '_')}"
            f"__{r.run_index}__{r.failure_mode}.json"
        )
        path = output_dir / filename
        data = asdict(r)
        with open(path, "w") as f:
            json.dump(data, f, indent=2)


def load_results(results_dir: Path) -> list[EvalResult]:
    results = []
    for p in sorted(results_dir.glob("*.json")):
        with open(p) as f:
            data = json.load(f)
        data["verdict"] = JudgeVerdict(**data["verdict"])
        results.append(EvalResult(**data))
    return results
