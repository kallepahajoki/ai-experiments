# NER Benchmark — Local Models for Entity Extraction

Benchmarking Named Entity Recognition across local spaCy models and local LLMs (Qwen 3.5 via Ollama), evaluating the tradeoffs between speed, accuracy, and infrastructure requirements for on-premise entity extraction.

## Experiments

### [`english-benchmark.md`](english-benchmark.md) — English NER (Complete)

Compares 3 spaCy models (sm/lg/trf) and 4 Qwen 3.5 sizes (0.8b/2b/4b/9b) on 141 English documents across 4 domains: news (CoNLL-2003), Wikipedia biographies, SEC filings, and legal contracts.

Evaluated using Gemini 2.5 Pro as LLM oracle (20 docs) and CoNLL-2003 human annotations (91 docs). The human evaluation revealed that the LLM oracle overstates the advantage of LLM-based NER by ~50%.

**Headline results (vs human annotations):**

| Model | F1 | Speed | Hardware |
|-------|-----|-------|----------|
| Qwen 3.5 9B | **0.717** | 45s/doc | GPU |
| Qwen 3.5 4B | 0.665 | 30s/doc | GPU |
| spaCy trf | 0.628 | 1.0s/doc | CPU |
| spaCy sm | 0.402 | 0.4s/doc | CPU |

### [`finnish-benchmark.md`](finnish-benchmark.md) — Finnish NER (Complete)

Compares 3 spaCy Finnish models (sm/md/lg, all CNN-based) and 3 Qwen 3.5 sizes (0.8b/2b/4b) on 141 Finnish documents across 3 domains: Turku NER corpus, FiNER/Digitoday tech news, and Finnish Wikipedia.

Complete reversal from English — spaCy dominates, Qwen models are unreliable for Finnish.

**Headline results (vs human annotations):**

| Model | F1 | Hardware | Notes |
|-------|-----|----------|-------|
| spaCy md | **0.417** | CPU | Clear winner |
| spaCy lg | 0.411 | CPU | No improvement over md |
| Qwen 3.5 2B | 0.284 | GPU | Crashes on FiNER |
| Qwen 3.5 4B | 0.274 | GPU | Best Qwen, still 34% behind spaCy |
| Qwen 3.5 9B | 0.256 | GPU | Worse than 4b — scaling inverted |
| Qwen 3.5 0.8B | 0.000 | GPU | Zero entities on tokenized text |

## Structure

```
ner-benchmark/
├── english-benchmark.md    # English NER experiment report
├── analyze.py              # Quantitative analysis (entity counts, distributions, agreement)
├── oracle_eval.py          # LLM oracle evaluation (Gemini 2.5 Pro via OpenRouter)
├── conll_eval.py           # CoNLL-2003 human ground truth evaluation
├── fetch_data.py           # Dataset download script
├── requirements.txt        # Python dependencies
├── datasets/
│   └── conll2003/
│       └── _ground_truth.json  # Human NER annotations
└── results/                # Raw benchmark outputs (JSON per model per dataset)
    ├── oracle/             # Cached oracle responses
    ├── oracle_evaluation.json
    └── conll_gt_evaluation.json
```

## Hardware

- **CPU inference (spaCy):** Mac Studio M2 Ultra
- **GPU inference (Qwen/Ollama):** RTX 4090, 24GB VRAM
- **Oracle:** Gemini 2.5 Pro via OpenRouter (~$0.50 for full evaluation)
