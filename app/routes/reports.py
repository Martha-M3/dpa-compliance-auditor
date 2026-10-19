"""
Audit report page (Figure 4.8; FR-13, FR-14).

Shows one audit: the compliance score, issues by severity, a tab per DPA
category with the result of each rule, and the list of affected records.
"""
import csv
import re
from datetime import datetime, timedelta

from flask import Blueprint, redirect, render_template, request, url_for
from flask_login import login_required
from sqlalchemy import func

from app.auditing.engine import load_rules
from app.extensions import db
from app.models import AuditResult, AuditRun, ComplianceRule, Dataset
from app.routes.dashboard import CATEGORY_STYLE, TONE_COLORS, health_band, score_band
from app.routes.upload import stored_path

reports_bp = Blueprint("reports", __name__)

SEVERITIES = ["Critical", "High", "Medium", "Low"]
PER_PAGE = 25

# The filter drop-downs on the reports list: {value in the URL: (label, ...)}
DATE_RANGES = {"7": ("Last 7 days", 7), "30": ("Last 30 days", 30), "90": ("Last 90 days", 90)}
LEVELS = {  # value: (label, lowest score allowed, score it must stay below)
    "compliant": ("Compliant", 80, None),
    "action": ("Action Required", 50, 80),
    "critical": ("Critical Violations", None, 50),
}


def count_records(path):
    """Number of data rows in a stored CSV (None if the file is missing)."""
    try:
        with open(path, newline="", encoding="utf-8-sig") as f:
            return max(sum(1 for _ in csv.reader(f)) - 1, 0)
    except OSError:
        return None


def short_section(source_section):
    """'Sections 30 and 32, Data Protection Act 2019' -> 'DPA Sec 30 and 32'"""
    match = re.match(r"Sections?\s+([^,]+)", source_section)
    return f"DPA Sec {match.group(1)}" if match else "DPA"


@reports_bp.route("/audits")
@login_required
def audits():
    """The "Audits" sidebar link: open the most recent audit (Figure 4.8)."""
    latest = AuditRun.query.order_by(AuditRun.start_time.desc()).first()
    if latest is None:
        # The reports list explains that nothing has been audited yet.
        return redirect(url_for("reports.index"))
    return redirect(url_for("reports.detail", audit_id=latest.audit_id))


def risk_band(score):
    """Risk label and tone for one category score (same thresholds as the overall health)."""
    if score >= 80:
        return "Low Risk", "good"
    if score >= 65:
        return "Moderate Risk", "warn"
    return "High Risk", "bad"


def build_summary(audit):
    """
    Everything the preview panel and the printable summary show for one audit:
    an executive summary, a score for each DPA category, and recommendations.
    """
    rules = load_rules()
    total = count_records(stored_path(audit.dataset_id))
    score = float(audit.compliance_score) if audit.compliance_score is not None else None

    per_rule = dict(
        db.session.query(ComplianceRule.rule_code, func.count(AuditResult.result_id))
        .join(AuditResult, AuditResult.rule_id == ComplianceRule.rule_id)
        .filter(AuditResult.audit_id == audit.audit_id)
        .group_by(ComplianceRule.rule_code)
        .all()
    )
    per_severity = dict(
        db.session.query(AuditResult.severity, func.count(AuditResult.result_id))
        .filter(AuditResult.audit_id == audit.audit_id)
        .group_by(AuditResult.severity)
        .all()
    )
    # Records with at least one violation, per category (a record counts once per category).
    records_by_category = dict(
        db.session.query(ComplianceRule.category, func.count(func.distinct(AuditResult.record_id)))
        .join(AuditResult, AuditResult.rule_id == ComplianceRule.rule_id)
        .filter(AuditResult.audit_id == audit.audit_id)
        .group_by(ComplianceRule.category)
        .all()
    )
    violating_records = (
        db.session.query(func.count(func.distinct(AuditResult.record_id)))
        .filter(AuditResult.audit_id == audit.audit_id)
        .scalar()
        or 0
    )
    violations = sum(per_rule.values())

    # --- Score breakdown: the overall score formula, applied to one category at a time ---
    breakdown = []
    for key in dict.fromkeys(rule["category"] for rule in rules):
        label = CATEGORY_STYLE.get(key, {"label": key.capitalize()})["label"]
        entry = {
            "label": label,
            "violations": sum(per_rule.get(r["rule_code"], 0) for r in rules if r["category"] == key),
            "score": None, "risk": None, "tone": "muted",
        }
        if total:
            entry["score"] = round(100 * (total - records_by_category.get(key, 0)) / total)
            entry["risk"], entry["tone"] = risk_band(entry["score"])
        breakdown.append(entry)

    # --- Recommendations: one for every rule that was broken ---
    recommendations = [
        rule["recommendation"] for rule in rules if per_rule.get(rule["rule_code"], 0) > 0
    ]

    # --- Executive summary: plain sentences built from the numbers above ---
    records_text = f"{total:,} records" if total is not None else "the dataset"
    if violations == 0:
        executive = (
            f"Automated analysis of {audit.dataset.file_name} ({records_text}) found no violations "
            "of the consent and retention requirements that were checked."
        )
    else:
        worst = max(breakdown, key=lambda entry: entry["violations"])
        by_severity = ", ".join(
            f"{per_severity[name]:,} {name}" for name in SEVERITIES if per_severity.get(name)
        )
        executive = (
            f"Automated analysis of {audit.dataset.file_name} ({records_text}) found {violations:,} "
            f"violations affecting {violating_records:,} records. Most findings are under "
            f"{worst['label']} ({worst['violations']:,}). By severity: {by_severity}."
        )
    status, tone = score_band(score)
    if score is not None:
        executive += f" The compliance score is {round(score)}%."

    return {
        "audit_id": audit.audit_id,
        "code": f"REP-{audit.audit_id:03d}",
        "file_name": audit.dataset.file_name,
        "run_by": audit.runner.username,
        "date": (audit.end_time or audit.start_time).strftime("%b %d, %Y"),
        "score": round(score) if score is not None else None,
        "status": status,
        "tone": tone,
        "executive": executive,
        "breakdown": breakdown,
        "recommendations": recommendations,
        "severity_counts": [(name, per_severity.get(name, 0)) for name in SEVERITIES],
        "violations": violations,
        "violating_records": violating_records,
        "total_records": total,
    }


@reports_bp.route("/reports")
@login_required
def index():
    """Compliance reports: filters, a list of audits, and a preview of one (Figure 4.9)."""
    page = request.args.get("page", 1, type=int)
    filters = {
        "date": request.args.get("date", ""),
        "dataset": request.args.get("dataset", ""),
        "level": request.args.get("level", ""),
    }

    query = AuditRun.query.join(Dataset, AuditRun.dataset_id == Dataset.dataset_id)
    if filters["date"] in DATE_RANGES:
        since = datetime.utcnow() - timedelta(days=DATE_RANGES[filters["date"]][1])
        query = query.filter(AuditRun.start_time >= since)
    if filters["dataset"]:
        query = query.filter(Dataset.file_name == filters["dataset"])
    if filters["level"] in LEVELS:
        _, low, high = LEVELS[filters["level"]]
        if low is not None:
            query = query.filter(AuditRun.compliance_score >= low)
        if high is not None:
            query = query.filter(AuditRun.compliance_score < high)

    audits = query.order_by(AuditRun.start_time.desc()).paginate(page=page, per_page=15, error_out=False)

    # Which report is shown in the preview: the one in the URL, else the newest on this page.
    preview_audit = None
    wanted = request.args.get("report", type=int)
    if wanted:
        preview_audit = db.session.get(AuditRun, wanted)
    if preview_audit is None and audits.items:
        preview_audit = audits.items[0]

    # Links keep the filters and page, and only change which report is previewed.
    keep = {key: value for key, value in filters.items() if value}
    rows = []
    for audit in audits.items:
        score = float(audit.compliance_score) if audit.compliance_score is not None else None
        status, tone = score_band(score)
        rows.append(
            {
                "href": url_for("reports.index", report=audit.audit_id, page=page, **keep),
                "code": f"REP-{audit.audit_id:03d}",
                "file_name": audit.dataset.file_name,
                "run_by": audit.runner.username,
                "date": audit.start_time.strftime("%b %d, %Y"),
                "score": round(score) if score is not None else None,
                "status": status,
                "tone": tone,
                "selected": preview_audit is not None and audit.audit_id == preview_audit.audit_id,
            }
        )

    dataset_names = [
        name for (name,) in db.session.query(Dataset.file_name)
        .join(AuditRun, AuditRun.dataset_id == Dataset.dataset_id)
        .distinct().order_by(Dataset.file_name).all()
    ]
    return render_template(
        "reports_list.html",
        rows=rows,
        audits=audits,
        filters=filters,
        keep=keep,
        date_ranges=DATE_RANGES,
        levels=LEVELS,
        dataset_names=dataset_names,
        summary=build_summary(preview_audit) if preview_audit else None,
    )


@reports_bp.route("/reports/<int:audit_id>/summary")
@login_required
def summary(audit_id):
    """A clean one-page summary meant for printing or saving as a PDF."""
    audit = db.get_or_404(AuditRun, audit_id)
    return render_template("report_summary.html", summary=build_summary(audit))


@reports_bp.route("/reports/<int:audit_id>")
@login_required
def detail(audit_id):
    audit = db.get_or_404(AuditRun, audit_id)
    rules = load_rules()

    # --- The tabs: one per rule category, in the order the rules file lists them ---
    category_keys = []
    for rule in rules:
        if rule["category"] not in category_keys:
            category_keys.append(rule["category"])
    selected = request.args.get("category", category_keys[0])
    if selected not in category_keys:
        selected = category_keys[0]

    # --- Counts for this audit ---
    per_rule = dict(
        db.session.query(ComplianceRule.rule_code, func.count(AuditResult.result_id))
        .join(AuditResult, AuditResult.rule_id == ComplianceRule.rule_id)
        .filter(AuditResult.audit_id == audit_id)
        .group_by(ComplianceRule.rule_code)
        .all()
    )
    per_severity = dict(
        db.session.query(AuditResult.severity, func.count(AuditResult.result_id))
        .filter(AuditResult.audit_id == audit_id)
        .group_by(AuditResult.severity)
        .all()
    )
    violating_records = (
        db.session.query(func.count(func.distinct(AuditResult.record_id)))
        .filter(AuditResult.audit_id == audit_id)
        .scalar()
        or 0
    )

    tabs = []
    for key in category_keys:
        total = sum(per_rule.get(r["rule_code"], 0) for r in rules if r["category"] == key)
        label = CATEGORY_STYLE.get(key, {"label": key.capitalize()})["label"]
        section = short_section(next(r["source_section"] for r in rules if r["category"] == key))
        tabs.append({"key": key, "label": f"{label} ({section})", "count": total, "active": key == selected})

    # --- One row per rule in the selected tab ---
    rule_rows = []
    for rule in rules:
        if rule["category"] != selected:
            continue
        n = per_rule.get(rule["rule_code"], 0)
        rule_rows.append(
            {
                "title": rule["violation_type"],
                "passed": n == 0,
                "count": n,
                "obligation": rule["obligation_text"],
                "section": rule["source_section"],
                "recommendation": rule["recommendation"],
            }
        )

    # --- Affected records for the selected tab, 25 per page ---
    page = request.args.get("page", 1, type=int)
    records = (
        AuditResult.query.join(ComplianceRule, AuditResult.rule_id == ComplianceRule.rule_id)
        .filter(AuditResult.audit_id == audit_id, ComplianceRule.category == selected)
        .order_by(AuditResult.result_id)
        .paginate(page=page, per_page=PER_PAGE, error_out=False)
    )

    # --- The header card ---
    score = float(audit.compliance_score) if audit.compliance_score is not None else None
    if score is None:
        grade_label, grade_tone, gradient = "In progress", "muted", None
    else:
        grade_label, grade_tone = health_band(round(score))
        gradient = (
            f"conic-gradient({TONE_COLORS[grade_tone]} 0% {score}%, "
            f"var(--color-border) {score}% 100%)"
        )

    finished = audit.end_time or audit.start_time
    return render_template(
        "report.html",
        audit=audit,
        dataset=audit.dataset,
        audited_at=finished.strftime("%b %d, %Y %H:%M") + " UTC",
        score=score,
        grade_label=grade_label,
        grade_tone=grade_tone,
        gradient=gradient,
        total_records=count_records(stored_path(audit.dataset_id)),
        violating_records=violating_records,
        severity_counts=[(name, per_severity.get(name, 0)) for name in SEVERITIES],
        tabs=tabs,
        selected=selected,
        rule_rows=rule_rows,
        records=records,
    )