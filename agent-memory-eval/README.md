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
| v4 — + reference date injection | 64.0% | 80% | 100% | **85%** | **75%** | 50% | 0% |
| v5 — + fact prefetch (fast path) | pending | | | | | | |

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

### v4 → v5: Fact prefetch into system prompt (pending)

The SS Preference category remains at 0% across multiple versions. Root cause: these questions ask for suggestions ("recommend recipes", "suggest phone accessories") where the gold answer expects the model to account for user preferences (grows cherry tomatoes, owns iPhone 13 Pro). The model doesn't call `memory.search` because nothing triggers recall.

**Solution**: Auto-inject matching facts from Postgres into the system prompt before the LLM runs. No tool call needed — the model always sees user preferences. Initial implementation called the full RAG pipeline (10-20s, timed out). Fixed to query the `memory_facts` Postgres table directly (~50ms).

### Observations on SS Preference

These questions have unusual gold answers — not factual answers but meta-descriptions of what the response *should account for* (e.g. "The user would prefer baking suggestions that take into account their previous success with the lemon drizzle cake"). This makes them harder to judge: even if the model uses the right preferences, the judge may mark it incorrect if the response format doesn't match the gold's meta-description. This category may have a ceiling effect from the judge prompt.

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
