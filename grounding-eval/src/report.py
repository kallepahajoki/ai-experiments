"""Aggregate evaluation results into comparison reports."""

from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from .evaluate import EvalResult, load_results
from .failure_modes import FAILURE_MODES


@dataclass
class ModelScore:
    model: str
    failure_mode: str
    total_runs: int
    detections: int
    failure_rate: float
    avg_confidence: float
    total_cost_usd: float


def aggregate_results(results: list[EvalResult]) -> list[ModelScore]:
    """Aggregate per-run results into per-model, per-failure-mode scores."""
    groups: dict[tuple[str, str], list[EvalResult]] = defaultdict(list)
    for r in results:
        groups[(r.subject_model, r.failure_mode)].append(r)

    scores = []
    for (model, mode), group in sorted(groups.items()):
        detections = sum(1 for r in group if r.verdict.detected)
        confidences = [r.verdict.confidence for r in group if r.verdict.detected]
        costs = [r.judge_cost_usd or 0.0 for r in group]

        scores.append(ModelScore(
            model=model,
            failure_mode=mode,
            total_runs=len(group),
            detections=detections,
            failure_rate=detections / len(group) if group else 0.0,
            avg_confidence=sum(confidences) / len(confidences) if confidences else 0.0,
            total_cost_usd=sum(costs),
        ))

    return scores


def format_failure_mode_legend() -> str:
    lines = []
    for mode_id, fm in FAILURE_MODES.items():
        lines.append(f"- **{fm.name}** [{fm.severity}]: {fm.description}")
    return "\n".join(lines)


def format_matrix(scores: list[ModelScore]) -> str:
    """Format scores as a models × failure_modes ASCII table."""
    models = sorted(set(s.model for s in scores))
    modes = list(FAILURE_MODES.keys())

    lookup = {(s.model, s.failure_mode): s for s in scores}

    # Header
    mode_short = {m: FAILURE_MODES[m].name[:16] for m in modes}
    col_width = 18
    header = f"{'Model':<40} " + " ".join(f"{mode_short[m]:>{col_width}}" for m in modes)
    separator = "-" * len(header)

    rows = [header, separator]
    for model in models:
        cells = []
        for mode in modes:
            s = lookup.get((model, mode))
            if s is None:
                cells.append(f"{'—':>{col_width}}")
            else:
                rate = f"{s.failure_rate:.0%}"
                det = f"{s.detections}/{s.total_runs}"
                cell = f"{rate} ({det})"
                cells.append(f"{cell:>{col_width}}")
        rows.append(f"{model:<40} " + " ".join(cells))

    return "\n".join(rows)


def format_summary(scores: list[ModelScore]) -> str:
    """Format a concise per-model summary."""
    models = sorted(set(s.model for s in scores))
    lines = []

    for model in models:
        model_scores = [s for s in scores if s.model == model]
        total_checks = sum(s.total_runs for s in model_scores)
        total_detections = sum(s.detections for s in model_scores)
        total_cost = sum(s.total_cost_usd for s in model_scores)
        overall_rate = total_detections / total_checks if total_checks else 0.0

        critical_modes = [s for s in model_scores if FAILURE_MODES[s.failure_mode].severity == "critical"]
        critical_detections = sum(s.detections for s in critical_modes)
        critical_total = sum(s.total_runs for s in critical_modes)
        critical_rate = critical_detections / critical_total if critical_total else 0.0

        lines.append(f"\n## {model}")
        lines.append(f"  Overall failure rate: {overall_rate:.1%} ({total_detections}/{total_checks})")
        lines.append(f"  Critical failure rate: {critical_rate:.1%} ({critical_detections}/{critical_total})")
        lines.append(f"  Total judge cost: ${total_cost:.4f}")

        # Top failure modes for this model
        detected = sorted(
            [s for s in model_scores if s.detections > 0],
            key=lambda s: s.failure_rate,
            reverse=True,
        )
        if detected:
            lines.append("  Detected failure modes:")
            for s in detected:
                lines.append(f"    - {FAILURE_MODES[s.failure_mode].name}: {s.failure_rate:.0%} ({s.detections}/{s.total_runs})")

    return "\n".join(lines)


def generate_report(results_dir: Path) -> str:
    """Load results and generate full report."""
    results = load_results(results_dir)
    scores = aggregate_results(results)

    report_parts = [
        "# Grounding Evaluation Report\n",
        "## Failure Modes\n",
        format_failure_mode_legend(),
        "\n## Model × Failure Mode Matrix\n",
        "```",
        format_matrix(scores),
        "```\n",
        "## Per-Model Summary",
        format_summary(scores),
    ]

    return "\n".join(report_parts)
