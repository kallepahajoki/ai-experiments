"""Failure mode definitions and judge prompt templates."""

from dataclasses import dataclass


@dataclass
class FailureMode:
    id: str
    name: str
    description: str
    severity: str  # critical, high, medium, low
    detection_difficulty: str  # easy, medium, hard
    judge_prompt: str


@dataclass
class JudgeVerdict:
    failure_mode: str
    detected: bool
    confidence: float  # 0.0 - 1.0
    evidence: str
    severity: str


FAILURE_MODES: dict[str, FailureMode] = {}


def _register(fm: FailureMode):
    FAILURE_MODES[fm.id] = fm


_register(FailureMode(
    id="fabricated_addition",
    name="Fabricated Addition",
    description="Model adds factual claims not present in the source.",
    severity="critical",
    detection_difficulty="hard",
    judge_prompt="""\
You are evaluating an LLM-generated summary for FABRICATED ADDITIONS — factual claims that appear in the output but have NO basis in the source document.

<source>
{source}
</source>

<output>
{output}
</output>

Instructions:
1. List every factual claim in the output.
2. For each claim, find the specific sentence in the source that supports it.
3. Any claim that cannot be grounded in the source is a fabricated addition.
4. Pay special attention to: country/origin attributions, cause/intent claims, identity claims, and any specific details not in the source.

Respond in JSON:
{{
  "claims": [
    {{"claim": "...", "grounded": true/false, "source_evidence": "exact quote or null"}}
  ],
  "fabricated_additions_found": true/false,
  "confidence": 0.0-1.0,
  "evidence": "summary of fabricated claims if any"
}}""",
))

_register(FailureMode(
    id="contradiction",
    name="Contradiction",
    description="Output directly conflicts with source — says X when source says Y.",
    severity="critical",
    detection_difficulty="easy",
    judge_prompt="""\
You are evaluating an LLM-generated summary for CONTRADICTIONS — statements that directly conflict with what the source document says.

<source>
{source}
</source>

<output>
{output}
</output>

Instructions:
1. Identify any statement in the output that says the opposite of, or is incompatible with, a statement in the source.
2. Quote both the source passage and the contradicting output passage.

Respond in JSON:
{{
  "contradictions": [
    {{"output_statement": "...", "source_statement": "...", "explanation": "..."}}
  ],
  "contradiction_found": true/false,
  "confidence": 0.0-1.0,
  "evidence": "summary if any"
}}""",
))

_register(FailureMode(
    id="entity_substitution",
    name="Entity Substitution",
    description="Correct fact type but wrong entity — names, organizations, locations swapped.",
    severity="high",
    detection_difficulty="easy",
    judge_prompt="""\
You are evaluating an LLM-generated summary for ENTITY SUBSTITUTIONS — cases where a named entity (person, organization, location) in the output is different from what the source says.

<source>
{source}
</source>

<output>
{output}
</output>

Instructions:
1. Extract all named entities (people, organizations, locations) from the output.
2. Verify each against the source. Flag any entity that appears in the output but not in the source, or that replaces a different entity from the source.
3. Minor variations in naming (e.g. "Defence Ministry" vs "Ministry of Defence") are NOT substitutions.

Respond in JSON:
{{
  "entities_in_output": ["..."],
  "substitutions": [
    {{"output_entity": "...", "source_entity": "...", "explanation": "..."}}
  ],
  "substitution_found": true/false,
  "confidence": 0.0-1.0,
  "evidence": "summary if any"
}}""",
))

_register(FailureMode(
    id="numerical_distortion",
    name="Numerical Distortion",
    description="Numbers changed, rounded incorrectly, or units swapped.",
    severity="high",
    detection_difficulty="easy",
    judge_prompt="""\
You are evaluating an LLM-generated summary for NUMERICAL DISTORTIONS — numbers, quantities, or units that differ from the source.

<source>
{source}
</source>

<output>
{output}
</output>

Instructions:
1. Extract all numbers, quantities, and units from both source and output.
2. Compare each pair. Flag any discrepancy, including rounding, unit changes, or magnitude errors.

Respond in JSON:
{{
  "numbers_in_source": ["..."],
  "numbers_in_output": ["..."],
  "distortions": [
    {{"output_value": "...", "source_value": "...", "explanation": "..."}}
  ],
  "distortion_found": true/false,
  "confidence": 0.0-1.0,
  "evidence": "summary if any"
}}""",
))

_register(FailureMode(
    id="temporal_drift",
    name="Temporal Drift",
    description="Dates, times, tenses, or sequence of events misrepresented.",
    severity="high",
    detection_difficulty="medium",
    judge_prompt="""\
You are evaluating an LLM-generated summary for TEMPORAL DRIFT — misrepresentation of dates, times, tenses, or event sequence.

<source>
{source}
</source>

<output>
{output}
</output>

Instructions:
1. Extract temporal expressions and event ordering from both texts.
2. Check for: wrong dates/times, tense changes (past→present, future→past), reordered events, training-data temporal bleed.

Respond in JSON:
{{
  "temporal_expressions_source": ["..."],
  "temporal_expressions_output": ["..."],
  "drifts": [
    {{"output_temporal": "...", "source_temporal": "...", "explanation": "..."}}
  ],
  "drift_found": true/false,
  "confidence": 0.0-1.0,
  "evidence": "summary if any"
}}""",
))

_register(FailureMode(
    id="hedging_removal",
    name="Hedging Removal (Certainty Inflation)",
    description="Source expresses uncertainty; output presents it as established fact.",
    severity="high",
    detection_difficulty="medium",
    judge_prompt="""\
You are evaluating an LLM-generated summary for HEDGING REMOVAL — cases where the source expresses uncertainty, suspicion, or conditionality, but the output presents the same information as established fact.

<source>
{source}
</source>

<output>
{output}
</output>

Instructions:
1. Identify all hedging/uncertainty language in the source: words like suspected, alleged, reportedly, may, might, could, appears to, according to current information, preliminary.
2. Check whether the output preserves this uncertainty or drops it.
3. Dropping hedging on critical claims (e.g. "suspected violation" → "violation") is more severe than on minor details.

Respond in JSON:
{{
  "hedging_in_source": [
    {{"expression": "...", "context": "..."}}
  ],
  "hedging_preserved_in_output": [
    {{"expression": "...", "preserved": true/false, "output_version": "..."}}
  ],
  "hedging_removal_found": true/false,
  "confidence": 0.0-1.0,
  "evidence": "summary if any"
}}""",
))

_register(FailureMode(
    id="hedging_addition",
    name="Hedging Addition (Certainty Deflation)",
    description="Source states something definitively; output softens it inappropriately.",
    severity="medium",
    detection_difficulty="medium",
    judge_prompt="""\
You are evaluating an LLM-generated summary for HEDGING ADDITION — cases where the source states something as fact, but the output adds inappropriate uncertainty.

<source>
{source}
</source>

<output>
{output}
</output>

Instructions:
1. Identify definitive statements in the source.
2. Check if the output adds hedging language (may, might, reportedly, allegedly) to these definitive statements.

Respond in JSON:
{{
  "inappropriate_hedging": [
    {{"source_statement": "...", "output_statement": "...", "added_hedging": "..."}}
  ],
  "hedging_addition_found": true/false,
  "confidence": 0.0-1.0,
  "evidence": "summary if any"
}}""",
))

_register(FailureMode(
    id="framing_shift",
    name="Framing Shift / Sentiment Injection",
    description="Factually accurate but adds editorial tone, bias, or implied causality not in source.",
    severity="medium",
    detection_difficulty="hard",
    judge_prompt="""\
You are evaluating an LLM-generated summary for FRAMING SHIFTS — cases where the output is factually accurate but introduces editorial tone, loaded language, bias, or implied causality not present in the source.

<source>
{source}
</source>

<output>
{output}
</output>

Instructions:
1. Compare the tone of source and output.
2. Flag any evaluative language, opinion words, dramatic framing, or causal implications not in the source.
3. Examples: "reckless", "alarming", "in a dramatic move", "this raises questions about".

Respond in JSON:
{{
  "framing_issues": [
    {{"output_phrase": "...", "issue": "..."}}
  ],
  "framing_shift_found": true/false,
  "confidence": 0.0-1.0,
  "evidence": "summary if any"
}}""",
))

_register(FailureMode(
    id="scope_creep",
    name="Scope Creep / Context Bleed",
    description="Model incorporates background knowledge not in the provided source.",
    severity="medium",
    detection_difficulty="hard",
    judge_prompt="""\
You are evaluating an LLM-generated summary for SCOPE CREEP — information in the output that comes from the model's training data or general knowledge rather than from the provided source document.

<source>
{source}
</source>

<output>
{output}
</output>

Instructions:
1. For every piece of information in the output, check if it can be traced to the source.
2. Flag any background context, historical references, explanations, or details that go beyond what the source provides.
3. This includes geopolitical context, prior incidents, explanations of terminology, etc.

Respond in JSON:
{{
  "scope_issues": [
    {{"output_content": "...", "explanation": "..."}}
  ],
  "scope_creep_found": true/false,
  "confidence": 0.0-1.0,
  "evidence": "summary if any"
}}""",
))

_register(FailureMode(
    id="omission",
    name="Omission of Critical Information",
    description="Key facts, caveats, or conditions in source are silently dropped.",
    severity="high",
    detection_difficulty="hard",
    judge_prompt="""\
You are evaluating an LLM-generated summary for OMISSION — important information present in the source that is missing from the output.

<source>
{source}
</source>

<output>
{output}
</output>

Instructions:
1. Identify the key facts, conditions, caveats, and qualifiers in the source.
2. Check which of these are present in the output and which are missing.
3. Focus on: negations, conditions (if/unless/only), safety/legal language, and information that changes the meaning if omitted.

Respond in JSON:
{{
  "key_facts_in_source": ["..."],
  "omitted_facts": [
    {{"fact": "...", "importance": "critical/high/medium/low"}}
  ],
  "critical_omission_found": true/false,
  "confidence": 0.0-1.0,
  "evidence": "summary if any"
}}""",
))

_register(FailureMode(
    id="composite_conflation",
    name="Composite Claim Conflation",
    description="Model merges two separate statements into one, creating a false combined claim.",
    severity="high",
    detection_difficulty="medium",
    judge_prompt="""\
You are evaluating an LLM-generated summary for COMPOSITE CONFLATION — cases where the output merges two separate facts from the source into a single statement, creating a false combined or causal claim.

<source>
{source}
</source>

<output>
{output}
</output>

Instructions:
1. Look for causal connectors (because, caused, led to, due to, resulting in) in the output.
2. Verify whether the stated relationship actually exists in the source.
3. Also check for merged statements where two independent facts are presented as related.

Respond in JSON:
{{
  "conflations": [
    {{"output_statement": "...", "source_facts": ["...", "..."], "explanation": "..."}}
  ],
  "conflation_found": true/false,
  "confidence": 0.0-1.0,
  "evidence": "summary if any"
}}""",
))

_register(FailureMode(
    id="instruction_leakage",
    name="Instruction Leakage / Prompt Injection Echo",
    description="Model echoes system prompt fragments or meta-instructions into output.",
    severity="medium",
    detection_difficulty="easy",
    judge_prompt="""\
You are evaluating an LLM-generated summary for INSTRUCTION LEAKAGE — cases where the output contains fragments of instructions, system prompts, or meta-commentary about the task rather than the actual summary.

<source>
{source}
</source>

<output>
{output}
</output>

Instructions:
1. Check if the output contains any instruction-like language ("I will now summarize", "As requested", "Here is the summary").
2. Check for system prompt fragments or role descriptions.
3. Minor task acknowledgments at the very start are low severity; substantial leakage is higher.

Respond in JSON:
{{
  "leakage_instances": [
    {{"text": "...", "type": "instruction_echo/system_prompt/meta_commentary"}}
  ],
  "leakage_found": true/false,
  "confidence": 0.0-1.0,
  "evidence": "summary if any"
}}""",
))


def get_judge_prompt(mode_id: str, source: str, output: str) -> str:
    fm = FAILURE_MODES[mode_id]
    return fm.judge_prompt.format(source=source, output=output)


def all_mode_ids() -> list[str]:
    return list(FAILURE_MODES.keys())
