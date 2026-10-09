from flask import Blueprint, render_template
from flask_login import login_required
from sqlalchemy import func

from app.extensions import db
from app.models import AuditRun, Dataset, AuditResult, ComplianceRule

dashboard_bp = Blueprint("dashboard", __name__)

CATEGORY_COLORS = {
    "consent": "#0D9488",
    "retention": "#F59E0B",
}


@dashboard_bp.route("/dashboard")
@login_required
def index():
    # --- The four headline numbers ---
    total_audits = db.session.query(func.count(AuditRun.audit_id)).scalar() or 0
    total_datasets = db.session.query(func.count(Dataset.dataset_id)).scalar() or 0
    active_violations = db.session.query(func.count(AuditResult.result_id)).scalar() or 0

    avg_score = db.session.query(func.avg(AuditRun.compliance_score)).scalar()
    overall_health = round(float(avg_score)) if avg_score is not None else None
    health_gradient = (
        f"conic-gradient(var(--color-primary) 0% {overall_health}%, "
        f"var(--color-border) {overall_health}% 100%)"
        if overall_health is not None
        else None
    )

    # --- The 5 most recent audits, with their dataset names ---
    recent_audits = (
        db.session.query(AuditRun, Dataset)
        .join(Dataset, AuditRun.dataset_id == Dataset.dataset_id)
        .order_by(AuditRun.start_time.desc())
        .limit(5)
        .all()
    )

    # --- Violations grouped by category (consent / retention) ---
    category_counts = (
        db.session.query(ComplianceRule.category, func.count(AuditResult.result_id))
        .join(AuditResult, AuditResult.rule_id == ComplianceRule.rule_id)
        .group_by(ComplianceRule.category)
        .all()
    )

    total_category_violations = sum(count for _, count in category_counts)
    category_breakdown = []
    gradient_stops = []
    cumulative = 0
    for category, count in category_counts:
        pct = round((count / total_category_violations) * 100)
        color = CATEGORY_COLORS.get(category, "#94A3B8")
        category_breakdown.append(
            {"name": category.capitalize(), "count": count, "pct": pct, "color": color}
        )
        gradient_stops.append(f"{color} {cumulative}% {cumulative + pct}%")
        cumulative += pct
    category_gradient = (
        f"conic-gradient({', '.join(gradient_stops)})" if gradient_stops else None
    )

    return render_template(
        "dashboard.html",
        total_audits=total_audits,
        total_datasets=total_datasets,
        active_violations=active_violations,
        overall_health=overall_health,
        health_gradient=health_gradient,
        recent_audits=recent_audits,
        category_breakdown=category_breakdown,
        total_category_violations=total_category_violations,
        category_gradient=category_gradient,
    )