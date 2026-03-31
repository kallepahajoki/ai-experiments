"""Generate LLM outputs from source documents for evaluation."""

import json
import time
from dataclasses import dataclass, asdict
from pathlib import Path

from .openrouter import OpenRouterClient, CompletionResult


@dataclass
class GeneratedOutput:
    case_id: str
    model: str
    run_index: int
    content: str
    prompt_tokens: int
    completion_tokens: int
    cost_usd: float | None
    latency_ms: float
    timestamp: float


def load_eval_case(path: Path) -> dict:
    with open(path) as f:
        return json.load(f)


def load_all_cases(eval_dir: Path) -> list[dict]:
    cases = []
    for p in sorted(eval_dir.glob("*.json")):
        cases.append(load_eval_case(p))
    return cases


def build_messages(case: dict, source_key: str = "text_en") -> list[dict]:
    source_text = case["source"].get(source_key) or case["source"]["text_fi"]
    task_prompt = case.get("task_prompt_fi") if source_key == "text_fi" else case["task_prompt"]
    if task_prompt is None:
        task_prompt = case["task_prompt"]

    return [
        {
            "role": "user",
            "content": f"{task_prompt}\n\n---\n\n{source_text}",
        }
    ]


def generate_outputs(
    client: OpenRouterClient,
    case: dict,
    models: list[str],
    runs_per_model: int = 3,
    temperature: float = 0.3,
    source_key: str = "text_en",
) -> list[GeneratedOutput]:
    messages = build_messages(case, source_key=source_key)
    outputs = []

    for model in models:
        for run_idx in range(runs_per_model):
            try:
                result = client.complete(
                    model=model,
                    messages=messages,
                    temperature=temperature,
                )
            except Exception as e:
                print(f"  ERROR {model} run {run_idx}: {e}")
                continue
            outputs.append(GeneratedOutput(
                case_id=case["id"],
                model=model,
                run_index=run_idx,
                content=result.content,
                prompt_tokens=result.prompt_tokens,
                completion_tokens=result.completion_tokens,
                cost_usd=result.cost_usd,
                latency_ms=result.latency_ms,
                timestamp=time.time(),
            ))

    return outputs


def save_outputs(outputs: list[GeneratedOutput], output_dir: Path):
    output_dir.mkdir(parents=True, exist_ok=True)
    for output in outputs:
        filename = f"{output.case_id}__{output.model.replace('/', '_')}__{output.run_index}.json"
        path = output_dir / filename
        with open(path, "w") as f:
            json.dump(asdict(output), f, indent=2)


def load_outputs(output_dir: Path) -> list[GeneratedOutput]:
    outputs = []
    for p in sorted(output_dir.glob("*.json")):
        with open(p) as f:
            data = json.load(f)
        outputs.append(GeneratedOutput(**data))
    return outputs
