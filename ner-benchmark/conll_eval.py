#!/usr/bin/env python3
"""
NER Benchmark — CoNLL-2003 Ground Truth Evaluation

Compares model outputs against human-annotated CoNLL-2003 NER ground truth.
"""

import json
import sys
from pathlib import Path
from collections import Counter, defaultdict

RESULTS_DIR = Path(__file__).parent / "results"
DATASETS_DIR = Path(__file__).parent / "datasets" / "conll2003"

# CoNLL type -> Anvil type mapping
CONLL_TYPE_MAP = {
    "PER": "PERSON",
    "ORG": "ORG",
    "LOC": "LOCATION",
    "MISC": "OTHER",
}


def load_ground_truth() -> dict[str, list[dict]]:
    """Load ground truth and group by document file.

    The fetch script grouped ~500 words into each file sequentially.
    We need to reconstruct which sentences went into which file.
    """
    gt = json.load(open(DATASETS_DIR / "_ground_truth.json"))

    # Reconstruct document groupings (same logic as fetch_data.py)
    doc_entities: dict[str, list[dict]] = {}
    current_words = 0
    doc_idx = 0

    for sentence in gt:
        tokens = sentence["sentence"].split()
        current_words += len(tokens)

        doc_name = f"conll2003_test_{doc_idx:03d}.txt"
        if doc_name not in doc_entities:
            doc_entities[doc_name] = []

        for ent in sentence["entities"]:
            anvil_type = CONLL_TYPE_MAP.get(ent["type"], "OTHER")
            doc_entities[doc_name].append({
                "name": ent["text"],
                "type": anvil_type,
            })

        if current_words >= 500:
            current_words = 0
            doc_idx += 1

    return doc_entities


def entity_key(name: str, etype: str) -> tuple[str, str]:
    return (name.strip().lower(), etype)


def entity_name_key(name: str) -> str:
    return name.strip().lower()


def load_model_conll_results() -> dict[str, list[dict]]:
    """Load all model results for conll2003 dataset."""
    results = {}
    for path in sorted(RESULTS_DIR.glob("*_conll2003.json")):
        parts = path.stem.split("_", 2)
        model_name = f"{parts[0]}_{parts[1]}"
        try:
            data = json.load(open(path))
            if not isinstance(data, list):
                data = [data]
            results[model_name] = data
        except (json.JSONDecodeError, FileNotFoundError):
            pass
    return results


def match_doc_results(model_results: list[dict], gt_docs: dict[str, list[dict]]) -> dict[str, list[dict]]:
    """Map model result documents to ground truth document names."""
    # Model results have documentId but we need to match to filenames
    # The documents were uploaded with their filenames as original_name
    # We need to match via the document names in the results

    # Build a mapping from the model results
    doc_map = {}
    for doc_result in model_results:
        doc_id = doc_result.get("documentId", "")
        entities = doc_result.get("entities", [])
        doc_map[doc_id] = entities

    return doc_map


def score_model(model_results: list[dict], gt_docs: dict[str, list[dict]]) -> dict:
    """Score a model against ground truth, matching at document level."""

    # We can't match by document ID directly (model has UUIDs, GT has filenames)
    # Instead, pool all entities and compare at corpus level

    # Collect all model entities (deduplicated per document)
    model_entities = set()
    for doc_result in model_results:
        for e in doc_result.get("entities", []):
            model_entities.add(entity_key(e["name"], e["type"]))

    # Collect all GT entities (deduplicated)
    gt_entities = set()
    gt_name_types = {}  # name -> type for type accuracy
    for doc_name, entities in gt_docs.items():
        for e in entities:
            key = entity_key(e["name"], e["type"])
            gt_entities.add(key)
            gt_name_types[entity_name_key(e["name"])] = e["type"]

    # Also build model name->type map
    model_name_types = {}
    for doc_result in model_results:
        for e in doc_result.get("entities", []):
            model_name_types[entity_name_key(e["name"])] = e["type"]

    tp = len(model_entities & gt_entities)
    fp = len(model_entities - gt_entities)
    fn = len(gt_entities - model_entities)

    precision = tp / (tp + fp) if (tp + fp) > 0 else 0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0

    # Type accuracy: for shared entity names, how often do types match?
    shared_names = set(gt_name_types.keys()) & set(model_name_types.keys())
    type_correct = sum(1 for n in shared_names if gt_name_types[n] == model_name_types[n])
    type_total = len(shared_names)
    type_acc = type_correct / type_total if type_total > 0 else 0

    # Per-type breakdown
    per_type = {}
    for etype in ["PERSON", "ORG", "LOCATION", "OTHER"]:
        gt_typed = {k for k in gt_entities if k[1] == etype}
        model_typed = {k for k in model_entities if k[1] == etype}
        t_tp = len(gt_typed & model_typed)
        t_fp = len(model_typed - gt_typed)
        t_fn = len(gt_typed - model_typed)
        t_p = t_tp / (t_tp + t_fp) if (t_tp + t_fp) > 0 else 0
        t_r = t_tp / (t_tp + t_fn) if (t_tp + t_fn) > 0 else 0
        t_f1 = 2 * t_p * t_r / (t_p + t_r) if (t_p + t_r) > 0 else 0
        per_type[etype] = {"precision": t_p, "recall": t_r, "f1": t_f1, "tp": t_tp, "fp": t_fp, "fn": t_fn}

    # Sample errors
    fps = sorted(model_entities - gt_entities)[:10]
    fns = sorted(gt_entities - model_entities)[:10]

    return {
        "precision": precision, "recall": recall, "f1": f1,
        "type_accuracy": type_acc,
        "tp": tp, "fp": fp, "fn": fn,
        "gt_total": len(gt_entities), "model_total": len(model_entities),
        "per_type": per_type,
        "false_positives": [{"name": n, "type": t} for n, t in fps],
        "false_negatives": [{"name": n, "type": t} for n, t in fns],
    }


def main():
    print("NER Benchmark — CoNLL-2003 Human Ground Truth Evaluation")
    print("=" * 70)

    # Load ground truth
    gt_docs = load_ground_truth()
    total_gt_entities = sum(len(ents) for ents in gt_docs.values())
    unique_gt = set()
    for ents in gt_docs.values():
        for e in ents:
            unique_gt.add(entity_key(e["name"], e["type"]))

    print(f"\nGround truth: {len(gt_docs)} documents, {total_gt_entities} entity mentions, {len(unique_gt)} unique entities")
    gt_types = Counter(e["type"] for ents in gt_docs.values() for e in ents)
    for t, c in gt_types.most_common():
        print(f"  {t}: {c}")

    # Load model results
    model_results = load_model_conll_results()
    print(f"\nModels: {', '.join(sorted(model_results.keys()))}")

    # Also score the oracle if available
    oracle_dir = RESULTS_DIR / "oracle"
    oracle_entities = set()
    if oracle_dir.exists():
        for f in oracle_dir.glob("conll2003_*.json"):
            data = json.load(open(f))
            for e in data.get("entities", []):
                oracle_entities.add(entity_key(e["name"], e["type"]))
        if oracle_entities:
            print(f"Oracle (Gemini 2.5 Pro): {len(oracle_entities)} unique entities on sampled docs")

    # Score each model
    scores = {}
    for model_name, results in sorted(model_results.items()):
        scores[model_name] = score_model(results, gt_docs)

    # Score oracle against GT too (only on its sampled docs)
    if oracle_entities:
        oracle_tp = len(oracle_entities & unique_gt)
        oracle_fp = len(oracle_entities - unique_gt)
        oracle_fn_sampled = len(unique_gt - oracle_entities)  # unfair - oracle only saw 5 docs
        oracle_p = oracle_tp / (oracle_tp + oracle_fp) if (oracle_tp + oracle_fp) > 0 else 0
        # Can't compute meaningful recall since oracle only saw 5 docs
        print(f"\nOracle precision vs GT: {oracle_p:.3f} ({oracle_tp} matches out of {len(oracle_entities)} oracle entities)")

    # Print results
    print(f"\n{'='*70}")
    print(" RESULTS vs HUMAN ANNOTATIONS (corpus-level, deduplicated)")
    print(f"{'='*70}")
    print(f"\nGround truth unique entities: {len(unique_gt)}")

    print(f"\n{'Model':<16} {'Precision':>10} {'Recall':>10} {'F1':>10} {'Type Acc':>10} {'Model#':>8} {'TP':>6} {'FP':>6} {'FN':>6}")
    print("-" * 90)

    for model in sorted(scores.keys()):
        s = scores[model]
        print(f"{model:<16} {s['precision']:>10.3f} {s['recall']:>10.3f} {s['f1']:>10.3f} {s['type_accuracy']:>10.3f} {s['model_total']:>8} {s['tp']:>6} {s['fp']:>6} {s['fn']:>6}")

    # Per-type breakdown
    print(f"\n{'='*70}")
    print(" PER-TYPE F1 SCORES")
    print(f"{'='*70}")

    types = ["PERSON", "ORG", "LOCATION", "OTHER"]
    print(f"\n{'Model':<16}" + "".join(f"{'  ' + t:>14}" for t in types))
    print("-" * 74)
    for model in sorted(scores.keys()):
        row = f"{model:<16}"
        for t in types:
            pt = scores[model]["per_type"].get(t, {})
            row += f"{pt.get('f1', 0):>14.3f}"
        print(row)

    # Error examples
    print(f"\n{'='*70}")
    print(" SAMPLE ERRORS (first 5 per model)")
    print(f"{'='*70}")

    for model in sorted(scores.keys()):
        s = scores[model]
        if s["false_positives"]:
            print(f"\n{model} — False Positives:")
            for e in s["false_positives"][:5]:
                print(f"  + \"{e['name']}\" ({e['type']})")
        if s["false_negatives"]:
            print(f"{model} — False Negatives:")
            for e in s["false_negatives"][:5]:
                print(f"  - \"{e['name']}\" ({e['type']})")

    # Save results
    output_path = RESULTS_DIR / "conll_gt_evaluation.json"
    json.dump(scores, open(output_path, "w"), indent=2, default=str)
    print(f"\nFull results saved to {output_path}")


if __name__ == "__main__":
    main()
