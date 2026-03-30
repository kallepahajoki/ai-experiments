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

## Model × Failure Mode Matrix

```
Model                                      Fabricated Addit      Contradiction   Entity Substitut   Numerical Distor     Temporal Drift   Hedging Removal    Hedging Addition   Framing Shift /    Scope Creep / Co   Omission of Crit   Composite Claim    Instruction Leak
----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
anthropic/claude-sonnet-4.6                       67% (2/3)           0% (0/3)           0% (0/3)           0% (0/3)           0% (0/3)         100% (3/3)           0% (0/3)         100% (3/3)          67% (2/3)           0% (0/3)           0% (0/3)           0% (0/3)
google/gemini-2.5-flash                          100% (3/3)           0% (0/3)           0% (0/3)           0% (0/3)         100% (3/3)           0% (0/3)           0% (0/3)         100% (3/3)          33% (1/3)           0% (0/3)           0% (0/3)         100% (3/3)
mistralai/mistral-small-2603                      33% (1/3)           0% (0/3)           0% (0/3)           0% (0/3)          33% (1/3)          33% (1/3)          33% (1/3)         100% (3/3)           0% (0/3)           0% (0/3)           0% (0/3)          33% (1/3)
nvidia/nemotron-3-super-120b-a12b:free            33% (1/3)          33% (1/3)           0% (0/3)           0% (0/3)           0% (0/3)          67% (2/3)           0% (0/3)          33% (1/3)          33% (1/3)           0% (0/3)           0% (0/3)           0% (0/3)
openai/gpt-5.4-mini                                0% (0/3)           0% (0/3)           0% (0/3)           0% (0/3)          33% (1/3)           0% (0/3)           0% (0/3)          33% (1/3)           0% (0/3)           0% (0/3)           0% (0/3)           0% (0/3)
qwen/qwen3.5-122b-a10b                             0% (0/3)           0% (0/3)           0% (0/3)           0% (0/3)          33% (1/3)         100% (3/3)           0% (0/3)          67% (2/3)           0% (0/3)           0% (0/3)           0% (0/3)          33% (1/3)
qwen/qwen3.5-9b                                   33% (1/3)          33% (1/3)          33% (1/3)           0% (0/3)          33% (1/3)          67% (2/3)           0% (0/3)         100% (3/3)          33% (1/3)           0% (0/3)          67% (2/3)          33% (1/3)
```

## Per-Model Summary

## anthropic/claude-sonnet-4.6
  Overall failure rate: 27.8% (10/36)
  Critical failure rate: 33.3% (2/6)
  Total judge cost: $0.3523
  Detected failure modes:
    - Framing Shift / Sentiment Injection: 100% (3/3)
    - Hedging Removal (Certainty Inflation): 100% (3/3)
    - Fabricated Addition: 67% (2/3)
    - Scope Creep / Context Bleed: 67% (2/3)

## google/gemini-2.5-flash
  Overall failure rate: 36.1% (13/36)
  Critical failure rate: 50.0% (3/6)
  Total judge cost: $0.3378
  Detected failure modes:
    - Fabricated Addition: 100% (3/3)
    - Framing Shift / Sentiment Injection: 100% (3/3)
    - Instruction Leakage / Prompt Injection Echo: 100% (3/3)
    - Temporal Drift: 100% (3/3)
    - Scope Creep / Context Bleed: 33% (1/3)

## mistralai/mistral-small-2603
  Overall failure rate: 22.2% (8/36)
  Critical failure rate: 16.7% (1/6)
  Total judge cost: $0.3095
  Detected failure modes:
    - Framing Shift / Sentiment Injection: 100% (3/3)
    - Fabricated Addition: 33% (1/3)
    - Hedging Addition (Certainty Deflation): 33% (1/3)
    - Hedging Removal (Certainty Inflation): 33% (1/3)
    - Instruction Leakage / Prompt Injection Echo: 33% (1/3)
    - Temporal Drift: 33% (1/3)

## nvidia/nemotron-3-super-120b-a12b:free
  Overall failure rate: 16.7% (6/36)
  Critical failure rate: 33.3% (2/6)
  Total judge cost: $0.3048
  Detected failure modes:
    - Hedging Removal (Certainty Inflation): 67% (2/3)
    - Contradiction: 33% (1/3)
    - Fabricated Addition: 33% (1/3)
    - Framing Shift / Sentiment Injection: 33% (1/3)
    - Scope Creep / Context Bleed: 33% (1/3)

## openai/gpt-5.4-mini
  Overall failure rate: 5.6% (2/36)
  Critical failure rate: 0.0% (0/6)
  Total judge cost: $0.2761
  Detected failure modes:
    - Framing Shift / Sentiment Injection: 33% (1/3)
    - Temporal Drift: 33% (1/3)

## qwen/qwen3.5-122b-a10b
  Overall failure rate: 19.4% (7/36)
  Critical failure rate: 0.0% (0/6)
  Total judge cost: $0.3040
  Detected failure modes:
    - Hedging Removal (Certainty Inflation): 100% (3/3)
    - Framing Shift / Sentiment Injection: 67% (2/3)
    - Instruction Leakage / Prompt Injection Echo: 33% (1/3)
    - Temporal Drift: 33% (1/3)

## qwen/qwen3.5-9b
  Overall failure rate: 36.1% (13/36)
  Critical failure rate: 33.3% (2/6)
  Total judge cost: $0.3513
  Detected failure modes:
    - Framing Shift / Sentiment Injection: 100% (3/3)
    - Composite Claim Conflation: 67% (2/3)
    - Hedging Removal (Certainty Inflation): 67% (2/3)
    - Contradiction: 33% (1/3)
    - Entity Substitution: 33% (1/3)
    - Fabricated Addition: 33% (1/3)
    - Instruction Leakage / Prompt Injection Echo: 33% (1/3)
    - Scope Creep / Context Bleed: 33% (1/3)
    - Temporal Drift: 33% (1/3)

---

## Model-by-Model Deep Dive

### openai/gpt-5.4-mini — The Gold Standard (5.6% failure rate)

The cleanest performer by far. All three runs are nearly identical, terse, factual prose. It preserves "according to current information" consistently, attributes the quote properly to Häkkänen, and uses neutral verbs ("responded", "said", "entered"). The only flags were minor: one run reattributed "immediately" from the minister's quote about security authorities to the Air Force's response, and one run used "entered" instead of "strayed into" which loses the accidental connotation. Remarkably disciplined output.

### anthropic/claude-sonnet-4.6 — Editorially Aggressive (27.8% failure rate)

Every single run has the same two problems:
1. **"Unauthorized Drones"** in the heading — the source says "suspected territorial violation" and the minister says drones "strayed" (harhautunut, implying accidental). "Unauthorized" fabricates intent.
2. **"scrambled"** an F/A-18 — the source says "has been on-site for identification". "Scrambled" is military jargon for emergency rapid deployment, adding drama not in the source.

It also drops "according to current information" every time, presenting preliminary crash details as established fact. Sonnet 4.6 consistently produces well-structured, professional-looking output that would pass a casual human review — which makes its errors more dangerous than a sloppy model's.

### google/gemini-2.5-flash — Worst Critical Failure Rate (50%)

**100% fabricated addition**, but interestingly not the HS-style "Russian drones" fabrication. Instead, every run calls it a "Finnish Ministry of Defence press release" — the source text never identifies its origin. Every run also titles it "Airspace Intrusion" which converts the minister's "strayed into" (accidental) into "intrusion" (deliberate). Plus 100% instruction leakage — every run starts with "Here's a summary of..." echoing the task prompt. And 100% temporal drift — consistently shifts present perfect ("has been on-site") to simple past ("deployed"), subtly making an ongoing situation sound concluded.

### nvidia/nemotron-3-super-120b-a12b:free — Invents Detection Methods (16.7%)

Lowest overall failure rate among the non-GPT models, but its errors are specific and interesting. One run fabricated **"Finnish radar"** as the detection method — the source says objects were "detected" without specifying how. Another run changed "investigating together with other authorities" to "leading the investigation" — a small word change that shifts the power dynamic. These are the kind of subtle distortions that could matter in diplomatic/security reporting.

### mistralai/mistral-small-2603 — The Overcorrector (22.2%)

Generally solid, but run 1 is notable: it replaced "according to current information" with **"confirmed"** — the exact opposite of hedging. The source explicitly marks crash info as preliminary; Mistral stated it as definitively verified. This is the single most dangerous hedging removal in the entire benchmark. Runs 0 and 2 were much better, showing variance in reliability. Also the only model flagged for hedging *addition* — one run softened definitive statements.

### qwen/qwen3.5-122b-a10b — Consistent Hedging Dropper (19.4%)

Zero critical failures (no fabrication, no contradiction), but **100% hedging removal**. Every single run drops "according to current information". It also consistently uses "confirmed" for the minister's statement where the source uses the neutral "states" (toteaa). The larger Qwen model is factually disciplined but systematically inflates certainty — it would make a poor newsroom tool despite being "accurate".

### qwen/qwen3.5-9b — Small Model Chaos (36.1%)

Tied worst with Gemini Flash but for different reasons. This model fails across **9 of 12 failure modes** — the most scattered failure profile. It conflates the minister's statement with a "Ministry of Defence report", merges separate facts with "subsequently" implying causation, substitutes entities, and removes hedging. Run 1 was the worst single output in the entire benchmark. This is what a model looks like when it doesn't have enough capacity to faithfully reproduce source material.

---

## Cross-Cutting Patterns

**Framing shift is universal.** Every model was flagged at least once. LLMs fundamentally want to editorialize — "stated" becomes "confirmed" or "emphasized", neutral events get dramatic verbs.

**"harhautunut" (strayed) is a litmus test.** The Finnish minister chose this word carefully — it implies accidental incursion, not hostile intent. Sonnet 4.6 turned it into "unauthorized", Gemini into "intrusion", GPT 5.4 mini into "entered" (neutral but losing the accidental implication). No model preserved the accidental connotation faithfully.

**Nobody fabricated "Russian drones".** The specific HS hallucination didn't reproduce here, likely because the task prompt used the English translation rather than asking models to interpret the Finnish original. This suggests the HS failure may have involved the model applying geopolitical priors to a Finnish-language source — a hypothesis worth testing with Finnish-language prompts.

**Cost vs quality is dramatic.** GPT 5.4 mini at $0.0007/run massively outperformed Sonnet 4.6 on faithfulness. The cheapest model was the most truthful.

## Could an LLM Judge Have Prevented the HS Error?

On 2026-03-30, Helsingin Sanomat editor-in-chief Erja Yläjärvi [published a statement](https://www.hs.fi/paakirjoitukset/art-2000011912865.html) confirming that HS had published erroneous information claiming Russian drones had been downed in Kouvola. The error was live for three minutes. Ilta-Sanomat made the same mistake. The root cause: **an AI tool used to summarize press releases had fabricated the Russia attribution**. The tool headlines press release alerts on an internal channel, and journalists picked up the hallucinated headline as breaking news. Yläjärvi wrote: "Tekoälytyökalu oli tässä tapauksessa täysin virheellisesti otsikoinut Puolustusministeriön tiedotehälytyksen Venäjään liittyväksi, vaikka itse tiedotteessa ei puhuttu maasta mitään." (The AI tool had completely erroneously headlined the Ministry of Defence press release alert as related to Russia, even though the press release itself said nothing about any country.)

This is a textbook **fabricated addition** — the most critical failure mode in our framework.

**Could an LLM-as-judge have caught it?** Yes, trivially. Our benchmark's fabricated addition judge prompt asks the judge to verify every factual claim against the source. In our test, Opus 4.6 successfully detected fabricated additions across all models that produced them — including far more subtle cases than a country attribution that doesn't exist in the source at all. Even a cheaper judge model would catch "Russian drones" when the source mentions no country.

**What would it cost?**

- Running the fabricated addition judge alone on one press release summary: **~$0.01** (500 input tokens + 300 output tokens at Opus 4.6 pricing)
- Running all 12 failure modes on one press release summary: **~$0.12**
- Running the full 12-mode evaluation on every press release HS processes in a day (estimate ~50-100 alerts): **$6-12/day**
- Using a cheaper judge (Sonnet 4.6 at ~$0.003/M input): **under $1/day** for all alerts


## Evaluation Metadata

- **Judge model:** anthropic/claude-opus-4.6
- **Runs per model:** 3
- **Total judge calls:** 252
- **Total judge cost:** ~$2.34
- **Eval case:** Finnish MoD press release on suspected drone territorial violation (2026-03-29)