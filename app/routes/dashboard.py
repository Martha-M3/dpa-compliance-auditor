from datetime import datetime, timedelta

from flask import Blueprint, render_template
from flask_login import login_required
from sqlalchemy import func

from app.extensions import db
from app.models import AuditRun, Dataset, AuditResult, ComplianceRule

dashboard_bp = Blueprint("dashboard", __name__)

# How each rule category is labelled and coloured in the category panel.
CATEGORY_STYLE = {
    "consent": {"label": "Consent Management", "color": "#D97706"},
    "retention": {"label": "Data Retention", "color": "#EF4444"},
}

# Ring colours for each tone (these are CSS variables defined in style.css).
TONE_COLORS = {
    "good": "var(--color-primary)",
    "warn": "var(--color-warn)",
    "bad": "var(--color-danger)",
}


def score_band(score):
    """Status label and tone for a single audit score."""
    if score is None:
        return "In progress", "muted"
    if score >= 80:
        return "Compliant", "good"
    if score >= 50:
        return "Action Required", "warn"
    return "Critical Violations", "bad"


def health_band(score):
    """Label and tone for the overall health score."""
    if score >= 80:
        return "Compliant", "good"
    if score >= 65:
        return "Mainly Compliant", "warn"
    if score >= 50:
        return "Partially Compliant", "warn"
    return "Non-Compliant", "bad"


def pluralize(n, one, many):
    return f"{n} {one if n == 1 else many}"


@dashboard_bp.route("/dashboard")
@login_required
def index():
    week_ago = datetime.utcnow() - timedelta(days=7)

    # --- Audit counts ---
    total_audits = db.session.query(func.count(AuditRun.audit_id)).scalar() or 0
    audits_this_week = (
        db.session.query(func.count(AuditRun.audit_id))
        .filter(AuditRun.start_time >= week_ago)
        .scalar()
        or 0
    )
    audited_datasets = (
        db.session.query(func.count(func.distinct(AuditRun.dataset_id))).scalar() or 0
    )

    # Datasets that have an audit scoring below 50 need urgent attention.
    needs_review = (
        db.session.query(func.count(func.distinct(AuditRun.dataset_id)))
        .filter(AuditRun.compliance_score < 50)
        .scalar()
        or 0
    )

    # --- Dataset counts ---
    total_datasets = db.session.query(func.count(Dataset.dataset_id)).scalar() or 0
    validated_datasets = (
        db.session.query(func.count(Dataset.dataset_id))
        .filter(Dataset.schema_validated.is_(True))
        .scalar()
        or 0
    )
    unvalidated_datasets = total_datasets - validated_datasets

    # --- Violation counts ---
    active_violations = db.session.query(func.count(AuditResult.result_id)).scalar() or 0
    violations_this_week = (
        db.session.query(func.count(AuditResult.result_id))
        .join(AuditRun, AuditResult.audit_id == AuditRun.audit_id)
        .filter(AuditRun.start_time >= week_ago)
        .scalar()
        or 0
    )
    high_violations = (
        db.session.query(func.count(AuditResult.result_id))
        .filter(func.lower(AuditResult.severity) == "high")
        .scalar()
        or 0
    )
    critical_violations = (
        db.session.query(func.count(AuditResult.result_id))
        .filter(func.lower(AuditResult.severity) == "critical")
        .scalar()
        or 0
    )

    # --- Overall health ring ---
    avg_score = db.session.query(func.avg(AuditRun.compliance_score)).scalar()
    if avg_score is None:
        overall_health = None
        health_label = "No scores yet"
        health_gradient = None
    else:
        overall_health = max(0, min(100, round(float(avg_score))))
        health_label, health_tone = health_band(overall_health)
        health_gradient = (
            f"conic-gradient({TONE_COLORS[health_tone]} 0% {overall_health}%, "
            f"var(--color-border) {overall_health}% 100%)"
        )

    # --- The sentence under "Habari, ..." ---
    if total_audits == 0:
        status_line = "No audits have been run yet. Upload a dataset to get started."
    elif overall_health is None:
        status_line = "Audits are running. Scores will appear when they finish."
    else:
        status_line = (
            "Compliance baseline is stable."
            if overall_health >= 80
            else "Compliance baseline needs attention."
        )
        if needs_review:
            status_line += (
                f" {pluralize(needs_review, 'dataset requires', 'datasets require')}"
                " immediate review."
            )

    # --- Small badges on the stat cards ---
    audits_badge = (
        {"text": "Active", "tone": "good"}
        if audits_this_week
        else {"text": "Idle", "tone": "muted"}
    )
    violations_badge = (
        {"text": f"+{violations_this_week}", "tone": "bad"}
        if violations_this_week
        else {"text": "No new", "tone": "good"}
    )
    datasets_badge = (
        {"text": "Normal", "tone": "good"}
        if unvalidated_datasets == 0
        else {"text": f"{unvalidated_datasets} to validate", "tone": "warn"}
    )

    # --- Recent audits table ---
    rows = (
        db.session.query(AuditRun, Dataset)
        .join(Dataset, AuditRun.dataset_id == Dataset.dataset_id)
        .order_by(AuditRun.start_time.desc())
        .limit(5)
        .all()
    )
    recent_audits = []
    for audit, dataset in rows:
        score = audit.compliance_score
        status, tone = score_band(score)
        recent_audits.append(
            {
                "file_name": dataset.file_name,
                "date": audit.start_time.strftime("%b %d, %Y"),
                "score": round(float(score)) if score is not None else None,
                "status": status,
                "tone": tone,
            }
        )

    # --- Violations by category ---
    category_counts = (
        db.session.query(ComplianceRule.category, func.count(AuditResult.result_id))
        .join(AuditResult, AuditResult.rule_id == ComplianceRule.rule_id)
        .group_by(ComplianceRule.category)
        .order_by(func.count(AuditResult.result_id).desc())
        .all()
    )
    total_category_violations = sum(n for _, n in category_counts)

    category_breakdown = []
    gradient_stops = []
    running = 0
    for category, n in category_counts:
        style = CATEGORY_STYLE.get(
            category, {"label": category.capitalize(), "color": "#94A3B8"}
        )
        start = running / total_category_violations * 100
        running += n
        end = running / total_category_violations * 100
        gradient_stops.append(f"{style['color']} {start:.2f}% {end:.2f}%")
        category_breakdown.append(
            {
                "label": style["label"],
                "color": style["color"],
                "pct": round(n / total_category_violations * 100),
            }
        )
    category_gradient = (
        f"conic-gradient({', '.join(gradient_stops)})" if gradient_stops else None
    )

    return render_template(
        "dashboard.html",
        status_line=status_line,
        total_audits=total_audits,
        audits_this_week=audits_this_week,
        audited_datasets=audited_datasets,
        total_datasets=total_datasets,
        validated_datasets=validated_datasets,
        active_violations=active_violations,
        high_violations=high_violations,
        critical_violations=critical_violations,
        overall_health=overall_health,
        health_label=health_label,
        health_gradient=health_gradient,
        audits_badge=audits_badge,
        violations_badge=violations_badge,
        datasets_badge=datasets_badge,
        recent_audits=recent_audits,
        category_breakdown=category_breakdown,
        category_gradient=category_gradient,
        total_category_violations=total_category_violations,
    )