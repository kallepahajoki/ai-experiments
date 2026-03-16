#!/usr/bin/env python3
"""
Train and export all Qwen 3.5 model sizes for Finnish NER.

Runs sequentially: 0.8b → 2b → 4b → 9b
Each model is trained, then exported to GGUF and registered in Ollama.

Usage:
    python train_all.py
    python train_all.py --skip-export        # train only, export later
    python train_all.py --models 0.8b 4b     # specific sizes only
    python train_all.py --epochs 2            # override epoch count for all
"""

import argparse
import subprocess
import sys
import time
from pathlib import Path

MODELS = ["0.8b", "2b", "4b", "9b"]

EPOCHS = {
    "0.8b": 3,
    "2b":   3,
    "4b":   2,
    "9b":   2,
}

QUANT = {
    "0.8b": "Q8_0",
    "2b":   "Q8_0",
    "4b":   "Q4_K_M",
    "9b":   "Q4_K_M",
}


def run_step(description: str, cmd: list[str]) -> bool:
    print(f"\n{'='*60}")
    print(f"  {description}")
    print(f"  → {' '.join(cmd)}")
    print(f"{'='*60}\n")

    start = time.time()
    result = subprocess.run(cmd)
    elapsed = time.time() - start

    minutes = int(elapsed // 60)
    seconds = int(elapsed % 60)

    if result.returncode == 0:
        print(f"\n✓ {description} completed in {minutes}m {seconds}s")
        return True
    else:
        print(f"\n✗ {description} FAILED (exit {result.returncode}) after {minutes}m {seconds}s")
        return False


def main():
    parser = argparse.ArgumentParser(description="Train all Qwen 3.5 sizes for Finnish NER")
    parser.add_argument("--models", nargs="+", choices=MODELS, default=MODELS,
                        help="Which model sizes to train (default: all)")
    parser.add_argument("--epochs", type=int, default=None,
                        help="Override epoch count for all models")
    parser.add_argument("--skip-export", action="store_true",
                        help="Skip GGUF export and Ollama registration")
    parser.add_argument("--data-dir", default="./data")
    parser.add_argument("--output-dir", default="./output")
    parser.add_argument("--learning-rate", type=float, default=2e-4)
    parser.add_argument("--lora-rank", type=int, default=16)
    parser.add_argument("--resume", action="store_true",
                        help="Resume each model from latest checkpoint")
    parser.add_argument("--time-limit", type=float, default=None,
                        help="Time limit in hours per model")
    args = parser.parse_args()

    results = {}
    total_start = time.time()

    for model_size in args.models:
        epochs = args.epochs if args.epochs is not None else EPOCHS[model_size]

        # Train
        train_ok = run_step(
            f"Training qwen3.5-{model_size} ({epochs} epochs)",
            [
                sys.executable, "train.py",
                "--model", model_size,
                "--epochs", str(epochs),
                "--data-dir", args.data_dir,
                "--output-dir", args.output_dir,
                "--learning-rate", str(args.learning_rate),
                "--lora-rank", str(args.lora_rank),
            ]
            + (["--resume"] if args.resume else [])
            + (["--time-limit", str(args.time_limit)] if args.time_limit else []),
        )

        if not train_ok:
            results[model_size] = "TRAIN FAILED"
            print(f"\nSkipping export for {model_size} due to training failure")
            continue

        # Export
        if not args.skip_export:
            quant = QUANT[model_size]
            export_ok = run_step(
                f"Exporting qwen3.5-{model_size} to GGUF ({quant})",
                [
                    sys.executable, "export_to_ollama.py",
                    "--model", model_size,
                    "--quant", quant,
                    "--output-dir", args.output_dir,
                ],
            )

            if export_ok:
                # Register in Ollama
                gguf_dir = Path(args.output_dir) / f"qwen3.5-{model_size}-fi-ner-gguf"
                model_tag = f"qwen3.5-{model_size}-fi-ner"
                register_ok = run_step(
                    f"Registering {model_tag} in Ollama",
                    ["ollama", "create", model_tag, "-f", str(gguf_dir / "Modelfile")],
                )
                results[model_size] = "OK" if register_ok else "EXPORT OK, OLLAMA FAILED"
            else:
                results[model_size] = "EXPORT FAILED"
        else:
            results[model_size] = "TRAINED (export skipped)"

    # Summary
    total_elapsed = time.time() - total_start
    total_min = int(total_elapsed // 60)
    total_sec = int(total_elapsed % 60)

    print(f"\n{'='*60}")
    print(f"  SUMMARY — {total_min}m {total_sec}s total")
    print(f"{'='*60}")
    for model_size in args.models:
        status = results.get(model_size, "NOT RUN")
        print(f"  qwen3.5-{model_size:>4s}  {status}")
    print()


if __name__ == "__main__":
    main()
