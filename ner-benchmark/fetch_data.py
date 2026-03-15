#!/usr/bin/env python3
"""
fetch_data.py — Downloads benchmark datasets for Atlas NER evaluation.
Each dataset is saved as individual .txt files ready for upload to Atlas.

Requirements: pip install -r requirements.txt
"""

import os
import json
import time
import argparse
from pathlib import Path


BASE_DIR = Path("./datasets")


def setup_dirs():
    dirs = [
        "un-resolutions", "conll2003", "sec-filings",
        "legal-contracts", "wikipedia-bios", "scientific-abstracts",
    ]
    for d in dirs:
        (BASE_DIR / d).mkdir(parents=True, exist_ok=True)


def fetch_un_resolutions(count: int = 20):
    """Fetch UN resolutions via the UN Digital Library API."""
    import requests

    out_dir = BASE_DIR / "un-resolutions"
    api_url = "https://digitallibrary.un.org/api/v1/search"

    try:
        params = {
            "q": "General Assembly resolution",
            "format": "json",
            "rows": count,
            "fq": "languageCode:en",
        }
        resp = requests.get(api_url, params=params, timeout=30)
        if resp.status_code == 200:
            data = resp.json()
            for i, doc in enumerate(data.get("docs", [])[:count]):
                title = doc.get("title", f"resolution_{i}")
                body = doc.get("description", doc.get("fulltext", ""))
                if body:
                    safe_title = "".join(
                        c if c.isalnum() or c in " -_" else "_"
                        for c in title[:80]
                    )
                    (out_dir / f"{i:02d}_{safe_title}.txt").write_text(body, encoding="utf-8")
            print(f"Saved {count} UN resolutions")
            return
    except Exception as e:
        print(f"UN API failed ({e})")

    print(
        "NOTE: UN resolutions may require manual download.\n"
        "Visit https://digitallibrary.un.org and search for GA/SC resolutions.\n"
        f"Save as .txt files in {out_dir}"
    )


def fetch_conll2003():
    """Download CoNLL-2003 test split, reconstruct as pseudo-documents."""
    from datasets import load_dataset

    out_dir = BASE_DIR / "conll2003"
    ds = load_dataset("eriktks/conll2003", trust_remote_code=True)
    test = ds["test"]

    tag_names = {
        0: "O", 1: "B-PER", 2: "I-PER", 3: "B-ORG", 4: "I-ORG",
        5: "B-LOC", 6: "I-LOC", 7: "B-MISC", 8: "I-MISC",
    }

    current_doc, current_words, doc_idx = [], 0, 0
    for example in test:
        tokens = example["tokens"]
        current_doc.append(" ".join(tokens))
        current_words += len(tokens)
        if current_words >= 500:
            (out_dir / f"conll2003_test_{doc_idx:03d}.txt").write_text(
                "\n".join(current_doc), encoding="utf-8"
            )
            current_doc, current_words = [], 0
            doc_idx += 1
    if current_doc:
        (out_dir / f"conll2003_test_{doc_idx:03d}.txt").write_text(
            "\n".join(current_doc), encoding="utf-8"
        )
        doc_idx += 1

    # Save ground truth annotations
    annotations = []
    for example in test:
        tokens, tags = example["tokens"], example["ner_tags"]
        entities, current = [], None
        for i, (token, tag_id) in enumerate(zip(tokens, tags)):
            tag = tag_names[tag_id]
            if tag.startswith("B-"):
                if current: entities.append(current)
                current = {"text": token, "type": tag[2:], "start_token": i}
            elif tag.startswith("I-") and current:
                current["text"] += f" {token}"
            else:
                if current: entities.append(current)
                current = None
        if current: entities.append(current)
        annotations.append({"sentence": " ".join(tokens), "entities": entities})

    (out_dir / "_ground_truth.json").write_text(
        json.dumps(annotations, indent=2), encoding="utf-8"
    )
    print(f"Saved {doc_idx} CoNLL-2003 documents + ground truth")


def fetch_sec_filings(count: int = 10):
    """Fetch SEC 10-K filing excerpts from EDGAR."""
    import re
    import requests

    out_dir = BASE_DIR / "sec-filings"
    headers = {"User-Agent": "AnvilAtlas/1.0 benchmark@example.com", "Accept": "application/json"}

    companies = [
        ("0000320193", "Apple"), ("0001018724", "Amazon"),
        ("0001652044", "Alphabet"), ("0000789019", "Microsoft"),
        ("0001318605", "Tesla"), ("0000021344", "Coca-Cola"),
        ("0000078003", "Pfizer"), ("0000093410", "Chevron"),
        ("0000050863", "Intel"), ("0000886982", "Goldman-Sachs"),
    ]

    fetched = 0
    for cik, name in companies[:count]:
        try:
            resp = requests.get(f"https://data.sec.gov/submissions/CIK{cik}.json",
                                headers=headers, timeout=30)
            if resp.status_code != 200: continue
            filings = resp.json().get("filings", {}).get("recent", {})
            forms, accessions, docs = filings.get("form", []), filings.get("accessionNumber", []), filings.get("primaryDocument", [])
            for i, form in enumerate(forms):
                if form == "10-K":
                    accession = accessions[i].replace("-", "")
                    url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{accession}/{docs[i]}"
                    filing = requests.get(url, headers=headers, timeout=60)
                    if filing.status_code == 200:
                        text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", filing.text)).strip()[:10000]
                        (out_dir / f"{name}_10K.txt").write_text(text, encoding="utf-8")
                        fetched += 1
                        print(f"  Saved {name} 10-K ({len(text)} chars)")
                    break
            time.sleep(0.2)
        except Exception as e:
            print(f"  Error fetching {name}: {e}")
    print(f"Saved {fetched} SEC 10-K filings")


def fetch_legal_contracts(count: int = 15):
    """Download legal contracts from HuggingFace."""
    from datasets import load_dataset

    out_dir = BASE_DIR / "legal-contracts"
    try:
        ds = load_dataset("albertvillanova/legal_contracts", split="train", trust_remote_code=True)
        for i in range(min(count, len(ds))):
            text = ds[i].get("text", ds[i].get("contract", ""))
            if text:
                (out_dir / f"contract_{i:03d}.txt").write_text(text[:15000], encoding="utf-8")
        print(f"Saved {min(count, len(ds))} legal contracts")
    except Exception:
        print("Primary dataset unavailable, trying pile-of-law/atticus_contracts...")
        ds = load_dataset("pile-of-law/pile-of-law", "atticus_contracts",
                          split="train", streaming=True, trust_remote_code=True)
        for i, example in enumerate(ds):
            if i >= count: break
            (out_dir / f"contract_{i:03d}.txt").write_text(
                example.get("text", "")[:15000], encoding="utf-8"
            )
        print(f"Saved {min(i+1, count)} legal contracts")


def fetch_wikipedia_bios(count: int = 25):
    """Fetch Wikipedia biographies across diverse domains."""
    import requests

    out_dir = BASE_DIR / "wikipedia-bios"
    subjects = [
        "Marie Curie", "Nelson Mandela", "Angela Merkel", "Jawaharlal Nehru", "Simón Bolívar",
        "Alan Turing", "Rosalind Franklin", "Albert Einstein", "Ada Lovelace", "Nikola Tesla",
        "Frida Kahlo", "Toni Morrison", "Ludwig van Beethoven", "Hayao Miyazaki", "Gabriel García Márquez",
        "Grace Hopper", "Hedy Lamarr", "Andrew Carnegie", "Coco Chanel",
        "Pelé", "Serena Williams", "Muhammad Ali",
        "Amelia Earhart", "Ernest Shackleton", "Ibn Battuta",
    ]

    fetched = 0
    for subject in subjects[:count]:
        try:
            params = {"action": "query", "titles": subject, "prop": "extracts",
                      "explaintext": True, "format": "json"}
            resp = requests.get("https://en.wikipedia.org/w/api.php", params=params,
                                headers={"User-Agent": "AnvilAtlas/1.0"}, timeout=15)
            if resp.status_code == 200:
                page = next(iter(resp.json()["query"]["pages"].values()))
                text = page.get("extract", "")[:8000]
                if text:
                    safe_name = subject.replace(" ", "_").replace("/", "_")
                    (out_dir / f"{safe_name}.txt").write_text(text, encoding="utf-8")
                    fetched += 1
                    print(f"  Saved {subject} ({len(text)} chars)")
            time.sleep(0.1)
        except Exception as e:
            print(f"  Error fetching {subject}: {e}")
    print(f"Saved {fetched} Wikipedia biographies")


def fetch_scientific_abstracts(count: int = 50):
    """Fetch scientific paper abstracts from arXiv API."""
    import requests
    import xml.etree.ElementTree as ET

    out_dir = BASE_DIR / "scientific-abstracts"
    queries = [
        ("cat:cs.CL+AND+transformer", 10),
        ("cat:q-bio+AND+CRISPR", 10),
        ("cat:econ+AND+climate+change", 10),
        ("cat:quant-ph+AND+quantum+computing", 10),
        ("cat:q-bio.NC+AND+brain+imaging", 10),
    ]

    fetched = 0
    for query, per_query in queries:
        try:
            resp = requests.get("http://export.arxiv.org/api/query",
                                params={"search_query": query, "max_results": per_query,
                                        "sortBy": "relevance"}, timeout=60)
            if resp.status_code != 200:
                print(f"  arXiv API error for '{query}': {resp.status_code}")
                continue

            root = ET.fromstring(resp.text)
            ns = {"atom": "http://www.w3.org/2005/Atom"}
            for entry in root.findall("atom:entry", ns):
                title = entry.findtext("atom:title", "", ns).strip().replace("\n", " ")
                abstract = entry.findtext("atom:summary", "", ns).strip().replace("\n", " ")
                if not abstract:
                    continue
                authors = ", ".join(
                    a.findtext("atom:name", "", ns)
                    for a in entry.findall("atom:author", ns)[:5]
                )
                published = entry.findtext("atom:published", "", ns)[:4]  # year

                text = f"Title: {title}\nAuthors: {authors}\nYear: {published}\n\nAbstract:\n{abstract}"
                safe_title = "".join(
                    c if c.isalnum() or c in " -_" else "" for c in title[:60]
                ).strip().replace(" ", "_")
                (out_dir / f"{fetched:03d}_{safe_title}.txt").write_text(text, encoding="utf-8")
                fetched += 1

            time.sleep(3)  # arXiv asks for 3s between requests
        except Exception as e:
            print(f"  Error for query '{query}': {e}")
    print(f"Saved {fetched} scientific abstracts")


def main():
    parser = argparse.ArgumentParser(description="Fetch benchmark datasets for Atlas NER evaluation")
    parser.add_argument("--datasets", nargs="*", default=["all"],
                        choices=["all", "un", "conll2003", "sec", "legal", "wikipedia", "scientific"])
    parser.add_argument("--base-dir", type=str, default="./datasets")
    args = parser.parse_args()

    global BASE_DIR
    BASE_DIR = Path(args.base_dir)
    setup_dirs()

    targets = args.datasets
    if "all" in targets:
        targets = ["un", "conll2003", "sec", "legal", "wikipedia", "scientific"]

    dispatch = {
        "un": fetch_un_resolutions, "conll2003": fetch_conll2003,
        "sec": fetch_sec_filings, "legal": fetch_legal_contracts,
        "wikipedia": fetch_wikipedia_bios, "scientific": fetch_scientific_abstracts,
    }
    for target in targets:
        print(f"\n{'='*50}\nFetching: {target}\n{'='*50}")
        dispatch[target]()

    print(f"\n{'='*50}\nDone. Dataset summary:")
    for d in sorted(BASE_DIR.iterdir()):
        if d.is_dir():
            print(f"  {d.name}: {len(list(d.glob('*.txt')))} files")


if __name__ == "__main__":
    main()
