#!/usr/bin/env python3
"""
NER Benchmark — Oracle Evaluation

Uses a SOTA model (Gemini 2.5 Pro via OpenRouter) as ground truth oracle.
Samples documents, runs oracle NER, then scores each model against it.

Usage:
    python oracle_eval.py [--sample N] [--dry-run]
"""

import json
import os
import sys
import time
import argparse
import urllib.request
import urllib.error
from pathlib import Path
from collections import defaultdict

RESULTS_DIR = Path(__file__).parent / "results"
ORACLE_DIR = RESULTS_DIR / "oracle"

OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
if not OPENROUTER_API_KEY:
    print("Error: OPENROUTER_API_KEY environment variable not set")
    print("  export OPENROUTER_API_KEY=sk-or-v1-...")
    sys.exit(1)
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
ORACLE_MODEL = "google/gemini-2.5-pro"

ATLAS_URL = "http://localhost:3001"
ATLAS_TOKEN = None  # loaded from config

ENTITY_TYPES = ["PERSON", "ORG", "LOCATION", "DATE", "EVENT", "PRODUCT", "OTHER"]

NER_PROMPT = """You are a Named Entity Recognition system. Extract ALL named entities from the given text.

Return a JSON array of objects with these fields:
- "name": the entity text as it appears in the source
- "type": one of PERSON, ORG, LOCATION, DATE, EVENT, PRODUCT, OTHER

Entity type guidelines:
- PERSON: people's names (e.g., "John Smith", "Marie Curie")
- ORG: organizations, companies, institutions (e.g., "Acme Corp", "SEC", "Harvard University")
- LOCATION: places, addresses, countries, cities (e.g., "New York", "Finland")
- DATE: dates, time periods (e.g., "March 2024", "Q3 2025", "1991")
- EVENT: named events (e.g., "World War II", "Olympics")
- PRODUCT: products, services, software (e.g., "iPhone 15", "Windows 11")
- OTHER: other named entities that don't fit above categories

Be thorough — extract every entity you can find. Return ONLY a valid JSON array, no other text.
If no entities found, return [].
Example: [{"name": "Acme Corp", "type": "ORG"}, {"name": "John Smith", "type": "PERSON"}]"""


def load_atlas_token():
    global ATLAS_TOKEN
    config_path = Path.home() / ".config" / "anvil" / "config.json"
    if not config_path.exists():
        config_path = Path.home() / ".anvil" / "config.json"
    if config_path.exists():
        cfg = json.loads(config_path.read_text())
        ATLAS_TOKEN = cfg.get("secret") or cfg.get("token")
    if not ATLAS_TOKEN:
        print("Error: No Atlas API token found", file=sys.stderr)
        sys.exit(1)


def atlas_request(path: str) -> dict:
    req = urllib.request.Request(
        f"{ATLAS_URL}{path}",
        headers={"Authorization": f"Bearer {ATLAS_TOKEN}"},
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())


def get_bench_spaces() -> dict[str, str]:
    """Return {space_name: space_id} for bench spaces."""
    data = atlas_request("/api/spaces")
    return {
        s["name"]: s["id"]
        for s in data["spaces"]
        if s["name"].startswith("bench-")
    }


def get_documents(space_id: str) -> list[dict]:
    data = atlas_request(f"/api/documents?spaceId={space_id}")
    return data.get("documents", [])


# ChromaDB direct access for chunk text
CHROMA_URL = "http://localhost:8000"
TENANT_ID = "2c5c2b43-f212-4289-b922-5d5a54606290"


def _chroma_collection_name(space_id: str) -> str:
    short_tenant = TENANT_ID.replace("-", "")[:8]
    short_space = space_id.replace("-", "")[:16]
    return f"atlas_{short_tenant}_{short_space}"


def _get_chroma_collection_id(collection_name: str) -> str | None:
    req = urllib.request.Request(
        f"{CHROMA_URL}/api/v2/tenants/default_tenant/databases/default_database/collections"
    )
    with urllib.request.urlopen(req) as resp:
        cols = json.loads(resp.read())
    for c in cols:
        if c["name"] == collection_name:
            return c["id"]
    return None


def get_chunks(document_id: str, space_id: str) -> list[dict]:
    """Get chunk texts for a document from ChromaDB."""
    col_name = _chroma_collection_name(space_id)
    col_id = _get_chroma_collection_id(col_name)
    if not col_id:
        return []

    body = json.dumps({
        "where": {"document_id": document_id},
        "include": ["documents", "metadatas"],
        "limit": 500,
    }).encode()

    req = urllib.request.Request(
        f"{CHROMA_URL}/api/v2/tenants/default_tenant/databases/default_database/collections/{col_id}/get",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req) as resp:
        data = json.loads(resp.read())

    chunks = []
    for doc_text, meta in zip(data.get("documents", []), data.get("metadatas", [])):
        chunks.append({"text": doc_text, "metadata": meta})

    # Sort by chunk_index
    chunks.sort(key=lambda c: c["metadata"].get("chunk_index", 0))
    return chunks


def call_oracle(text: str) -> list[dict]:
    """Call OpenRouter with the oracle model to extract entities."""
    body = json.dumps({
        "model": ORACLE_MODEL,
        "messages": [
            {"role": "system", "content": NER_PROMPT},
            {"role": "user", "content": text},
        ],
        "temperature": 0.1,
    }).encode()

    req = urllib.request.Request(
        OPENROUTER_URL,
        data=body,
        headers={
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        print(f"  Oracle API error {e.code}: {body[:200]}", file=sys.stderr)
        return []

    content = data["choices"][0]["message"]["content"]
    return parse_entities(content)


def parse_entities(content: str) -> list[dict]:
    """Parse entity JSON from model response."""
    content = content.strip()
    # Try direct parse
    try:
        parsed = json.loads(content)
        if isinstance(parsed, list):
            return validate_entities(parsed)
    except json.JSONDecodeError:
        pass
    # Try code block
    import re
    match = re.search(r"```(?:json)?\s*([\s\S]*?)```", content)
    if match:
        try:
            parsed = json.loads(match.group(1).strip())
            if isinstance(parsed, list):
                return validate_entities(parsed)
        except json.JSONDecodeError:
            pass
    # Try finding array
    match = re.search(r"\[[\s\S]*\]", content)
    if match:
        try:
            parsed = json.loads(match.group(0))
            if isinstance(parsed, list):
                return validate_entities(parsed)
        except json.JSONDecodeError:
            pass
    print(f"  Warning: could not parse oracle response: {content[:100]}...", file=sys.stderr)
    return []


def validate_entities(arr: list) -> list[dict]:
    valid_types = set(ENTITY_TYPES)
    results = []
    for item in arr:
        if not isinstance(item, dict):
            continue
        name = item.get("name", "").strip()
        if not name:
            continue
        etype = str(item.get("type", "OTHER")).upper()
        if etype not in valid_types:
            etype = "OTHER"
        results.append({"name": name, "type": etype})
    return results


def entity_key(e: dict) -> tuple[str, str]:
    """Normalize to (lowercase name, type)."""
    return (e["name"].strip().lower(), e["type"])


def entity_name_key(e: dict) -> str:
    """Just the normalized name, for type-agnostic matching."""
    return e["name"].strip().lower()


def load_model_results() -> dict[str, dict[str, list[dict]]]:
    """Load all benchmark results: model -> dataset -> [doc_results]."""
    results = {}
    for path in sorted(RESULTS_DIR.glob("*.json")):
        parts = path.stem.split("_", 2)
        if len(parts) < 3:
            continue
        model_name = f"{parts[0]}_{parts[1]}"
        dataset = parts[2]
        if model_name not in results:
            results[model_name] = {}
        try:
            data = json.load(open(path))
            if not isinstance(data, list):
                data = [data]
            results[model_name][dataset] = data
        except (json.JSONDecodeError, FileNotFoundError):
            pass
    return results


def select_sample_docs(spaces: dict[str, str], sample_per_dataset: int) -> dict[str, tuple[str, list[dict]]]:
    """Select sample documents from each dataset. Pick docs with varying entity density."""
    model_results = load_model_results()
    sampled = {}

    ds_map = {
        "bench-wikipedia-bios": "wikipedia",
        "bench-sec-filings": "sec",
        "bench-legal-contracts": "legal",
        "bench-conll2003": "conll2003",
    }

    for space_name, space_id in sorted(spaces.items()):
        ds_key = ds_map.get(space_name)
        if not ds_key:
            continue

        docs = get_documents(space_id)
        ready_docs = [d for d in docs if d.get("status") == "ready"]

        if not ready_docs:
            continue

        # Rank docs by entity count from spacy_sm (if available) for stratified sampling
        ref_model = "spacy_sm"
        doc_entity_counts = {}
        if ref_model in model_results and ds_key in model_results[ref_model]:
            for doc_result in model_results[ref_model][ds_key]:
                doc_id = doc_result.get("documentId")
                if doc_id:
                    doc_entity_counts[doc_id] = doc_result.get("extracted", 0)

        # Sort by entity count, pick evenly spaced samples
        if doc_entity_counts:
            ready_docs.sort(key=lambda d: doc_entity_counts.get(d["id"], 0))

        n = min(sample_per_dataset, len(ready_docs))
        if n <= 0:
            continue

        # Pick evenly spaced indices for stratified sampling
        if n >= len(ready_docs):
            selected = ready_docs
        else:
            step = len(ready_docs) / n
            selected = [ready_docs[int(i * step)] for i in range(n)]

        sampled[ds_key] = (space_id, selected)
        print(f"  {space_name}: selected {len(selected)}/{len(ready_docs)} docs")

    return sampled


def run_oracle(sampled_docs: dict[str, tuple[str, list[dict]]], dry_run: bool = False) -> dict[str, dict[str, list[dict]]]:
    """Run oracle NER on sampled documents. Returns dataset -> doc_id -> [entities]."""
    ORACLE_DIR.mkdir(exist_ok=True)
    oracle_results: dict[str, dict[str, list[dict]]] = {}

    for ds_key, (space_id, docs) in sorted(sampled_docs.items()):
        oracle_results[ds_key] = {}
        print(f"\n--- {ds_key} ({len(docs)} docs) ---")

        for doc in docs:
            doc_id = doc["id"]
            doc_name = doc.get("original_name", doc_id[:8])
            cache_path = ORACLE_DIR / f"{ds_key}_{doc_id[:8]}.json"

            # Use cached result if available
            if cache_path.exists():
                cached = json.load(open(cache_path))
                oracle_results[ds_key][doc_id] = cached["entities"]
                print(f"  {doc_name}: {len(cached['entities'])} entities (cached)")
                continue

            if dry_run:
                print(f"  {doc_name}: [dry run - would call oracle]")
                continue

            # Get chunk text from ChromaDB
            chunks = get_chunks(doc_id, space_id)
            if not chunks:
                print(f"  {doc_name}: no chunks, skipping")
                continue

            # Combine chunk texts (send as one request for efficiency)
            full_text = "\n\n".join(c.get("text", "") for c in chunks)

            # Truncate if very long (Gemini has large context but let's be reasonable)
            if len(full_text) > 50000:
                full_text = full_text[:50000]

            print(f"  {doc_name}: {len(chunks)} chunks, {len(full_text)} chars...", end="", flush=True)
            entities = call_oracle(full_text)
            oracle_results[ds_key][doc_id] = entities
            print(f" {len(entities)} entities")

            # Cache result
            cache_data = {
                "document_id": doc_id,
                "document_name": doc_name,
                "dataset": ds_key,
                "model": ORACLE_MODEL,
                "chunks": len(chunks),
                "chars": len(full_text),
                "entities": entities,
            }
            json.dump(cache_data, open(cache_path, "w"), indent=2)

            # Rate limiting
            time.sleep(1)

    return oracle_results


def score_models(oracle_results: dict, model_results: dict) -> dict:
    """Score each model against oracle ground truth."""
    scores = {}

    for model_name, datasets in sorted(model_results.items()):
        model_scores = {
            "precision_sum": 0, "recall_sum": 0, "f1_sum": 0,
            "type_correct": 0, "type_total": 0,
            "total_oracle": 0, "total_model": 0, "total_tp": 0,
            "per_dataset": {},
            "false_positives": [],
            "false_negatives": [],
        }

        for ds_key, oracle_docs in oracle_results.items():
            if ds_key not in datasets:
                continue

            ds_scores = {"tp": 0, "fp": 0, "fn": 0, "type_correct": 0, "type_total": 0}

            # Build doc_id -> model entities map
            model_doc_entities = {}
            for doc_result in datasets[ds_key]:
                doc_id = doc_result.get("documentId")
                if doc_id:
                    model_doc_entities[doc_id] = doc_result.get("entities", [])

            for doc_id, oracle_entities in oracle_docs.items():
                if not oracle_entities:
                    continue

                model_entities = model_doc_entities.get(doc_id, [])

                oracle_set = {entity_key(e) for e in oracle_entities}
                model_set = {entity_key(e) for e in model_entities}

                # Also build name-only sets for type accuracy
                oracle_names = {entity_name_key(e): e["type"] for e in oracle_entities}
                model_names = {entity_name_key(e): e["type"] for e in model_entities}

                tp = len(oracle_set & model_set)
                fp = len(model_set - oracle_set)
                fn = len(oracle_set - model_set)

                ds_scores["tp"] += tp
                ds_scores["fp"] += fp
                ds_scores["fn"] += fn

                # Type accuracy: for entities found by both (by name), how often do types match?
                shared_names = set(oracle_names.keys()) & set(model_names.keys())
                for name in shared_names:
                    ds_scores["type_total"] += 1
                    if oracle_names[name] == model_names[name]:
                        ds_scores["type_correct"] += 1

                # Collect sample false positives/negatives
                for e in sorted(model_set - oracle_set):
                    if len(model_scores["false_positives"]) < 10:
                        model_scores["false_positives"].append({"name": e[0], "type": e[1], "dataset": ds_key})
                for e in sorted(oracle_set - model_set):
                    if len(model_scores["false_negatives"]) < 10:
                        model_scores["false_negatives"].append({"name": e[0], "type": e[1], "dataset": ds_key})

            # Compute per-dataset precision/recall/F1
            tp, fp, fn = ds_scores["tp"], ds_scores["fp"], ds_scores["fn"]
            precision = tp / (tp + fp) if (tp + fp) > 0 else 0
            recall = tp / (tp + fn) if (tp + fn) > 0 else 0
            f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0
            type_acc = ds_scores["type_correct"] / ds_scores["type_total"] if ds_scores["type_total"] > 0 else 0

            model_scores["per_dataset"][ds_key] = {
                "precision": precision, "recall": recall, "f1": f1,
                "type_accuracy": type_acc,
                "tp": tp, "fp": fp, "fn": fn,
            }

            model_scores["total_tp"] += tp
            model_scores["total_model"] += tp + fp
            model_scores["total_oracle"] += tp + fn
            model_scores["type_correct"] += ds_scores["type_correct"]
            model_scores["type_total"] += ds_scores["type_total"]

        # Overall scores
        tp = model_scores["total_tp"]
        total_model = model_scores["total_model"]
        total_oracle = model_scores["total_oracle"]
        model_scores["precision"] = tp / total_model if total_model > 0 else 0
        model_scores["recall"] = tp / total_oracle if total_oracle > 0 else 0
        p, r = model_scores["precision"], model_scores["recall"]
        model_scores["f1"] = 2 * p * r / (p + r) if (p + r) > 0 else 0
        model_scores["type_accuracy"] = (
            model_scores["type_correct"] / model_scores["type_total"]
            if model_scores["type_total"] > 0 else 0
        )

        scores[model_name] = model_scores

    return scores


def print_results(scores: dict):
    print(f"\n{'='*80}")
    print(" QUALITATIVE EVALUATION — Oracle: Gemini 2.5 Pro")
    print(f"{'='*80}")

    # Overall table
    print(f"\n{'Model':<16} {'Precision':>10} {'Recall':>10} {'F1':>10} {'Type Acc':>10} {'TP':>6} {'FP':>6} {'FN':>6}")
    print("-" * 80)

    for model in sorted(scores.keys()):
        s = scores[model]
        print(f"{model:<16} {s['precision']:>10.3f} {s['recall']:>10.3f} {s['f1']:>10.3f} {s['type_accuracy']:>10.3f} {s['total_tp']:>6} {s['total_model']-s['total_tp']:>6} {s['total_oracle']-s['total_tp']:>6}")

    # Per-dataset breakdown
    datasets = set()
    for s in scores.values():
        datasets.update(s["per_dataset"].keys())

    for ds in sorted(datasets):
        print(f"\n--- {ds} ---")
        print(f"{'Model':<16} {'Precision':>10} {'Recall':>10} {'F1':>10} {'Type Acc':>10}")
        print("-" * 60)
        for model in sorted(scores.keys()):
            ds_scores = scores[model]["per_dataset"].get(ds)
            if not ds_scores:
                continue
            print(f"{model:<16} {ds_scores['precision']:>10.3f} {ds_scores['recall']:>10.3f} {ds_scores['f1']:>10.3f} {ds_scores['type_accuracy']:>10.3f}")

    # Error examples
    print(f"\n{'='*80}")
    print(" SAMPLE ERRORS (first 5 per model)")
    print(f"{'='*80}")
    for model in sorted(scores.keys()):
        s = scores[model]
        if s["false_positives"]:
            print(f"\n{model} — False Positives (model found, oracle didn't):")
            for e in s["false_positives"][:5]:
                print(f"  - \"{e['name']}\" ({e['type']}) [{e['dataset']}]")
        if s["false_negatives"]:
            print(f"\n{model} — False Negatives (oracle found, model missed):")
            for e in s["false_negatives"][:5]:
                print(f"  - \"{e['name']}\" ({e['type']}) [{e['dataset']}]")


def main():
    parser = argparse.ArgumentParser(description="NER Oracle Evaluation")
    parser.add_argument("--sample", type=int, default=5, help="Docs to sample per dataset")
    parser.add_argument("--dry-run", action="store_true", help="Don't call oracle API")
    args = parser.parse_args()

    load_atlas_token()

    print("NER Benchmark — Oracle Evaluation")
    print(f"Oracle model: {ORACLE_MODEL}")
    print(f"Sample size: {args.sample} docs per dataset")

    # Get benchmark spaces
    print("\nSelecting sample documents...")
    spaces = get_bench_spaces()
    sampled = select_sample_docs(spaces, args.sample)

    if not sampled:
        print("No documents to evaluate!")
        sys.exit(1)

    total_docs = sum(len(docs) for _, docs in sampled.values())
    print(f"\nTotal sample: {total_docs} documents")

    # Run oracle
    print("\nRunning oracle NER...")
    oracle_results = run_oracle(sampled, dry_run=args.dry_run)

    if args.dry_run:
        print("\n[Dry run complete — no API calls made]")
        return

    # Load model results and score
    print("\nScoring models...")
    model_results = load_model_results()
    scores = score_models(oracle_results, model_results)

    # Print results
    print_results(scores)

    # Save full results
    output_path = RESULTS_DIR / "oracle_evaluation.json"
    json.dump(scores, open(output_path, "w"), indent=2, default=str)
    print(f"\nFull results saved to {output_path}")


if __name__ == "__main__":
    main()
