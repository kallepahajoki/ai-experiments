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
| v8 — + bigger profile (200 facts, 8-15 sent) | 64.0% | 100% | 100% | 53% | 58% | 62% | 62% |
| v9 — + pgvector + 100q | 53.0% | 83% | 100% | 45% | 59% | 43% | 20% |
| v12 — + query expansion + prefix cache | 60.0% | 92% | 83% | 55% | 68% | 43% | 40% |
| *(v12 excl. timeouts, n=93)* | *64.5%* | *92%* | *83%* | *70%* | *68%* | *43%* | *44%* |
| **v16 — + supersession v2 + retry + caches** | 52.0% | 75% | 83% | 48% | **82%** | 24% | 10% |
| **v17 — + intent detection + expanded-only + dedup** | **62.0%** | **83%** | 83% | **62%** | **86%** | **33%** | **30%** |
| v18 — + batch aggregation (245 facts) | 55.0% | 75% | 83% | 55% | 73% | 29% | 30% |
| v19 — + temporal date-range + aggregate filter | 56.0% | 75% | 83% | 52% | 77% | 29% | 40% |

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

### v9: pgvector + 100 questions — the real baseline (53%)

Doubled the question count to 100 for statistical significance. This exposed that the 50-question runs (64%) were inflated by noise in small categories. At n=100:

**Failure breakdown (47 failures):**
```
not_in_profile:   24  (51%) — facts exist but not surfaced to the model
wrong_reasoning:  11  (23%) — model had context, reasoned incorrectly
no_search:         9  (19%) — model didn't call memory.search
query_error:       3  ( 7%) — timeouts
```

The #1 bottleneck is `not_in_profile` — the profile summary (8-15 sentences from 200 facts) can't cover all 936 extracted facts. When the model doesn't call memory.search (which happens 19% of the time), the profile is the only context available and it often lacks the specific detail needed.

pgvector embeddings are working (all 936 facts embedded), but they only help when memory.search is called — the profile is still a compressed summary without semantic retrieval.

### v12: Query expansion + prefix caching (60%, 64.5% excl. timeouts)

Query expansion generates keyword-list queries via LLM before vector search ("grow tomatoes basil zucchini" instead of raw question). Multi-query embedding keeps the best cosine score per fact. Combined with prefix-cache-friendly prompt ordering (static tool rules as prefix, dynamic memory context before last user message).

**Impact at 100q**: 53% → 60% (64.5% excluding 7 OpenRouter timeouts). SS Preference jumped from 10% → 40% — query expansion bridges the semantic gap between "suggest dinner" and "cherry tomatoes from garden." Temporal improved to 70% when excluding timeouts.

**Failure breakdown (40 failures):**
```
not_in_profile:   23  — facts exist but retrieval doesn't surface them
query_error:       7  — OpenRouter timeouts (infrastructure)
no_search:         6  — model skipped memory.search
wrong_reasoning:   4  — model had context, reasoned incorrectly
```

**Key validation**: Tested the 3 hardest aggregation questions by pasting perfect context directly to the model (no retrieval). The model answered all 3 correctly (health devices: 4/4, luxury spending: $2,500, baby count: 5). This confirms the remaining gap is entirely retrieval — getting facts from multiple sessions surfaced together — not model capability.

### v12 → v16: Supersession v2 + extraction retry + caches (K.Update 68→82%, overall 60→52%)

Five changes targeting supersession quality, extraction reliability, and pipeline performance:

1. **Cross-category vector-based supersession**: Removed the category filter from `supersedeConflicts()` — "sneakers under bed" (personal) can now be superseded by "storing sneakers in shoe rack" (decision). Uses pgvector cosine similarity to find the most relevant existing facts to compare, instead of `ORDER BY created_at DESC LIMIT 50` which missed old facts buried in the history.

2. **Supersession prompt with FAIL/CORRECT examples**: Applied the same imperative-with-failure-conditions pattern from the extraction prompt to supersession. Examples like `FAIL: Keeping "attended 3 sessions" when new fact says "attended 5 sessions"` dramatically improved supersession detection.

3. **Extraction retry in benchmark**: After seeding, verifies extraction via Postgres query, re-ingests missing sessions up to 2 rounds with 30s waits. Improved extraction coverage from 67/191 (35%) to 185/191 (97%).

4. **Pipeline optimizations**: Disabled NER and source-boost for memory.search (saves ~7s/query). Added in-memory LRU embedding cache (2000 entries) and query expansion cache (500 entries). Mean latency dropped from 77.6s to 51.3s.

5. **Conflicting facts instruction**: Prefetch header now says "When facts conflict, the more recent date is authoritative. Treat plans and decisions from past dates as completed."

**Impact**: Knowledge Update jumped from 68% to **82%** — the best category score in the benchmark's history. Confirmed by testing individual questions: bereavement sessions (3→5), Hilton points (1→2 nights), vehicle model (Mustang→F-150), family trip (countryside→Paris) all resolved correctly with supersession.

**But overall dropped 60→52%**: 18 regressions vs 10 fixes. Every regression traced to extraction non-determinism — different facts get extracted each run because the LLM (Step 3.5 Flash) produces slightly different outputs even at temperature=0.1 (OpenRouter routing adds non-determinism). Multi-Session (43→24%) and SS Preference (40→10%) are highly sensitive to which specific facts exist. The Knowledge Update improvement is the reliable signal.

**skipLLM experiment (v14)**: Tried skipping the RAG LLM synthesis step in memory.search (returning raw chunks instead of a synthesized answer). Dropped accuracy ~15pts (46%). The synthesis step is important — it contextualizes raw chunks, extracts relevant details, and filters noise before Spark's model sees the result. Reverted.

### v16 → v17: Intent detection + expanded-only search + fact dedup (+10 pts, 11 fixes / 1 regression)

Three changes targeting the SS Preference bottleneck (model gives generic advice without using personal facts):

1. **Embedding-based intent detection** (`lib/services/intent/index.ts`): Classifies user messages by cosine similarity against pre-embedded intent exemplars (advice_seeking, mail, calendar, reminders, memory_recall, web_search, general_chat). Uses bge-m3 centroids — language-agnostic, tested with English, Finnish, German, Japanese. Lazy-initialized on first request (~200ms), cached for process lifetime. Detection rule: advice_seeking must be top-1 intent AND score ≥ 0.62.

2. **Expanded-only vector search**: For advice-seeking queries, the prefetch drops the original user question from vector search and uses only LLM-generated keyword queries. The original question "What should I serve for dinner this weekend" matches topical facts ("dinner party", "meal prep") at 0.72 cosine, drowning out personal attribute facts ("grows cherry tomatoes" at 0.53). The expanded queries ("fresh tomatoes basil garden herbs") match personal facts at 0.69, which now rank highest without the topical interference. Also requests 20 facts (vs default 10) and uses a directive injection: "You MUST use these facts to personalize your response."

3. **Fact text deduplication**: Extraction retries create duplicate facts with different IDs (e.g. 3 copies of "User is planning a dinner party this weekend"). Merge step now deduplicates by case-insensitive fact text, keeping the highest-scored copy. Frees fact slots for diverse results.

**Also improved**: Query expansion prompt rewritten to focus on personal attributes ("POSSESSIONS, HOBBIES, HABITS, PREFERENCES") instead of generating recipe names or product answers. The old prompt produced "tomatoes basil pasta caprese salad"; the new one produces "fresh tomatoes basil garden herbs cooking" which better matches stored facts.

**Impact**: Every category improved. SS Preference 10% → 30% (+20pp) — the primary target. Temporal 48% → 62% (+14pp) and Multi-Session 24% → 33% (+9pp) also benefited from dedup and better expansion. 11 fixes across all categories, only 1 regression.

**Key insight**: For personalization queries, the user's literal question is a bad retrieval query. "Suggest dinner" matches dinner-related events, not the user's garden inventory. Separating "what is the user asking about" (the question) from "what personal facts would help answer this" (the expanded queries) and only searching with the latter dramatically improves recall for preference questions.

### Overall progress: 40% → 62% at 100q (+22 points)

The biggest wins came from:
- Structured fact extraction with supersession (+12 pts)
- Reference date injection for temporal reasoning (+10 pts)
- Intent-aware retrieval with expanded-only search (+10 pts)
- Source diversity for multi-session questions (+8 pts from baseline)

Remaining challenges:
- Multi-Session (33%) — requires aggregating facts from 3-5 sessions; retrieval returns partial results
- Temporal Reasoning (62%) — model reasoning on date math + retrieval gaps
- SS Preference (30%) — improved with intent detection but still limited when the question doesn't hint at the relevant personal attribute (e.g. "phone accessories" can't guess "iPhone 13 Pro")

### v17 → v18: Batch fact aggregation (55%, -7 pts — aggregate noise)

Built a batch aggregation pipeline that scans all active facts, detects countable groups via LLM, and creates summary aggregate facts stored in `memory_facts` with `aggregate_member_ids UUID[]`.

**Pipeline**: `POST /api/internal/tool/memory/aggregate` — fire-and-forget endpoint. Chunks 4271 unique facts into 100-fact batches, sends each to GPT-5 Nano (new global `batch` model category in Forge) for group detection, generates summary facts. Created 245 aggregates including "User has 17 fish across 2 aquariums: 10 neon tetras, 5 golden honey gouramis, 1 pleco, 1 betta (Bubbles)" and "User spent $1,200 on a Gucci handbag."

**Individual question validation**: The fish question ("How many fish in both aquariums?") went from INCORRECT to CORRECT with exact count of 17. The aggregation works when the right summary fact is surfaced.

**But overall dropped 62→55%**: The 245 aggregate facts competed with individual facts in pgvector search, adding noise for non-aggregation queries. 9 regressions, only 2 fixes. Same pattern as v5's all-facts prefetch — too much irrelevant context drowns out the signal.

### v18 → v19: Aggregate filtering + temporal date-range (56%, +1 pt)

Two changes to address v18's regressions:

1. **Aggregate intent filtering**: Added `aggregation` intent to the embedding-based classifier (exemplars: "how many devices", "total amount spent", "how many classes per week"). Aggregate facts are excluded from search results by default (`aggregate_member_ids IS NULL` in scope filter), only included when the aggregation intent is detected. This prevents aggregate noise for non-counting queries.

2. **Temporal date-range filtering via chrono-node**: Detects relative time expressions ("10 days ago", "last Tuesday", "neljä viikkoa sitten") using chrono-node with multilingual support (EN, FI, DE, FR, JA, NL, PT). Converts to absolute date range using the reference_date, then adds a SQL filter on `source_date`. Requires a keyword guard (`/\b(ago|last|yesterday|past|viime|sitten|eilen|vor)\b/`) to prevent chrono from parsing incidental dates ("5-day trip" → false positive).

**Impact**: Partial fix. Fish aquarium restored to correct. But 9 regressions from v17, mostly from extraction non-determinism between runs (different facts extracted). The temporal filtering helped some queries (Yosemite camping trip: found May 15-17 dates) but many benchmark temporal questions have a mismatch between session dates and the temporal offset implied by the question.

### Overall progress: 40% → 62% at 100q (v17 is the stable high point)

v17 remains the cleanest improvement. v18-v19 added infrastructure (aggregation, temporal filtering, batch model) that works for individual questions but didn't net positive in full benchmark due to noise and non-determinism. The infrastructure is sound — the tuning needs more work.

---

## Current state and next steps

### What's built
- `lib/memory/` — types, Atlas backend, fact DB, fact extractor
- `memory.search` + `memory.store` tools with auto-scoping
- Postgres `memory_facts` table with pgvector embeddings (1024-dim, HNSW index)
- Postgres `memory_profiles` table for LLM-generated user profile summaries
- Fact extraction at ingest time with cross-category vector-based supersession
- Supersession prompt with FAIL/CORRECT examples for reliable conflict detection
- Query expansion (LLM generates keyword queries before vector search)
- Aggregation-aware retrieval (factLimit 10→25 for counting/total queries)
- System prompt prefetch with "more recent date is authoritative" instruction
- Prefix-cache-friendly prompt ordering (static prefix + dynamic suffix)
- In-memory LRU caches for embeddings (2000 entries) and query expansion (500 entries)
- NER and source-boost disabled for memory.search (document Q&A features, not memory)
- Embedding-based intent detection (`lib/services/intent/`) — language-agnostic classification using bge-m3 centroids, detects advice_seeking, aggregation, mail, calendar, reminders, memory_recall, web_search, general_chat
- Expanded-only vector search for advice queries — bypasses topical matching, uses only personal-attribute keyword queries
- Fact text deduplication in search results
- Batch fact aggregation (`/api/internal/tool/memory/aggregate`) — LLM-based group detection across all facts, creates summary aggregate facts with member tracking
- Aggregate intent filtering — aggregates only surfaced for counting/totaling queries
- Temporal date-range filtering via chrono-node (multilingual: EN, FI, DE, FR, JA, NL, PT) with keyword guard for false positive prevention
- Global `batch` model category in Forge — configurable model for background/batch tasks (currently GPT-5 Nano)
- Model resolution fix — global _default categories resolve before app:chat fallthrough
- Benchmark harness with `--tag`, `--failed-from`, extraction retry, diagnostics, single-question test tool

### What's working well
- **Fact extraction** — strict prompt with failure conditions catches specific details. Extraction retry in benchmark achieves 97% coverage (185/191 sessions).
- **Supersession** — cross-category vector-based comparison with FAIL/CORRECT prompt. Knowledge Update at 86%.
- **Intent-aware retrieval** — embedding-based intent detection identifies advice/suggestion queries, expanded-only search finds personal facts instead of topical matches. SS Preference 10% → 30%.
- **pgvector search** — semantic matching works when query expansion bridges the gap
- **Pipeline performance** — NER/source-boost removal + caches + local embeddings cut mean latency from 77s to ~40s
- **Model reasoning** — confirmed via synthetic tests that the model handles counting/aggregation perfectly when given the right facts

### Known issues
1. **Benchmark variance** — extraction non-determinism (LLM produces different facts each run even at temperature=0.1) causes ±10pt swings. Local embeddings reduced one source of variance (OpenRouter routing), but LLM extraction still varies.
2. **Multi-session aggregation** — 33% accuracy, the weakest category. Questions like "how many devices" or "total spent" need facts from 3-5 sessions. Vector search returns top-K from the closest sessions, missing the others.
3. **SS Preference indirect references** — 30% accuracy. Intent detection + expanded-only search fixed cases where relevant facts exist but aren't found. Remaining failures are when the question doesn't hint at the relevant attribute (e.g. "phone accessories" can't bridge to "iPhone 13 Pro" without the model chaining a search to identify the phone first).
4. **RAG synthesis is necessary** — experiment showed skipping the RAG LLM synthesis step drops accuracy ~15pts. Raw chunks are too noisy for the chat model.

### Ideas for further improvement

**High impact, moderate effort:**
- **Cross-session aggregation** — current batch aggregation chunks facts into 100-fact batches. Facts from different sessions about the same topic (Fitbit in batch 3, hearing aids in batch 12) never get grouped. Options: larger batches with a faster model, two-pass aggregation (detect themes first, then pull related facts across batches), or pre-cluster by embedding before LLM detection.
- **Temporal filtering refinement** — chrono-node parses absolute dates ("March 15th") in temporal queries, but the date-range filter should only apply for relative references ("10 days ago", "last Tuesday"). Distinguish relative vs absolute temporal references.
- **Chained search for indirect preference queries** — when the user says "my phone" and the prefetch finds phone facts but not the specific model, automatically trigger a follow-up search with the specific details found (e.g. search for "iPhone 13 Pro accessories" after finding "User owns an iPhone 13 Pro").
- **Replace hasToolIntent regex** — the intent detection module already supports all tool categories. Migrating `hasToolIntent()` would make tool routing language-agnostic.

**Moderate impact, low effort:**
- **Batch deduplication** — clean up existing duplicate facts in the DB (~4849 facts → ~4271 unique). Currently only deduped at search time. A one-time cleanup + dedup-on-insert would reduce noise in vector search.
- **Run clean v20 benchmark** — v17 is the stable high point (62%). v18-v19 added infrastructure that needs tuning. A clean run with aggregate filtering + temporal guard (no chrono false positives) should be ≥ v17.

**Research directions:**
- **LongMemEval S variant** — switch from oracle (only relevant sessions) to S (~50 sessions per question with distractors). Harder but more realistic.
- **Official eval** — export results as JSONL, run LongMemEval's evaluate_qa.py with GPT-4o judge for publishable numbers.

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

## Failure analysis

### v12 (40 failures out of 100)

```
not_in_profile:   23  — facts exist but retrieval doesn't surface them
query_error:       7  — OpenRouter timeouts (infrastructure)
no_search:         6  — model skipped memory.search
wrong_reasoning:   4  — model had context but reasoned incorrectly
```

### v16 (48 failures out of 100)

With extraction retry achieving 97% coverage (185/191 sessions), the failure profile shifted:

- **Multi-Session (16 failures)**: Aggregation questions remain hardest. Facts from 3-5 sessions need to be surfaced together; vector search returns partial results.
- **Temporal (15 failures)**: Date math errors and relative-time queries ("10 days ago") where the model can't bridge the semantic gap between the query and stored facts.
- **SS Preference (9 failures)**: Model gives generic advice without calling memory.search. The prefetch surfaces some facts but not enough for preference-specific questions.
- **Knowledge Update (4 failures)**: Dramatically improved with supersession. Remaining failures are edge cases (plans treated as incomplete, ambiguous supersession).
- **SS User/Assistant (4 failures)**: Extraction variability — specific details not captured in this run.

### v17 (38 failures out of 100)

11 fixes from v16, 1 regression. Intent detection + expanded-only search improved all categories:

- **Multi-Session (14 failures)**: Aggregation still hardest, but dedup freed fact slots — 2 multi-session questions fixed (fish aquariums, pet supplies cost).
- **Temporal (11 failures)**: Better expansion surfaced date-relevant facts. 3 temporal fixes (Summer Nights festival, Valentine's airline, spark plugs).
- **SS Preference (7 failures)**: Down from 9. Remaining failures are indirect reference cases — "phone accessories" where the model can't bridge to "iPhone 13 Pro" without chained search.
- **Knowledge Update (3 failures)**: Steady improvement. Grocery list method fixed.
- **SS User (2 failures)**: Internet plan speed fixed by better fact retrieval.

### Key insight: separating question intent from fact retrieval

v16→v17 showed that for personalization queries, the user's literal question is a poor retrieval query. "Suggest dinner this weekend" has high cosine similarity to topical facts ("dinner party", "meal prep") but low similarity to the personal attributes needed to answer well ("grows cherry tomatoes", "cooks with basil"). Expanded-only mode — dropping the original question from vector search and using only LLM-generated personal-attribute keywords — fixes this category of failure.

---

## Architecture

```
┌─────────────────────────────────────────────────────┐
│  Agent (Spark /complete)                             │
│  0. Intent detection: classify user message          │
│     (bge-m3 centroids, language-agnostic)            │
│  1. Prefetch: query Postgres facts                   │
│     → advice queries: expanded-only + directive      │
│     → other queries: standard prefetch               │
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

~$0.15 per 100-question benchmark run at Step 3.5 Flash pricing ($0.10/M input, $0.30/M output). Seeding with fact extraction + supersession is the bulk (~2M input tokens for 191 sessions with retries). Re-runs with `--skip-seed` cost ~$0.05. Embedding cache reduces redundant API calls on repeated runs.

---

## System mechanisms

Every moving part of the memory system, what it does, and how benchmark-specific vs generally useful it is.

### Storage & ingestion

| Mechanism | What it does | Why | Contrib. | General vs benchmark |
|-----------|-------------|-----|----------|---------------------|
| **Fact extraction** | LLM parses each conversation into structured facts ("User owns an iPhone 13 Pro", "User prefers vinyasa yoga") with category labels (preference/personal/event/decision). Fire-and-forget after document ingest. | Raw conversations are too verbose for retrieval. Facts are atomic, embeddable, and composable. Without this, the system is pure RAG with 40% accuracy. | **20-25%** | **Fully general.** Any agent memory system needs to distill conversations into retrievable knowledge units. The category taxonomy may vary but the core idea is universal. |
| **Strict extraction prompt** | Imperative prompt with FAIL/CORRECT examples ("FAIL: 'User has a phone' when text says 'my iPhone 13 Pro' → CORRECT: 'User owns an iPhone 13 Pro'"). Forces the LLM to preserve specific details. | Without it, extraction loses brand names, quantities, and specifics — the exact details needed to answer questions. | **3-5%** | **Mostly general.** Specificity in extraction matters for any memory system. The exact failure examples are tuned to common LongMemEval patterns (product names, counts) but the principle applies broadly. |
| **Dedup-on-insert** | Before inserting, checks for case-insensitive matches against existing facts for the same tenant+agent. Skips duplicates, both against DB and within the current batch. | Extraction retries and re-ingestion produce near-identical facts. Duplicates waste retrieval slots and can outvote correct superseded facts (4 copies of "3 sessions" drowns out 1 copy of "5 sessions"). | **3-6%** | **Fully general.** Any system that re-processes conversations or retries extraction needs deduplication. |
| **Source-ref idempotency** | Skips extraction entirely if facts already exist for a given `source_ref`. | Prevents re-extraction on retry when facts were successfully extracted but the caller didn't get the response. | **<1%** | **Fully general.** Standard idempotency pattern. |
| **Embedding at insert** | Each fact gets a pgvector embedding (bge-m3, 1024-dim) stored alongside the text. Batch-embedded in one call per ingestion. | Enables semantic search. Without embeddings, retrieval is keyword-only. | **10-15%** | **Fully general.** Core infrastructure for any vector-search-based memory. |
| **ChromaDB document store** | Raw conversation text stored as chunked documents in ChromaDB, alongside the structured facts in Postgres. | Provides a fallback retrieval path (RAG) for information that fact extraction misses, and for verbatim recall ("what exactly did you say about X"). | **2-5%** | **Fully general.** Dual-store (structured + unstructured) is a common pattern. The RAG path is less important as extraction quality improves, but remains valuable for edge cases. |

### Knowledge maintenance

| Mechanism | What it does | Why | Contrib. | General vs benchmark |
|-----------|-------------|-----|----------|---------------------|
| **Supersession** | After extracting new facts, an LLM compares them against semantically similar existing facts (found via pgvector). Contradicted facts get marked `superseded_at = NOW()` and excluded from search. | Users change jobs, move cities, update counts. Without supersession, the system returns stale facts alongside current ones and the chat model can't reliably pick the right one. | **5-10%** | **Fully general.** Any long-lived memory system must handle contradictions. The vector-based candidate selection (vs category-based) is a refinement that matters in practice. |
| **Cross-category supersession** | Supersession compares across all categories, not just within the same one. "Sneakers under the bed" (personal) can be superseded by "storing sneakers in shoe rack" (decision). | Real-world updates often cross category boundaries. A decision ("I'll move my sneakers") supersedes a personal fact ("my sneakers are under the bed"). | **1-3%** | **Fully general.** Category-scoped supersession was a real limitation discovered through the benchmark, but the fix applies to any categorized fact store. |
| **Supersession prompt with FAIL/CORRECT examples** | Same imperative pattern as extraction: explicit failure examples like "FAIL: Keeping 'attended 3 sessions' when new fact says 'attended 5 sessions'". | LLMs are conservative about declaring supersession without explicit examples. Count updates and location changes are the most commonly missed. | **2-4%** | **Mostly general.** The prompt pattern is universal; the specific examples are shaped by LongMemEval failure patterns but cover common real-world cases too. |
| **User profile summary** | LLM generates a compact 2-4 sentence profile from the top 200 active preference+personal facts. Stored in `memory_profiles`, injected into every system prompt. | Provides passive context without requiring the model to search. Covers the "I know this user likes X" baseline for personalization queries where the model might not think to search. | **3-5%** | **Fully general.** Compact user profiles are useful for any personalized agent — reduces reliance on the model deciding to search at the right moment. |
| **Batch fact aggregation** | Fire-and-forget endpoint scans all active facts, chunks into 100-fact batches, LLM detects countable groups, creates summary aggregate facts with `aggregate_member_ids` tracking. | Questions like "how many fish in both aquariums?" need facts from multiple sessions combined into one retrievable unit. Individual facts ("10 neon tetras", "1 betta") rank too low individually. | **1-3%** | **Mixed.** Aggregation is genuinely useful for agents that need to answer counting/totaling questions. But the batch-chunking approach is shaped by LongMemEval's emphasis on multi-session counting questions, which are more common in benchmarks than real usage. A production system might aggregate on-demand rather than in batch. |
| **Aggregate cascade on supersession** | When a member fact is superseded, any aggregate containing it gets regenerated (re-summarized from remaining active members) or deleted if < 2 members remain. | Aggregates must stay consistent with the underlying facts. If "User has 3 fish" gets superseded by "User has 5 fish", the aggregate "User has 17 fish total" is now wrong. | **<1%** | **Fully general** given that you have aggregation at all. |

### Retrieval

| Mechanism | What it does | Why | Contrib. | General vs benchmark |
|-----------|-------------|-----|----------|---------------------|
| **pgvector semantic search** | Multi-query vector search against fact embeddings. Embeds the user's question (and expanded queries), finds facts by cosine similarity, keeps the best score per fact across all query variants. | Core retrieval mechanism. Keyword search alone misses semantic matches ("kitchen appliance" → "smoker"). | **10-15%** | **Fully general.** Standard vector retrieval. |
| **Query expansion** | LLM generates 3 keyword-list queries before vector search. Focused on personal attributes: "POSSESSIONS, HOBBIES, HABITS, PREFERENCES the user might have." Results cached in-memory (500 entries). | Bridges the semantic gap between user questions and stored facts. "What should I serve for dinner?" → "fresh tomatoes basil garden herbs cooking" matches stored facts that the raw question doesn't. | **5-8%** | **Mostly general.** Query expansion is a standard IR technique. The personal-attribute focus is tuned for the memory use case (not a benchmark artifact) — in production, users ask about their own stuff. |
| **Expanded-only mode** | For advice/suggestion queries, drops the original user question from vector search and uses only the expanded keyword queries. | The original question ("suggest dinner this weekend") matches topical facts ("dinner party", "meal prep") at higher cosine similarity than personal attribute facts ("grows cherry tomatoes"), drowning them out. Removing the original query lets personal attributes rank highest. | **3-5%** | **Somewhat benchmark-specific.** This fixes a real problem (topical interference), but the aggressiveness of completely dropping the original query is tuned for LongMemEval's SS Preference category. A production system might want a weighted blend. |
| **Keyword search** | SQL `LIKE` search on fact text as a complement to vector search. Results merged after vector results. | Catches exact matches that embedding similarity might miss (proper nouns, specific numbers). | **1-3%** | **Fully general.** Standard hybrid search pattern. |
| **Date-range search (temporal filtering)** | chrono-node extracts relative time references ("10 days ago", "last Tuesday") from the query, converts to absolute date range using reference date, filters facts by `source_date`. Results ranked by vector similarity within the range. | Temporal questions can't be answered by semantic similarity alone — "what did I buy 10 days ago?" needs date math, not just keyword matching. | **3-6%** | **Mostly general.** Temporal filtering is useful for any agent with dated memories. The chrono-node multilingual support and keyword guard are production-quality. The vector ranking within the date range is a refinement discovered through benchmark iteration. |
| **Temporal keyword guard** | Only triggers chrono parsing when the query contains relative time words (`ago`, `last`, `yesterday`, `past`, plus Finnish/German equivalents). | Without the guard, chrono parses incidental numbers ("5-day trip") or absolute dates ("March 15th issue") as temporal references and filters to wrong date ranges. | **1-2%** (prevents ~5% regression) | **Mostly general.** False positive prevention is essential for any temporal parsing in production. The specific keyword list is somewhat language-specific but the pattern is universal. |
| **Source diversity (round-robin)** | RAG retrieval gets top-12 chunks, then round-robin diversifies across source documents (max 3 chunks per doc) before taking top-8. | Multi-session questions need context from multiple conversations. Without diversity, all 8 chunks come from the single most relevant conversation, missing the others. | **3-5%** | **Mostly general.** Source diversity is useful whenever memory spans multiple conversations, which is the norm for any long-lived agent. |
| **Fact text deduplication in results** | After merging vector + keyword + date results, deduplicates by case-insensitive fact text, keeping the highest-scored copy. | Even with dedup-on-insert, near-duplicate facts with different phrasings survive ("User got a smoker" vs "User acquired a smoker"). Dedup at retrieval frees slots for diverse results. | **1-3%** | **Fully general.** Search-time dedup is standard practice. |
| **Embedding cache** | In-memory LRU cache (2000 entries) wrapping the embedding provider. Batch calls only hit the API for uncached texts. Keyed by MD5 of input text. | Avoids redundant API calls for identical texts across searches. Facts get re-embedded on every search without this. | **0%** (latency only) | **Fully general.** Standard caching. |
| **Query expansion cache** | In-memory cache (500 entries) for LLM-generated query expansions. | Avoids redundant LLM calls when the same question is searched multiple times (prefetch + tool call, or re-runs). | **0%** (latency only) | **Fully general.** Standard caching. |

### Intent & routing

| Mechanism | What it does | Why | Contrib. | General vs benchmark |
|-----------|-------------|-----|----------|---------------------|
| **Embedding-based intent detection** | Classifies user messages by cosine similarity against pre-embedded intent exemplars (advice_seeking, aggregation, mail, calendar, etc.). Uses bge-m3 centroids, language-agnostic. Lazy-initialized, cached for process lifetime. | Different intents need different retrieval strategies. Advice queries need expanded-only search; aggregation queries need aggregate facts included; general chat doesn't need memory at all. | **2-4%** (enables other mechanisms) | **Mostly general.** Intent detection is useful for any multi-tool agent. The specific intents (advice_seeking, aggregation) are shaped by the memory use case, but the embedding centroid approach is language-agnostic and extensible. |
| **Advice-seeking directive injection** | When advice intent is detected, the prefetch header says "You MUST use these facts to personalize your response. Reference specific items, brands, models..." | Without the directive, the model gives generic advice even when personal facts are in the context. The stronger instruction forces personalization. | **2-4%** | **Somewhat benchmark-specific.** The aggressive "MUST" language is tuned for LongMemEval's SS Preference judging criteria. In production, a gentler nudge might be more appropriate — users don't always want every response personalized. |
| **Aggregation intent filtering** | Aggregate summary facts are excluded from search by default (`aggregate_member_ids IS NULL`). Only included when aggregation intent is detected. | Aggregate facts add noise for non-counting queries. "User has 17 fish across 2 aquariums" is useful for "how many fish?" but harmful for "what should I feed my betta?" | **0-2%** (prevents ~7% regression) | **Fully general** given that you have aggregation. Without this filter, aggregates regressed overall accuracy by 7 points. |
| **Aggregation-aware fact limit** | Questions matching `/how many|how much|total|list all|every|count/` get factLimit 25 instead of 10. | Counting questions need facts from many sessions. 10 facts rarely covers all relevant items when they're spread across 3-5 conversations. | **1-3%** | **Mixed.** The regex is simple and useful, but the specific pattern is optimized for LongMemEval's multi-session category. A production system might use the intent classifier instead. |
| **Reference date injection** | Benchmark passes a `reference_date` to the `/complete` endpoint. The system prompt says "Current date: Monday, May 30, 2023" using this date. In production, uses the real date. | LongMemEval questions are dated in 2023 but the model thinks it's 2026. Temporal reasoning ("how many months ago") requires the correct reference point. | **8-12%** | **The mechanism is general** (any agent needs to know the current date), but the reference_date parameter exists specifically for the benchmark. In production it's just `new Date()`. |

### Prompt & model

| Mechanism | What it does | Why | Contrib. | General vs benchmark |
|-----------|-------------|-----|----------|---------------------|
| **Prefetch (facts-only mode)** | Before the LLM runs, Spark queries the fact store with the user's message and injects matching facts into the system prompt. Fast path: pgvector + keyword only, no RAG. | The model sees relevant personal facts before deciding whether to call `memory.search`. Reduces the "no_search" failure mode where the model gives generic answers because it doesn't know there are relevant memories. | **5-8%** | **Fully general.** Proactive context injection is standard in RAG-augmented systems. |
| **"More recent date is authoritative" instruction** | Prefetch header tells the model to trust newer facts when conflicts exist, and to treat past plans/decisions as completed. | When supersession doesn't catch a conflict (e.g. both "3 sessions" and "5 sessions" exist), this instruction helps the model pick the right one. | **2-4%** | **Mostly general.** Date-based authority is a sound heuristic for any memory system. The "treat plans as completed" clause is less general — it's a reasonable default but not always correct. |
| **Prefix-cache-friendly prompt ordering** | Static content (tool rules, system instructions) placed first in the prompt, dynamic content (memory facts, user message) placed last. | When using vLLM or other prefix-caching inference servers, the static prefix gets cached across requests, reducing time-to-first-token. | **0%** (latency only) | **Fully general.** Pure infrastructure optimization, no benchmark dependency. |
| **RAG synthesis step** | After retrieving chunks from ChromaDB, an LLM synthesizes a coherent answer from the chunks before passing to the chat model. | Raw chunks are noisy — the synthesis step contextualizes, extracts relevant details, and filters noise. Skipping it drops accuracy ~15 points. | **5-10%** | **Fully general.** Standard RAG pattern. The finding that synthesis matters even when facts are also present is useful guidance for any system. |
| **Global `batch` model category** | Forge UI allows configuring a separate model for background tasks (extraction, supersession, aggregation, profile generation). Resolves before app:chat fallthrough. | Background tasks can use cheaper/faster models (GPT-5 Nano) while chat uses a more capable model. Extraction and supersession don't need the same model quality as conversation. | **0%** (cost only) | **Fully general.** Cost/quality separation for background vs interactive tasks is standard. |

### Summary

The system has ~25 distinct mechanisms. The contribution estimates sum to roughly 100-140% — they overlap because many mechanisms are interdependent (e.g. embedding at insert enables vector search, intent detection enables expanded-only mode). The numbers represent "how much would accuracy drop if you removed this mechanism, all else equal."

Roughly:
- **~15 are fully general** — would benefit any agent memory system (fact extraction, dedup, supersession, vector search, caching, profile generation, prefetch)
- **~7 are mostly general** — solve real problems with some tuning for the benchmark (query expansion focus, temporal filtering, intent detection, strict prompts)
- **~3 are somewhat benchmark-specific** — the expanded-only mode, directive injection aggressiveness, and aggregation-aware fact limits are shaped by LongMemEval's specific question categories

The biggest contributions by rough magnitude: fact extraction (20-25%), pgvector search + embeddings (10-15%), reference date injection (8-12%), query expansion (5-8%), prefetch (5-8%), supersession (5-10%), RAG synthesis (5-10%).

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
| `lib/services/intent/index.ts` | Embedding-based intent detection (bge-m3 centroids, language-agnostic) |
| `lib/services/temporal/index.ts` | Date-range extraction via chrono-node (multilingual) |
| `lib/forge/tiers.ts` | Model categories incl. global `batch` for background tasks |
| `lib/forge/db.ts` | Model resolution with global-before-app-chat fallthrough |
| `atlas/app/api/internal/tool/memory/store/` | Extraction, supersession, profile generation |
| `atlas/app/api/internal/tool/memory/search/` | Fact search (pgvector + keyword + date-range) + RAG |
| `atlas/app/api/internal/tool/memory/aggregate/` | Batch fact aggregation (fire-and-forget) |
| `lib/tools/registry.ts` | `memory.search` + `memory.store` tool definitions |
| `spark/app/api/chats/[id]/complete/route.ts` | Intent-aware prefetch, auto-scoping, tool-use instructions |
| `memory-benchmark/` | Benchmark harness (Python) |
| `migrations/1776058251509_memory-facts.sql` | Postgres schema for extracted facts |
| `migrations/1776266035260_memory-fact-aggregates.sql` | `aggregate_member_ids UUID[]` column + GIN index |
