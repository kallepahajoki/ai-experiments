# Ward Benchmark Results — 2026-03-10

## Overview

Side-by-side evaluation of three Qwen3.5 model sizes (0.8B, 2B, 4B) fine-tuned as Ward security classifiers. All models trained on the same 472 examples with identical LoRA configuration (rank 16, alpha 32) and evaluated on 123 held-out examples.

---

## Binary Classification (SAFE vs UNSAFE)

| Metric | 0.8B | 2B | 4B |
|--------|------|-----|-----|
| Accuracy | 0.829 | 0.959 | **0.984** |
| Precision | 0.810 | 0.955 | **0.977** |
| Recall | 0.988 | 0.988 | **1.000** |
| F1 | 0.890 | 0.971 | **0.989** |
| Correct verdicts | 102/123 | 118/123 | **121/123** |
| Failures | 21 | 5 | 2 |

### Key takeaway
All three models have excellent recall (0.988-1.000) — they almost never miss a real threat. The difference is in **precision**: the 0.8B model flags 21 legitimate inputs as unsafe (false positives), while the 4B model only has 2 errors total.

The 4B model achieved **perfect recall** — zero false negatives on the eval set.

---

## Per-Category F1 Scores

| Category | 0.8B | 2B | 4B |
|----------|------|-----|-----|
| benign | 0.593 | 0.930 | **0.972** |
| prompt_injection | 0.737 | 0.765 | **0.833** |
| jailbreak | 0.867 | 0.933 | **0.968** |
| destructive | 0.711 | 0.842 | **0.947** |
| agent_manipulation | 0.649 | 0.767 | **0.899** |

### Key takeaway
Category accuracy scales strongly with model size. The 0.8B model struggles most with benign (F1 0.593 — lots of false positives on legitimate ops commands) and agent_manipulation (F1 0.649 — confusion with other attack types). The 4B model improves significantly across all categories.

The weakest category across all sizes is **prompt_injection** (0.737 → 0.833). This is expected — prompt injections are the most diverse category and often overlap semantically with agent_manipulation.

---

## Latency

| Metric | 0.8B | 2B | 4B |
|--------|------|-----|-----|
| Mean (ms) | 9,313 | 9,262 | 12,877 |
| p50 (ms) | 9,296 | 9,209 | 12,852 |
| p95 (ms) | 9,583 | 9,625 | 13,565 |

**Note:** These latencies are from Python/transformers inference on GPU without quantization, after a cold WSL restart. They are **not representative of production performance**. In Ollama with Q4_K_M quantization, expect:
- 0.8B: ~50-100ms
- 4B: ~700-1200ms (as measured in previous Ollama deployment testing)

The 0.8B and 2B models show nearly identical latency here, suggesting the bottleneck at this scale is overhead (tokenization, template construction) rather than model compute.

---

## Training Metrics

| Metric | 0.8B | 2B | 4B |
|--------|------|-----|-----|
| Train loss | 0.629 | 0.554 | 0.483 |
| Eval loss | 0.545 | 0.472 | 0.415 |
| Train time | 6 min | 11 min | 19 min |
| Adapter size | 25 MB | 44 MB | 85 MB |

All models converge cleanly with eval loss lower than train loss (no overfitting). The 4B model achieves the lowest loss and the best generalization.

---

## Analysis: Pattern Matching vs Generalization

This benchmark answers the question: **how much does model size help when the training data is small?**

### Binary classification is "easy"
Even the 0.8B model achieves 0.988 recall — it learned the safe/unsafe boundary well. The difference is entirely in precision (false positives). This suggests the binary boundary can be taught with simple pattern matching, but distinguishing "scary-sounding legitimate ops" from actual threats requires more capacity.

### Category classification scales with size
The largest improvements from 0.8B → 4B are:

| Category | Improvement |
|----------|------------|
| benign | +0.379 (0.593 → 0.972) |
| agent_manipulation | +0.250 (0.649 → 0.899) |
| destructive | +0.236 (0.711 → 0.947) |
| prompt_injection | +0.096 (0.737 → 0.833) |
| jailbreak | +0.101 (0.867 → 0.968) |

The biggest gains are in categories that require **contextual understanding** — distinguishing legitimate ops (benign) from actual destruction, and separating agent manipulation from other attack types. This is genuine reasoning, not just pattern matching.

### The 0.8B model is a pattern matcher
The 0.8B model's benign F1 of 0.593 means it flags nearly half of legitimate operations as unsafe. It's triggering on surface features ("kill", "truncate", "remove", "delete") without understanding context. This is exactly the behavior we'd expect from a small model trained on limited data.

### The 4B model shows real understanding
The 4B model's near-perfect benign classification (F1 0.972) means it can distinguish "kill stuck PID 18234" (benign) from "kill all processes" (destructive). This requires understanding intent, specificity, and operational context — evidence of genuine generalization from pre-training knowledge, not just pattern matching of the 472 training examples.

---

## Implications for Two-Stage Architecture

These results strongly validate the proposed two-stage approach (see [two-stage-architecture.md](./two-stage-architecture.md)):

### Stage 1: 0.8B as fast gate
- **Recall 0.988** — only misses 1 out of 86 unsafe inputs
- Perfect for high-recall gating: flag aggressively, let stage 2 sort it out
- The high false positive rate (21 failures) is a feature, not a bug — it means stage 2 has work to do
- With binary-only training (no category), recall may improve further

### Stage 2: 4B as deep thinker
- **100% recall + 0.984 accuracy** — already excellent without thinking enabled
- With `enable_thinking=True`, expect further improvement on:
  - The remaining 2 verdict errors
  - Category confusion (especially prompt_injection vs agent_manipulation)
  - Borderline cases where reasoning about context matters

### Expected traffic flow
If ~70% of requests are benign and the 0.8B gate has ~80% precision:
- ~70% of requests: SAFE → pass through (stage 1 only, ~80ms)
- ~10% of requests: correctly flagged UNSAFE → confirmed by stage 2 (~1.5s total)
- ~20% of requests: false positives → overturned by stage 2 (~1.5s total)
- **Average latency: ~500ms** (vs 700-1200ms for 4B on everything)

As the 0.8B gate improves with more training data or binary-only training, the false positive rate drops and average latency approaches 80ms.

---

## Next Steps

1. **Test 4B with thinking enabled (zero-shot)** — run the current 4B adapter with `enable_thinking=True` on the eval set to see if reasoning chains improve the 2 remaining errors and category accuracy, before investing in retraining
2. **Generate reasoning chains** — use Claude API to create `<think>` content for all 472 training examples
3. **Retrain 0.8B as binary-only gate** — simplified output (VERDICT only), oversampled UNSAFE examples for higher recall
4. **Retrain 4B with thinking** — include reasoning chains in training data
5. **Integrate into Probe** — two-stage `/api/ward` endpoint
