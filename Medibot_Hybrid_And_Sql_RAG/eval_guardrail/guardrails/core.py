"""
Shared guardrail infrastructure: the verdict contract, and structured logging.

This is the one file both guardrails/input_guard.py (Phase 1) and
guardrails/output_guard.py (Phase 2) build on - the verdict shape, the
generic refusal, the fail-closed guarantee, and the structured event log are
not specific to either layer, so they're built once here instead of being
duplicated (or drifting apart) between the two guards.
"""

from __future__ import annotations

import functools
import json
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Literal, Union

from pydantic import BaseModel, Field, ValidationError

# ============================================================================
# Verdict contract
# ============================================================================

# Every category either guard can produce, as a single closed list shared
# across both layers. "safe" and "error" are universal; the rest belong to
# one specific layer. Using Literal means a judge response with an
# unexpected category value fails Pydantic validation -> caught by
# fail_closed() below -> treated as blocked, rather than silently accepted
# as some new, unrecognised category.
GuardrailCategory = Literal[
    "safe",
    # input-guard categories (Phase 1)
    "prompt_injection",
    "role_override",
    "off_topic",
    # output-guard categories (Phase 2)
    "leaked_restricted_content",
    "pii_leak",
    "fabrication",
    # universal
    "error",
]


class GuardrailVerdict(BaseModel):
    """
    The result of a single guardrail check.

    This is the exact JSON shape the LLM judge is asked to produce (passed as
    `output_schema` to OpenEvals' create_llm_as_judge) - the verdict comes
    back already structured via the model's own structured-output/tool-call
    support, never inferred by us scanning its free-text reply.

    `reason` is INTERNAL ONLY. It is written to the structured event log for
    debugging and must never be returned to the end user - see
    GENERIC_REFUSAL below.
    """

    allowed: bool = Field(description="True only if the content is safe to pass through.")
    category: GuardrailCategory = Field(description="Which policy this verdict falls under.")
    reason: str = Field(description="Internal-only explanation. Never shown to the end user.")


# Shown to the user on ANY block, regardless of which layer or category
# fired. Input and output guards both import this exact string rather than
# each defining their own - if the wording ever differed between the two
# layers, an attacker could fingerprint which guardrail blocked them just by
# comparing the refusal text.
GENERIC_REFUSAL = (
    "I'm not able to help with that request. If you think this is a mistake, "
    "please rephrase your question or contact IT support."
)


# How this executes, in order:
#   1. fail_closed("error") runs ONCE, when a guard file is loaded (e.g. when
#      @fail_closed(category_on_error="error") appears above a function in
#      input_guard.py). It builds `blocked` and `decorator`, then returns
#      `decorator` and is done - it never runs again for that guard.
#   2. Python immediately calls decorator(fn), where fn is the real, undecorated
#      guardrail function (e.g. check_input_guardrail). This builds `wrapper`
#      and returns it. From this point on, the name check_input_guardrail
#      actually refers to `wrapper`, not to the 3 lines originally written -
#      the original function only still exists as the hidden variable `fn`
#      inside wrapper's closure.
#   3. EVERY TIME check_input_guardrail(...) is called afterward (step 1 and
#      2 do NOT repeat), it's really wrapper(...) that runs, and it's only
#      here that the try/except below actually executes.
def fail_closed(category_on_error: GuardrailCategory = "error"):
    """
    Decorator for a guardrail check function that returns a GuardrailVerdict
    (or a dict/object that should validate as one).

    Converts two failure modes into a blocked verdict instead of letting
    either one through:

      1. The function raises - LLM call errors, network failure, timeout.
      2. The function returns something that isn't a valid GuardrailVerdict -
         the judge's structured output came back incomplete or malformed.

    This makes "fail closed" a property of the code itself rather than
    something every new guardrail check has to remember to implement
    correctly by hand.
    """

    def blocked(reason: str) -> GuardrailVerdict:
        """The one verdict both failure modes below produce - defined once so
        it can't drift between them."""
        return GuardrailVerdict(allowed=False, category=category_on_error, reason=reason)

    # The extra nesting here (decorator wraps wrapper) is the standard Python
    # shape for a decorator that itself takes an argument - it's what makes
    # `@fail_closed(category_on_error="...")` work instead of just `@fail_closed`.
    def decorator(
        fn: Callable[..., Union[GuardrailVerdict, dict]]
    ) -> Callable[..., GuardrailVerdict]:
        @functools.wraps(fn)
        def wrapper(*args, **kwargs) -> GuardrailVerdict:
            # Failure mode 1: the check itself crashed.
            try:
                result = fn(*args, **kwargs)
            except Exception as exc:
                return blocked(f"Guardrail check raised {type(exc).__name__}: {exc}")

            # Happy path: already a valid verdict, nothing left to do.
            if isinstance(result, GuardrailVerdict):
                return result

            # Failure mode 2: the check returned *something*, but it doesn't
            # match the verdict shape (missing field, wrong type, etc).
            try:
                return GuardrailVerdict.model_validate(result)
            except ValidationError as exc:
                return blocked(f"Guardrail check returned an unparseable verdict: {exc}")

        return wrapper

    return decorator


# ============================================================================
# Structured, append-only event logging
# ============================================================================
#
# The spec requires every guardrail decision to be logged "as a structured
# event", not printed to console. This is what later phases read as evidence:
# Phase 3's adversarial-test writeups pull the real verdict JSON from here,
# and Phase 9's report aggregates block/allow counts from this same file.

LOG_DIR = Path(__file__).resolve().parents[1] / "logs_and_reports"
LOG_FILE = LOG_DIR / "guardrail_events.jsonl"

# One row per /chat REQUEST (latency + token usage), as opposed to
# guardrail_events.jsonl's one row per guardrail DECISION. Kept as a separate
# file rather than extra columns on the guardrail log because the two have
# different grains - a single request writes two guardrail rows but only one
# metrics row. `request_id` joins them.
METRICS_FILE = LOG_DIR / "request_metrics.jsonl"


def new_request_id() -> str:
    """One ID shared by the input and output guard logs for a single /chat call."""
    return uuid.uuid4().hex[:12]


def log_guardrail_event(
    layer: str,
    verdict: GuardrailVerdict,
    *,
    latency_ms: float,
    request_id: str | None = None,
) -> dict:
    """
    Append one guardrail decision to logs_and_reports/guardrail_events.jsonl.

    Returns the event dict that was written, so a caller (e.g. a test or the
    README adversarial-case writeup) can show the exact JSON produced without
    re-reading the file.
    """
    event = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "request_id": request_id or new_request_id(),
        "layer": layer,  # "input" or "output"
        "allowed": verdict.allowed,
        "category": verdict.category,
        "reason": verdict.reason,  # internal log only - never sent to the user
        "latency_ms": round(latency_ms, 1),
    }

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    with LOG_FILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(event) + "\n")

    return event


def _sum_token_usage(usage_by_model: dict | None) -> dict:
    """
    Flatten LangChain's per-model usage dict into whole-request totals.

    The callback reports usage keyed by model name, e.g.
    {"openai/gpt-oss-120b": {"input_tokens": 524, "output_tokens": 33, ...}},
    because a request could in principle hit more than one model. Summing
    gives the per-request number the spec asks for; the raw per-model
    breakdown is kept alongside it in the log line.
    """
    totals = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
    for per_model in (usage_by_model or {}).values():
        for key in totals:
            totals[key] += per_model.get(key) or 0
    return totals


def log_request_metrics(
    *,
    request_id: str,
    role: str,
    retrieval_type: str,
    total_latency_ms: float,
    usage_by_model: dict | None = None,
) -> dict:
    """
    Append one request's latency + token usage to logs_and_reports/request_metrics.jsonl.

    The spec requires these be "queryable" without a dashboard, so this is a
    flat JSONL line: token totals are top-level keys (greppable with jq)
    rather than nested, with the per-model breakdown kept underneath for
    cases where one request hits more than one model.

    Returns the event dict that was written.
    """
    event = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "request_id": request_id,
        "role": role,
        # "blocked" when either guardrail refused - which layer and why is in
        # guardrail_events.jsonl under this same request_id.
        "retrieval_type": retrieval_type,
        "total_latency_ms": round(total_latency_ms, 1),
        **_sum_token_usage(usage_by_model),
        "usage_by_model": usage_by_model or {},
    }

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    with METRICS_FILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(event) + "\n")

    return event


class Timer:
    """
    Tiny context manager so call sites measuring guardrail latency don't each
    hand-roll their own time.monotonic() bookkeeping.

    Usage:
        with Timer() as t:
            verdict = check_input_guardrail(question)
        log_guardrail_event("input", verdict, latency_ms=t.elapsed_ms)
    """

    def __enter__(self) -> "Timer":
        self._start = time.monotonic()
        self.elapsed_ms = 0.0
        return self

    def __exit__(self, *exc) -> None:
        self.elapsed_ms = (time.monotonic() - self._start) * 1000
