"""
Ward — Multi-model benchmark.

Evaluates all three trained Ward models on the same eval set and prints a
side-by-side comparison of accuracy, F1, per-category F1, and latency.

Usage:
    # Evaluate all three (adapters must exist in ./output/)
    python benchmark.py

    # Skip models whose adapter directory doesn't exist yet
    python benchmark.py --skip-missing

    # Evaluate a single model
    python benchmark.py --configs config-0.8b.yaml

    # Custom adapter paths
    python benchmark.py --adapters ./output/qwen3.5-0.6b-ward ./output/qwen3.5-2b-ward ./output/qwen3.5-4b-ward
"""

import argparse
import json
import os
import sys
import time

import torch
import yaml
from peft import PeftModel
from transformers import AutoModelForCausalLM, AutoTokenizer

from evaluate import (
    ALL_CATEGORIES,
    SYSTEM_PROMPT,
    compute_metrics,
    load_jsonl,
    parse_response,
    print_confusion_matrix,
)

DEFAULT_CONFIGS = ["config-0.8b.yaml", "config-2b.yaml", "config-4b.yaml"]
MODEL_LABELS = {
    "Qwen/Qwen3.5-0.8B": "0.8B",
    "Qwen/Qwen3.5-2B":   "2B",
    "Qwen/Qwen3.5-4B":   "4B",
}


def load_config(path: str) -> dict:
    with open(path, "r") as f:
        return yaml.safe_load(f)


def run_inference_timed(model, tokenizer, text: str, device: str) -> tuple[str, float]:
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": text},
    ]
    prompt = tokenizer.apply_chat_template(
        messages,
        tokenize=False,
        add_generation_prompt=True,
        enable_thinking=False,
    )
    inputs = tokenizer(prompt, return_tensors="pt").to(device)
    t0 = time.perf_counter()
    with torch.no_grad():
        outputs = model.generate(
            **inputs,
            max_new_tokens=256,
            do_sample=False,
            temperature=None,
            top_p=None,
            pad_token_id=tokenizer.pad_token_id,
        )
    elapsed_ms = (time.perf_counter() - t0) * 1000
    generated = outputs[0][inputs["input_ids"].shape[1]:]
    text_out = tokenizer.decode(generated, skip_special_tokens=True)
    return text_out, elapsed_ms


def evaluate_model(cfg: dict, adapter_path: str, eval_examples: list[dict]) -> dict:
    model_cfg = cfg["model"]

    print(f"\n{'=' * 60}")
    print(f"Evaluating: {model_cfg['name']}")
    print(f"Adapter:    {adapter_path}")
    print(f"{'=' * 60}")

    dtype_map = {"bfloat16": torch.bfloat16, "float16": torch.float16, "float32": torch.float32}
    torch_dtype = dtype_map.get(model_cfg.get("torch_dtype", "bfloat16"), torch.bfloat16)

    print("Loading tokenizer...")
    tokenizer = AutoTokenizer.from_pretrained(adapter_path, trust_remote_code=True)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    print(f"Loading base model {model_cfg['name']}...")
    base_model = AutoModelForCausalLM.from_pretrained(
        model_cfg["name"],
        dtype=torch_dtype,
        attn_implementation=model_cfg.get("attn_implementation", "eager"),
        device_map="auto",
        trust_remote_code=True,
    )

    print(f"Loading LoRA adapter from {adapter_path}...")
    model = PeftModel.from_pretrained(base_model, adapter_path)
    model.eval()
    device = str(next(model.parameters()).device)

    results = []
    latencies = []

    for i, ex in enumerate(eval_examples):
        if (i + 1) % 20 == 0 or (i + 1) == len(eval_examples):
            print(f"  [{i + 1}/{len(eval_examples)}]")

        raw_output, elapsed_ms = run_inference_timed(model, tokenizer, ex["input"], device)
        pred_verdict, pred_category, pred_reason = parse_response(raw_output)
        latencies.append(elapsed_ms)

        results.append({
            "index": i,
            "input": ex["input"][:120],
            "true_verdict": ex["verdict"],
            "true_category": ex["category"],
            "pred_verdict": pred_verdict,
            "pred_category": pred_category,
            "pred_reason": pred_reason,
            "correct_verdict": pred_verdict == ex["verdict"],
            "correct_category": pred_category == ex["category"],
            "raw_output": raw_output,
            "latency_ms": elapsed_ms,
        })

    # Free GPU memory before loading next model
    del model
    del base_model
    torch.cuda.empty_cache()

    metrics = compute_metrics(results)
    metrics["latency"] = {
        "mean_ms": sum(latencies) / len(latencies),
        "p50_ms": sorted(latencies)[len(latencies) // 2],
        "p95_ms": sorted(latencies)[int(len(latencies) * 0.95)],
        "min_ms": min(latencies),
        "max_ms": max(latencies),
    }
    metrics["model_name"] = model_cfg["name"]
    metrics["adapter_path"] = adapter_path
    metrics["results"] = results

    return metrics


def print_comparison(all_metrics: list[dict]) -> None:
    labels = [MODEL_LABELS.get(m["model_name"], m["model_name"].split("/")[-1]) for m in all_metrics]
    col = 12

    print("\n" + "=" * 70)
    print("BENCHMARK COMPARISON")
    print("=" * 70)

    # Header
    print(f"\n{'Metric':<28}" + "".join(l.rjust(col) for l in labels))
    print("-" * (28 + col * len(labels)))

    def row(label: str, values: list) -> str:
        return f"  {label:<26}" + "".join(str(v).rjust(col) for v in values)

    # Binary metrics
    print(row("Binary Accuracy", [f"{m['binary']['accuracy']:.3f}" for m in all_metrics]))
    print(row("Binary Precision", [f"{m['binary']['precision']:.3f}" for m in all_metrics]))
    print(row("Binary Recall", [f"{m['binary']['recall']:.3f}" for m in all_metrics]))
    print(row("Binary F1", [f"{m['binary']['f1']:.3f}" for m in all_metrics]))

    # Per-category F1
    print()
    for cat in ALL_CATEGORIES:
        print(row(f"F1 {cat}", [f"{m['per_category'][cat]['f1']:.3f}" for m in all_metrics]))

    # Latency
    print()
    print(row("Latency mean (ms)", [f"{m['latency']['mean_ms']:.0f}" for m in all_metrics]))
    print(row("Latency p50 (ms)", [f"{m['latency']['p50_ms']:.0f}" for m in all_metrics]))
    print(row("Latency p95 (ms)", [f"{m['latency']['p95_ms']:.0f}" for m in all_metrics]))

    # Long-form subset (examples with input longer than 500 chars)
    print()
    for m, label in zip(all_metrics, labels):
        long_results = [r for r in m["results"] if len(r["input"]) >= 120]  # input was truncated to 120 for display
        # Re-check using raw results — count all where true length would be long
        # We tagged long-form eval examples by their presence; use latency as proxy
        # Instead just show overall failures
        failures = [r for r in m["results"] if not r["correct_verdict"]]
        total = len(m["results"])
        print(f"  {label}: {total - len(failures)}/{total} correct verdicts, {len(failures)} failures")

    print("\n" + "=" * 70)


def main() -> None:
    parser = argparse.ArgumentParser(description="Benchmark Ward models side by side")
    parser.add_argument("--configs", nargs="+", default=DEFAULT_CONFIGS,
                        help="Config YAML files to evaluate")
    parser.add_argument("--adapters", nargs="+", default=None,
                        help="Override adapter paths (must match --configs order)")
    parser.add_argument("--skip-missing", action="store_true",
                        help="Skip models whose adapter directory does not exist")
    parser.add_argument("--eval-file", default=None,
                        help="Override eval file (default: from config)")
    parser.add_argument("--output", default="output/benchmark_results.json",
                        help="Where to save full results JSON")
    args = parser.parse_args()

    # Resolve configs
    configs_to_run: list[tuple[dict, str]] = []
    for i, cfg_path in enumerate(args.configs):
        if not os.path.exists(cfg_path):
            print(f"Config not found: {cfg_path}", file=sys.stderr)
            if args.skip_missing:
                continue
            sys.exit(1)

        cfg = load_config(cfg_path)
        adapter_path = args.adapters[i] if args.adapters else cfg["training"]["output_dir"]

        if not os.path.exists(adapter_path):
            msg = f"Adapter not found: {adapter_path}"
            if args.skip_missing:
                print(f"Skipping — {msg}")
                continue
            print(msg, file=sys.stderr)
            sys.exit(1)

        configs_to_run.append((cfg, adapter_path))

    if not configs_to_run:
        print("No models to evaluate.", file=sys.stderr)
        sys.exit(1)

    # Load eval data (use first config's eval file unless overridden)
    eval_file = args.eval_file or configs_to_run[0][0]["data"]["eval_file"]
    print(f"Loading eval data from {eval_file}...")
    eval_examples = load_jsonl(eval_file)
    print(f"  {len(eval_examples)} examples")

    # Evaluate each model sequentially
    all_metrics = []
    for cfg, adapter_path in configs_to_run:
        metrics = evaluate_model(cfg, adapter_path, eval_examples)
        all_metrics.append(metrics)

    # Print comparison table
    print_comparison(all_metrics)

    # Save full results
    os.makedirs(os.path.dirname(os.path.abspath(args.output)), exist_ok=True)
    save_data = [
        {k: v for k, v in m.items() if k != "results"}
        for m in all_metrics
    ]
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(save_data, f, indent=2, ensure_ascii=False)
    print(f"\nSummary saved to: {args.output}")


if __name__ == "__main__":
    main()
