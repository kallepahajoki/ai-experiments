# grounding-eval — Source-Grounded LLM Output Evaluation

## Motivation

When LLMs summarize or report on source documents, they introduce errors ranging from subtle hedging removal to outright fabrication. These errors are especially dangerous in journalism and public communication where they can spread as fact.

**Driving case:** On 2026-03-29, the Finnish Ministry of Defence published a press release about a suspected drone territorial violation in Southeast Finland. The source contained **zero country attribution**. Helsingin Sanomat's breaking news attributed the drones to Russia — a hallucinated fabrication that demonstrates the real-world stakes of this failure mode.

## What This Experiment Does

1. **Generates LLM outputs** from source documents using various models via OpenRouter
2. **Evaluates outputs** for 12 failure modes (see `llm_eval_failure_modes.md`) using a judge model
3. **Benchmarks models** against each other on faithfulness to source material
4. **Produces structured reports** showing which models introduce which types of errors

## Architecture

```
eval_data/              # Annotated source documents + expected failure modes
src/
  openrouter.py         # OpenRouter API client
  generate.py           # Run subject models to produce outputs from source docs
  evaluate.py           # Run judge model to score outputs against sources
  failure_modes.py      # Failure mode definitions and detection prompts
  report.py             # Aggregate results into comparison tables
  cli.py                # CLI entry point
```

## Implementation Plan

### Phase 1: Core Infrastructure

#### 1.1 OpenRouter Client (`src/openrouter.py`)
- Thin wrapper around OpenRouter API (chat completions endpoint)
- Model selection by ID, temperature control, retry with backoff
- Cost tracking per request (OpenRouter returns token counts + pricing)
- Support for streaming (optional, not needed for eval)

#### 1.2 Failure Mode Registry (`src/failure_modes.py`)
- Dataclass for each failure mode: name, description, severity, detection prompt template
- Load from the 12 modes defined in `llm_eval_failure_modes.md`
- Each mode has a judge prompt that takes (source, output) and returns structured assessment
- Output schema: `{detected: bool, confidence: float, evidence: str, severity: str}`

### Phase 2: Generation & Evaluation Pipeline

#### 2.1 Subject Model Generation (`src/generate.py`)
- Takes an eval case (source doc + task prompt) and a list of subject model IDs
- Calls each model N times (configurable, default 3) to capture variance
- Stores outputs with metadata: model, timestamp, tokens, cost
- Output format: JSON lines per eval case

#### 2.2 Judge Evaluation (`src/evaluate.py`)
- Takes (source, model_output, failure_mode) triples
- Runs judge model (strong model — e.g. `anthropic/claude-sonnet-4` via OpenRouter) on each
- Two-stage approach from the doc:
  - **Stage 1 — Structured extraction:** Extract claims, entities, numbers, temporal expressions, hedging markers from both source and output. Compare programmatically.
  - **Stage 2 — LLM judge:** For hard-to-automate modes (fabrication, scope creep, framing shift), use judge model with targeted prompts.
- Returns per-output, per-failure-mode scores
- Self-consistency check: run judge multiple times, flag disagreements

### Phase 3: Eval Data

#### 3.1 Eval Case Format
Already implemented in `eval_data/defmin_drone_incident.json`:
- Source document (original language + English)
- Task prompt for subject models
- Expected failure modes with severity
- Pre-annotated key claims, absent claims to watch for, hedging language

#### 3.2 Expand Eval Dataset
- More Finnish news/government sources (good domain for testing — Finnish is lower-resource, more hallucination-prone)
- Vary domains: government press releases, financial reports, medical guidelines
- Include "clean" cases where faithful summarization is straightforward (to avoid bias toward failure detection)
- Synthetic cases: manually construct source+output pairs with known injected errors for calibrating the judge

### Phase 4: Benchmarking & Reporting

#### 4.1 Model Comparison (`src/report.py`)
- Matrix: models × failure modes, cells = failure rate
- Aggregate across eval cases
- Statistical significance tests (multiple runs per model)
- Cost-effectiveness: accuracy per dollar

#### 4.2 Judge Calibration
- Run judge on synthetic cases with known ground truth
- Measure judge precision/recall per failure mode
- Compare different judge models (is Opus better than Sonnet as judge? Is a cheaper model sufficient for easy modes?)

### Phase 5: CLI & Automation (`src/cli.py`)

```
# Generate outputs from all subject models for all eval cases
python -m grounding_eval generate --models meta-llama/llama-3.1-8b,google/gemini-flash-2.0 --cases eval_data/

# Evaluate all generated outputs
python -m grounding_eval evaluate --judge anthropic/claude-sonnet-4

# Generate comparison report
python -m grounding_eval report --output results/
```

## Models to Benchmark (via OpenRouter)

**Subject models (varying quality tiers):**
- `anthropic/claude-sonnet-4` — strong baseline
- `google/gemini-flash-2.0` — fast/cheap tier
- `meta-llama/llama-3.1-8b-instruct` — small open model
- `meta-llama/llama-3.1-70b-instruct` — large open model
- `mistralai/mistral-small` — European model, potentially better on Finnish
- `openai/gpt-4o-mini` — budget tier

**Judge model:**
- `anthropic/claude-sonnet-4` (default) — good balance of quality and cost for judging
- Option to use `anthropic/claude-opus-4` for hardest failure modes

## Key Design Decisions

1. **OpenRouter for everything** — single API, unified billing, easy model comparison
2. **Judge-as-evaluator pattern** — strong model evaluates weaker models, with structured extraction as pre-filter
3. **Per-failure-mode scoring** — not just "good/bad" but which specific error types each model is prone to
4. **Finnish-language sources** — deliberately harder than English, exposes more model weaknesses, and the motivating use case is Finnish media
5. **Annotated ground truth** — eval cases include pre-annotated claims and hedging so we can validate judge accuracy
