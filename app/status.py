"""
One place that decides how an audit is labelled (this replaces two separate rules that disagreed, defect DEF-04).

A score of 80 or more is Compliant, 50 to 79 is Action Required, and below 50 is Critical Violations.
If the dataset itself is compliant but the organisation's policy does not address a topic of the Act, the
status is Review: the data look fine but a person should check the policy.
These bands are working values chosen for the prototype; the Act prescribes no scores.
"""

COMPLIANT_FROM = 80
ACTION_FROM = 50


def score_status(score, policy_gap=False):
    """(label, tone) for a compliance score. `tone` is the CSS colour class: good, warn, bad or muted."""
    if score is None:
        return "In progress", "muted"
    if score >= COMPLIANT_FROM:
        return ("Review", "warn") if policy_gap else ("Compliant", "good")
    if score >= ACTION_FROM:
        return "Action Required", "warn"
    return "Critical Violations", "bad"


def risk_band(score):
    """Risk label and tone for one category score."""
    if score >= COMPLIANT_FROM:
        return "Low Risk", "good"
    if score >= 65:
        return "Moderate Risk", "warn"
    return "High Risk", "bad"


def has_policy_gap(audit):
    """True if the audit compared a policy and at least one topic was not found in it."""
    return any(f.verdict == "Not found" for f in audit.policy_findings)
