#!/usr/bin/env python3
"""
Sample Finnish NER benchmark documents for Atlas upload.

Selects a representative subset from the large annotated corpora
to keep benchmark runs tractable (~120 docs total).
"""

import json
import random
import shutil
from pathlib import Path

random.seed(42)

BASE_DIR = Path(__file__).parent / "datasets-fi"
SAMPLE_DIR = Path(__file__).parent / "datasets-fi-sample"


def sample_annotated_dataset(name: str, source_dir: Path, target_dir: Path, n: int):
    """Sample n documents from an annotated dataset, keeping ground truth."""
    txt_files = sorted(source_dir.glob("*.txt"))
    if not txt_files:
        print(f"  No .txt files in {source_dir}")
        return

    sampled = random.sample(txt_files, min(n, len(txt_files)))

    target_dir.mkdir(parents=True, exist_ok=True)

    total_entities = 0
    for txt_file in sampled:
        # Copy document
        shutil.copy2(txt_file, target_dir / txt_file.name)

        # Copy ground truth if it exists
        gt_file = txt_file.with_name(txt_file.stem + "_ground_truth.json")
        if gt_file.exists():
            shutil.copy2(gt_file, target_dir / gt_file.name)
            gt_data = json.loads(gt_file.read_text(encoding="utf-8"))
            total_entities += sum(len(item["entities"]) for item in gt_data)

    print(f"  {name}: sampled {len(sampled)}/{len(txt_files)} docs, {total_entities} entities")


def main():
    # Clean previous sample
    if SAMPLE_DIR.exists():
        shutil.rmtree(SAMPLE_DIR)

    # Turku NER: 60 docs from 800
    sample_annotated_dataset(
        "turku-ner",
        BASE_DIR / "turku-ner",
        SAMPLE_DIR / "turku-ner",
        n=60,
    )

    # FiNER: 60 docs from 3947
    sample_annotated_dataset(
        "finer-digitoday",
        BASE_DIR / "finer-digitoday",
        SAMPLE_DIR / "finer-digitoday",
        n=60,
    )

    # Wikipedia: all 21
    wiki_src = BASE_DIR / "wikipedia-fi"
    wiki_dst = SAMPLE_DIR / "wikipedia-fi"
    wiki_dst.mkdir(parents=True, exist_ok=True)
    wiki_files = list(wiki_src.glob("*.txt"))
    for f in wiki_files:
        shutil.copy2(f, wiki_dst / f.name)
    print(f"  wikipedia-fi: all {len(wiki_files)} docs (no ground truth)")

    # Summary
    print(f"\nTotal sample:")
    total = 0
    for d in sorted(SAMPLE_DIR.iterdir()):
        if d.is_dir():
            n = len(list(d.glob("*.txt")))
            total += n
            print(f"  {d.name}: {n} docs")
    print(f"  TOTAL: {total} docs")


if __name__ == "__main__":
    main()
