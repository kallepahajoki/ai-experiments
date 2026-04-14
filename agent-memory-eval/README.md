# Agent Memory Evaluation

**Long-term memory for AI chat agents** — iterative development of a memory subsystem for the Anvil platform, benchmarked against LongMemEval (ICLR 2025). Starting from pure RAG retrieval, progressively adding structured fact extraction, temporal supersession, and source diversity to improve recall accuracy.

The memory system sits between agents and storage — agents call `memory.search` and `memory.store` without knowing the backend. Today that's Atlas (vector RAG) + Postgres (structured facts). The benchmark tests the complete pipeline: seed conversations → ask questions → judge answers.

---

## Benchmark: LongMemEval

500 questions across 6 categories testing different memory abilities, derived from synthetic multi-session chat histories. We use the **oracle** variant (only relevant sessions per question, ~2 sessions avg) for fast iteration, with 50-question shuffled subsets covering all types.

**Model**: Step 3.5 Flash (~200B MoE) via OpenRouter for chat, RAG answer generation, and judging.

**Evaluation**: LLM-as-judge via Forge `/api/chat` — binary CORRECT/INCORRECT per question with type-specific judge prompts (temporal reasoning checks chronological accuracy, knowledge update checks recency, etc.).

---

## Results

| Version | Overall | SS User | SS Assist | Temporal | K.Update | Multi-Sess | SS Pref |
|---------|---------|---------|-----------|----------|----------|------------|---------|
| v0 — Atlas RAG only | 40.0% | 80% | 50% | 46% | 42% | 25% | 12% |
| v1 — + fact extraction | 52.0% | 100% | 100% | 62% | 42% | 25% | 25% |
| v2 — + supersession + diversity | 56.0% | 80% | 100% | 62% | 67% | 50% | 0% |
| v3 — + proactive search prompt | 54.0% | 80% | 100% | 69% | 58% | 25% | 12% |
| v4 — + reference date injection | **64.0%** | 80% | 100% | **85%** | **75%** | 50% | 0% |
| v5 — + all-facts prefetch (354 facts) | 58.0% | 80% | 100% | 85% | 58% | 37% | 0% |
| v6 — + user profile + chunk dates + expiry | **64.0%** | 100% | 100% | 62% | **75%** | 50% | **25%** |
| v7 — + strict extraction prompts | 62.0% | 100% | 100% | 69% | 58% | 50% | 25% |

### v0 → v1: Structured fact extraction (+12 pts)

At ingest time, an LLM extracts concrete facts from each conversation ("User prefers dark roast coffee", "User bought a Honda Civic 2024") and stores them in a Postgres `memory_facts` table with category (preference/personal/event/decision) and source date. On search, matching facts are prepended to the RAG answer as "Known facts:" so the model sees them prominently.

**Impact**: Single-session questions jumped to 100% — the fact store surfaces specific personal details and assistant-provided information that RAG chunks sometimes bury.

### v1 → v2: Fact supersession + source diversity (+4 pts)

**Supersession**: When new facts are extracted, a second LLM call checks existing facts for contradictions. "User moved to Helsinki" supersedes "User lives in Tampere". Only active (non-superseded) facts are returned during search.

**Source diversity**: RAG retrieval increased from top-8 to top-12, then round-robin diversified across source documents (max 3 chunks per document) before taking the final 8. This ensures multi-session questions get context from multiple conversations.

**Impact**: Knowledge Update 42% → 67% (supersession ensures latest info wins). Multi-Session 25% → 50% (diversity pulls from multiple conversations).

### v2 → v3: Proactive search prompt (-2 pts, noisy)

Expanded the tool-use instruction to tell the model: "Also use memory.search BEFORE giving suggestions, recommendations, or advice." Aimed at getting the model to check memory before answering preference questions where nothing in the question explicitly triggers recall.

**Impact**: Mixed. SS Preference recovered slightly (0% → 12.5%), Temporal improved (+7.7), but Knowledge Update regressed (-8.4, likely noise at n=12). 7 judge errors also pulled the overall down. The prompt alone isn't reliable enough — the model still doesn't consistently connect "suggest recipes" with "check what this user likes to cook."

### v3 → v4: Reference date injection (+10 pts)

The benchmark questions have a `question_date` (e.g. "2023/05/30") but the model was answering relative-time questions ("how many months ago") using today's date (2026). Added a `reference_date` parameter to the `/complete` endpoint — the tool instruction now says "Current date: Monday, May 30, 2023" using the question's reference date for benchmarks, or the real date for production use.

**Impact**: Temporal Reasoning jumped from 62% → **85%** — most failures were purely date math errors. Knowledge Update also rose to **75%**, likely because temporal context helps the model pick the most recent fact.

### v4 → v5: All-facts prefetch — too much noise (-6 pts)

Injected all 354 active facts into the system prompt (~5K tokens). The model should see preferences like "User grows cherry tomatoes" and use them when asked "suggest dinner with homegrown ingredients."

**Result**: Overall dropped from 64% to 58%. The noise from hundreds of irrelevant facts (trip plans, random events, purchase history) confused the model on other categories. Knowledge Update fell from 75% to 58%. SS Preference remained at 0% — the model still gave generic responses and even asked "what's your phone model?" despite facts stating "User owns iPhone 13 Pro" being in the prompt.

**Lesson**: Brute-force context injection doesn't work. The LLM ignores or gets confused by large blocks of injected context. Need either semantic fact retrieval (embed facts, vector search) or a very focused profile summary.

### Observations on SS Preference

Two compounding problems make this category resistant to improvement:

1. **Gold answer format**: Gold answers are meta-descriptions ("The user would prefer baking suggestions that take into account their previous success with the lemon drizzle cake"), not factual answers. The judge checks whether the response *accounts for* specific preferences, which requires reading between the lines.

2. **Model behavior**: Even with all facts in the system prompt, the model gives generic advice and asks follow-up questions ("What's your phone model?") rather than using injected context. This suggests either the facts block is too long to attend to, or the model's instruction-following for injected context is weak at this prompt length.

### v5 → v6: User profile + chunk dates + auto-expiry (=64%, SS Pref 0→25%)

Three changes inspired by MemPalace (metadata filtering) and SuperMemory (user profiles):

1. **User profile summary**: After fact extraction, an LLM generates a compact 2-4 sentence profile from the top 50 active preference+personal facts. Stored in `memory_profiles` table, injected into the system prompt (~250 tokens). Example: *"The user is a frequent traveler with United Airlines Premier Gold status... owns a rare 1978 Rumours vinyl, a full MCU Funko POP! set, and 17 vintage cameras... enjoys astrophotography, BBQ experimentation..."*

2. **ChromaDB chunk metadata**: `source_date` field threaded from memory.store through the ingest pipeline to chunk metadata. Enables temporal filtering at retrieval time.

3. **Fact auto-expiry**: `expires_at` column on memory_facts, filtered in search queries. Time-bound facts can be set to expire.

**Impact**: SS Preference recovered to 25% (2/8) — the profile contains enough specific details for some questions (guitar: profile mentions Fender Stratocaster; colleague connection: profile reflects work context). Temporal regressed from 85% to 62% — likely noise at n=13, not a systematic issue.

**Key finding on SS Preference ceiling**: Only 2 of 8 key preference facts (iPhone 13 Pro, quinoa meal prep, cherry tomatoes, podcast genres, etc.) were extracted by the fact extraction LLM. The extraction prompt catches general preferences but misses specific product names and contextual details embedded in conversation.

### v6 → v7: Strict extraction prompts with failure conditions (=62%)

Rewrote the extraction prompt with imperative rules and explicit failure examples (inspired by [Arthur Soares' blog on model instruction compliance](https://arthur.earth/it-feels-like-a-different-team/)):

- "FAIL: 'User has a phone' when text says 'my iPhone 13 Pro' → CORRECT: 'User owns an iPhone 13 Pro'"
- Every brand, model, quantity, ingredient MUST appear in extracted fact

**Extraction quality improved dramatically**: iPhone 13 Pro, cherry tomatoes, basil and mint, true crime podcasts, history podcasts, Fender Stratocaster — all now extracted (previously missing). Total facts rose from 345 to 400+.

**SS Preference held at 25%**: The 2 questions that pass are ones where the model calls `memory.search` and gets the right facts back (dinner with homegrown ingredients → cherry tomatoes; commute activities → history podcasts like Hardcore History). The 6 failures are where the model gives generic answers without searching. The facts exist, retrieval works when triggered — the bottleneck is now profile coverage (top-50 facts → 4-8 sentence summary loses specifics) and tool invocation reliability.

### Overall progress: 40% → 64% (+24 points)

The biggest wins came from:
- Structured fact extraction with supersession (+12 pts)
- Reference date injection for temporal reasoning (+10 pts)
- Source diversity for multi-session questions (+8 pts from baseline)

Remaining challenges:
- SS Preference (25%) — combination of extraction gaps, profile coverage, and meta-gold-answer format
- Temporal Reasoning (62-85%, varies) — noise from small sample size (n=13)
- Multi-Session (50%) — diversity helped but cross-document synthesis still hard

---

## Concrete example: end-to-end data flow

To illustrate what the system actually sees at each stage, here's a real example from the benchmark — the "dinner with homegrown ingredients" question (SS Preference category).

### 1. Source conversation (ingested as memory)

A session from `2023/05/23` where the user discusses gardening and cooking:

```
USER: I'm trying to find some new recipe ideas that use fresh basil
      and mint. Can you suggest any?

ASSISTANT: What a refreshing combination! Fresh basil and mint can add
           a bright, herbaceous flavor to many dishes...

USER: What are some good companion plants for tomatoes?

ASSISTANT: Tomatoes benefit from being paired with certain companion
           plants...

USER: I've been using basil and mint in my cooking lately. I've even
      harvested some cherry tomatoes from my garden. Do you have any
      suggestions for companion plants that could help my cherry
      tomatoes grow better?

ASSISTANT: What a great combination! Basil, mint, and cherry tomatoes
           are a match made in heaven...
```

### 2. Extracted facts (stored in Postgres memory_facts)

The fact extraction LLM processes this conversation and should extract:

```json
[
  {"fact": "User cooks with fresh basil and mint", "category": "preference"},
  {"fact": "User owns cherry tomato plants", "category": "personal"},
  {"fact": "User has harvested cherry tomatoes from their garden", "category": "personal"},
  {"fact": "User has tomato, pepper, and cucumber seedlings", "category": "personal"}
]
```

> **Reliability issue found**: In the v8 run, the fact extraction silently failed for this session — the fire-and-forget LLM call timed out or errored. The basil/mint/cherry tomato facts were not stored, causing the question to fail.

### 3. User profile (injected into system prompt, ~500 tokens)

Generated from the top 200 active preference+personal facts:

```
The user is a Senior Marketing Specialist with 3 years and 9 months
of experience... Their devices include an iPhone 13 Pro with a cracked
screen protector, a Fender Stratocaster guitar... They enjoy cooking
with lemon and poppyseeds, experimenting with apple wood chips and
marinades for BBQ, favor Sweet Baby Ray's sauce... gardening marigold,
tomato, pepper, and cucumber seedlings with a peat moss-perlite-
vermiculite mix... They listen to history, science, true crime, and
self-improvement podcasts during their 40-minute commute...
```

Note: the profile mentions "tomato, pepper, and cucumber seedlings" but NOT "cherry tomatoes" or "basil and mint" — those facts weren't extracted, so they couldn't make it into the profile.

### 4. Benchmark question

```
Q: What should I serve for dinner this weekend with my homegrown ingredients?

Gold: The user would prefer dinner suggestions that incorporate their
      homegrown cherry tomatoes and herbs like basil and mint,
      highlighting recipes that showcase their garden produce.
```

### 5. LLM tool calls (from llm_calls table)

**Call 1** — LLM decides to search memory:
```json
{
  "function": "memory.search",
  "arguments": {
    "query": "homegrown garden ingredients cooking preferences tomatoes peppers cucumbers"
  }
}
```
Duration: 39,987ms (full RAG pipeline)

**Call 2** — LLM synthesizes answer from profile + RAG results:

> "Based on what you're growing in your garden (tomatoes, peppers, cucumbers), here are some delicious dinner ideas..."

### 6. What went wrong

The model used the profile's "tomato, pepper, and cucumber seedlings" — but the gold answer wants "cherry tomatoes and herbs like basil and mint." The specific gardening facts were never extracted, so neither the profile nor memory.search could surface them. The answer is reasonable given the available data, but the judge marks it INCORRECT because it doesn't mention the specific ingredients.

### 7. Failure classification

```
Failure: wrong_reasoning (had some context but wrong specifics)
Root cause: missing_facts (extraction failed for this session)
```

This example shows how a single extraction failure cascades through the entire pipeline — the profile misses the detail, memory.search can't find it, and the model gives a plausible but incorrect answer.

---

## Failure analysis (v8, 18 failures out of 50)

Diagnostic tool (`diagnose.py`) cross-references results with the Postgres fact store, profile table, and LLM call audit log to classify each failure:

```
wrong_reasoning:  8  — model had context but reasoned incorrectly
no_search:        5  — model didn't call memory.search when it should have
not_in_profile:   5  — facts exist in DB but not in the profile summary
```

The "wrong_reasoning" failures are further decomposed:
- 3 are **RAG returning incomplete chunks** (not all relevant sessions found)
- 2 are **supersession failures** (old facts overriding new ones — therapist frequency, airline status)
- 2 are **model arithmetic/ordering errors** (date math, counting)
- 1 is a **possible judge error** (answer looks correct but marked wrong)

---

## Architecture

```
┌─────────────────────────────────────────────────────┐
│  Agent (Spark /complete)                             │
│  1. Prefetch: query Postgres facts (~50ms)           │
│     → inject matching facts into system prompt       │
│  2. LLM runs with facts + tool-use instruction       │
│  3. LLM may call memory.search for deeper recall     │
│  → auto-scoped by agent_id + project_id              │
├─────────────────────────────────────────────────────┤
│  Memory endpoints (Atlas /api/internal/tool/memory/) │
│  ┌──────────────────┐  ┌──────────────────────────┐ │
│  │  Fact store       │  │  Atlas RAG               │ │
│  │  (Postgres)       │  │  (ChromaDB + LLM)        │ │
│  │                   │  │                          │ │
│  │  • keyword search │  │  • semantic search       │ │
│  │  • supersession   │  │  • source diversity      │ │
│  │  • date-ordered   │  │  • top-K retrieval       │ │
│  └──────────────────┘  └──────────────────────────┘ │
│  Results merged: facts prepended to RAG answer       │
├─────────────────────────────────────────────────────┤
│  Fact extraction (at ingest time)                    │
│  • LLM extracts preference/personal/event/decision   │
│  • Supersession check against existing facts          │
│  • Fire-and-forget (doesn't block store response)     │
└─────────────────────────────────────────────────────┘
```

### Dual scope

Memory can be scoped by `agent_id`, `project_id`, or both:
- **Agent-scoped**: "What did we discuss about my car?" — the agent remembers across all projects
- **Project-scoped**: "What decisions have we made?" — any agent in the project can recall shared context
- **Both**: intersection — a specific agent's contributions within a specific project

### Cost

~$0.08 per 50-question benchmark run at Step 3.5 Flash pricing ($0.10/M input, $0.30/M output). Seeding with fact extraction is the bulk (~616K input tokens for 91 sessions). Re-runs with `--skip-seed` cost ~$0.03.

---

## Running the benchmark

```bash
cd memory-benchmark
pip install -r requirements.txt

# Full run (cleanup → seed → query → judge)
FORGE_SECRET=dev-secret-local ANVIL_API_TOKEN=anvil_xxx \
  python benchmark.py --max-questions 50

# Re-run after code changes (reuse seeded data)
python benchmark.py --max-questions 50 --skip-seed

# Cleanup all benchmark data
python benchmark.py --cleanup
```

Requires Atlas, Spark, Forge, Board, Probe running locally. Data files in `data/` (gitignored) from [xiaowu0162/longmemeval-cleaned](https://huggingface.co/datasets/xiaowu0162/longmemeval-cleaned).

---

## Files

All code lives in the Anvil toolkit repo (`ai-toolkit/`), not here. This directory contains only the writeup.

| Path | Purpose |
|------|---------|
| `lib/memory/` | Type definitions, Atlas backend, fact DB, fact extractor |
| `atlas/app/api/internal/tool/memory/` | Store + search endpoints (fact extraction, supersession, diversity) |
| `lib/tools/registry.ts` | `memory.search` + `memory.store` tool definitions |
| `spark/app/api/chats/[id]/complete/route.ts` | Auto-scoping, tool-use instructions |
| `memory-benchmark/` | Benchmark harness (Python) |
| `migrations/1776058251509_memory-facts.sql` | Postgres schema for extracted facts |
