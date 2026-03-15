#!/usr/bin/env python3
"""
NER Benchmark Quantitative Analysis

Reads JSON result files from results/ and produces:
- Entity counts per model/dataset
- Entity type distributions
- Cross-model agreement (shared vs unique entities)
- Per-document statistics
"""

import json
import sys
from pathlib import Path
from collections import Counter, defaultdict

RESULTS_DIR = Path(__file__).parent / "results"

ENTITY_TYPES = ["PERSON", "ORG", "LOCATION", "DATE", "EVENT", "PRODUCT", "OTHER"]

DATASETS = ["wikipedia", "sec", "legal", "conll2003"]
SPACY_MODELS = ["sm", "lg", "trf"]
QWEN_MODELS = ["08b", "2b", "4b"]


def load_result(path: Path) -> list[dict]:
    """Load a benchmark result JSON file, returning list of per-document results."""
    with open(path) as f:
        data = json.load(f)
    if isinstance(data, list):
        return data
    return [data]


def extract_entities(results: list[dict]) -> list[dict]:
    """Flatten all entities from all documents in a result set."""
    entities = []
    for doc in results:
        for e in doc.get("entities", []):
            entities.append(e)
    return entities


def entity_key(e: dict) -> tuple[str, str]:
    """Normalize entity to (lowercase name, type) for comparison."""
    return (e["name"].strip().lower(), e["type"])


def load_all_results() -> dict[str, dict[str, list[dict]]]:
    """Load all results keyed by model -> dataset -> results."""
    all_results = {}
    for path in sorted(RESULTS_DIR.glob("*.json")):
        name = path.stem  # e.g. spacy_sm_wikipedia
        parts = name.split("_", 2)
        if len(parts) < 3:
            continue
        backend = parts[0]  # spacy or qwen
        model = parts[1]    # sm, lg, trf, 08b, 2b, 4b
        dataset = parts[2]  # wikipedia, sec, legal, conll2003
        model_name = f"{backend}_{model}"
        if model_name not in all_results:
            all_results[model_name] = {}
        try:
            all_results[model_name][dataset] = load_result(path)
        except (json.JSONDecodeError, FileNotFoundError) as e:
            print(f"  Warning: skipping {path.name}: {e}", file=sys.stderr)
    return all_results


def print_section(title: str):
    print(f"\n{'='*70}")
    print(f" {title}")
    print(f"{'='*70}")


def analyze_entity_counts(all_results: dict):
    print_section("ENTITY COUNTS BY MODEL AND DATASET")

    # Gather all models and datasets
    models = sorted(all_results.keys())
    datasets = sorted({ds for m in all_results.values() for ds in m.keys()})

    # Header
    header = f"{'Model':<16}" + "".join(f"{ds:>14}" for ds in datasets) + f"{'TOTAL':>14}"
    print(header)
    print("-" * len(header))

    for model in models:
        row = f"{model:<16}"
        total = 0
        for ds in datasets:
            results = all_results[model].get(ds, [])
            entities = extract_entities(results)
            count = len(entities)
            total += count
            row += f"{count:>14}"
        row += f"{total:>14}"
        print(row)


def analyze_type_distribution(all_results: dict):
    print_section("ENTITY TYPE DISTRIBUTION (% of total)")

    models = sorted(all_results.keys())

    header = f"{'Model':<16}" + "".join(f"{t:>10}" for t in ENTITY_TYPES)
    print(header)
    print("-" * len(header))

    for model in models:
        all_entities = []
        for ds_results in all_results[model].values():
            all_entities.extend(extract_entities(ds_results))

        total = len(all_entities) or 1
        type_counts = Counter(e["type"] for e in all_entities)

        row = f"{model:<16}"
        for t in ENTITY_TYPES:
            pct = type_counts.get(t, 0) / total * 100
            row += f"{pct:>9.1f}%"
        print(row)


def analyze_cross_model_agreement(all_results: dict):
    print_section("CROSS-MODEL AGREEMENT (per dataset)")

    datasets = sorted({ds for m in all_results.values() for ds in m.keys()})
    models = sorted(all_results.keys())

    for ds in datasets:
        print(f"\n--- {ds} ---")

        # Collect entity sets per model
        model_entities: dict[str, set] = {}
        for model in models:
            results = all_results[model].get(ds, [])
            entities = extract_entities(results)
            model_entities[model] = {entity_key(e) for e in entities}

        active_models = [m for m in models if m in model_entities and model_entities[m]]
        if len(active_models) < 2:
            print("  (need at least 2 models to compare)")
            continue

        # Entities found by ALL models
        all_sets = [model_entities[m] for m in active_models]
        unanimous = set.intersection(*all_sets) if all_sets else set()

        # Entities found by at least 2 models
        entity_model_count: Counter = Counter()
        for m in active_models:
            for e in model_entities[m]:
                entity_model_count[e] += 1
        majority = {e for e, c in entity_model_count.items() if c >= 2}

        # All entities (union)
        union = set.union(*all_sets) if all_sets else set()

        print(f"  Models compared: {len(active_models)}")
        print(f"  Union (any model):       {len(union):>6}")
        print(f"  Majority (2+ models):    {len(majority):>6}")
        print(f"  Unanimous (all models):  {len(unanimous):>6}")
        if union:
            print(f"  Agreement rate:          {len(unanimous)/len(union)*100:>5.1f}%")

        # Per-model unique entities (found only by that model)
        print(f"\n  Unique to each model:")
        for m in active_models:
            unique = model_entities[m] - set.union(*(model_entities[m2] for m2 in active_models if m2 != m))
            print(f"    {m:<16} {len(unique):>6} unique ({len(unique)/max(len(model_entities[m]),1)*100:.1f}% of its entities)")


def analyze_spacy_vs_llm(all_results: dict):
    print_section("SPACY vs LLM COMPARISON")

    datasets = sorted({ds for m in all_results.values() for ds in m.keys()})

    spacy_models = [m for m in all_results if m.startswith("spacy_")]
    qwen_models = [m for m in all_results if m.startswith("qwen_")]

    if not spacy_models or not qwen_models:
        print("  Need both spaCy and Qwen results for comparison")
        return

    for ds in datasets:
        print(f"\n--- {ds} ---")

        # Best spaCy = trf if available, else lg, else sm
        spacy_entities = set()
        for m in ["spacy_trf", "spacy_lg", "spacy_sm"]:
            if m in all_results and ds in all_results[m]:
                entities = extract_entities(all_results[m][ds])
                spacy_entities = {entity_key(e) for e in entities}
                spacy_label = m
                break

        # Best Qwen = 4b if available
        qwen_entities = set()
        for m in ["qwen_4b", "qwen_2b", "qwen_08b"]:
            if m in all_results and ds in all_results[m]:
                entities = extract_entities(all_results[m][ds])
                qwen_entities = {entity_key(e) for e in entities}
                qwen_label = m
                break

        if not spacy_entities and not qwen_entities:
            print("  No data")
            continue

        # Union of all spaCy models
        all_spacy = set()
        for m in spacy_models:
            if ds in all_results[m]:
                all_spacy |= {entity_key(e) for e in extract_entities(all_results[m][ds])}

        all_qwen = set()
        for m in qwen_models:
            if ds in all_results[m]:
                all_qwen |= {entity_key(e) for e in extract_entities(all_results[m][ds])}

        shared = all_spacy & all_qwen
        only_spacy = all_spacy - all_qwen
        only_qwen = all_qwen - all_spacy

        print(f"  All spaCy (union):  {len(all_spacy):>6}")
        print(f"  All Qwen (union):   {len(all_qwen):>6}")
        print(f"  Shared:             {len(shared):>6}")
        print(f"  Only spaCy:         {len(only_spacy):>6}")
        print(f"  Only Qwen:          {len(only_qwen):>6}")

        # Show some examples of only-spacy and only-qwen
        if only_spacy:
            examples = sorted(only_spacy, key=lambda x: x[0])[:5]
            print(f"  Sample spaCy-only:  {', '.join(f'{n} ({t})' for n,t in examples)}")
        if only_qwen:
            examples = sorted(only_qwen, key=lambda x: x[0])[:5]
            print(f"  Sample Qwen-only:   {', '.join(f'{n} ({t})' for n,t in examples)}")


def analyze_per_document_stats(all_results: dict):
    print_section("PER-DOCUMENT STATISTICS")

    models = sorted(all_results.keys())
    datasets = sorted({ds for m in all_results.values() for ds in m.keys()})

    print(f"{'Model':<16} {'Docs':>6} {'Mean':>8} {'Median':>8} {'Min':>6} {'Max':>6} {'StdDev':>8}")
    print("-" * 70)

    for model in models:
        doc_counts = []
        for ds in datasets:
            for doc in all_results[model].get(ds, []):
                doc_counts.append(doc.get("extracted", 0))

        if not doc_counts:
            continue

        import statistics
        mean = statistics.mean(doc_counts)
        median = statistics.median(doc_counts)
        stdev = statistics.stdev(doc_counts) if len(doc_counts) > 1 else 0
        print(f"{model:<16} {len(doc_counts):>6} {mean:>8.1f} {median:>8.1f} {min(doc_counts):>6} {max(doc_counts):>6} {stdev:>8.1f}")


def main():
    print("NER Benchmark — Quantitative Analysis")
    print(f"Results directory: {RESULTS_DIR}")

    all_results = load_all_results()
    if not all_results:
        print("No results found!")
        sys.exit(1)

    print(f"\nLoaded {len(all_results)} models:")
    for model in sorted(all_results.keys()):
        datasets = list(all_results[model].keys())
        print(f"  {model}: {', '.join(datasets)}")

    analyze_entity_counts(all_results)
    analyze_type_distribution(all_results)
    analyze_per_document_stats(all_results)
    analyze_cross_model_agreement(all_results)
    analyze_spacy_vs_llm(all_results)

    print(f"\n{'='*70}")
    print(" Analysis complete")
    print(f"{'='*70}")


if __name__ == "__main__":
    main()
