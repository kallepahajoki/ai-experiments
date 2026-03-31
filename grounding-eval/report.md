# Grounding Evaluation Report

## Failure Modes

- **Fabricated Addition** [critical]: Model adds factual claims not present in the source.
- **Contradiction** [critical]: Output directly conflicts with source — says X when source says Y.
- **Entity Substitution** [high]: Correct fact type but wrong entity — names, organizations, locations swapped.
- **Numerical Distortion** [high]: Numbers changed, rounded incorrectly, or units swapped.
- **Temporal Drift** [high]: Dates, times, tenses, or sequence of events misrepresented.
- **Hedging Removal (Certainty Inflation)** [high]: Source expresses uncertainty; output presents it as established fact.
- **Hedging Addition (Certainty Deflation)** [medium]: Source states something definitively; output softens it inappropriately.
- **Framing Shift / Sentiment Injection** [medium]: Factually accurate but adds editorial tone, bias, or implied causality not in source.
- **Scope Creep / Context Bleed** [medium]: Model incorporates background knowledge not in the provided source.
- **Omission of Critical Information** [high]: Key facts, caveats, or conditions in source are silently dropped.
- **Composite Claim Conflation** [high]: Model merges two separate statements into one, creating a false combined claim.
- **Instruction Leakage / Prompt Injection Echo** [medium]: Model echoes system prompt fragments or meta-instructions into output.

---

## Round 2 Results (8 models, 2 eval cases, 3 runs each)

Eval cases:
1. **Drone incident** — MoD press release on suspected territorial violation by drones in Southeast Finland (2026-03-29)
2. **NATO nuclear law amendment** — MoD press release proposing amendments to nuclear energy and criminal law to align with NATO (2026-03-05). Extremely sensitive: a proposal for consultation, not a decision; contains explicit denial that Finland seeks nuclear weapons.

### English Results

```
Model                                      Fabricated Addit      Contradiction   Entity Substitut   Numerical Distor     Temporal Drift   Hedging Removal    Hedging Addition   Framing Shift /    Scope Creep / Co   Omission of Crit   Composite Claim    Instruction Leak
----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
anthropic/claude-sonnet-4.6                       17% (1/6)           0% (0/6)           0% (0/6)           0% (0/6)          33% (2/6)          50% (3/6)           0% (0/6)          83% (5/6)          17% (1/6)           0% (0/6)           0% (0/6)           0% (0/6)
google/gemini-3-flash-preview                     33% (2/6)           0% (0/6)           0% (0/6)           0% (0/6)          17% (1/6)          50% (3/6)           0% (0/6)         100% (6/6)          17% (1/6)           0% (0/6)           0% (0/6)          83% (5/6)
minimax/minimax-m2.7                              67% (4/6)           0% (0/6)          17% (1/6)           0% (0/6)          50% (3/6)          33% (2/6)           0% (0/6)         100% (6/6)          67% (4/6)           0% (0/6)          50% (3/6)           0% (0/6)
mistralai/mistral-large-2512                     100% (6/6)          17% (1/6)           0% (0/6)           0% (0/6)          50% (3/6)          17% (1/6)          17% (1/6)         100% (6/6)         100% (6/6)           0% (0/6)          17% (1/6)          67% (4/6)
openai/gpt-4o-2024-11-20                          50% (3/6)          17% (1/6)          50% (3/6)           0% (0/6)          17% (1/6)          83% (5/6)           0% (0/6)          83% (5/6)          50% (3/6)           0% (0/6)           0% (0/6)           0% (0/6)
openai/gpt-5.4-mini                               33% (2/6)           0% (0/6)           0% (0/6)           0% (0/6)           0% (0/6)           0% (0/6)           0% (0/6)          67% (4/6)          17% (1/6)           0% (0/6)           0% (0/6)           0% (0/6)
qwen/qwen3.5-122b-a10b                             0% (0/6)           0% (0/6)           0% (0/6)           0% (0/6)          17% (1/6)          83% (5/6)           0% (0/6)          50% (3/6)          17% (1/6)           0% (0/6)          17% (1/6)          33% (2/6)
qwen/qwen3.5-397b-a17b                             0% (0/6)           0% (0/6)           0% (0/6)           0% (0/6)          67% (4/6)          33% (2/6)           0% (0/6)          67% (4/6)           0% (0/6)           0% (0/6)          33% (2/6)           0% (0/6)
```

| Model | Overall | Critical | Key pattern |
|---|---|---|---|
| **openai/gpt-5.4-mini** | **9.7%** | 16.7% | Lowest overall, clean and terse |
| anthropic/claude-sonnet-4.6 | 16.7% | 8.3% | Improved from R1, still editorializes |
| qwen/qwen3.5-397b-a17b | 16.7% | **0.0%** | Zero critical failures |
| qwen/qwen3.5-122b-a10b | 18.1% | **0.0%** | Zero critical, barely behind 397b |
| google/gemini-3-flash-preview | 25.0% | 16.7% | Better than Gemini 2.5 Flash was |
| openai/gpt-4o-2024-11-20 | 29.2% | 33.3% | Disappointing — 50% entity substitution, 83% hedging removal |
| minimax/minimax-m2.7 | 31.9% | 33.3% | Heavy fabrication and scope creep |
| mistralai/mistral-large-2512 | **40.3%** | **58.3%** | 100% fabrication, 100% scope creep |

### Finnish Results

```
Model                                      Fabricated Addit      Contradiction   Entity Substitut   Numerical Distor     Temporal Drift   Hedging Removal    Hedging Addition   Framing Shift /    Scope Creep / Co   Omission of Crit   Composite Claim    Instruction Leak
----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
anthropic/claude-sonnet-4.6                       17% (1/6)          17% (1/6)           0% (0/6)          50% (3/6)          67% (4/6)          83% (5/6)           0% (0/6)          67% (4/6)           0% (0/6)           0% (0/6)           0% (0/6)           0% (0/6)
google/gemini-3-flash-preview                     50% (3/6)          17% (1/6)           0% (0/6)          17% (1/6)          50% (3/6)          50% (3/6)           0% (0/6)          33% (2/6)          33% (2/6)           0% (0/6)          33% (2/6)         100% (6/6)
minimax/minimax-m2.7                               0% (0/6)          33% (2/6)           0% (0/6)          17% (1/6)          50% (3/6)          67% (4/6)          17% (1/6)          17% (1/6)           0% (0/6)           0% (0/6)           0% (0/6)           0% (0/6)
mistralai/mistral-large-2512                      50% (3/6)           0% (0/6)          17% (1/6)           0% (0/6)          50% (3/6)          83% (5/6)           0% (0/6)          83% (5/6)          50% (3/6)           0% (0/6)           0% (0/6)           0% (0/6)
openai/gpt-4o-2024-11-20                           0% (0/6)           0% (0/6)           0% (0/6)           0% (0/6)          83% (5/6)          83% (5/6)           0% (0/6)          67% (4/6)           0% (0/6)          17% (1/6)          33% (2/6)           0% (0/6)
openai/gpt-5.4-mini                               17% (1/6)          17% (1/6)           0% (0/6)          17% (1/6)         100% (6/6)          50% (3/6)          33% (2/6)          83% (5/6)           0% (0/6)           0% (0/6)          17% (1/6)           0% (0/6)
qwen/qwen3.5-122b-a10b                            33% (2/6)          17% (1/6)           0% (0/6)           0% (0/6)         100% (6/6)          50% (3/6)           0% (0/6)          50% (3/6)          33% (2/6)           0% (0/6)          50% (3/6)          17% (1/6)
qwen/qwen3.5-397b-a17b                            17% (1/6)          17% (1/6)           0% (0/6)           0% (0/6)          83% (5/6)          50% (3/6)           0% (0/6)          50% (3/6)           0% (0/6)          17% (1/6)          33% (2/6)           0% (0/6)
```

| Model | Overall | Critical | Key pattern |
|---|---|---|---|
| **minimax/minimax-m2.7** | **16.7%** | 16.7% | Surprise Finnish winner, zero fabrication |
| qwen/qwen3.5-397b-a17b | 22.2% | 16.7% | Consistent across languages |
| openai/gpt-4o-2024-11-20 | 23.6% | **0.0%** | Zero critical in Finnish, redeems itself |
| anthropic/claude-sonnet-4.6 | 25.0% | 16.7% | Stable, 83% hedging removal persists |
| mistralai/mistral-large-2512 | 27.8% | 25.0% | Much better than English (40.3%) |
| openai/gpt-5.4-mini | 27.8% | 16.7% | 100% temporal drift — loses edge in Finnish |
| qwen/qwen3.5-122b-a10b | 29.2% | 25.0% | Worse than 397b in Finnish |
| google/gemini-3-flash-preview | 31.9% | 33.3% | 100% instruction leakage persists |

### English vs Finnish Comparison

| Model | English | Finnish | Change |
|---|---|---|---|
| minimax/minimax-m2.7 | 31.9% | **16.7%** | much improved |
| qwen/qwen3.5-397b-a17b | 16.7% | 22.2% | slightly worse |
| openai/gpt-4o-2024-11-20 | 29.2% | 23.6% | improved |
| anthropic/claude-sonnet-4.6 | 16.7% | 25.0% | worse |
| mistralai/mistral-large-2512 | 40.3% | 27.8% | much improved |
| openai/gpt-5.4-mini | **9.7%** | 27.8% | much worse |
| qwen/qwen3.5-122b-a10b | 18.1% | 29.2% | worse |
| google/gemini-3-flash-preview | 25.0% | 31.9% | worse |

---

## Analysis

### Model Rankings

**Best English summarizer: GPT 5.4 Mini (9.7%).** Terse, factual, disciplined. But falls off significantly in Finnish (27.8%), suggesting its faithfulness advantage is partly tied to English fluency rather than deep source-grounding ability.

**Best Finnish summarizer: MiniMax M2.7 (16.7%).** A surprise — this model was mediocre in English (31.9%) but excelled in Finnish with zero fabrication. Wild swing suggests language-specific training strengths.

**Most consistent across languages: Qwen 3.5 397B (16.7% EN / 22.2% FI).** Zero critical failures in English, modest degradation in Finnish. The most predictable model in the benchmark.

**Most improved model: Mistral Large 2512.** Terrible in English (40.3%, 100% fabrication) but mid-pack in Finnish (27.8%). The English fabrication was systematic scope creep and attribution errors, not Finnish-language issues.

### Qwen 122B vs 397B

| | 122B | 397B |
|---|---|---|
| English | 18.1% | 16.7% |
| Finnish | 29.2% | 22.2% |
| Critical (EN) | 0.0% | 0.0% |
| Critical (FI) | 25.0% | 16.7% |

Nearly identical in English, but the 397B pulls ahead in Finnish — lower failure rate, fewer critical failures. The extra parameters help most where the task is hardest. Both models maintain zero critical failures in English, making them the safest choice for high-stakes summarization when used in English.

### GPT-4o: An Iconic Model's Blind Spots

GPT-4o-2024-11-20 at 29.2% English failure rate was the weakest OpenAI model tested — worse than GPT 5.4 mini by 3x. Notable problems: 50% entity substitution (swapping organizations), 83% hedging removal (presenting proposals as decisions). However, it redeemed itself in Finnish with zero critical failures, suggesting its English errors are editorial choices rather than comprehension failures.

### The Nuclear Case Effect

Adding the NATO nuclear law amendment case raised failure rates across the board. This case is harder: longer source, more hedging language, critical negations ("Finland does NOT seek nuclear weapons"), and a legally precise distinction between what would be allowed (transit/possession) and what stays criminalised (acquisition/manufacture/detonation). Models that were clean on the drone case stumbled here — the nuclear topic attracted more scope creep and framing shifts.

### Persistent Patterns

**Framing shift remains near-universal.** 6 of 8 models hit 67%+ in English. LLMs editorialize by default.

**Hedging removal is the silent killer.** Most models drop uncertainty language at 50%+ rates. For newsroom use, this is arguably more dangerous than outright fabrication — a reader won't question a summary that sounds confident.

**Instruction leakage is a Gemini problem.** 83-100% across both languages and both rounds. The "Here's a summary of..." prefix is baked into Gemini's behavior.

**Nobody fabricated "Russian drones"** — across either round, either language, or any model. The specific HS hallucination remains unreproduced. We don't know what model HS uses, its system prompt, what additional context (e.g. recent news, geopolitical priors, retrieval-augmented context) is fed alongside the press release, or whether it's a fine-tuned or older model. A judge call checking the output against the source would have caught it regardless of the cause.

---

## Could an LLM Judge Have Prevented the HS Error?

On 2026-03-30, Helsingin Sanomat editor-in-chief Erja Yläjärvi [published a statement](https://www.hs.fi/paakirjoitukset/art-2000011912865.html) confirming that HS had published erroneous information claiming Russian drones had been downed in Kouvola. The error was live for three minutes. Ilta-Sanomat made the same mistake. The root cause: **an AI tool used to summarize press releases had fabricated the Russia attribution**. The tool headlines press release alerts on an internal channel, and journalists picked up the hallucinated headline as breaking news. Yläjärvi wrote: "Tekoälytyökalu oli tässä tapauksessa täysin virheellisesti otsikoinut Puolustusministeriön tiedotehälytyksen Venäjään liittyväksi, vaikka itse tiedotteessa ei puhuttu maasta mitään." (The AI tool had completely erroneously headlined the Ministry of Defence press release alert as related to Russia, even though the press release itself said nothing about any country.)

This is a textbook **fabricated addition** — the most critical failure mode in our framework.

**Could an LLM-as-judge have caught it?** Yes, trivially. Our benchmark's fabricated addition judge prompt asks the judge to verify every factual claim against the source. In our test, Opus 4.6 successfully detected fabricated additions across all models that produced them — including far more subtle cases than a country attribution that doesn't exist in the source at all. Even a cheaper judge model would catch "Russian drones" when the source mentions no country.

**What would it cost?**

- Running the fabricated addition judge alone on one press release summary: **~$0.01** (500 input tokens + 300 output tokens at Opus 4.6 pricing)
- Running all 12 failure modes on one press release summary: **~$0.12**
- Running the full 12-mode evaluation on every press release HS processes in a day (estimate ~50-100 alerts): **$6-12/day**
- Using a cheaper judge (Sonnet 4.6 at ~$0.003/M input): **under $1/day** for all alerts

---

## Round 1 Results (archived)

Initial exploratory round with 7 models, 1 eval case (drone incident only), 3 runs per model in English and 1 run in Finnish. These results used different models (Gemini 2.5 Flash, Mistral Small 2603, Nemotron 120B, Qwen 9B) and are preserved for reference but superseded by Round 2.

### Round 1 English (1 case, 3 runs, 7 models)

| Model | Overall | Critical |
|---|---|---|
| openai/gpt-5.4-mini | **5.6%** | **0.0%** |
| nvidia/nemotron-3-super-120b-a12b:free | 16.7% | 33.3% |
| qwen/qwen3.5-122b-a10b | 19.4% | 0.0% |
| mistralai/mistral-small-2603 | 22.2% | 16.7% |
| anthropic/claude-sonnet-4.6 | 27.8% | 33.3% |
| google/gemini-2.5-flash | 36.1% | 50.0% |
| qwen/qwen3.5-9b | 36.1% | 33.3% |

### Round 1 Finnish (1 case, 1 run, 7 models)

| Model | Overall | Critical |
|---|---|---|
| qwen/qwen3.5-122b-a10b | **8.3%** | 0.0% |
| openai/gpt-5.4-mini | 16.7% | 0.0% |
| anthropic/claude-sonnet-4.6 | 33.3% | 0.0% |
| nvidia/nemotron-3-super-120b-a12b:free | 41.7% | 50.0% |
| qwen/qwen3.5-9b | 41.7% | 0.0% |
| google/gemini-2.5-flash | 50.0% | 50.0% |
| mistralai/mistral-small-2603 | **66.7%** | **100.0%** |

---

## Evaluation Metadata

**Round 2 English:**
- **Judge model:** anthropic/claude-opus-4.6
- **Subject models:** 8 (claude-sonnet-4.6, gemini-3-flash-preview, mistral-large-2512, gpt-5.4-mini, gpt-4o-2024-11-20, qwen3.5-122b-a10b, qwen3.5-397b-a17b, minimax-m2.7)
- **Eval cases:** 2 (drone incident, NATO nuclear amendment)
- **Runs per model:** 3
- **Total judge calls:** 576
- **Total judge cost:** ~$6.00

**Round 2 Finnish:**
- **Judge model:** anthropic/claude-opus-4.6
- **Subject models:** 8 (same as above)
- **Eval cases:** 2
- **Runs per model:** 3
- **Total judge calls:** 576
- **Total judge cost:** ~$8.28

**Round 1 English:**
- **Judge model:** anthropic/claude-opus-4.6
- **Runs per model:** 3
- **Total judge calls:** 252
- **Total judge cost:** ~$2.34

**Round 1 Finnish:**
- **Judge model:** anthropic/claude-opus-4.6
- **Runs per model:** 1
- **Total judge calls:** 84
- **Total judge cost:** ~$1.10
