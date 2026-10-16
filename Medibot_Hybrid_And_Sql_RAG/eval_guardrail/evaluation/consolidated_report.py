"""
Evaluation report (spec component 06) - consolidates guardrail block/allow
counts, RAGAS metric scores, LLM-as-a-judge scores and heuristic pass/fail
counts into one Markdown report with a clear overall pass/fail verdict.

Deliberately lightweight: reads the JSON/CSV files ragas_eval.py's pipeline
already writes to logs_and_reports/, plus the guardrail event log, rather
than importing ragas_eval.py itself - that module's top-level imports pull in
ragas/langchain, which this report doesn't need and shouldn't pay the cost
of just to read four files. This also means the report can be regenerated
standalone, with no live LLM calls and no API quota spent:

cd /home/himesh/codebasics_cohort/AI_Projects/Medibot_Hybrid_And_Sql_RAG
python -m eval_guardrail.evaluation.consolidated_report
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

_EVAL_GUARDRAIL_DIR = Path(__file__).resolve().parent.parent
_REPORTS_DIR = _EVAL_GUARDRAIL_DIR / "logs_and_reports"
_GUARDRAIL_LOG = _REPORTS_DIR / "guardrail_events.jsonl"
OUT_PATH = _REPORTS_DIR / "evaluation_report.md"

# Pass thresholds - the spec requires "a defined pass threshold per metric."
# Faithfulness/relevancy set higher than precision/recall because a wrong or
# unsupported claim (what those two catch) is worse than imperfect ranking of
# otherwise-relevant chunks.
RAGAS_THRESHOLDS = {
    "faithfulness": 0.70,
    "answer_relevancy": 0.70,
    "context_precision": 0.60,
    "context_recall": 0.60,
    "answer_correctness": 0.60,
}
JUDGE_MEAN_THRESHOLD = 3.5  # out of 5

# These two are safety-critical - a failure means an RBAC leak or a citation
# from a collection the role can't access, not a quality nuance - so they
# must pass 100% of the time. The other two tolerate occasional misses.
HEURISTIC_STRICT_CHECKS = {"restricted_role_refused", "citation_access"}
HEURISTIC_LOOSE_THRESHOLD = 0.90


def _load_json(path: Path) -> dict:
    """
    Read one report JSON file, returning {} if it doesn't exist yet - lets
    the report render a clear "not yet run" section instead of crashing when
    a pipeline step hasn't produced its file.
    """
    if not path.exists():
        return {}
    return json.loads(path.read_text())


def summarize_guardrail_log(log_path: Path = _GUARDRAIL_LOG) -> dict:
    """
    Aggregate every guardrail decision logged in guardrail_events.jsonl into
    allow/block counts per layer, plus a breakdown by category.

    Reads the whole append-only log (not scoped to one eval run) - this
    intentionally reports cumulative guardrail behaviour across every live
    request and test run ever made, input-layer and output-layer combined
    history, not just the most recent capture_responses() call.

    Args:
        log_path: path to guardrail_events.jsonl

    Returns:
        dict keyed by layer ("input"/"output"), each value
        {"allowed": int, "blocked": int, "by_category": {category: count}}

    Example:
        summarize_guardrail_log()
        # Returns: {
        #   "input":  {"allowed": 150, "blocked": 12,
        #              "by_category": {"safe": 150, "prompt_injection": 7,
        #                              "role_override": 5}},
        #   "output": {"allowed": 155, "blocked": 7,
        #              "by_category": {"safe": 155, "fabrication": 6,
        #                              "pii_leak": 1}},
        # }
    """
    counts: dict = {}
    if not log_path.exists():
        return counts

    for line in log_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        event = json.loads(line)
        layer = event.get("layer", "unknown")
        bucket = counts.setdefault(layer, {"allowed": 0, "blocked": 0, "by_category": {}})
        if event.get("allowed"):
            bucket["allowed"] += 1
        else:
            bucket["blocked"] += 1
        category = event.get("category", "unknown")
        bucket["by_category"][category] = bucket["by_category"].get(category, 0) + 1

    return counts


def evaluate_ragas(ragas_summary: dict) -> dict:
    """
    Apply RAGAS_THRESHOLDS to ragas_summary.json's aggregate section.

    Args:
        ragas_summary: ragas_summary.json's parsed contents (or {} if the
                       file doesn't exist yet)

    Returns:
        dict keyed by metric name, each value {"mean", "scored", "total",
        "threshold", "passed"} - "passed" is False (not None) when the
        metric never scored anything, so a missing run never silently counts
        as passing

    Example:
        evaluate_ragas(ragas_summary)
        # Returns: {"faithfulness": {"mean": 0.91, "scored": 20, "total": 24,
        #                            "threshold": 0.7, "passed": True}, ...}
    """
    aggregate = ragas_summary.get("aggregate", {})
    results = {}
    for metric, threshold in RAGAS_THRESHOLDS.items():
        stats = aggregate.get(metric, {})
        mean = stats.get("mean")
        results[metric] = {
            "mean": mean,
            "scored": stats.get("scored", 0),
            "total": stats.get("total", 0),
            "threshold": threshold,
            "passed": mean is not None and mean >= threshold,
        }
    return results


def evaluate_judge(judge_summary: dict) -> dict:
    """
    Apply JUDGE_MEAN_THRESHOLD to judge_summary.json's mean score.

    Args:
        judge_summary: judge_summary.json's parsed contents (or {} if the
                       file doesn't exist yet)

    Returns:
        dict with keys: mean, scored, total, threshold, passed

    Example:
        evaluate_judge(judge_summary)
        # Returns: {"mean": 4.21, "scored": 24, "total": 24,
        #           "threshold": 3.5, "passed": True}
    """
    mean = judge_summary.get("mean")
    return {
        "mean": mean,
        "scored": judge_summary.get("scored", 0),
        "total": judge_summary.get("total", 0),
        "threshold": JUDGE_MEAN_THRESHOLD,
        "passed": mean is not None and mean >= JUDGE_MEAN_THRESHOLD,
    }


def evaluate_heuristics(heuristics_summary: dict) -> dict:
    """
    Apply per-check thresholds to heuristics_summary.json's "checks" section.

    Args:
        heuristics_summary: heuristics_summary.json's parsed contents (or {}
                            if the file doesn't exist yet)

    Returns:
        dict keyed by check name, each value {"passed", "total", "rate",
        "threshold", "passed_threshold"} - "passed" here is the raw count
        from the summary file; "passed_threshold" is the pass/fail verdict

    Example:
        evaluate_heuristics(heuristics_summary)
        # Returns: {"restricted_role_refused": {"passed": 27, "total": 27,
        #            "rate": 1.0, "threshold": 1.0, "passed_threshold": True},
        #           ...}
    """
    checks = heuristics_summary.get("checks", {})
    results = {}
    for check_name, stats in checks.items():
        total = stats.get("total", 0)
        passed = stats.get("passed", 0)
        rate = (passed / total) if total else 0.0
        threshold = 1.0 if check_name in HEURISTIC_STRICT_CHECKS else HEURISTIC_LOOSE_THRESHOLD
        results[check_name] = {
            "passed": passed,
            "total": total,
            "rate": round(rate, 4),
            "threshold": threshold,
            "passed_threshold": rate >= threshold,
        }
    return results


def build_verdict(ragas_eval: dict, judge_eval: dict, heuristics_eval: dict) -> dict:
    """
    Roll every per-metric pass/fail into one overall PASS/FAIL verdict,
    naming exactly which checks failed.

    Guardrail counts are reported but not part of this verdict - they're a
    cumulative, all-time log (see summarize_guardrail_log), not a per-run
    pass/fail signal the way the other three are.

    Args:
        ragas_eval: evaluate_ragas()'s output
        judge_eval: evaluate_judge()'s output
        heuristics_eval: evaluate_heuristics()'s output

    Returns:
        dict with keys: overall ("PASS"/"FAIL"), failed_checks (list of
        dotted names, e.g. "ragas.faithfulness")

    Example:
        build_verdict(ragas_eval, judge_eval, heuristics_eval)
        # Returns: {"overall": "FAIL",
        #           "failed_checks": ["ragas.answer_correctness",
        #                             "heuristic.has_citation"]}
    """
    failed_checks = []

    for metric, result in ragas_eval.items():
        if not result["passed"]:
            failed_checks.append(f"ragas.{metric}")

    if not judge_eval["passed"]:
        failed_checks.append("judge.mean_score")

    for check_name, result in heuristics_eval.items():
        if not result["passed_threshold"]:
            failed_checks.append(f"heuristic.{check_name}")

    return {"overall": "PASS" if not failed_checks else "FAIL", "failed_checks": failed_checks}


def _demo_heuristic_failure_example() -> dict:
    """
    Reproduce the known-bad empty-answer fixture inline (rather than
    importing ragas_eval.py's demo_heuristic_failure, which would pull in
    that module's heavy ragas/langchain imports) - gives the report a
    guaranteed, reproducible "heuristic check correctly failing a bad
    response" example per the spec's component 06 requirement, independent
    of whatever today's live dataset happens to contain.

    Returns:
        dict with keys: id, check, passed, reason - passed is always False
    """
    answer = "   "
    passed = bool(answer and answer.strip())
    return {
        "id": "DEMO-BAD-01",
        "check": "non_empty_answer",
        "passed": passed,
        "reason": "answer is non-empty" if passed else "answer field is empty or whitespace-only",
    }


def _pick_guardrail_block_examples(log_path: Path = _GUARDRAIL_LOG, limit: int = 3) -> list[dict]:
    """
    Pull up to `limit` distinct-category blocked events from the guardrail
    log, most recent first, for the spec's required "example of a guardrail
    correctly blocking an unsafe request."

    Excludes category="error" - those are fail_closed() catching a crashed
    or malformed judge call (e.g. a rate limit), not the guardrail actually
    recognising unsafe content, so they'd misrepresent what this example is
    meant to demonstrate.

    Args:
        log_path: path to guardrail_events.jsonl
        limit: max examples to return

    Returns:
        list of event dicts (as logged by log_guardrail_event), each a
        distinct (layer, category) combination, most recent occurrence first
    """
    if not log_path.exists():
        return []

    lines = [line for line in log_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    seen_combos = set()
    examples = []
    for line in reversed(lines):
        event = json.loads(line)
        if event.get("allowed") or event.get("category") == "error":
            continue
        combo = (event.get("layer"), event.get("category"))
        if combo in seen_combos:
            continue
        seen_combos.add(combo)
        examples.append(event)
        if len(examples) >= limit:
            break
    return examples


def _load_csv(path: Path) -> list[dict]:
    """
    Read a report CSV into a list of row dicts, [] if the file doesn't exist
    yet. Plain csv.DictReader rather than pandas - this module stays free of
    any dependency heavier than the standard library (see module docstring).
    """
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _fmt_score(value: str | None) -> str:
    """ragas_scores.csv writes NaN cells as empty strings - render those as
    N/A rather than a blank table cell, which reads as a rendering bug."""
    try:
        return f"{float(value):.4f}"
    except (TypeError, ValueError):
        return "N/A"


def _cell(text: str | None) -> str:
    """Escape a free-text value for safe use inside a Markdown table cell -
    a literal `|` or newline would otherwise break the row into pieces."""
    return (text or "").replace("|", "\\|").replace("\n", " ").strip()


def _build_question_answer_lookup(ragas_rows: list[dict]) -> dict[str, dict[str, str]]:
    """
    id -> {"question", "answer"}, built from ragas_scores.csv's
    user_input/response columns. ragas_scores.csv is built from every
    captured row regardless of category or guardrail block, so it's the one
    report that's always complete enough to cross-reference question/answer
    text into the heuristics table, which doesn't carry that text itself.
    """
    return {
        row["id"]: {"question": row.get("user_input", ""), "answer": row.get("response", "")}
        for row in ragas_rows
        if row.get("id")
    }


def _render_ragas_question_table(rows: list[dict]) -> list[str]:
    """One row per captured question, with its answer, all 5 RAGAS metrics
    as columns."""
    if not rows:
        return ["_No per-question RAGAS scores available yet._", ""]
    lines = [
        "| Question | Answer | Category | Collection | Faithfulness | Answer Relevancy | Context Precision | Context Recall | Answer Correctness |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for row in rows:
        lines.append(
            f"| {_cell(row.get('user_input'))} | {_cell(row.get('response'))} | "
            f"{row.get('category', '')} | {row.get('collection', '')} | "
            f"{_fmt_score(row.get('faithfulness'))} | {_fmt_score(row.get('answer_relevancy'))} | "
            f"{_fmt_score(row.get('context_precision'))} | {_fmt_score(row.get('context_recall'))} | "
            f"{_fmt_score(row.get('answer_correctness'))} |"
        )
    lines.append("")
    return lines


def _render_judge_question_table(rows: list[dict]) -> list[str]:
    """One row per captured question, with its answer, grade and the
    judge's justification."""
    if not rows:
        return ["_No per-question judge scores available yet._", ""]
    lines = [
        "| Question | Answer | Category | Collection | Role | Score | Justification |",
        "|---|---|---|---|---|---|---|",
    ]
    for row in rows:
        lines.append(
            f"| {_cell(row.get('question'))} | {_cell(row.get('answer'))} | "
            f"{row.get('category', '')} | {row.get('collection', '')} | {row.get('role', '')} | "
            f"{row.get('answer_quality_score', '')} | {_cell(row.get('justification'))} |"
        )
    lines.append("")
    return lines


def _render_heuristics_question_table(rows: list[dict], qa_lookup: dict[str, dict[str, str]]) -> list[str]:
    """
    One row per captured question, with its answer, one column per
    heuristic check - heuristics_results.csv is flat (one row per
    question x check), so this pivots it into the more readable
    question-wise shape. Question/answer text comes from qa_lookup
    (built from ragas_scores.csv) since heuristics_results.csv only
    carries the question id, not its text.
    """
    if not rows:
        return ["_No per-question heuristic results available yet._", ""]

    check_names: list[str] = []
    by_question: dict[str, dict[str, bool]] = {}
    for row in rows:
        check = row["check"]
        if check not in check_names:
            check_names.append(check)
        passed = row["passed"] in ("True", "true", "1")
        by_question.setdefault(row["id"], {})[check] = passed

    header = ["Question", "Answer"] + check_names
    lines = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    for question_id, checks in by_question.items():
        qa = qa_lookup.get(question_id, {})
        cells = [_cell(qa.get("question") or question_id), _cell(qa.get("answer"))]
        cells += ["✅" if checks.get(c) else "❌" for c in check_names]
        lines.append("| " + " | ".join(cells) + " |")
    lines.append("")
    return lines


def render_report(
    ragas_eval: dict,
    judge_eval: dict,
    heuristics_eval: dict,
    guardrail_counts: dict,
    verdict: dict,
) -> str:
    """
    Render the consolidated Markdown report and write it to
    logs_and_reports/evaluation_report.md.

    Args:
        ragas_eval: evaluate_ragas()'s output
        judge_eval: evaluate_judge()'s output
        heuristics_eval: evaluate_heuristics()'s output
        guardrail_counts: summarize_guardrail_log()'s output
        verdict: build_verdict()'s output

    Returns:
        the rendered Markdown text (also written to
        logs_and_reports/evaluation_report.md)
    """
    # Several blank lines between major sections, rather than just one "" -
    # a single blank line disappears once GitHub/VS Code render the
    # Markdown, so the sections run together visually.
    def section_break() -> list[str]:
        return [""] * 6

    ragas_rows = _load_csv(_REPORTS_DIR / "ragas_scores.csv")
    qa_lookup = _build_question_answer_lookup(ragas_rows)

    lines = []
    lines.append("# MediBot Evaluation & Guardrail Report")
    lines.append("")
    banner = "✅ PASS" if verdict["overall"] == "PASS" else "❌ FAIL"
    lines.append(f"## Overall verdict: {banner}")
    lines.append("")
    if verdict["failed_checks"]:
        lines.append("Failed checks:")
        for check in verdict["failed_checks"]:
            lines.append(f"- `{check}`")
    else:
        lines.append("All thresholds met.")

    lines.extend(section_break())
    lines.append("## Guardrail block/allow counts (cumulative, all logged requests)")
    lines.append("")
    if guardrail_counts:
        lines.append("| Layer | Allowed | Blocked | By category |")
        lines.append("|---|---|---|---|")
        for layer, stats in guardrail_counts.items():
            by_cat = ", ".join(f"{cat}={n}" for cat, n in sorted(stats["by_category"].items()))
            lines.append(f"| {layer} | {stats['allowed']} | {stats['blocked']} | {by_cat} |")
    else:
        lines.append("_No guardrail events logged yet._")

    lines.extend(section_break())
    lines.append("## RAGAS metrics")
    lines.append("")
    lines.extend(_render_ragas_question_table(ragas_rows))
    lines.append("**Aggregate**")
    lines.append("")
    lines.append("| Metric | Mean | Threshold | Scored/Total | Result |")
    lines.append("|---|---|---|---|---|")
    for metric, result in ragas_eval.items():
        mean_str = f"{result['mean']:.4f}" if result["mean"] is not None else "N/A"
        mark = "✅" if result["passed"] else "❌"
        lines.append(
            f"| {metric} | {mean_str} | {result['threshold']} | "
            f"{result['scored']}/{result['total']} | {mark} |"
        )

    lines.extend(section_break())
    lines.append("## LLM-as-a-Judge (answer quality, 1-5)")
    lines.append("")
    lines.extend(_render_judge_question_table(_load_csv(_REPORTS_DIR / "judge_scores.csv")))
    lines.append("**Aggregate**")
    lines.append("")
    mean_str = f"{judge_eval['mean']:.2f}" if judge_eval["mean"] is not None else "N/A"
    mark = "✅" if judge_eval["passed"] else "❌"
    lines.append(
        f"Mean score: **{mean_str}** (threshold {judge_eval['threshold']}, "
        f"{judge_eval['scored']}/{judge_eval['total']} scored) {mark}"
    )

    lines.extend(section_break())
    lines.append("## Heuristic checks")
    lines.append("")
    lines.extend(_render_heuristics_question_table(_load_csv(_REPORTS_DIR / "heuristics_results.csv"), qa_lookup))
    lines.append("**Aggregate**")
    lines.append("")
    lines.append("| Check | Passed/Total | Rate | Threshold | Result |")
    lines.append("|---|---|---|---|---|")
    for check_name, result in heuristics_eval.items():
        mark = "✅" if result["passed_threshold"] else "❌"
        lines.append(
            f"| {check_name} | {result['passed']}/{result['total']} | "
            f"{result['rate']:.1%} | {result['threshold']:.0%} | {mark} |"
        )

    lines.extend(section_break())
    lines.append("## Required examples")
    lines.append("")
    lines.append("### Heuristic check correctly failing a bad response")
    lines.append("")
    lines.append("```json")
    lines.append(json.dumps(_demo_heuristic_failure_example(), indent=2))
    lines.append("```")
    lines.append("")

    lines.append("### Guardrail correctly blocking an unsafe request")
    lines.append("")
    block_examples = _pick_guardrail_block_examples()
    if block_examples:
        for example in block_examples:
            lines.append("```json")
            lines.append(json.dumps(example, indent=2))
            lines.append("```")
    else:
        lines.append("_No blocked guardrail events found in the log yet._")
    lines.append("")

    report_text = "\n".join(lines)
    _REPORTS_DIR.mkdir(exist_ok=True)
    OUT_PATH.write_text(report_text, encoding="utf-8")
    return report_text


def main() -> None:
    """
    Read every report file ragas_eval.py's pipeline has already written
    (ragas_summary.json, judge_summary.json, heuristics_summary.json) plus
    the guardrail event log, apply pass/fail thresholds to each, and render
    the consolidated report.

    Args:
        none

    Returns:
        None - writes logs_and_reports/evaluation_report.md and prints its
        path (not the report's contents - it's meant to be read as
        rendered Markdown, not scrolled through in a terminal)

    Example:
        python -m eval_guardrail.evaluation.consolidated_report
        # Written to: .../logs_and_reports/evaluation_report.md
    """
    ragas_summary = _load_json(_REPORTS_DIR / "ragas_summary.json")
    judge_summary = _load_json(_REPORTS_DIR / "judge_summary.json")
    heuristics_summary = _load_json(_REPORTS_DIR / "heuristics_summary.json")

    ragas_eval = evaluate_ragas(ragas_summary)
    judge_eval = evaluate_judge(judge_summary)
    heuristics_eval = evaluate_heuristics(heuristics_summary)
    guardrail_counts = summarize_guardrail_log()

    verdict = build_verdict(ragas_eval, judge_eval, heuristics_eval)
    render_report(ragas_eval, judge_eval, heuristics_eval, guardrail_counts, verdict)

    print(f"Written to: {OUT_PATH}")


if __name__ == "__main__":
    sys.exit(main())
