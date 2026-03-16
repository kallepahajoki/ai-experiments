#!/usr/bin/env python3
"""
Finnish NER Benchmark — Ground Truth Evaluation

Compares model outputs against human-annotated ground truth from
Turku NER corpus and FiNER/Digitoday corpus.
"""

import json
import sys
from pathlib import Path
from collections import Counter

RESULTS_DIR = Path(__file__).parent / "results-fi"
SAMPLE_DIR = Path(__file__).parent / "datasets-fi-sample"

# Finnish spaCy NER type mapping to unified types
# Turku NER / FiNER types: PER, ORG, LOC, PRO, EVENT, DATE
# spaCy Finnish types: PER, ORG, LOC, PRO, EVENT, DATE (same)
# Atlas/Qwen types: PERSON, ORG, LOCATION, PRODUCT, EVENT, DATE, OTHER
TYPE_MAP = {
    # spaCy Finnish -> unified
    "PER": "PERSON",
    "LOC": "LOCATION",
    "GPE": "LOCATION",
    "PRO": "PRODUCT",
    # Already correct
    "ORG": "ORG",
    "EVENT": "EVENT",
    "DATE": "DATE",
    "PERSON": "PERSON",
    "LOCATION": "LOCATION",
    "PRODUCT": "PRODUCT",
    "OTHER": "OTHER",
    # spaCy misc types
    "NORP": "OTHER",
    "CARDINAL": "OTHER",
    "ORDINAL": "OTHER",
    "QUANTITY": "OTHER",
    "PERCENT": "OTHER",
    "MONEY": "OTHER",
    "TIME": "DATE",
    "WORK_OF_ART": "PRODUCT",
    "FAC": "LOCATION",
    "LANGUAGE": "OTHER",
    "LAW": "OTHER",
}


def normalize_type(t: str) -> str:
    return TYPE_MAP.get(t, "OTHER")


def entity_key(name: str, etype: str) -> tuple[str, str]:
    return (name.strip().lower(), normalize_type(etype))


def entity_name_key(name: str) -> str:
    return name.strip().lower()


def load_ground_truth(dataset: str) -> dict[str, list[dict]]:
    """Load ground truth from sampled dataset."""
    ds_dir = SAMPLE_DIR / dataset
    gt_docs = {}

    for gt_file in sorted(ds_dir.glob("*_ground_truth.json")):
        # Corresponding txt file
        txt_name = gt_file.name.replace("_ground_truth.json", ".txt")
        gt_data = json.loads(gt_file.read_text(encoding="utf-8"))

        entities = []
        for item in gt_data:
            for ent in item.get("entities", []):
                entities.append({
                    "name": ent["text"],
                    "type": normalize_type(ent["type"]),
                })
        gt_docs[txt_name] = entities

    return gt_docs


def load_model_results(model: str, dataset: str) -> list[dict] | None:
    """Load model results for a dataset."""
    path = RESULTS_DIR / f"{model}_{dataset}.json"
    if not path.exists() or path.stat().st_size == 0:
        return None
    try:
        data = json.load(open(path))
        if not isinstance(data, list):
            data = [data]
        return data
    except (json.JSONDecodeError, FileNotFoundError):
        return None


def score_model(model_results: list[dict], gt_docs: dict[str, list[dict]]) -> dict:
    """Score a model against ground truth at corpus level."""

    # Collect all model entities (deduplicated)
    model_entities = set()
    model_name_types = {}
    for doc_result in model_results:
        for e in doc_result.get("entities", []):
            etype = normalize_type(e.get("type", "OTHER"))
            key = entity_key(e["name"], etype)
            model_entities.add(key)
            model_name_types[entity_name_key(e["name"])] = etype

    # Collect all GT entities (deduplicated)
    gt_entities = set()
    gt_name_types = {}
    for doc_name, entities in gt_docs.items():
        for e in entities:
            key = entity_key(e["name"], e["type"])
            gt_entities.add(key)
            gt_name_types[entity_name_key(e["name"])] = e["type"]

    tp = len(model_entities & gt_entities)
    fp = len(model_entities - gt_entities)
    fn = len(gt_entities - model_entities)

    precision = tp / (tp + fp) if (tp + fp) > 0 else 0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0

    # Type accuracy
    shared_names = set(gt_name_types.keys()) & set(model_name_types.keys())
    type_correct = sum(1 for n in shared_names if gt_name_types[n] == model_name_types[n])
    type_total = len(shared_names)
    type_acc = type_correct / type_total if type_total > 0 else 0

    # Per-type breakdown
    per_type = {}
    for etype in ["PERSON", "ORG", "LOCATION", "PRODUCT", "EVENT", "DATE", "OTHER"]:
        gt_typed = {k for k in gt_entities if k[1] == etype}
        model_typed = {k for k in model_entities if k[1] == etype}
        t_tp = len(gt_typed & model_typed)
        t_fp = len(model_typed - gt_typed)
        t_fn = len(gt_typed - model_typed)
        t_p = t_tp / (t_tp + t_fp) if (t_tp + t_fp) > 0 else 0
        t_r = t_tp / (t_tp + t_fn) if (t_tp + t_fn) > 0 else 0
        t_f1 = 2 * t_p * t_r / (t_p + t_r) if (t_p + t_r) > 0 else 0
        if gt_typed or model_typed:
            per_type[etype] = {
                "precision": t_p, "recall": t_r, "f1": t_f1,
                "tp": t_tp, "fp": t_fp, "fn": t_fn,
            }

    # Sample errors
    fps = sorted(model_entities - gt_entities)[:10]
    fns = sorted(gt_entities - model_entities)[:10]

    return {
        "precision": precision, "recall": recall, "f1": f1,
        "type_accuracy": type_acc,
        "tp": tp, "fp": fp, "fn": fn,
        "gt_total": len(gt_entities), "model_total": len(model_entities),
        "per_type": per_type,
        "false_positives": [{"name": n, "type": t} for n, t in fps[:5]],
        "false_negatives": [{"name": n, "type": t} for n, t in fns[:5]],
    }


def main():
    print("Finnish NER Benchmark — Ground Truth Evaluation")
    print("=" * 70)

    MODELS = ["spacy_sm", "spacy_md", "spacy_lg", "qwen_08b", "qwen_2b", "qwen_4b", "qwen_9b"]
    # Keys must match both the results-fi filenames AND the datasets-fi-sample dir names
    # Results: spacy_sm_finer.json -> dataset key "finer"
    # Sample dir: datasets-fi-sample/finer-digitoday/ -> dir name "finer-digitoday"
    DATASETS = {
        "turku-ner": ("Turku NER Corpus", "turku-ner"),
        "finer": ("FiNER / Digitoday", "finer-digitoday"),
    }

    all_scores = {}

    for ds_key, (ds_name, ds_dir_name) in DATASETS.items():
        print(f"\n{'='*70}")
        print(f" {ds_name}")
        print(f"{'='*70}")

        gt_docs = load_ground_truth(ds_dir_name)
        total_gt = sum(len(ents) for ents in gt_docs.values())
        unique_gt = set()
        for ents in gt_docs.values():
            for e in ents:
                unique_gt.add(entity_key(e["name"], e["type"]))

        print(f"Ground truth: {len(gt_docs)} docs, {total_gt} mentions, {len(unique_gt)} unique entities")
        gt_types = Counter(e["type"] for ents in gt_docs.values() for e in ents)
        for t, c in gt_types.most_common():
            print(f"  {t}: {c}")

        print(f"\n{'Model':<12} {'Prec':>8} {'Recall':>8} {'F1':>8} {'TypeAcc':>8} {'Model#':>8} {'TP':>6} {'FP':>6} {'FN':>6}")
        print("-" * 78)

        for model in MODELS:
            results = load_model_results(model, ds_key)
            if results is None:
                print(f"{model:<12} {'—':>8} {'—':>8} {'—':>8} {'—':>8} {'FAIL':>8}")
                continue

            scores = score_model(results, gt_docs)
            all_scores[f"{model}_{ds_key}"] = scores

            print(f"{model:<12} {scores['precision']:>8.3f} {scores['recall']:>8.3f} "
                  f"{scores['f1']:>8.3f} {scores['type_accuracy']:>8.3f} "
                  f"{scores['model_total']:>8} {scores['tp']:>6} {scores['fp']:>6} {scores['fn']:>6}")

    # Combined scores (both datasets)
    print(f"\n{'='*70}")
    print(" COMBINED SCORES (Turku NER + FiNER)")
    print(f"{'='*70}")

    print(f"\n{'Model':<12} {'Prec':>8} {'Recall':>8} {'F1':>8} {'TypeAcc':>8}")
    print("-" * 50)

    for model in MODELS:
        total_tp = 0
        total_fp = 0
        total_fn = 0
        total_type_correct = 0
        total_type_shared = 0
        has_data = False

        for ds_key in DATASETS.keys():
            key = f"{model}_{ds_key}"
            if key in all_scores:
                s = all_scores[key]
                total_tp += s["tp"]
                total_fp += s["fp"]
                total_fn += s["fn"]
                # Approximate type accuracy from per-dataset
                has_data = True

        if not has_data or (total_tp + total_fp) == 0:
            print(f"{model:<12} {'—':>8} {'—':>8} {'—':>8} {'—':>8}")
            continue

        p = total_tp / (total_tp + total_fp) if (total_tp + total_fp) > 0 else 0
        r = total_tp / (total_tp + total_fn) if (total_tp + total_fn) > 0 else 0
        f1 = 2 * p * r / (p + r) if (p + r) > 0 else 0

        # Average type accuracy
        ta_vals = []
        for ds_key in DATASETS.keys():
            key = f"{model}_{ds_key}"
            if key in all_scores:
                ta_vals.append(all_scores[key]["type_accuracy"])
        ta = sum(ta_vals) / len(ta_vals) if ta_vals else 0

        print(f"{model:<12} {p:>8.3f} {r:>8.3f} {f1:>8.3f} {ta:>8.3f}")

    # Per-type F1 (combined)
    print(f"\n{'='*70}")
    print(" PER-TYPE F1 (combined)")
    print(f"{'='*70}")

    types = ["PERSON", "ORG", "LOCATION", "PRODUCT", "EVENT", "DATE"]
    print(f"\n{'Model':<12}" + "".join(f"{t:>10}" for t in types))
    print("-" * (12 + 10 * len(types)))

    for model in MODELS:
        row = f"{model:<12}"
        for etype in types:
            total_tp = 0
            total_fp = 0
            total_fn = 0
            for ds_key in DATASETS.keys():
                key = f"{model}_{ds_key}"
                if key in all_scores:
                    pt = all_scores[key]["per_type"].get(etype, {})
                    total_tp += pt.get("tp", 0)
                    total_fp += pt.get("fp", 0)
                    total_fn += pt.get("fn", 0)
            if total_tp + total_fp + total_fn > 0:
                p = total_tp / (total_tp + total_fp) if (total_tp + total_fp) > 0 else 0
                r = total_tp / (total_tp + total_fn) if (total_tp + total_fn) > 0 else 0
                f1 = 2 * p * r / (p + r) if (p + r) > 0 else 0
                row += f"{f1:>10.3f}"
            else:
                row += f"{'—':>10}"
        print(row)

    # Error examples
    print(f"\n{'='*70}")
    print(" SAMPLE ERRORS")
    print(f"{'='*70}")

    for model in MODELS:
        for ds_key, (ds_name, _) in DATASETS.items():
            key = f"{model}_{ds_key}"
            if key not in all_scores:
                continue
            s = all_scores[key]
            if s["false_positives"]:
                print(f"\n{model} ({ds_name}) — False Positives:")
                for e in s["false_positives"][:3]:
                    print(f"  + \"{e['name']}\" ({e['type']})")
            if s["false_negatives"]:
                print(f"{model} ({ds_name}) — False Negatives:")
                for e in s["false_negatives"][:3]:
                    print(f"  - \"{e['name']}\" ({e['type']})")

    # Save results
    output_path = RESULTS_DIR / "finnish_gt_evaluation.json"
    json.dump(all_scores, open(output_path, "w"), indent=2, default=str, ensure_ascii=False)
    print(f"\nFull results saved to {output_path}")


if __name__ == "__main__":
    main()
