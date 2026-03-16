#!/usr/bin/env python3
"""
Prepare Finnish NER training data for Qwen finetuning.

Converts annotated Turku NER + FiNER ground truth into
instruction-tuning JSONL format (chat messages).

Usage:
    python prepare_data.py [--datasets-dir ../datasets-fi] [--output-dir ./data]

The datasets-fi directory should be created by running fetch_finnish_data.py
from the ner-benchmark directory first.
"""

import json
import random
import argparse
from pathlib import Path


SYSTEM_PROMPT = """Olet nimettyjen entiteettien tunnistaja (NER). Poimi tekstistä kaikki nimetyt entiteetit.

Palauta JSON-lista, jossa jokainen entiteetti on muodossa:
{"text": "entiteetin teksti", "type": "tyyppi"}

Tuetut tyypit: PER (henkilö), ORG (organisaatio), LOC (paikka), PRO (tuote), EVENT (tapahtuma), DATE (päivämäärä).

Jos entiteettejä ei löydy, palauta tyhjä lista: []
Palauta VAIN JSON, ei mitään muuta."""


def load_ground_truth_files(dataset_dir: Path) -> list:
    """Load all ground truth JSON files from a dataset directory."""
    examples = []
    for gt_file in sorted(dataset_dir.glob("*_ground_truth.json")):
        data = json.loads(gt_file.read_text(encoding="utf-8"))
        for item in data:
            sentence = item["sentence"]
            entities = item["entities"]
            if sentence.strip():
                examples.append({"text": sentence, "entities": entities})
    return examples


def to_chat_format(example: dict) -> dict:
    """Convert a single example to chat instruction format."""
    return {
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": example["text"]},
            {
                "role": "assistant",
                "content": json.dumps(
                    example["entities"], ensure_ascii=False
                ),
            },
        ]
    }


def main():
    parser = argparse.ArgumentParser(description="Prepare Finnish NER finetune data")
    parser.add_argument("--datasets-dir", default="./datasets-fi",
                        help="Path to datasets-fi directory with ground truth")
    parser.add_argument("--output-dir", default="./data",
                        help="Output directory for train/eval JSONL")
    parser.add_argument("--train-ratio", type=float, default=0.85)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    random.seed(args.seed)
    datasets_dir = Path(args.datasets_dir)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    all_examples = []

    # Load Turku NER
    turku_dir = datasets_dir / "turku-ner"
    if turku_dir.exists():
        turku = load_ground_truth_files(turku_dir)
        print(f"Loaded {len(turku)} examples from Turku NER")
        all_examples.extend(turku)

    # Load FiNER
    finer_dir = datasets_dir / "finer-digitoday"
    if finer_dir.exists():
        finer = load_ground_truth_files(finer_dir)
        print(f"Loaded {len(finer)} examples from FiNER")
        all_examples.extend(finer)

    if not all_examples:
        print(f"No ground truth found in {datasets_dir}")
        return

    # Split by entity presence
    with_entities = [e for e in all_examples if e["entities"]]
    without_entities = [e for e in all_examples if not e["entities"]]

    print(f"\nWith entities: {len(with_entities)}")
    print(f"Without entities: {len(without_entities)}")

    # Keep ~10% negative examples
    neg_count = max(1, len(with_entities) // 10)
    random.shuffle(without_entities)
    selected = with_entities + without_entities[:neg_count]
    random.shuffle(selected)

    # Convert to chat format
    chat_data = [to_chat_format(ex) for ex in selected]

    # Split
    split_idx = int(len(chat_data) * args.train_ratio)
    train_data = chat_data[:split_idx]
    eval_data = chat_data[split_idx:]

    # Save
    train_path = output_dir / "train.jsonl"
    eval_path = output_dir / "eval.jsonl"

    with open(train_path, "w", encoding="utf-8") as f:
        for item in train_data:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")

    with open(eval_path, "w", encoding="utf-8") as f:
        for item in eval_data:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")

    print(f"\nPrepared {len(train_data)} train + {len(eval_data)} eval examples")
    print(f"Saved to {output_dir}")


if __name__ == "__main__":
    main()
