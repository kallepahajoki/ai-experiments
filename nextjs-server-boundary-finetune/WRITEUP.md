# Fine-tuning Qwen 3.5 27B for Agentic Error Correction

## The Problem

Next.js projects that use Node.js built-in modules (crypto, net, fs, etc.) through instrumentation hooks or server components fail to build with `Module not found: Can't resolve 'X'` webpack errors. The correct fix is to add `config.externals` in the webpack config. The common wrong fix — `resolve.fallback: { module: false }` — silences the build error but makes modules `undefined` at runtime, causing crashes.

Base Qwen 3.5 27B, when used as a coding agent via Claude Code + OpenRouter, would spiral when encountering this error — trying various wrong approaches without converging on the correct fix.

## What We Built

A LoRA fine-tune (rank 32, 82 training examples, 5 epochs) that teaches the model to:
1. Recognize the `Module not found` webpack error pattern
2. Apply `config.externals` (not `resolve.fallback`)
3. Include transitive dependencies (e.g., pg → pgpass, split2, pg-pool, pg-protocol)

## Key Decisions and Why

### 1. Removing the system prompt and conversational framing

**Initial state:** Training data had `"You are an expert software engineer..."` system prompt and user messages like `"I'm getting build errors in my Next.js project..."` with full source file listings.

**Problem:** Claude Code doesn't inject a custom system prompt, and the model never sees conversational requests from a human — it sees tool results from running commands.

**Fix:** Removed system prompt entirely. Stripped user messages to just build output + config file. Removed source file listings (the error output already contains import lines and traces).

**Lesson:** Training data format must match inference format. A model fine-tuned on interactive Q&A won't activate reliably in an agentic tool-use context.

### 2. Adding tool-use formatted examples

**Problem:** In agentic use, build output arrives inside Qwen's `<tool_response>` XML wrapper (rendered from `role: "tool"` messages). The model had never seen the error pattern in this context during training.

**Fix:** Added three tiers of training examples:
- **Plain** (user/assistant) — error + config as a plain user message
- **Full tool-use** (user → assistant+tool_call → tool → assistant+tool_call → tool → assistant) — simulates running build, reading config, then fixing
- **Minimal tool-response-only** (user → assistant+tool_call → tool → assistant) — just the build error in a `<tool_response>`, no config read

**Lesson:** The `<tool_response>` wrapper changes the token context significantly. A LoRA trained only on plain messages may not activate when the same error text appears inside tool result framing. Including examples in multiple formats makes the LoRA robust across contexts.

### 3. Minimal tool-response-only examples for generalization

**Rationale:** If some examples contain only the error as a bare `<tool_response>` with no surrounding context (no config read, no multi-step flow), the LoRA is forced to activate on the error text itself. This maximizes generalization — the pattern fires regardless of what else is in the conversation.

**Gotcha:** Qwen 3.5's chat template requires at least one `role: "user"` message. Our initial minimal examples started with `role: "assistant"` and crashed with `TemplateError: No user query found`. Fixed by adding a brief agentic user prompt ("Fix the build error.") as the first message.

### 4. The fallback vs externals problem (first test failure)

**What happened:** First test run — the model correctly identified the problem in its analysis text ("use externals, don't use resolve.fallback") but then generated `resolve.fallback` code anyway.

**Root cause:** The base model has seen far more `resolve.fallback` examples on the internet than `config.externals`. The LoRA (rank 32, 52 examples, 3 epochs) nudged the model's knowledge but wasn't strong enough to override the code generation prior.

**Fix:**
- Added 5 new dedicated negative examples that specifically show `resolve.fallback` → wrong → `config.externals` → right
- Added pg-specific negative examples (matching the real test case)
- Increased synthetic examples from 40 → 60
- Increased wrong-approach discussion rate from 30% → 50% of examples
- Bumped epochs from 3 → 5
- Result: 74/82 examples explicitly mention fallback as wrong

**Lesson:** For a fine-tune that needs to correct a common-but-wrong pattern, the anti-pattern signal must be very strong. It's not enough to show the right answer — you need to repeatedly show "this common thing is wrong, do this instead." The model's base training has massive inertia toward popular patterns.

### 5. Quantization works fine

The LoRA was merged into full weights and exported as Q4_K_M GGUF for Ollama. The fine-tuned behavior survived quantization — the model still correctly identifies the error and generates externals code. Q4 is aggressive but the pattern is distinctive enough (specific code structure, specific module names) that it survives the precision loss.

## Training Details

| Parameter | Run 1 | Run 2 (final) |
|-----------|-------|---------------|
| Examples | 52 | 82 |
| Epochs | 3 | 5 |
| LoRA rank | 32 | 32 |
| Final eval loss | 0.033 | 0.011 |
| Final train loss | 0.164 | 0.017 |
| Training time | 11 min | 26 min |
| GPU | A100 80GB SXM | A100 80GB SXM |

## Infrastructure Notes

- **RunPod** with network volume (EUR-IS-1 region) for persistent venv + HF cache
- Network volume persists venv (~13GB) and model weights (~52GB) across pod restarts
- System packages (`apt-get`) are ephemeral — must reinstall on each pod restart
- GGUF export needs ~120GB free (bf16 intermediate + final quant)
- `scripts/clean_output.sh` frees 50-100GB between runs
- Always set `HF_HOME=/workspace/hf_cache` before training or HuggingFace re-downloads 52GB to `/root/.cache`
- `TORCHDYNAMO_DISABLE=1` avoids torch compile cache filling the container disk

## What Worked in the Final Test

The fine-tuned model, running as a coding agent via Claude Code:
1. Ran `npm run build`, saw the `Module not found: Can't resolve 'pg'` error
2. Read `next.config.mjs`
3. Correctly identified the fix: webpack `config.externals`
4. Explicitly warned against `resolve.fallback`
5. Included pg's transitive dependencies (pgpass, split2, pg-pool, pg-protocol)
6. Wrote the config, re-ran the build, saw remaining errors (crypto, net, fs/promises, path)
7. Iterated to add those modules to externals

The base model spiraled on this same error. The fine-tuned model solved it in two iterations.

### Generalization beyond training data

Notably, when the model encountered a `stream` module error caused by `tsdav → sax → stream` (a CalDAV client's XML parser dependency), it correctly identified the transitive dependency chain and externalized `stream`. Neither `sax` nor `tsdav` appear anywhere in the training data. The model learned the *pattern* of tracing transitive dependencies through `node_modules` import chains, not just the specific packages (pg → pgpass, mongoose → mongodb) it was trained on.
