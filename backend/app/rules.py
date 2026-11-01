"""Deterministic eligibility rule engine.

No eval(), no LLM judgement here. Each rule is a (field, op, value) triple compared against
the user's profile. If a value is missing or a rule cannot be checked automatically, the
result is 'check' (flagged), never a silent approval.
"""
from __future__ import annotations

from typing import Any, Optional

from .models import MatchResult, Profile, Rule, RuleResult, Scheme
from .options import FIELD_LABELS

OP_WORDS = {
    "eq": "is",
    "in": "is one of",
    "not_in": "is not one of",
    "lte": "at most",
    "gte": "at least",
    "lt": "below",
    "gt": "above",
    "between": "between",
}

OPTIONAL_FIELDS = ["age", "gender", "business_type"]


def describe_rule(field: str, op: str, value: Any) -> str:
    label = FIELD_LABELS.get(field, field)
    if op == "between" and isinstance(value, (list, tuple)) and len(value) == 2:
        return f"{label} between {value[0]} and {value[1]}"
    if isinstance(value, (list, tuple)):
        value = ", ".join(str(v).replace("_", " ") for v in value)
    else:
        value = str(value).replace("_", " ")
    return f"{label} {OP_WORDS.get(op, op)} {value}"


def _norm(v: Any) -> Any:
    return v.strip().lower().replace(" ", "_") if isinstance(v, str) else v


def _norm_state(v: Any) -> Any:
    return v.strip().lower() if isinstance(v, str) else v


def _holds(rule: Rule, profile: dict) -> Optional[bool]:
    """True if the condition holds for this profile, False if not, None if undecidable."""
    if rule.field == "other" or rule.op == "other":
        return None
    actual = profile.get(rule.field)
    if actual is None:
        return None
    norm = _norm_state if rule.field == "state" else _norm
    actual = norm(actual)
    value = rule.value
    try:
        if rule.op in ("eq", "in", "not_in"):
            options = value if isinstance(value, (list, tuple)) else [value]
            options = [norm(o) for o in options]
            if any(o in ("all", "any", "all india", "all_india") for o in options):
                return rule.op != "not_in"
            hit = actual in options
            return (not hit) if rule.op == "not_in" else hit
        if rule.op == "between":
            lo, hi = float(value[0]), float(value[1])
            return lo <= float(actual) <= hi
        number, limit = float(actual), float(value)
        return {
            "lte": number <= limit,
            "gte": number >= limit,
            "lt": number < limit,
            "gt": number > limit,
        }[rule.op]
    except (TypeError, ValueError, KeyError, IndexError):
        return None


def _result(rule: Rule, kind: str, profile: dict) -> RuleResult:
    holds = _holds(rule, profile)
    text = rule.text or describe_rule(rule.field, rule.op, rule.value)
    if holds is None:
        if rule.field == "other" or rule.op == "other":
            reason = "This condition cannot be checked automatically. Please confirm it yourself."
        else:
            reason = "Needs an answer you did not provide."
        return RuleResult(rule_id=rule.id, kind=kind, text=text, status="check", reason=reason)
    if kind == "eligibility":
        status = "pass" if holds else "fail"
    else:  # exclusion: the condition holding is bad news
        status = "fail" if holds else "pass"
    reason = ""
    if status == "fail":
        reason = (
            "This requirement is not met." if kind == "eligibility" else "This exclusion applies to you."
        )
    return RuleResult(rule_id=rule.id, kind=kind, text=text, status=status, reason=reason)


def evaluate(scheme: Scheme, profile: Profile) -> MatchResult:
    data = profile.model_dump()
    results = [_result(r, "eligibility", data) for r in scheme.eligibility]
    results += [_result(r, "exclusion", data) for r in scheme.exclusions]

    if any(r.status == "fail" for r in results):
        verdict = "ineligible"
    elif not results or any(r.status == "check" for r in results):
        verdict = "conditional"
    else:
        verdict = "eligible"

    missing = [f for f in OPTIONAL_FIELDS if data.get(f) is None]
    return MatchResult(verdict=verdict, results=results, missing_optional=missing)
