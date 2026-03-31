# grounding-eval — Next Steps

## Eval Data

- **Finnish-source, English-output condition.** We have English→English and Finnish→Finnish. Adding Finnish→English would test hypothesis that cross-language translation adds a fabrication opportunity. If fabrication rates go up vs English→English, the translation step is the culprit.
- **More eval cases.** Two cases gives directional signal but limited statistical power. Good candidates:
  - Finnish government budget proposals (numbers-heavy, tests numerical distortion)
  - Onnettomuustutkintakeskus (Safety Investigation Authority) reports (heavy hedging, preliminary findings)
  - STM/THL health advisories (conditions and caveats matter, tests omission)
  - Ulkoministeriö travel advisories (tests scope creep — models love adding geopolitical context)
- **Synthetic calibration cases.** Manually construct source+output pairs with known injected errors. Ground truth for measuring judge precision/recall per failure mode. Currently we treat Opus as ground truth but it's not perfect (see framing shift disagreements).

## Judge Optimization

- **Two-tier judge.** Use Sonnet for easy modes (numerical distortion, contradiction, entity substitution, instruction leakage — all 94-100% agreement) and Opus only for hard modes (framing shift, temporal drift, fabricated addition). Estimated 50-60% cost reduction.
- **MiniMax as pre-screen.** At $0.86/576 calls, run MiniMax first, only escalate to Opus where MiniMax flags something or for hard modes. Could reduce Opus calls by 70%+.
- **Judge prompt tuning.** Framing shift has 40-73% agreement — the prompt may be too subjective. Consider tightening the definition or splitting into sub-categories (loaded language vs implied causality vs tone shift).

## Infrastructure

- **Concurrent generation.** Generation is still sequential per model. Could parallelize across models like we do for judge calls.
- **Incremental eval.** Currently re-runs all judge calls if anything changes. Could hash (source, output, mode, judge_model) to skip already-computed results.
- **Cost estimation before run.** Add `--dry-run` flag that estimates total cost based on token counts before making any API calls.
- **Fix async client lifecycle.** The event loop cleanup issue is worked around but not properly fixed. Consider using a single `async def main()` pattern instead of mixing `asyncio.run()` with sync context managers.

## Analysis

- **Per-case breakdown.** The nuclear case clearly raised failure rates — quantify how much per model and per failure mode. Which models handled the nuclear case's negations ("Finland does NOT seek...") correctly?
- **Output length correlation.** Qwen models produce 3-5x more tokens than GPT/Sonnet. Does verbosity correlate with failure rate? More words = more chances to drift?
- **Confidence calibration.** We collect confidence scores from the judge but don't use them. Are high-confidence detections more likely to be true positives?
- **Cross-language error transfer.** Do models that fabricate in English fabricate the same things in Finnish, or different things? Model-specific vs language-specific error patterns.
