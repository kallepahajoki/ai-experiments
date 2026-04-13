# AI Experiments

Practical experiments in fine-tuning small language models for targeted tasks — exploring where a few dozen carefully crafted examples can close the gap between a model that almost works and one that does.

Each subdirectory is a self-contained experiment with its own training data, scripts, and evaluation harness. The common thread: QLoRA on consumer hardware (RTX 4090, 24GB VRAM), Qwen 3.5 models, and deployment via Ollama.

---

## Experiments

### [`ward-security-classifier/`](ward-security-classifier/)

**LLM security classifier** — fine-tunes Qwen3.5 (0.8B / 2B / 4B) to detect prompt injection, jailbreaks, destructive commands, and agent manipulation. Designed as an input screening layer for AI agent pipelines.

Key results from benchmarking three model sizes on 472 training examples:

| | 0.8B | 2B | 4B |
|---|---|---|---|
| Accuracy | 82.9% | 95.9% | **98.4%** |
| Recall | 98.8% | 98.8% | **100%** |
| F1 | 0.890 | 0.971 | **0.989** |

The 4B model achieves perfect recall (zero missed threats) and shows genuine contextual reasoning — distinguishing "kill stuck PID 18234" (safe ops) from "kill all data" (destructive) — rather than pattern-matching on keywords.

Includes a proposed [two-stage architecture](ward-security-classifier/docs/two-stage-architecture.md): a 0.8B fast gate (~80ms) screens every request, escalating only flagged inputs to the 4B model for deep classification with chain-of-thought reasoning.

### [`ner-benchmark/`](ner-benchmark/)

**Named Entity Recognition benchmark** — compares local spaCy models (sm/lg/trf) against Qwen 3.5 LLMs (0.8B–9B via Ollama) for on-premise entity extraction across 4 English document domains.

Evaluated with both an LLM oracle (Gemini 2.5 Pro) and CoNLL-2003 human annotations, revealing that LLM oracles overstate the advantage of LLM-based NER by ~50%.

| | spaCy trf (CPU) | Qwen 3.5 9B (GPU) |
|---|---|---|
| F1 (human GT) | 0.628 | **0.717** |
| Recall | **0.793** | 0.748 |
| Precision | 0.519 | **0.688** |
| Speed | 1.0s/doc | 45s/doc |
| PERSON F1 | **0.915** | 0.875 |
| ORG F1 | 0.720 | **0.847** |

The two approaches are complementary: spaCy has higher recall (catches more entities), Qwen has higher precision (fewer false positives).

**Finnish NER** results tell a different story — spaCy dominates (F1 0.417 vs Qwen 4b's 0.274), and Qwen 0.8b extracts zero entities from tokenized Finnish text. No transformer pipeline exists for Finnish spaCy, so the CNN-based `fi_core_news_md` is the clear default. Qwen finetuning on Finnish NER data is a logical next step.

### [`ner-finetune-finnish/`](ner-finetune-finnish/)

**Finnish NER finetuning** — QLoRA finetune of Qwen 3.5 (0.8B/2B/4B) on Finnish NER data from Turku NER corpus and FiNER/Digitoday. Motivated by the benchmark above showing that base Qwen 3.5 models are essentially useless for Finnish entity extraction (best F1: 0.274 vs spaCy's 0.417).

Uses the full Turku NER corpus (~800 docs, 11k entities) and FiNER/Digitoday (~3,700 docs, 196k entities) as training data, formatted as instruction-tuning examples with a Finnish system prompt. Exports finetuned models to GGUF for Ollama deployment.

### [`grounding-eval/`](grounding-eval/)

**Source-grounded LLM output evaluation** — benchmarks how faithfully LLMs reproduce source material, detecting 12 failure modes from fabricated claims to subtle hedging removal. Uses an LLM judge (Claude Opus 4.6 via OpenRouter) to evaluate outputs from 7 subject models.

Motivated by a real incident: on 2026-03-29, Helsingin Sanomat's AI press release tool [fabricated a Russia attribution](https://www.hs.fi/paakirjoitukset/art-2000011912865.html) for a Finnish MoD drone press release that contained no country information. The erroneous breaking news was live for three minutes before correction.

Two eval cases: the drone incident press release, and a NATO nuclear law amendment proposal (sensitive — contains critical hedging and explicit denials). Benchmarked 8 models across both English and Finnish, 3 runs each, judged by Claude Opus 4.6 via OpenRouter (1,152 judge calls per language).

English results (2 cases × 8 models × 3 runs):

| Model | Overall failure rate | Critical failure rate | Notable patterns |
|---|---|---|---|
| openai/gpt-5.4-mini | **9.7%** | 16.7% | Lowest overall, clean and terse |
| anthropic/claude-sonnet-4.6 | 16.7% | 8.3% | Persistent editorial tone |
| qwen/qwen3.5-397b-a17b | 16.7% | **0.0%** | Zero critical failures |
| qwen/qwen3.5-122b-a10b | 18.1% | **0.0%** | Zero critical, barely behind 397b |
| google/gemini-3-flash-preview | 25.0% | 16.7% | 83% instruction leakage |
| openai/gpt-4o-2024-11-20 | 29.2% | 33.3% | 50% entity substitution, 83% hedging removal |
| minimax/minimax-m2.7 | 31.9% | 33.3% | Heavy fabrication and scope creep |
| mistralai/mistral-large-2512 | 40.3% | 58.3% | 100% fabrication, 100% scope creep |

Finnish results tell a different story — MiniMax M2.7 wins (16.7%), GPT 5.4 mini falls to 27.8%, and Qwen 397b is the most consistent across languages. A single fabricated-addition judge call (~$0.01) would have caught the HS error before publication.

### [`nextjs-server-boundary-finetune/`](nextjs-server-boundary-finetune/)

**Targeted reasoning correction** — fine-tunes Qwen3.5-27B to fix a specific Next.js webpack error where Node.js built-in modules fail to resolve in server bundles.

The 27B model (dense) gets tantalizingly close but picks the wrong webpack mechanism: `resolve.fallback: { crypto: false }` (silences the error, crashes at runtime) instead of `config.externals` (resolves modules from Node.js at runtime). The larger 122B MoE variant gets it right. This experiment tests whether QLoRA with ~43 synthetic training examples can install the correct reasoning path without needing 4x the parameters.

Training data deliberately excludes the real target project so it serves as a held-out generalization test.

### [`agent-memory-eval/`](agent-memory-eval/)

**Long-term memory for AI chat agents** — iterative development of a memory subsystem benchmarked against LongMemEval (ICLR 2025, 500 questions across 6 recall categories). Starting from pure vector RAG, progressively adding structured fact extraction, temporal supersession, and retrieval diversity.

| Version | Overall | Best improvement |
|---------|---------|-----------------|
| v0 — RAG only | 40.0% | — |
| v1 — + fact extraction | 52.0% | SS Assistant 50% → 100% |
| v2 — + supersession + diversity | 56.0% | Knowledge Update 42% → 67%, Multi-Session 25% → 50% |

The memory layer abstracts storage behind `memory.search` / `memory.store` tools — agents don't know about the backend. Today: Atlas (ChromaDB vector search) + Postgres (structured facts with LLM extraction and supersession). Dual-scoped by agent and/or project.

---

## Hardware

All experiments target a single RTX 4090 (24GB VRAM) using 4-bit NF4 quantization and gradient checkpointing. Trained models are exported to GGUF and served via Ollama for inference.

## License

Personal research. Code generated with assistance from Claude (Anthropic). Reasoning datasets for Ward generated with Gemini 2.5 Flash on OpenRouter.
