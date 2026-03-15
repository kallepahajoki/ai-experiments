# Training Run 004 — Two-Stage Architecture: 0.8B Gate + 4B Thinker

**Date:** 2026-03-11
**Hardware:** RTX 4090 (24GB VRAM), WSL2
**Training time:** ~8 min (gate) + ~30 min (thinker)
**Dataset:** 472 train / 123 eval + 26 hard eval

---

## Motivation

Run 003 showed that the 4B model achieves strong accuracy (96.6% on standard eval) but at 700-1200ms latency via Ollama — too slow for inline screening of every request. The 0.8B model is fast (~150ms via Ollama) but less precise. The two-stage architecture combines both: fast gate filters most traffic, slow thinker only activates on flagged inputs.

## Architecture

```
Input → Gate (0.8B, ~150ms) → SAFE → pass through
                             → UNSAFE → Thinker (4B, ~1s) → final verdict
```

The gate model errs on the side of caution (high recall, accepts false positives). The thinker then reviews gate-flagged inputs with reasoning to overturn false positives.

## Training Changes

### Gate Model (0.8B)
- **Mode:** `gate` — binary SAFE/UNSAFE only, no category/reason
- **Thinking:** Disabled (`enable_thinking=False`)
- **Output format:** Just `VERDICT: SAFE` or `VERDICT: UNSAFE`
- **System prompt:** "Respond with ONLY VERDICT: SAFE or VERDICT: UNSAFE. When in doubt, respond UNSAFE."
- **Oversampling:** 2x UNSAFE examples to bias toward higher recall
- **Sequence length:** 256 tokens (minimal — just needs the input + verdict)
- **Config:** `config-0.8b-gate.yaml`

### Thinker Model (4B)
- **Mode:** `thinker` — full classification with reasoning chains
- **Thinking:** Enabled (`enable_thinking=True`) — model generates `<think>` block before verdict
- **Output format:** Thinking chain + VERDICT + CATEGORY + REASON
- **System prompt:** Detailed classifier prompt asking model to "think carefully"
- **Training data:** `train_thinker.jsonl` with reasoning chains generated via Gemini 2.5 Flash
- **Sequence length:** 768 tokens (room for thinking + classification)
- **Config:** `config-4b-thinker.yaml`

### Reasoning Chain Generation
- Used Gemini 2.5 Flash via OpenRouter to generate thinking chains for all 472 training examples
- Cost: ~$0.10 total (~$0.0002/example)
- Speed: ~1 second per example
- Average thinking length: 516 characters (~3-4 sentences)
- Quality: Specific references to input patterns, proper category disambiguation
- Alternative tested: Kimi K2.5 — too slow (30-60s/request due to internal thinking token consumption)

## Results

### Standard Eval (123 examples)

| Metric | Gate (0.8B) | Thinker (4B) | Two-Stage Net |
|--------|:-----------:|:------------:|:-------------:|
| Accuracy | 0.837 | **0.967** | ~0.967 |
| Precision | 0.817 | **0.988** | ~0.988 |
| Recall | **0.988** | 0.965 | ~0.965 |
| F1 | 0.894 | **0.976** | ~0.976 |
| FP | 19 | **1** | ~1 |
| FN | **1** | 3 | 3 |

The gate catches 98.8% of threats (1 false negative). The thinker then reviews the gate's UNSAFE calls and overturns most false positives (from 19 down to ~1).

### Hard Eval (26 ambiguous cases)

| Metric | Gate (0.8B) | Thinker (4B) |
|--------|:-----------:|:------------:|
| Accuracy | 0.462 | **0.808** |
| Precision | 0.435 | **0.750** |
| Recall | **0.909** | 0.818 |
| FP | 13 | **3** |
| FN | **1** | 2 |

The hard eval specifically tests:
- **Legitimate ops that look dangerous** (SSL rotation, Docker cleanup, DB migration, pen testing)
- **Attacks with plausible business wrappers** (GDPR requests with hidden instructions, budget emails with buried injections)
- **Multilingual buried payloads** (German, Finnish)

The gate flags almost everything dangerous-looking (13/15 legitimate ops flagged as UNSAFE — expected and desired). The thinker correctly identifies most of them as safe, cutting false positives from 13 to 3.

### Training Metrics

**Gate (0.8B):**
- Epoch 1: loss 0.395, accuracy 0.892
- Epoch 3: loss 0.214, accuracy 0.949
- Eval loss: 0.263

**Thinker (4B):**
- Epoch 1: loss 0.657, token accuracy 83.5%, eval accuracy 88.3%
- Epoch 2: loss 0.564, token accuracy 85.0%, eval accuracy 88.8% (best)
- Epoch 3: loss 0.496, token accuracy 86.5%, eval accuracy 88.7%
- Slight overfitting by epoch 3; `load_best_model_at_end=true` selected epoch 2

## Known Gaps

### Gate False Negatives (misses)
1. Subtle cross-tenant data requests without destructive keywords (board presentation requesting all tenant data)
2. Multi-step attacks where individual steps look benign

### Thinker Weaknesses
1. Long documents exceeding 768-token context (procurement email at 4148 chars produced empty output)
2. Multi-step nginx routing with external IP exfiltration (missed the buried malicious step)
3. Phishing template generation with claimed "training" context

### Pipeline Leakage
If the gate says SAFE, the thinker never sees it. The gate's 1 FN on standard eval (creative writing jailbreak) and 1 FN on hard eval (cross-tenant request) are blind spots.

## Deployment

- Gate: Converted to GGUF Q4_K_M, deployed to Ollama as `anvil-ward-gate-q4`
- Thinker: Adapter trained, GGUF conversion pending
- Probe integration: Two-stage `screen()` implemented in `lib/ward.ts`, UI updated with stage indicators and expandable thinking chains

## Files Changed

- `train.py` — added gate/thinker/standard modes
- `evaluate.py` — mode-aware eval with `--eval-file` override
- `config-0.8b-gate.yaml` — gate training config
- `config-4b-thinker.yaml` — thinker training config
- `data/train_thinker.jsonl` — training data with reasoning chains
- `data/eval_hard.jsonl` — 26 ambiguous eval cases
- `data/generate_thinking.py` — Gemini Flash reasoning chain generator
- `inference_twostage.py` — CLI two-stage inference tool
- `deploy/Modelfile-ward-gate-q4` — Ollama Modelfile for gate
- `probe/lib/ward.ts` — two-stage screen() logic
- `probe/lib/db.ts` — ward_log schema with stage/thinking columns
- `probe/app/page.tsx` — UI with gate/thinker config and stage indicators
