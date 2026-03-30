# LLM Output Failure Modes: Evaluation Reference

A reference for building source-grounded LLM output evaluation tooling.
Each failure mode includes a detection strategy and example prompt approach.

---

## 1. Fabricated Addition (Hallucinated Attribution)
**What it is:** Model adds factual claims not present in the source — most dangerous type.
**HS drone case:** Source had no country attribution; model added "Russian drones."
**Detection:** For every factual claim in output, require a grounding sentence from source. Flag ungrounded claims.
**Prompt pattern:** *"List each factual claim. Cite the exact source passage supporting it. Mark claims with no source support as UNSUPPORTED."*

---

## 2. Contradiction
**What it is:** Output directly conflicts with source (says X when source says Y).
**Example:** Source: "3 drones recovered." Summary: "5 drones shot down."
**Detection:** Semantic contradiction search — easier than fabrication detection, most eval tools catch this reasonably well.
**Prompt pattern:** *"Does any statement in the output contradict the source? Quote both."*

---

## 3. Entity Substitution
**What it is:** Correct fact type, wrong entity — names, organizations, locations swapped.
**Example:** Source mentions Ministry of Defence; output attributes the statement to Ministry of Interior.
**Detection:** Extract named entities from both source and output, diff them. Flag entities in output not present in source.
**Prompt pattern:** NER extraction + set comparison, or direct: *"Are all organizations, people, and locations in the output present in the source?"*

---

## 4. Numerical Distortion
**What it is:** Numbers changed, rounded incorrectly, or units swapped.
**Example:** "€1.2 million" becomes "€12 million" or "1.2 billion."
**Detection:** Extract all numerics + units from both texts, compare pairs. Even small changes matter in financial/casualty/measurement contexts.
**Prompt pattern:** *"List every number and unit in the output. Verify each against the source exactly."*

---

## 5. Temporal Drift
**What it is:** Dates, times, tenses, or sequence of events misrepresented.
**Example:** Source: "will hold talks next week." Output: "held talks last week."
**Detection:** Extract temporal expressions and event ordering, compare against source.
**Special case:** Model's training cutoff bleeding into output — e.g., stating something as current when source describes it as past.

---

## 6. Hedging Removal (Certainty Inflation)
**What it is:** Source expresses uncertainty or conditionality; output presents it as fact.
**Example:** Source: "authorities suspect the device may be of foreign origin." Output: "device confirmed to be foreign-made."
**Detection:** Extract epistemic markers (may, might, suspected, alleged, reportedly, could) from source. Check if output preserves or drops them.
**Prompt pattern:** *"Does the output preserve all uncertainty language from the source, or does it state uncertain things as facts?"*

---

## 7. Hedging Addition (Certainty Deflation)
**What it is:** Opposite of above — source states something definitively, output softens it inappropriately.
**Example:** Source: "criminal charges filed." Output: "authorities are considering possible charges."
**Detection:** Same epistemic marker analysis, bidirectional.

---

## 8. Framing Shift / Sentiment Injection
**What it is:** Factually accurate but adds editorial tone, bias, or implied causality not in source.
**Example:** Source is neutral; output uses loaded language ("reckless decision," "surprising move").
**Detection:** Sentiment/tone analysis on output vs source. Harder to automate; LLM judge works better here than rule-based.
**Prompt pattern:** *"Does the output introduce any evaluative language, opinion, or implied causality not present in the source?"*

---

## 9. Scope Creep / Context Bleed
**What it is:** Model incorporates background knowledge or prior context not in the provided source.
**Example:** Source is a press release about an incident; output adds historical context about Russia-Finland relations from training data.
**Detection:** Ask model to flag any information in output that cannot be traced to source. Hard to fully automate — requires strict grounding constraint in original prompt too.
**Prompt pattern:** *"Does the output contain any information that requires knowledge beyond what is in the provided source document?"*

---

## 10. Omission of Critical Information
**What it is:** Key facts, caveats, or conditions in source are silently dropped.
**Example:** Source: "offer valid for residents only." Summary omits the residency condition.
**Detection:** Harder — requires knowing what's "critical." Heuristics: negations, conditions (if/unless/only), legal/safety language. Or: summarize source independently and diff against output.
**Prompt pattern:** *"Are there any conditions, limitations, or caveats in the source that are missing from the output?"*

---

## 11. Instruction Leakage / Prompt Injection Echo
**What it is:** Model echoes system prompt fragments, meta-instructions, or injected content into output.
**Relevance:** Especially if source documents are user-supplied (could contain injection attempts).
**Detection:** Check output for system prompt fragments; detect instruction-style language in output.

---

## 12. Composite Claim Conflation
**What it is:** Model merges two separate statements into one, creating a false combined claim.
**Example:** Source says A happened, and separately that B happened. Output: "A caused B."
**Detection:** Causal/relational claim extraction — look for causal connectors (because, caused, led to, due to) and verify the relationship exists in source.

---

## Priority Matrix for Newsroom / High-Stakes Use

| Failure Mode | Frequency | Severity | Detection Difficulty |
|---|---|---|---|
| Fabricated Addition | High | Critical | Hard |
| Hedging Removal | High | High | Medium |
| Contradiction | Medium | Critical | Easy |
| Entity Substitution | Medium | High | Easy |
| Numerical Distortion | Medium | High | Easy |
| Framing Shift | High | Medium | Hard |
| Temporal Drift | Medium | High | Medium |
| Scope Creep | High | Medium | Hard |
| Omission | Medium | High | Hard |
| Composite Conflation | Low | High | Medium |

---

## Implementation Notes

- **Easy wins first:** Entity substitution, numerical distortion, and contradiction are amenable to structured extraction + comparison — low LLM cost, high recall.
- **Hardest to automate:** Fabricated addition, scope creep, omission — these require grounding reasoning, not just comparison. Use a strong model (Sonnet/Opus class) as judge.
- **Two-stage approach works well:** Fast rule-based / extraction pass first, then LLM judge only on flagged items or high-stakes outputs.
- **Calibrate per domain:** Hedging removal is critical for legal/medical/security; framing shift matters more for journalism; numerical distortion for finance.
- **Ground truth for evals:** Build a small annotated test set per failure mode — synthetic examples work fine for unit testing detection logic.
