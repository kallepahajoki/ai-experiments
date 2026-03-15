#!/usr/bin/env python3
"""
fetch_finnish_benchmark_data.py

Downloads Finnish NER benchmark datasets.
Annotated datasets go into their own dirs with ground truth preserved.
Unannotated datasets are saved as .txt files for upload to Atlas.

Requirements:
    pip install requests
"""

import json
import subprocess
import requests
import time
from pathlib import Path

BASE_DIR = Path(__file__).parent / "datasets-fi"


def setup_dirs():
    dirs = [
        "turku-ner",
        "finer-digitoday",
        "wikipedia-fi",
    ]
    for d in dirs:
        (BASE_DIR / d).mkdir(parents=True, exist_ok=True)


def extract_entities_from_bio(token_tag_pairs):
    """Extract entity spans from BIO-tagged token-tag pairs."""
    entities = []
    current = None

    for token, tag in token_tag_pairs:
        if tag.startswith("B-"):
            if current:
                entities.append(current)
            current = {"text": token, "type": tag[2:]}
        elif tag.startswith("I-") and current:
            current["text"] += f" {token}"
        else:
            if current:
                entities.append(current)
                current = None

    if current:
        entities.append(current)
    return entities


# ─────────────────────────────────────────────
# Dataset 1: Turku NER Corpus
# ─────────────────────────────────────────────

def fetch_turku_ner():
    """Clone Turku NER corpus and extract documents with ground truth."""
    out_dir = BASE_DIR / "turku-ner"
    repo_url = "https://github.com/TurkuNLP/turku-ner-corpus.git"
    clone_dir = out_dir / "repo"

    if clone_dir.exists():
        print("Turku NER already cloned")
    else:
        print("Cloning Turku NER corpus...")
        subprocess.run(
            ["git", "clone", "--depth", "1", repo_url, str(clone_dir)],
            check=True,
        )

    # Find CoNLL/TSV annotation files
    conll_files = (
        list(clone_dir.rglob("*.tsv"))
        + list(clone_dir.rglob("*.conll"))
        + list(clone_dir.rglob("*.conllu"))
    )

    print(f"Found {len(conll_files)} annotation files")

    total_docs = 0
    total_entities = 0

    for conll_file in sorted(conll_files):
        sentences = []
        annotations = []
        current_tokens = []
        current_tags = []

        with open(conll_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    if current_tokens:
                        sentences.append(" ".join(current_tokens))
                        annotations.append(list(zip(current_tokens, current_tags)))
                        current_tokens = []
                        current_tags = []
                    continue

                parts = line.split("\t")
                if len(parts) >= 2:
                    token = parts[0]
                    # NER tag is typically last column
                    tag = parts[-1] if parts[-1].startswith(("B-", "I-", "O")) else "O"
                    current_tokens.append(token)
                    current_tags.append(tag)

        if current_tokens:
            sentences.append(" ".join(current_tokens))
            annotations.append(list(zip(current_tokens, current_tags)))

        if not sentences:
            continue

        # Batch into ~500-word pseudo-documents
        doc_idx = 0
        batch_sents = []
        batch_annots = []
        word_count = 0

        stem = conll_file.stem

        for sent, annot in zip(sentences, annotations):
            batch_sents.append(sent)
            batch_annots.append(annot)
            word_count += len(sent.split())

            if word_count >= 500:
                doc_name = f"{stem}_{doc_idx:03d}"
                doc_path = out_dir / f"{doc_name}.txt"
                doc_path.write_text("\n".join(batch_sents), encoding="utf-8")

                gt_data = []
                for s, a in zip(batch_sents, batch_annots):
                    ents = extract_entities_from_bio(a)
                    gt_data.append({"sentence": s, "entities": ents})

                gt_path = out_dir / f"{doc_name}_ground_truth.json"
                gt_path.write_text(
                    json.dumps(gt_data, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )

                total_docs += 1
                total_entities += sum(len(item["entities"]) for item in gt_data)

                batch_sents = []
                batch_annots = []
                word_count = 0
                doc_idx += 1

        # Remaining sentences
        if batch_sents:
            doc_name = f"{stem}_{doc_idx:03d}"
            doc_path = out_dir / f"{doc_name}.txt"
            doc_path.write_text("\n".join(batch_sents), encoding="utf-8")

            gt_data = []
            for s, a in zip(batch_sents, batch_annots):
                ents = extract_entities_from_bio(a)
                gt_data.append({"sentence": s, "entities": ents})

            gt_path = out_dir / f"{doc_name}_ground_truth.json"
            gt_path.write_text(
                json.dumps(gt_data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            total_docs += 1
            total_entities += sum(len(item["entities"]) for item in gt_data)

    print(f"Processed Turku NER: {total_docs} documents, {total_entities} entities")


# ─────────────────────────────────────────────
# Dataset 2: FiNER / Digitoday
# ─────────────────────────────────────────────

def fetch_finer():
    """Clone FiNER dataset and extract documents with ground truth."""
    out_dir = BASE_DIR / "finer-digitoday"
    repo_url = "https://github.com/mpsilfve/finer-data.git"
    clone_dir = out_dir / "repo"

    if clone_dir.exists():
        print("FiNER already cloned")
    else:
        print("Cloning FiNER dataset...")
        subprocess.run(
            ["git", "clone", "--depth", "1", repo_url, str(clone_dir)],
            check=True,
        )

    # Find data files - FiNER uses various formats
    data_files = (
        list(clone_dir.rglob("*.csv"))
        + list(clone_dir.rglob("*.conll"))
        + list(clone_dir.rglob("*.bio"))
        + list(clone_dir.rglob("*.tsv"))
    )

    # Filter out non-data files (README, etc.)
    data_files = [f for f in data_files if f.stat().st_size > 1000]

    print(f"Found {len(data_files)} data files")

    total_docs = 0
    total_entities = 0

    for data_file in sorted(data_files):
        sentences = []
        annotations = []
        current_tokens = []
        current_tags = []

        with open(data_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    if current_tokens:
                        sentences.append(" ".join(current_tokens))
                        annotations.append(list(zip(current_tokens, current_tags)))
                        current_tokens = []
                        current_tags = []
                    continue

                # Handle both tab and space separated
                if "\t" in line:
                    parts = line.split("\t")
                else:
                    parts = line.split()

                if len(parts) >= 2:
                    token = parts[0]
                    tag = parts[-1].strip()
                    if not tag.startswith(("B-", "I-", "O")):
                        tag = "O"
                    current_tokens.append(token)
                    current_tags.append(tag)

        if current_tokens:
            sentences.append(" ".join(current_tokens))
            annotations.append(list(zip(current_tokens, current_tags)))

        if not sentences:
            continue

        # Batch into ~500-word pseudo-documents
        doc_idx = 0
        batch_sents = []
        batch_annots = []
        word_count = 0

        stem = data_file.stem

        for sent, annot in zip(sentences, annotations):
            batch_sents.append(sent)
            batch_annots.append(annot)
            word_count += len(sent.split())

            if word_count >= 500:
                doc_name = f"finer_{stem}_{doc_idx:03d}"
                doc_path = out_dir / f"{doc_name}.txt"
                doc_path.write_text("\n".join(batch_sents), encoding="utf-8")

                gt_data = []
                for s, a in zip(batch_sents, batch_annots):
                    ents = extract_entities_from_bio(a)
                    gt_data.append({"sentence": s, "entities": ents})

                gt_path = out_dir / f"{doc_name}_ground_truth.json"
                gt_path.write_text(
                    json.dumps(gt_data, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )

                total_docs += 1
                total_entities += sum(len(item["entities"]) for item in gt_data)

                batch_sents = []
                batch_annots = []
                word_count = 0
                doc_idx += 1

        # Remaining
        if batch_sents:
            doc_name = f"finer_{stem}_{doc_idx:03d}"
            doc_path = out_dir / f"{doc_name}.txt"
            doc_path.write_text("\n".join(batch_sents), encoding="utf-8")

            gt_data = []
            for s, a in zip(batch_sents, batch_annots):
                ents = extract_entities_from_bio(a)
                gt_data.append({"sentence": s, "entities": ents})

            gt_path = out_dir / f"{doc_name}_ground_truth.json"
            gt_path.write_text(
                json.dumps(gt_data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            total_docs += 1
            total_entities += sum(len(item["entities"]) for item in gt_data)

    print(f"Processed FiNER: {total_docs} documents, {total_entities} entities")


# ─────────────────────────────────────────────
# Dataset 3: Finnish Wikipedia
# ─────────────────────────────────────────────

def fetch_wikipedia_fi(count=25):
    """Fetch Finnish Wikipedia articles."""
    out_dir = BASE_DIR / "wikipedia-fi"

    # Entity-rich Finnish subjects across domains
    subjects = [
        # Finnish politics & history
        "Urho Kekkonen", "Tarja Halonen", "Carl Gustaf Emil Mannerheim",
        "Sanna Marin", "Risto Ryti",
        # Finnish companies & orgs
        "Nokia", "KONE", "Wärtsilä", "Finnair", "Supercell (yritys)",
        # Finnish culture
        "Jean Sibelius", "Alvar Aalto", "Tove Jansson",
        "Akseli Gallen-Kallela", "Kalevala",
        # Finnish cities & geography
        "Helsinki", "Tampere", "Turku", "Lappi (maakunta)", "Saimaa",
        # Science & sports
        "Linus Torvalds", "Mika Häkkinen", "Kimi Räikkönen",
        "Paavo Nurmi", "Teknologian tutkimuskeskus VTT",
    ]

    fetched = 0
    for subject in subjects[:count]:
        try:
            params = {
                "action": "query",
                "titles": subject,
                "prop": "extracts",
                "explaintext": True,
                "format": "json",
            }
            resp = requests.get(
                "https://fi.wikipedia.org/w/api.php",
                params=params,
                headers={"User-Agent": "AnvilAtlas/1.0"},
                timeout=15,
            )

            if resp.status_code == 200:
                pages = resp.json()["query"]["pages"]
                page = next(iter(pages.values()))
                text = page.get("extract", "")

                if text and len(text) > 200:
                    text = text[:8000]
                    safe_name = (
                        subject.replace(" ", "_")
                        .replace("/", "_")
                        .replace("(", "")
                        .replace(")", "")
                    )
                    filepath = out_dir / f"{safe_name}.txt"
                    filepath.write_text(text, encoding="utf-8")
                    fetched += 1
                    print(f"  Saved {subject} ({len(text)} chars)")

            time.sleep(0.2)

        except Exception as e:
            print(f"  Error fetching {subject}: {e}")

    print(f"Saved {fetched} Finnish Wikipedia articles")


# ─────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────

def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Fetch Finnish NER benchmark datasets"
    )
    parser.add_argument(
        "--datasets",
        nargs="*",
        default=["all"],
        choices=["all", "turku", "finer", "wikipedia"],
    )
    args = parser.parse_args()

    setup_dirs()

    targets = args.datasets
    if "all" in targets:
        targets = ["turku", "finer", "wikipedia"]

    for target in targets:
        print(f"\n{'='*50}")
        print(f"Fetching: {target}")
        print(f"{'='*50}")

        if target == "turku":
            fetch_turku_ner()
        elif target == "finer":
            fetch_finer()
        elif target == "wikipedia":
            fetch_wikipedia_fi()

    print(f"\n{'='*50}")
    print("Done. Dataset summary:")
    for d in sorted(BASE_DIR.iterdir()):
        if d.is_dir():
            txt_files = list(d.glob("*.txt"))
            gt_files = list(d.glob("*_ground_truth.json"))
            print(f"  {d.name}: {len(txt_files)} docs, {len(gt_files)} with ground truth")


if __name__ == "__main__":
    main()
