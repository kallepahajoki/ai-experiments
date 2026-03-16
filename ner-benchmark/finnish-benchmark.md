# Finnish NER Benchmark — spaCy vs Qwen 3.5 LLMs

**Date:** 2026-03-15
**Infrastructure:** Mac Studio (CPU for spaCy) + RTX 4090 GPU server (Ollama for Qwen)
**Ground truth:** Turku NER Corpus + FiNER/Digitoday human annotations

## Objective

Compare NER quality for Finnish text across local spaCy Finnish models and Qwen 3.5 LLMs (via Ollama), to determine if the same model recommendations from the English benchmark apply to Finnish.

## Models

### spaCy Finnish (CPU only, CNN-based)

| Model | Size | Notes |
|-------|------|-------|
| `fi_core_news_sm` | ~15 MB | Fastest, no word vectors |
| `fi_core_news_md` | ~45 MB | 50k floret vectors |
| `fi_core_news_lg` | ~530 MB | 200k floret vectors |

No transformer pipeline exists for Finnish spaCy — all three are CNN-based (unlike English where `en_core_web_trf` uses RoBERTa). Trained on the Turku NER Corpus.

### Qwen 3.5 via Ollama (GPU)

| Model | Params |
|-------|--------|
| `qwen3.5:0.8b` | 0.8B |
| `qwen3.5:2b` | 2B |
| `qwen3.5:4b` | 4B |
| `qwen3.5:9b` | 9B |

Same models as the English benchmark.

## Datasets

| Dataset | Docs | Source | Ground Truth | Notes |
|---------|------|--------|-------------|-------|
| **Turku NER** | 60 (sampled from 800) | [TurkuNLP/turku-ner-corpus](https://github.com/TurkuNLP/turku-ner-corpus) | Yes | spaCy was **trained** on this — home-field advantage |
| **FiNER/Digitoday** | 60 (sampled from 3,716) | [mpsilfve/finer-data](https://github.com/mpsilfve/finer-data) | Yes | Tech news domain, fairer comparison |
| **Finnish Wikipedia** | 21 | Finnish Wikipedia API | No | Entity-rich biographies and articles |

141 documents total. Entity types: PER, ORG, LOC, PRO, EVENT, DATE.

## Results

### Entity Counts

| Model | Turku NER | FiNER | Wikipedia | Total |
|-------|-----------|-------|-----------|-------|
| spaCy sm | 2,658 | 4,502 | 3,438 | 10,598 |
| spaCy md | 2,656 | 4,407 | 3,706 | 10,769 |
| spaCy lg | 2,630 | 4,518 | 3,743 | 10,891 |
| Qwen 0.8b | **0** | **0** | 1,007 | 1,007 |
| Qwen 2b | 629 | FAIL* | 1,354 | 1,983 |
| Qwen 4b | 1,112 | 3,764 | 2,846 | 7,722 |
| Qwen 9b | 968 | 3,183 | 2,633 | 6,784 |

*Qwen 2b crashes Atlas on FiNER documents — consistent across retries. Similar to the English benchmark where 2b extracted zero entities from legal contracts.

### Ground Truth Evaluation — Turku NER Corpus

spaCy has a home-field advantage here (trained on this corpus).

| Model | Precision | Recall | **F1** | Type Acc |
|-------|-----------|--------|--------|----------|
| **spaCy lg** | 0.555 | **0.851** | **0.671** | **0.950** |
| spaCy md | 0.545 | 0.851 | 0.664 | 0.944 |
| spaCy sm | 0.500 | 0.756 | 0.602 | 0.903 |
| Qwen 4b | 0.431 | 0.511 | 0.468 | 0.928 |
| Qwen 2b | 0.338 | 0.244 | 0.284 | 0.868 |
| Qwen 0.8b | — | — | — | — |

### Ground Truth Evaluation — FiNER/Digitoday

Fairer comparison — different domain from spaCy's training data.

| Model | Precision | Recall | **F1** | Type Acc |
|-------|-----------|--------|--------|----------|
| **spaCy md** | 0.274 | **0.365** | **0.313** | 0.815 |
| spaCy lg | 0.262 | 0.362 | 0.304 | **0.810** |
| spaCy sm | 0.258 | 0.346 | 0.296 | 0.766 |
| Qwen 4b | 0.189 | 0.203 | 0.196 | 0.776 |
| Qwen 9b | 0.179 | 0.168 | 0.173 | **0.799** |
| Qwen 2b | — | — | FAIL | — |
| Qwen 0.8b | — | — | — | — |

### Combined Scores (both datasets)

| Model | Precision | Recall | **F1** | Type Acc |
|-------|-----------|--------|--------|----------|
| **spaCy md** | 0.358 | **0.501** | **0.417** | 0.879 |
| spaCy lg | 0.350 | 0.499 | 0.411 | **0.880** |
| spaCy sm | 0.332 | 0.460 | 0.385 | 0.835 |
| Qwen 2b | 0.338 | 0.244 | 0.284 | 0.868 |
| Qwen 4b | 0.261 | 0.289 | 0.274 | 0.852 |
| Qwen 9b | 0.261 | 0.251 | 0.256 | 0.874 |

### Per-Type F1 (combined)

| Model | PERSON | ORG | LOCATION | PRODUCT | EVENT | DATE |
|-------|--------|-----|----------|---------|-------|------|
| spaCy md | **0.620** | 0.525 | **0.778** | **0.336** | 0.219 | **0.331** |
| spaCy lg | 0.601 | **0.528** | 0.777 | 0.347 | **0.250** | 0.290 |
| spaCy sm | 0.574 | 0.525 | 0.650 | 0.309 | 0.291 | 0.312 |
| Qwen 2b | 0.403 | 0.237 | 0.278 | 0.212 | 0.094 | 0.437 |
| Qwen 4b | 0.348 | 0.344 | 0.448 | 0.201 | 0.070 | 0.312 |
| Qwen 9b | 0.325 | 0.308 | 0.463 | 0.166 | 0.131 | 0.265 |

## Key Findings

### 1. spaCy dominates Finnish NER — no contest

spaCy md/lg achieve F1 0.41-0.42 combined, while the best Qwen model manages only 0.28. This is a **complete reversal** from English, where Qwen 9b (0.717) beat spaCy trf (0.628).

### 2. Qwen 3.5 is not multilingual enough for Finnish NER

- **0.8b:** Extracts zero entities from tokenized Finnish text. Only works on clean Wikipedia prose.
- **2b:** Crashes Atlas on FiNER documents. Manages weak results (F1 0.284) on Turku NER.
- **4b:** Best Qwen model (F1 0.274) but still 34% behind spaCy md (0.417).
- **9b:** Actually worse than 4b (F1 0.256). More parameters doesn't help — the model needs Finnish NER training data, not more capacity.

The English NER prompt works poorly for Finnish — the models don't understand Finnish morphology well enough to identify entity boundaries in agglutinative text. The Qwen scaling curve is **flat or inverted** for Finnish, unlike English where 9b was the clear winner.

### 3. spaCy md is the sweet spot

spaCy md (45 MB) matches or slightly beats lg (530 MB) on most metrics. The extra word vectors in lg don't provide meaningful improvement for Finnish NER. Both significantly outperform sm.

### 4. The tokenized format hurts LLMs disproportionately

Both annotated corpora use space-separated tokenized text (from CoNLL format). spaCy handles this fine (it's what it was trained on). Qwen models struggle — the tokenized format breaks the natural language patterns they rely on. On clean Wikipedia prose, Qwen 4b extracts 2,846 entities (reasonable), but on tokenized text the count drops dramatically.

### 5. All models struggle on FiNER

Even spaCy only achieves F1 0.30 on FiNER, compared to 0.67 on Turku NER. FiNER's tech news domain is harder — many product names, company abbreviations, and compound Finnish words that are difficult to parse.

## Comparison with English Benchmark

| Metric | English (best) | Finnish (best) |
|--------|---------------|----------------|
| Best overall F1 | Qwen 9b: 0.717 | spaCy md: 0.417 |
| Best CPU F1 | spaCy trf: 0.628 | spaCy md: 0.417 |
| Best LLM F1 | Qwen 9b: 0.717 | Qwen 4b: 0.274 |
| LLM scaling | More params = better | Flat/inverted |
| Winner | LLM (with GPU) | spaCy (CPU) |

Finnish NER is significantly harder for all models, but the gap is much wider for LLMs. spaCy drops from 0.628 → 0.417 (34% decrease), while Qwen drops from 0.717 → 0.284 (60% decrease).

## Recommendations

### For Finnish NER today

**Use spaCy `fi_core_news_md`** — it's the clear winner. Fast (CPU), decent accuracy, good type classification. The lg model offers no meaningful improvement despite being 10x larger.

**Do not use Qwen 3.5 for Finnish NER** without finetuning. The base models lack sufficient Finnish language understanding for reliable entity extraction.

### Finetuning opportunity

The poor Qwen performance on Finnish suggests a LoRA finetune on Turku NER + FiNER training data could yield significant improvements. With ~5,000+ annotated Finnish sentences available, this is a viable path. See the [benchmark plan](../finnish-ner-benchmark-plan.md) Phase 2 for the finetuning approach.

### For Atlas default configuration

- **English:** spaCy trf (CPU) or Qwen 9b (GPU) — see [English benchmark](english-benchmark.md)
- **Finnish:** spaCy md (CPU) only — LLM backend not recommended for Finnish
- **Language detection → model routing** would allow Atlas to automatically select the right backend per document language

## Reproduction

```bash
# Fetch datasets
python fetch_finnish_data.py

# Sample for benchmark
python sample_finnish_data.py

# Upload to Atlas
for space in turku-ner finer-digitoday wikipedia-fi; do
    anvil atlas space create "bench-fi-${space}"
    anvil atlas upload --space "bench-fi-${space}" --skip-embeddings datasets-fi-sample/${space}/*.txt
done

# Run NER (spaCy)
for model in fi_core_news_sm fi_core_news_md fi_core_news_lg; do
    for space in turku-ner finer wikipedia; do
        anvil atlas ner --space "bench-fi-${space}" --backend spacy -m "${model}" --preview --json > "results-fi/spacy_${model##*_}_${space}.json"
    done
done

# Run NER (Qwen)
for model in qwen3.5:0.8b qwen3.5:2b qwen3.5:4b; do
    for space in turku-ner finer wikipedia; do
        anvil atlas ner --space "bench-fi-${space}" --backend llm -m "${model}" --preview --json > "results-fi/qwen_${model##*:}_${space}.json"
    done
done

# Evaluate
python finnish_eval.py
```
