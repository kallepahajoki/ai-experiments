"""
Generate reasoning chains for Ward thinker training data.

Reads train.jsonl, generates a <think> reasoning chain for each example
using an LLM API, and writes train_thinker.jsonl with the added "thinking" field.

Usage:
    python data/generate_thinking.py
    python data/generate_thinking.py --input data/train.jsonl --output data/train_thinker.jsonl
    python data/generate_thinking.py --dry-run              # preview prompts without calling API
    python data/generate_thinking.py --resume               # skip examples that already have thinking

Requires:
    OPENROUTER_API_KEY environment variable (or pass via --api-key)
    pip install openai
"""

import argparse
import json
import os
import sys
import time

GENERATION_PROMPT = """\
You are helping train a security classifier for an AI agent platform called Anvil.

Given the input text and the correct classification, write a 2-4 sentence reasoning chain \
explaining WHY this input is {verdict}/{category}. The reasoning should:

1. Identify the specific signals or patterns in the input that indicate the classification
2. Explain why this is {category} and NOT a similar category (e.g., why prompt_injection not agent_manipulation)
3. For SAFE inputs, explain why it might look suspicious but is actually legitimate

Be specific to this input — don't be generic. Reference actual words, patterns, or structures in the text.

Input: {input}
Correct verdict: {verdict}
Correct category: {category}
Correct reason: {reason}

Write ONLY the reasoning chain (2-4 sentences), nothing else."""

DEFAULT_MODEL = "moonshotai/kimi-k2.5"


def load_jsonl(path: str) -> list[dict]:
    examples = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                examples.append(json.loads(line))
    return examples


def write_jsonl(path: str, examples: list[dict]) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for ex in examples:
            f.write(json.dumps(ex, ensure_ascii=False) + "\n")


def generate_thinking(client, example: dict, model: str) -> str:
    """Call LLM API to generate a reasoning chain for one example."""
    prompt = GENERATION_PROMPT.format(
        input=example["input"],
        verdict=example["verdict"],
        category=example["category"],
        reason=example["reason"],
    )

    response = client.chat.completions.create(
        model=model,
        max_tokens=2048,
        messages=[{"role": "user", "content": prompt}],
    )
    content = response.choices[0].message.content
    if content is None:
        raise ValueError(f"API returned None content (finish_reason={response.choices[0].finish_reason})")
    return content.strip()


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate reasoning chains for Ward thinker training")
    parser.add_argument("--input", default="data/train.jsonl", help="Input JSONL file")
    parser.add_argument("--output", default="data/train_thinker.jsonl", help="Output JSONL file with thinking")
    parser.add_argument("--dry-run", action="store_true", help="Preview prompts without calling API")
    parser.add_argument("--resume", action="store_true", help="Skip examples that already have thinking in output")
    parser.add_argument("--batch-size", type=int, default=10, help="Save progress every N examples")
    parser.add_argument("--model", default=DEFAULT_MODEL, help=f"Model to use (default: {DEFAULT_MODEL})")
    parser.add_argument("--api-key", default=None, help="API key (default: OPENROUTER_API_KEY env var)")
    parser.add_argument("--base-url", default="https://openrouter.ai/api/v1", help="API base URL")
    args = parser.parse_args()

    examples = load_jsonl(args.input)
    print(f"Loaded {len(examples)} examples from {args.input}")
    print(f"Model: {args.model}")

    # If resuming, load existing output and skip already-processed examples
    existing = {}
    if args.resume and os.path.exists(args.output):
        existing_list = load_jsonl(args.output)
        for ex in existing_list:
            if "thinking" in ex:
                existing[ex["input"]] = ex
        print(f"  Resuming: {len(existing)} examples already have thinking chains")

    if args.dry_run:
        for ex in examples[:3]:
            prompt = GENERATION_PROMPT.format(
                input=ex["input"],
                verdict=ex["verdict"],
                category=ex["category"],
                reason=ex["reason"],
            )
            print(f"\n{'='*60}")
            print(prompt)
        print(f"\n{'='*60}")
        print(f"Dry run: would process {len(examples)} examples")
        return

    api_key = args.api_key or os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        print("Error: set OPENROUTER_API_KEY or pass --api-key", file=sys.stderr)
        sys.exit(1)

    from openai import OpenAI
    client = OpenAI(api_key=api_key, base_url=args.base_url)

    results = []
    errors = 0
    t_start = time.perf_counter()

    for i, ex in enumerate(examples):
        # Skip if already processed
        if ex["input"] in existing:
            results.append(existing[ex["input"]])
            continue

        try:
            thinking = generate_thinking(client, ex, args.model)
            ex_with_thinking = {**ex, "thinking": thinking}
            results.append(ex_with_thinking)

            if (i + 1) % 10 == 0:
                elapsed = time.perf_counter() - t_start
                rate = (i + 1) / elapsed
                remaining = (len(examples) - i - 1) / rate if rate > 0 else 0
                print(f"  [{i + 1}/{len(examples)}] {ex['verdict']}/{ex['category']}  "
                      f"({rate:.1f}/s, ~{remaining:.0f}s remaining)")

        except Exception as e:
            print(f"  Error on example {i}: {e}", file=sys.stderr)
            results.append(ex)
            errors += 1
            time.sleep(2)

        # Save progress periodically
        if (i + 1) % args.batch_size == 0:
            write_jsonl(args.output, results)

    write_jsonl(args.output, results)

    with_thinking = sum(1 for r in results if "thinking" in r)
    elapsed = time.perf_counter() - t_start
    print(f"\nDone: {with_thinking}/{len(results)} examples have reasoning chains "
          f"({errors} errors, {elapsed:.0f}s)")
    print(f"Written to: {args.output}")


if __name__ == "__main__":
    main()
