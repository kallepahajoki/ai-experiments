# Sage Deep Research: Lessons from Building an LLM Research Pipeline

Practical findings from building and optimizing a multi-stage research pipeline that decomposes questions into sub-queries, searches the web, extracts facts from sources, reviews quality, and synthesizes reports. Built as part of the [Anvil AI Toolkit](https://anvisuite.com) platform.

**Hardware**: AMD Radeon RX 7900 XTX (24GB VRAM, RDNA3, ROCm)
**Local model**: Qwen 3.5 9B (Q4_K_M, via Ollama 0.18.2)
**Cloud model**: StepFun Step 3.5 Flash (200B MoE / 10B active, via OpenRouter)
**Inference server**: Ollama (local), OpenRouter (cloud)

---

## Table of Contents

1. [Pipeline Architecture](#pipeline-architecture)
2. [The Thinking Mode Discovery](#the-thinking-mode-discovery)
3. [Multi-Tier Model Routing](#multi-tier-model-routing)
4. [Step 3.5 Flash: Price/Performance Analysis](#step-35-flash-priceperformance-analysis)
5. [Ollama Parallel Mode on AMD](#ollama-parallel-mode-on-amd)
6. [The Retry Cascade Trap](#the-retry-cascade-trap)
7. [Observability: Timeline Telemetry](#observability-timeline-telemetry)
8. [Key Numbers](#key-numbers)

---

## Pipeline Architecture

The Sage research pipeline processes a query through these stages:

```
decompose → search → rank → fetch → extract → review → evaluate → synthesize → doc_review → correct → journeyman_review
```

Each stage is a separate LLM call (or set of calls) with a specific purpose:

| Stage | What it does | Calls per run | Tokens per call |
|---|---|---|---|
| **decompose** | Break query into 5-9 sub-questions | 1 | ~200 in / ~800 out |
| **search** | Web search via SearXNG (no LLM) | 5-9 | — |
| **rank** | Pick which search results to fetch | 5-9 | ~1000 in / ~300 out |
| **fetch** | HTTP fetch of web pages (no LLM) | 15-25 | — |
| **extract** | Pull factual claims from each page | 15-25 | ~8000 in / ~800 out |
| **review_facts** | Per-subquestion fact quality check | 5-9 | ~3000 in / ~600 out |
| **evaluate** | Coverage gap analysis | 0-1 | ~2000 in / ~500 out |
| **synthesize** | Write the final report | 1 | ~12000 in / ~4000 out |
| **doc_review** | Whole-document correctness check | 1-2 | ~5000 in / ~1000 out |
| **correct** | Fix flagged issues via RAG search | 0-3 | ~600 in / ~200 out |
| **journeyman_review** | Independent quality gate | 1 | ~10000 in / ~1000 out |

The pipeline also includes a post-journeyman verification step that checks each raised concern against the research corpus (via Atlas RAG search) before accepting a rejection.

---

## The Thinking Mode Discovery

### The problem

After several optimizations, Sage research runs were taking 40-60 minutes on local Qwen 3.5 9B. Rank calls that should have taken 5-10 seconds were taking 70-90 seconds. Extract calls were 60-200 seconds each. We spent significant time investigating Ollama parallel mode, retry cascades, and cold-start effects before discovering the actual root cause.

### The smoking gun

Direct testing against the Ollama API revealed that a trivial "say hello in 5 words" prompt was generating **4,303 completion tokens** and taking **62 seconds** — for a 7-token response. The model was generating ~4,296 internal reasoning tokens that Ollama hid from the response content but still counted toward `eval_count` and wall time.

```
WITHOUT think:false:  4303 tokens, 62.0 seconds, "Hello, how are you today?"
WITH    think:false:     8 tokens,  0.1 seconds, "Hello there, how are you?"
```

**538x wall-time difference for the same prompt and same response.**

### Root cause

Qwen 3.5 declares `"capabilities": ["completion", "vision", "tools", "thinking"]` in its Ollama model manifest. Ollama 0.18+ enables thinking mode by default for any model with this capability, unless the request explicitly includes `"think": false`. The model generates a `<think>...</think>` internal monologue before every response, which:

- Counts toward `eval_count` (token generation metric)
- Consumes wall time at normal ~70 t/s generation speed
- Is hidden from `.message.content` in the response
- Is **invisible** in audit logs that only record the response content
- Is **not visible** in prompt-side analysis (because the overhead is on the response side)

### Impact on research pipeline

Every Sage LLM call had been generating ~3,000-5,000 hidden thinking tokens. Historical data confirms this was present from the very first run:

| Run | Purpose | Avg completion tokens | Avg wall time | Effective t/s |
|---|---|---|---|---|
| SAGE-4 (thinking on) | rank | 4,557 | 69s | 66 t/s |
| SAGE-4 (thinking on) | extract | 4,007 | 64s | 62 t/s |
| **SAGE-15 (thinking off)** | **rank** | **253** | **7s** | **36 t/s** |
| **SAGE-15 (thinking off)** | **extract** | **899** | **30s** | **30 t/s** |

The per-token speed was always normal (~60-70 t/s solo). The apparent "slowness" was entirely from generating 5-20x more tokens than the response needed.

### Quality impact of disabling thinking

**Critically, disabling thinking did NOT reduce output quality.** Comparative analysis of SAGE-4 (thinking on, all local) vs SAGE-15 (thinking off, cloud synthesize):

| Metric | SAGE-4 (thinking on) | SAGE-15 (thinking off) |
|---|---|---|
| Total facts extracted | ~350 | **449** |
| Facts kept by reviewer | ~300 | **420** |
| Specific genetic markers in output | 2 (C9orf72, SOD1) | **8** (C9orf72, UNC13A rs12608932, NEK1, SOD1, TARDBP, FUS, TBK1, OPTN) |
| Clinical thresholds cited | few | **MTP <21 kPa, FVC <80%, 20-month SRSI cutoff, OR 1.48** |
| Tables in output | 0 | **1** (bulbar vs limb comparison) |
| Doc review issues | 1-5 per run | **0** |
| Wall time | ~60 min | **8.7 min** |

The thinking tokens were **pure waste** for Sage's extraction heavy workload. The model was ruminating internally and then producing roughly the same fact list it would produce without thinking. For structured JSON extraction tasks (rank, review_facts, extract), thinking mode is actively harmful — it adds latency without improving the output because the task is fundamentally pattern matching, not deep reasoning.

In the SAGE-15 run where we disabled thinking, the decomposition and synthesis tasks were executed by the Step 3.5 flash model through OpenRouter. It is possible, that disabling thinking for these critical steps of the research would have degraded the quality of the final report.

### Recommendation

**Disable thinking by default for all Ollama LLM calls** (`think: false` in the request body). For Qwen 3.5 and similar models with thinking capability, the hidden reasoning overhead inflates wall time 10-100x with no measurable quality benefit on structured extraction/review tasks. If a specific use case genuinely benefits from chain-of-thought reasoning (e.g., complex multi-step math), enable it explicitly with `think: true` per-call.

---

## Multi-Tier Model Routing

### The architecture

Not all pipeline stages need the same model. We implemented per-purpose routing through Forge (the model configuration service) with three tiers:

| Tier | Forge category | Purposes | Model |
|---|---|---|---|
| **Bulk work** | `chat` | rank, extract, review_facts, evaluate, rephrase, prewarm, verify_issue | Local Qwen 3.5 9B |
| **Linchpin** | `synthesize` | decompose, synthesize | Cloud Step 3.5 Flash |
| **Critical reading** | `review` | doc_review, journeyman_review | Cloud Step 3.5 Flash |

### Why these tiers

**Decompose and synthesize are the two highest-leverage calls.** Decompose frames the entire research scope ("what 5-9 questions should we investigate?") — bad decomposition wastes the entire subsequent pipeline. Synthesize writes the final report — it defines the output quality. Both are 1 call per run, both benefit most from model intelligence, both are cheap at cloud pricing.

**Extract is the bulk work.** 15-25 calls per run, each processing an 8k-token web page. The task is "pull factual claims from this text" — reading comprehension, not creative reasoning. A 9B local model handles this adequately, and does not need thinking enabled. The volume makes cloud cost real (but still cheap — see Step 3.5 Flash section).

**Doc review and journeyman review need critical reading** — cross-referencing claims against sources, detecting contradictions, evaluating numerical consistency. A cloud model catches issues (like doing weighted-average arithmetic to spot survival statistic inconsistencies) that a 9B model misses.

---

## Step 3.5 Flash: Price/Performance Analysis

### The model

StepFun Step 3.5 Flash is a **200B parameter Mixture-of-Experts model with ~10B active parameters per token**. Available via OpenRouter as both free (shared rate limits) and paid tiers.

### Performance data from production runs

| Call type | Input tokens | Output tokens | Wall time | Cost | Throughput |
|---|---|---|---|---|---|
| **decompose** | 193 | 1,380 | 1s | $0.0008 | 854 t/s |
| **synthesize** | 12,036 | 3,610 | 5s | $0.0016 | 658 t/s |
| **doc_review** | 4,548 | 8,799 | 3s | $0.0031 | 170 t/s |

**Total cloud cost per research run: ~$0.008 (less than one cent).**

### Comparison with alternatives

| Model | Per-run cost | Synthesize quality | Doc review quality |
|---|---|---|---|
| **Local Qwen 3.5 9B** | $0.00 (electricity) | Serviceable, list-like | Misses numerical inconsistencies |
| **Step 3.5 Flash (paid)** | **~$0.008** | Strong narrative, tables, precise citations | **Catches arithmetic errors, terminology precision** |
| **Claude Haiku 4.5** | ~$0.15 | Not tested yet | Not tested yet |
| **Claude Sonnet 4.5** | ~$0.35 | Not tested yet | Not tested yet |

### Why Step 3.5 Flash punches above its weight

Despite having only 10B active parameters per token (comparable to Qwen 9B in raw compute per forward pass), Step 3.5 Flash's **200B total parameters** give it access to a much broader set of specialized experts. For medical research synthesis:

- **Domain terminology**: Uses ALS-specific clinical terms naturally (ALSFRS-R, SRSI cutoff, pseudobulbar affect) without being prompted
- **Numerical reasoning**: Catches weighted-average inconsistencies by doing arithmetic (0.25 × 20 + 0.75 × 30 = 27.5, document says 29.8 — flagged)
- **Structured output**: Produces comparison tables unprompted when the data supports it
- **Citation precision**: Maps specific claims to specific references rather than citing indiscriminately

At $0.008 per research run, the cost is essentially invisible. Running 100 research projects a month would cost $0.80. This makes the "should we use cloud or local?" question irrelevant for the linchpin calls — cloud wins on quality AND is effectively free.

### Free tier warning

OpenRouter's free tier for Step 3.5 Flash has **shared rate limits** across all free-tier users. During our testing, a synthesize call (the single highest-stakes call in the pipeline) failed with a 429 because another user's traffic saturated the shared bucket. **Use the paid tier for any production workload** — the cost difference is literally fractions of a cent per call and eliminates shared-bucket contention.

---

## All-Cloud Model Comparison: Step 3.5 Flash vs Claude Haiku 4.5

We ran the identical query ("The onset and progression of bulbar ALS", moderate depth, scientific register) through both models with all pipeline stages on cloud (no local Qwen). Same concurrency (2), same extractor code, same synthesize/review prompts.

### Quantitative comparison

| Metric | Step 3.5 Flash (SAGE-23) | Claude Haiku 4.5 (SAGE-24) |
|---|---|---|
| **Wall time** | 12.7 min | **3.9 min** |
| **Cost** | $0.061 | $0.076 |
| **Extract calls** | 18 | 19 |
| **Avg tokens/extract** | **2,827** | 795 |
| **Total extract output** | **50,894 tok** | 15,097 tok |
| **Total output (all calls)** | **125,441 tok** | 28,176 tok |
| **Final report length** | 18,410 chars | **30,548 chars** |
| **Citations in report** | 95 | **136** |
| **Unique references** | **29** | 14 |

### The extraction-synthesis paradox

**Haiku extracts 3.6× fewer tokens per page but produces a 1.7× longer, more detailed final report.** This reveals fundamentally different strategies:

**Step Flash** is a **copy-machine extractor** with a **summary synthesizer**: it extracts exhaustively (pulling near-verbatim content from sources, averaging 2,827 tokens per page) but then compresses aggressively during synthesis. Much of the extracted material doesn't survive into the final report. 51k tokens of extraction → 18k character report.

**Haiku** is a **selective extractor** with an **authoring synthesizer**: it extracts concisely (pulling only key claims, averaging 795 tokens per page) but expands during synthesis with domain knowledge, creating coherent subsections and explanatory prose. 15k tokens of extraction → 30k character report.

### Qualitative analysis

**Step Flash report** ("selective depth" style):
- Unique section on **selective bulbar motor neuron vulnerability** with specific molecular data: MMP9 ~2.5-fold lower in resistant motor neurons, calcium-binding protein expression differences, glycinergic vs GABAergic inhibition balance
- **Speech decline trajectory** with specific clinical threshold: ~120 words per minute transition to rapid decline phase, with 3-month lead time for articulatory changes detectable before perceived problems
- Elegant intrinsic/extrinsic vulnerability factor organization
- Weaker on general epidemiology and molecular mechanism depth

**Haiku report** ("comprehensive textbook" style):
- Deep **molecular mechanism sections**: glutamate excitotoxicity (EAAT2, GLT-1, system xc−), calcium dysregulation (AMPAR/NMDAR pathways), mitochondrial dysfunction with motor neuron type-specific vulnerability, TDP-43 pathology (present in ~97% of ALS patients), ER stress/UPR signaling, autophagy dysfunction with specific ALS gene involvement at each stage (C9ORF72 early, p62 intermediate, VCP late)
- **Spastic vs flaccid bulbar palsy distinction** — clinically important differentiation Step Flash missed entirely
- **Better epidemiology**: FRALim register 21-year longitudinal data, racial variation in bulbar onset (27-28% similar between European- and African-Americans), breakdown of all onset types (spinal 58-82%, mixed 9.9-17.1%, thoracic 1.5-3.5%, respiratory 1.7%)
- **Detailed physical examination findings**: specific clinical signs (jaw jerk preservation despite weakness, pharyngeal reflex loss, palate/vocal cord movement assessment)

### Which is "better"?

Neither dominates across all dimensions:

- **For a researcher wanting unique mechanistic insights**: Step Flash's selective vulnerability section (MMP9, calcium-binding proteins, E/I balance) contains material Haiku's report doesn't cover. These are specific, citable data points.
- **For a clinician wanting comprehensive reference**: Haiku's report is more thorough on mechanisms, epidemiology, clinical presentation, and diagnostic approach. It reads like a review article.
- **For cost efficiency**: Step Flash at $0.061 vs Haiku at $0.076 — negligible difference. Both are under 10 cents.
- **For speed**: Haiku is 3× faster (3.9 min vs 12.7 min) even at the same concurrency=2. With higher concurrency (8+), Haiku could finish in under 2 minutes.

### Recommendation

**For production all-cloud deployment, Haiku is the better default.** It produces a more comprehensive report, runs faster, costs only marginally more, and its "selective extraction + expansive synthesis" strategy is more token-efficient. The 14 references (vs Step Flash's 29) are cited more densely (136 vs 95 citations), suggesting higher citation-per-claim discipline.

**Step Flash remains the best value for the hybrid architecture** (local Qwen for extraction, Step Flash for linchpin calls only), where its $0.008/run cost for just the 2-3 cloud-tier calls is essentially free.

---

## Ollama Parallel Mode on AMD

### What it promises

`OLLAMA_NUM_PARALLEL=N` allows a single Ollama instance to serve N concurrent requests against one loaded model by maintaining N separate KV caches.

### What actually happens on AMD ROCm (RX 7900 XTX)

**Ollama's parallel mode on AMD is time-slicing, not true batching.** Unlike vLLM's continuous batching where concurrent requests share GPU forward passes, Ollama's parallel mode context-switches between KV caches sequentially. Each additional parallel slot:

- **Slows every concurrent call proportionally**: 2 slots = ~50% slower per call; 4 slots = ~75% slower per call
- **Does NOT increase total throughput**: net tokens-per-second across all slots remains roughly constant
- **Adds VRAM per slot**: ~3-4 GB per KV cache at 32k context for a 9B model
- **Lazy-allocates slots**: first concurrent burst pays a per-slot allocation cost (30-60s on first run after restart)

Empirical wall-time data across concurrent configurations:

| Config | Rank wall time (solo) | Extract wall time (concurrent) | Notes |
|---|---|---|---|
| NUM_PARALLEL=1 | 7s | 30s | Baseline |
| NUM_PARALLEL=2 | 7s solo, ~14s concurrent | ~50s | 2x per-call slowdown when both slots used |
| NUM_PARALLEL=4 | 7s solo | ~100-120s | 4x per-call slowdown; time-slicing overhead |

**Recommendation**: `NUM_PARALLEL=2` is the sweet spot for AMD consumer GPUs. It gives genuine (modest) parallelism for the pipeline's natural concurrency (multiple sub-questions processing simultaneously) without cratering per-call performance. Going above 2 provides no net throughput gain and risks hitting client-side timeouts (see next section).

### vLLM would be different

vLLM's continuous batching genuinely overlaps GPU compute across concurrent sequences. The same 4-way concurrency that makes Ollama 4x slower per call would make vLLM ~3.5x faster in total throughput. We were unable to stabilize vLLM on ROCm nightly for this hardware during the testing period. A purpose-built vLLM rig with native GPU support (e.g., AMD Instinct or NVIDIA hardware) would dramatically change the economics of local inference.

---

## The Retry Cascade Trap

### The bug

We implemented a retry wrapper around LLM calls to handle transient cloud provider errors (429 rate limits, 502/503 from OpenRouter). The wrapper retried on any error matching `message.includes('fetch failed')` — a broad pattern intended to catch network failures.

### How it cascaded

In Node.js 18+ (undici), **AbortSignal.timeout firing during a fetch also surfaces as `TypeError: fetch failed`** with the abort wrapped as the cause. So when a local Ollama call took longer than the 600-second client timeout:

1. AbortSignal.timeout fires → `TypeError: fetch failed`
2. Retry wrapper matches `'fetch failed'` → retries
3. **The original request is still running on Ollama** (Forge → Ollama connection stays open)
4. The retry creates a NEW concurrent request for the same logical task
5. Two requests now share the GPU → both slower → both more likely to timeout → more retries
6. **Cascading collapse**: 4 concurrent requests for the same sub-question's rank call, all competing for GPU time, all generating 4000+ thinking tokens

### The data signature

```
sq-2 rank #1:  718s, 2418 tok, 3.4 t/s  ← 20x slower than normal
sq-2 rank #2:  711s, 2336 tok, 3.3 t/s  ← DUPLICATE, started 5 min later
sq-2 rank #3:  510s, 2385 tok, 4.7 t/s  ← THIRD attempt
sq-2 rank #4:  345s, 2437 tok, 7.1 t/s  ← FOURTH attempt (getting faster as others finish)
```

The per-token speed (3-7 t/s) is consistent with 6-8 way GPU sharing — far exceeding the 2-way parallelism the semaphore should allow. The retries created phantom concurrency that bypassed the client-side gate.

### The fix

Distinguish AbortError (client-side timeout — WE gave up) from genuine network failures (server is down):

```typescript
const isAbort = errName === 'AbortError' || errName === 'TimeoutError' ||
                cause?.name === 'AbortError' || message.includes('aborted');
const isHardNetworkErr = !isAbort && (message.includes('ECONNREFUSED') || ...);

// AbortError: DO NOT retry. The upstream call is still running.
// Network error: retry (server genuinely unreachable).
```

### Lesson

**Never retry on client-side timeouts when the upstream call may still be running.** The retry doubles the load on the upstream, which makes the original call even slower, which triggers more retries. This is a distributed-systems antipattern that's especially dangerous with GPU inference where each additional concurrent request directly degrades all others.

---

## Observability: Timeline Telemetry

### What we built

A per-task timeline UI (`/sage/[taskId]/timeline`) that visualizes every LLM call AND non-LLM event (search, fetch, Atlas ingest, semaphore queue wait) on a Gantt chart with per-purpose lanes.

### Why it was critical

Without the timeline, we were debugging by looking at log timestamps and guessing. The timeline made several problems immediately obvious:

1. **The 5-minute cold-start gap** between decompose and first rank — visible as dead space between lanes
2. **The retry cascade** — visible as duplicate bars in the same lane for the same sub-question
3. **Semaphore queue depth** — the `llm_wait` lane showed exactly how long calls waited for a slot
4. **The I/O vs LLM ratio** — fetches and ingests are specks compared to LLM bars; the pipeline is entirely LLM-bound

### Implementation

- `llm_calls` table extended with `task_id`, `purpose`, `sub_question_id`, `started_at` columns
- `task_events` table for non-LLM work (search, fetch, ingest, semaphore queue)
- AsyncLocalStorage context (`sageContext`) propagates task_id through all async boundaries without threading params through every function signature
- Timeline UI: server-rendered SVG Gantt chart with 3-second meta-refresh polling, no JS framework dependencies

The telemetry overhead is negligible (fire-and-forget Postgres inserts) and the data pays for itself on every debugging session.

---

## Key Numbers

### Wall time evolution (same query: "The onset and progression of bulbar ALS")

| Run | Config | Wall time | Notes |
|---|---|---|---|
| SAGE-4 | All local Qwen 9B, thinking on, concurrency 1 | **60 min** | Baseline |
| SAGE-5 | All local, thinking on, concurrency 2 | **47 min** | First parallel attempt |
| SAGE-6 | All local, thinking on, concurrency 4 | **39 min** | Diminishing returns from Ollama parallel |
| SAGE-10 | Qwen + Step Flash (cloud synth), thinking on | **74 min** | Retry cascade + undici timeout bug |
| SAGE-13 | Qwen + Step Flash, thinking on, cascade fix attempt | **stuck** | Cascade fix didn't load (.next cache) |
| **SAGE-15** | **Qwen + Step Flash, thinking OFF, cascade fix** | **8.7 min** | **7x speedup from baseline** |

### Cost per research run

| Configuration | Cloud cost | Wall time | Quality |
|---|---|---|---|
| All local (Qwen 9B) | $0.00 | 60 min | Good |
| Hybrid (Qwen local + Step Flash cloud) | **$0.008** | **8.7 min** | **Better** |
| Projected all-cloud (Step Flash everything) | ~$0.10-0.15 | ~3-5 min | TBD |

### Per-call costs on Step 3.5 Flash (via OpenRouter paid tier)

| Call type | Typical cost |
|---|---|
| decompose | $0.0008 |
| synthesize | $0.0016 |
| doc_review | $0.0031 |
| **Total per run (3 cloud calls)** | **~$0.008** |

### Tokens per second (Qwen 3.5 9B on 7900 XTX)

| Mode | Solo | 2-way concurrent |
|---|---|---|
| With thinking (hidden tokens) | ~66 t/s (but generating 4000 tokens for a 300-token task) | ~33 t/s |
| Without thinking | ~66 t/s (generating only the actual response tokens) | ~33 t/s |

The per-token speed is identical. The difference is entirely in how many tokens are generated.

---

## Summary of Recommendations

1. **Disable thinking mode by default** on Qwen 3.5 and similar models with `thinking` capability. Pass `think: false` in every Ollama API call. The hidden reasoning overhead is 10-100x with no quality benefit on structured extraction/review tasks.

2. **Use a multi-tier model architecture.** Route the 2-3 highest-leverage calls (decompose + synthesize) to a capable cloud model. Keep the 15-25 bulk extraction calls on local hardware. Total cloud cost is under $0.01/run.

3. **Step 3.5 Flash is remarkably cost-effective** for structured research tasks. At $0.008/run it outperforms local 9B models on synthesis quality while being 10-50x faster on wall time.

4. **Ollama parallel mode on AMD is time-slicing, not batching.** Stay at NUM_PARALLEL=2 maximum. For genuine inference parallelism, use vLLM or similar continuous-batching servers.

5. **Never retry on client-side timeouts** when the upstream may still be processing. Distinguish AbortError from network failures. Retrying a timed-out GPU inference call creates cascading load that collapses the system.

6. **Build per-task telemetry early.** The timeline visualization paid for itself within hours of deployment by making retry cascades, cold-start gaps, and thinking-mode overhead visually obvious.
