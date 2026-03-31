# Judge Calibration Report

**Baseline:** anthropic/claude-opus-4.6 (576 judgements)


## minimax/minimax-m2.7
  Agreement with Opus: **82.8%** (477/576)
  False positives (candidate flags, Opus doesn't): 39
  False negatives (candidate misses, Opus catches): 60
  Total cost: **$0.86**

  Per failure mode:
    Fabricated Addition                        77% agree  (FP:0 FN:11)
    Contradiction                              96% agree  (FP:1 FN:1)
    Entity Substitution                        88% agree  (FP:5 FN:1)
    Numerical Distortion                      100% agree  (FP:0 FN:0)
    Temporal Drift                             52% agree  (FP:16 FN:7) ⚠️
    Hedging Removal (Certainty Inflation)      79% agree  (FP:5 FN:5)
    Hedging Addition (Certainty Deflation)     98% agree  (FP:1 FN:0)
    Framing Shift / Sentiment Injection        62% agree  (FP:1 FN:17) ⚠️
    Scope Creep / Context Bleed                75% agree  (FP:4 FN:8)
    Omission of Critical Information           94% agree  (FP:3 FN:0)
    Composite Claim Conflation                 85% agree  (FP:3 FN:4)
    Instruction Leakage / Prompt Injection Echo   88% agree  (FP:0 FN:6)

## qwen/qwen3.5-122b-a10b
  Agreement with Opus: **86.3%** (497/576)
  False positives (candidate flags, Opus doesn't): 7
  False negatives (candidate misses, Opus catches): 72
  Total cost: **$6.42**

  Per failure mode:
    Fabricated Addition                        83% agree  (FP:2 FN:6)
    Contradiction                              96% agree  (FP:0 FN:2)
    Entity Substitution                        94% agree  (FP:2 FN:1)
    Numerical Distortion                      100% agree  (FP:0 FN:0)
    Temporal Drift                             69% agree  (FP:0 FN:15) ⚠️
    Hedging Removal (Certainty Inflation)      90% agree  (FP:0 FN:5)
    Hedging Addition (Certainty Deflation)     98% agree  (FP:0 FN:1)
    Framing Shift / Sentiment Injection        40% agree  (FP:0 FN:29) ⚠️
    Scope Creep / Context Bleed                85% agree  (FP:3 FN:4)
    Omission of Critical Information          100% agree  (FP:0 FN:0)
    Composite Claim Conflation                 88% agree  (FP:0 FN:6)
    Instruction Leakage / Prompt Injection Echo   94% agree  (FP:0 FN:3)

## anthropic/claude-sonnet-4.6
  Agreement with Opus: **89.2%** (514/576)
  False positives (candidate flags, Opus doesn't): 13
  False negatives (candidate misses, Opus catches): 49
  Total cost: **$3.57**

  Per failure mode:
    Fabricated Addition                        83% agree  (FP:4 FN:4)
    Contradiction                              98% agree  (FP:0 FN:1)
    Entity Substitution                        98% agree  (FP:0 FN:1)
    Numerical Distortion                      100% agree  (FP:0 FN:0)
    Temporal Drift                             69% agree  (FP:3 FN:12) ⚠️
    Hedging Removal (Certainty Inflation)      85% agree  (FP:3 FN:4)
    Hedging Addition (Certainty Deflation)     98% agree  (FP:0 FN:1)
    Framing Shift / Sentiment Injection        73% agree  (FP:0 FN:13)
    Scope Creep / Context Bleed                88% agree  (FP:0 FN:6)
    Omission of Critical Information          100% agree  (FP:0 FN:0)
    Composite Claim Conflation                 85% agree  (FP:1 FN:6)
    Instruction Leakage / Prompt Injection Echo   94% agree  (FP:2 FN:1)