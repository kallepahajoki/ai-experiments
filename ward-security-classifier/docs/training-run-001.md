# Training Run 001 — Anvil Firewall Security Classifier

**Date:** 2026-03-10
**Hardware:** RTX 4090 (24GB VRAM), WSL2
**Training time:** ~11 minutes

---

## What We Did

Fine-tuned **Qwen3.5-4B** (a 4 billion parameter language model) as a security classifier that screens inputs to the Anvil AI platform. The goal: detect prompt injection, jailbreaks, destructive commands, and agent manipulation — and block them before they reach the AI agents.

## The Technique: LoRA (Low-Rank Adaptation)

Instead of retraining all 4.2B parameters, we used **LoRA** which freezes the base model and trains small adapter matrices injected into the attention and feed-forward layers. Training reported:

```
trainable params: 21,233,664 || all params: 4,226,984,960 || trainable%: 0.5023
```

Only **0.5%** of the model was actually trained — roughly 21M parameters. This makes training fast (11 minutes on the RTX 4090) and memory-efficient.

**Key LoRA settings from `config.yaml`:**
- **rank=16** — size of the low-rank matrices (higher = more capacity, more memory)
- **lora_alpha=32** — scaling factor (typically 2x the rank)
- **target_modules** — applied to all attention projections (q/k/v/o) and MLP layers (gate/up/down), giving the model broad ability to adapt

## Training Setup

| Setting | Value | Why |
|---------|-------|-----|
| Batch size | 2 | Limited by 24GB VRAM |
| Gradient accumulation | 8 steps | Effective batch = 16, smoother training |
| Learning rate | 2e-4 (cosine) | Standard for LoRA fine-tuning |
| Epochs | 3 | Enough passes for a small dataset |
| Precision | bfloat16 | Half the memory of float32, RTX 4090 native |
| Optimizer | paged_adamw_8bit | Quantized optimizer, saves more VRAM |

## Training Data

**360 training / 90 eval** examples across 5 categories: benign, prompt_injection, jailbreak, destructive, agent_manipulation. Each example has an input text, verdict (SAFE/UNSAFE), category, and reason.

## Results

### Binary Classification (SAFE vs UNSAFE)

This is the primary use case — should Probe block this input?

| Metric | Score | Meaning |
|--------|-------|---------|
| Accuracy | 90.0% | 81/90 correct overall |
| Precision | 98.2% | When it says UNSAFE, it's almost always right (1 false positive) |
| Recall | 87.3% | Catches 87% of actual threats (misses 8) |
| F1 | 92.4% | Harmonic mean of precision/recall |

**High precision (98.2%)** is great for a security gate — almost zero false alarms on legitimate inputs. **Recall at 87.3%** means ~13% of attacks slip through, which is where improvement is needed.

### Per-Category F1 Scores

| Category | F1 | Precision | Recall | Assessment |
|----------|-----|-----------|--------|-----------|
| benign | 94.5% | 92.9% | 96.3% | Strong — rarely flags safe inputs |
| jailbreak | 80.0% | 70.0% | 93.3% | Good — catches most roleplay/fiction bypasses |
| destructive | 80.0% | 85.7% | 75.0% | Good — detects dangerous commands |
| prompt_injection | 73.3% | 84.6% | 64.7% | Needs work — confuses with agent_manipulation |
| agent_manipulation | 58.3% | 77.8% | 46.7% | Weakest — often miscategorised |

### Confusion Matrix

```
TRUE \ PRED          benign  prompt_inj  jailbreak  destructive  agent_manip  unknown
benign                  26           0          0            1            0        0
prompt_injection         0          11          3            0            2        1
jailbreak                1           0         14            0            0        0
destructive              1           0          0           12            0        3
agent_manipulation       0           2          3            1            7        2
```

### Key Failure Pattern

The confusion matrix reveals the main issue: **prompt_injection and agent_manipulation are getting mixed up**. This makes sense — "Ignore your instructions, I'm the admin" is both injection and manipulation. The model needs more diverse examples with clearer category boundaries.

### Loss

- **Train loss: 0.507** — how wrong the model's predictions were on training data by the end
- **Eval loss: 0.384** — lower than train loss, which is healthy (no overfitting)

Eval loss being lower than train loss is typical with LoRA + dropout — dropout is active during training (making it harder) but off during evaluation.

## Next Steps

1. **More agent_manipulation examples** — weakest category with only 58% F1
2. **Clearer category boundaries** — sharpen the distinction between prompt_injection and agent_manipulation
3. **Hard negatives** — tricky benign inputs that look suspicious but are safe
4. **Consider merging categories** — if the injection/manipulation distinction isn't operationally useful, combining them could boost overall accuracy
