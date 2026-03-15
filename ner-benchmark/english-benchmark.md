# English NER Benchmark — spaCy vs Local LLMs

**Date:** 2026-03-15
**Infrastructure:** Mac Studio (CPU for spaCy) + RTX 4090 GPU server (Ollama for Qwen)
**Oracle:** Gemini 2.5 Pro via OpenRouter | **Ground truth:** CoNLL-2003 human annotations

## Objective

Compare NER quality and speed across local spaCy models and local Qwen 3.5 LLM models for English text, to determine the best configuration for a knowledge base entity extraction pipeline. The system runs on-premise — no cloud NER APIs.

## Models

### spaCy (CPU only)

| Model | Size | Type |
|-------|------|------|
| `en_core_web_sm` | 12 MB | Statistical |
| `en_core_web_lg` | 560 MB | Statistical + word vectors |
| `en_core_web_trf` | 438 MB | Transformer (RoBERTa) |

### Qwen 3.5 via Ollama (GPU)

| Model | Params |
|-------|--------|
| `qwen3.5:0.8b` | 0.8B |
| `qwen3.5:2b` | 2B |
| `qwen3.5:4b` | 4B |
| `qwen3.5:9b` | 9B |

All LLM models use the same system prompt requesting JSON entity extraction with types: PERSON, ORG, LOCATION, DATE, EVENT, PRODUCT, OTHER.

## Datasets

| Dataset | Docs | Source | Notes |
|---------|------|--------|-------|
| **wikipedia-bios** | 25 | Wikipedia API | Well-structured biographies |
| **sec-filings** | 10 | SEC EDGAR | 10-K filings, XBRL artifacts |
| **legal-contracts** | 15 | HuggingFace | Dense legalese |
| **conll2003** | 91 | CoNLL-2003 test set | Classic NER benchmark, has human annotations |

141 documents total.

## Evaluation Methodology

Three complementary evaluations:

1. **Quantitative** (all 141 docs) — entity counts, type distributions, cross-model agreement
2. **LLM Oracle** (20 sampled docs) — Gemini 2.5 Pro as ground truth, precision/recall/F1
3. **Human Ground Truth** (91 CoNLL-2003 docs) — comparison against human annotations, most reliable

## Results

### Speed

| Model | Time/doc | Factor | Hardware |
|-------|----------|--------|----------|
| en_core_web_sm | 0.4s | **1.0x** | CPU |
| en_core_web_lg | 0.3s | **0.8x** | CPU |
| en_core_web_trf | 1.0s | **2.5x** | CPU |
| qwen3.5:0.8b | 11.6s | **29x** | GPU |
| qwen3.5:2b | 19.1s | **48x** | GPU |
| qwen3.5:4b | 29.8s | **75x** | GPU |
| qwen3.5:9b | 45.1s | **113x** | GPU |

### Entity Counts

| Model | CoNLL | Wiki | Legal | SEC | Total |
|-------|-------|------|-------|-----|-------|
| spacy_sm | 7,236 | 3,994 | 2,345 | 285 | 13,860 |
| spacy_lg | 7,372 | 4,058 | 2,015 | 223 | 13,668 |
| spacy_trf | 7,019 | 3,907 | 1,610 | 109 | 12,645 |
| qwen 0.8b | 1,988 | 1,184 | 81 | 0 | 3,253 |
| qwen 2b | 4,365 | 2,031 | **0** | 103 | 6,499 |
| qwen 4b | 4,687 | 2,903 | 760 | 289 | 8,639 |
| qwen 9b | 4,675 | 2,897 | 384 | 233 | 8,189 |

spaCy extracts 2–4x more entities. Many are noise — ~30% end up as OTHER (numbers, percentages, quantities).

Notable: **Qwen 2b extracts zero entities from legal contracts** — consistently across retries. The 0.8b model (smaller) finds 81. The 2b model appears to "overthink" dense legalese and conclude nothing qualifies, while 0.8b is naive enough to try.

### Type Distribution

| Model | PERSON | ORG | LOC | DATE | EVENT | PRODUCT | OTHER |
|-------|--------|-----|-----|------|-------|---------|-------|
| spacy_trf | 19% | 15% | 16% | 19% | 1% | 2% | **29%** |
| qwen 9b | 23% | 22% | 24% | 16% | 6% | 5% | 4% |
| qwen 0.8b | **41%** | 23% | 18% | 7% | 6% | 4% | 1% |

LLMs have more balanced distributions and much better EVENT/PRODUCT detection. Qwen 0.8b is biased toward PERSON (41%).

### CoNLL-2003 Human Ground Truth (most reliable)

| Model | Precision | Recall | **F1** | Type Acc |
|-------|-----------|--------|--------|----------|
| **qwen 9b** | **0.688** | 0.748 | **0.717** | 0.887 |
| qwen 4b | 0.635 | 0.698 | 0.665 | 0.895 |
| spacy_trf | 0.519 | **0.793** | 0.628 | **0.903** |
| qwen 2b | 0.544 | 0.604 | 0.572 | 0.848 |
| spacy_lg | 0.368 | 0.614 | 0.460 | 0.791 |
| qwen 0.8b | 0.599 | 0.369 | 0.457 | 0.817 |
| spacy_sm | 0.323 | 0.533 | 0.402 | 0.764 |

#### Per-Type F1

| Model | PERSON | ORG | LOCATION | MISC |
|-------|--------|-----|----------|------|
| spacy_trf | **0.915** | 0.720 | 0.746 | **0.195** |
| qwen 9b | 0.875 | **0.847** | **0.761** | 0.091 |
| qwen 4b | 0.819 | 0.801 | 0.757 | 0.080 |

### LLM Oracle Evaluation (Gemini 2.5 Pro)

| Model | F1 (oracle) | F1 (human GT) | Oracle bias |
|-------|-------------|---------------|-------------|
| qwen 4b | 0.622 | 0.665 | -0.043 |
| qwen 9b | 0.611 | 0.717 | -0.106 |
| spacy_trf | 0.478 | 0.628 | -0.150 |

The LLM oracle systematically undervalues spaCy (bias of -0.150 for spaCy_trf vs -0.043 for Qwen 4b). Oracle precision vs human GT is only 70%. **Lesson: LLM oracles are a reasonable proxy but systematically favor LLM-style extraction.**

### Qwen Scaling Curve

| Model | F1 | Δ |
|-------|----|---|
| 0.8b | 0.457 | — |
| 2b | 0.572 | +0.115 |
| 4b | 0.665 | +0.093 |
| 9b | 0.717 | +0.052 |

Diminishing returns but still meaningful at 9b. The 0.8b→2b jump is largest.

## Key Findings

1. **Qwen 9b is the best model overall** (F1=0.717 vs human GT), but spaCy_trf is competitive (0.628) at 45x the speed on CPU.

2. **spaCy_trf has the highest recall** (0.793) — it catches more real entities than any LLM, but with lower precision (more false positives).

3. **spaCy_trf dominates PERSON extraction** (F1=0.915). **Qwen 9b dominates ORG** (F1=0.847). They have complementary strengths.

4. **LLM oracle bias is real and measurable.** It overstated the Qwen advantage by ~50%. Human annotations are essential for reliable evaluation.

5. **Small LLMs fail on specialized domains.** Qwen 2b extracts zero entities from legal text. Models below 4b are unreliable for anything beyond well-structured content.

6. **spaCy's ~30% OTHER bucket is genuine noise** — not a labeling difference. These are numbers, percentages, and quantities that shouldn't be entities.

## Recommendations

| Scenario | Model | Speed | F1 |
|----------|-------|-------|-----|
| Default (CPU) | spaCy trf | 2.5x | 0.628 |
| Best quality (GPU) | Qwen 9b | 113x | 0.717 |
| Good quality (GPU) | Qwen 4b | 75x | 0.665 |
| Bulk processing (CPU) | spaCy sm | 1.0x | 0.402 |

A hybrid approach works well: spaCy trf on ingest for instant high-recall results, with optional Qwen re-analysis for precision-critical spaces.

## Reproduction

Scripts in this directory:
- `fetch_data.py` — download benchmark datasets
- `analyze.py` — quantitative analysis
- `oracle_eval.py` — LLM oracle evaluation (requires OpenRouter API key)
- `conll_eval.py` — CoNLL-2003 human ground truth evaluation

The NER extraction itself runs through the [Anvil Atlas](https://github.com/...) CLI (`anvil atlas ner --preview --json`), which calls either a spaCy microservice or Ollama for LLM inference.
