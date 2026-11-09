"""
Administrator pages (FR-03, FR-04; Figure 4.10): compliance rules, rule candidates from the Act, user
management and the system log. Every page here is limited to the Administrator role.
"""
import json
import re
from datetime import datetime, timedelta
from pathlib import Path

from flask import Blueprint, current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user
from sqlalchemy import func

from app import rules_store
from app.activity import log_event
from app.decorators import role_required
from app.extensions import db
from app.models import ActivityLog, AuditRun, CandidateReview, ComplianceRule, PolicyDocument, User
from app.routes.auth import EMAIL_PATTERN, MIN_PASSWORD_LENGTH, USERNAME_PATTERN

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")

CANDIDATES_PATH = Path(__file__).resolve().parents[2] / "data" / "knowledge_base" / "act_candidates.json"
CATEGORIES = {"consent": "Consent", "retention": "Data Retention"}
SEVERITIES = ["Critical", "High", "Medium", "Low"]
ROLES = {"ComplianceOfficer": "Compliance Officer", "Administrator": "Administrator"}


def load_candidates():
    """Rule candidates extracted from the Act that nobody has decided on yet, best first."""
    try:
        data = json.loads(CANDIDATES_PATH.read_text(encoding="utf-8"))["candidates"]
    except (OSError, ValueError, KeyError):
        return []
    decided = {r.candidate_code for r in CandidateReview.query.all()}
    existing = {r.rule_code for r in ComplianceRule.query.all()}
    return [c for c in data if c["candidate_code"] not in decided and c["candidate_code"] not in existing]


def monitoring_cards():
    """The four small figures under the rules table."""
    midnight = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    today = AuditRun.query.filter(AuditRun.start_time >= midnight).count()
    recent = AuditRun.query.filter(AuditRun.end_time.isnot(None)).order_by(AuditRun.audit_id.desc()).limit(100).all()
    seconds = [(a.end_time - a.start_time).total_seconds() for a in recent]
    average = sum(seconds) / len(seconds) if seconds else None
    admins = User.query.filter_by(role="Administrator", active=True).count()
    officers = User.query.filter_by(role="ComplianceOfficer", active=True).count()
    started = current_app.config.get("STARTED_AT") or datetime.utcnow()
    running = datetime.utcnow() - started
    hours, rest = divmod(int(running.total_seconds()), 3600)
    return [
        {"label": "Audits today", "value": str(today), "note": "since midnight (UTC)"},
        {"label": "Average processing time", "value": f"{average:.2f}s" if average is not None else "-",
         "note": f"based on the last {len(seconds)} audits" if seconds else "no audits yet"},
        {"label": "Running for", "value": f"{hours}h {rest // 60}m", "note": "since the server last started"},
        {"label": "Active users", "value": str(admins + officers), "note": f"{admins} administrators, {officers} compliance officers"},
    ]


# ---------------------------------------------------------------------------
# Compliance rules
# ---------------------------------------------------------------------------

@admin_bp.route("/rules")
@role_required("Administrator")
def rules():
    rules_store.seed_rules()
    db.session.commit()
    rows = ComplianceRule.query.order_by(ComplianceRule.rule_id).all()
    return render_template("admin_rules.html", rules=rows, candidates=load_candidates(),
                           cards=monitoring_cards(), categories=CATEGORIES,
                           policy_count=PolicyDocument.query.count())


@admin_bp.route("/rules/<int:rule_id>/toggle", methods=["POST"])
@role_required("Administrator")
def toggle_rule(rule_id):
    rule = db.get_or_404(ComplianceRule, rule_id)
    rule.enabled = not rule.enabled
    log_event("rule_toggled", f"{rule.rule_code} {'enabled' if rule.enabled else 'disabled'}")
    db.session.commit()
    flash(f"Rule {rule.rule_code} is now {'on' if rule.enabled else 'off'}.", "success")
    return redirect(url_for("admin.rules"))


def read_rule_form(existing=None):
    """Validate the rule form. Returns (values, error)."""
    values = {
        "category": request.form.get("category", ""),
        "violation_type": " ".join(request.form.get("violation_type", "").split()),
        "obligation_text": " ".join(request.form.get("obligation_text", "").split()),
        "source_section": " ".join(request.form.get("source_section", "").split()),
        "severity": request.form.get("severity", ""),
        "recommendation": " ".join(request.form.get("recommendation", "").split()),
    }
    error = None
    if values["category"] not in CATEGORIES:
        error = "Choose a category."
    elif not values["violation_type"] or len(values["violation_type"]) > 100:
        error = "Give the rule a short name (100 characters at most)."
    elif len(values["obligation_text"]) < 20:
        error = "Describe the obligation in at least 20 characters. This text is compared with policy documents."
    elif len(values["source_section"]) > 100:
        error = "The source section is too long (100 characters at most)."
    elif values["severity"] not in SEVERITIES:
        error = "Choose a severity."
    elif not values["recommendation"]:
        error = "Write a recommendation for the Compliance Officer."
    return values, error


@admin_bp.route("/rules/new", methods=["GET", "POST"])
@role_required("Administrator")
def new_rule():
    values = {"category": "consent", "violation_type": "", "obligation_text": "", "source_section": "",
              "severity": "Medium", "recommendation": ""}
    if request.method == "POST":
        values, error = read_rule_form()
        if error:
            flash(error, "error")
        else:
            number = 1
            while ComplianceRule.query.filter_by(rule_code=f"CUSTOM-{number:02d}").first():
                number += 1
            rule = ComplianceRule(rule_code=f"CUSTOM-{number:02d}", origin="manual", enabled=True, check_config=None, **values)
            db.session.add(rule)
            log_event("rule_added", rule.rule_code)
            db.session.commit()
            flash(f"Rule {rule.rule_code} was added. It is compared with policy documents.", "success")
            return redirect(url_for("admin.rules"))
    return render_template("admin_rule_form.html", rule=None, values=values, categories=CATEGORIES, severities=SEVERITIES)


@admin_bp.route("/rules/<int:rule_id>/edit", methods=["GET", "POST"])
@role_required("Administrator")
def edit_rule(rule_id):
    rule = db.get_or_404(ComplianceRule, rule_id)
    values = {k: getattr(rule, k) or "" for k in ("category", "violation_type", "obligation_text", "source_section", "severity", "recommendation")}
    if request.method == "POST":
        values, error = read_rule_form(rule)
        if rule.is_dataset_rule:
            values["category"] = rule.category   # the category of a rule that checks data cannot change
        if error:
            flash(error, "error")
        else:
            for key, value in values.items():
                setattr(rule, key, value)
            log_event("rule_edited", rule.rule_code)
            db.session.commit()
            flash(f"Rule {rule.rule_code} was updated.", "success")
            return redirect(url_for("admin.rules"))
    return render_template("admin_rule_form.html", rule=rule, values=values, categories=CATEGORIES, severities=SEVERITIES)


@admin_bp.route("/rules/candidates/<code>/<decision>", methods=["POST"])
@role_required("Administrator")
def review_candidate(code, decision):
    if decision not in ("approve", "reject"):
        flash("Unknown decision.", "error")
        return redirect(url_for("admin.rules"))
    candidate = next((c for c in load_candidates() if c["candidate_code"] == code), None)
    if candidate is None:
        flash("That candidate was not found, or it has already been reviewed.", "error")
        return redirect(url_for("admin.rules"))
    if decision == "approve":
        db.session.add(ComplianceRule(
            rule_code=candidate["candidate_code"], category=candidate["category"],
            obligation_text=candidate["obligation_text"], source_section=candidate["source_section"][:100],
            violation_type=f"Policy obligation ({candidate['reference']})", severity="Medium",
            recommendation=f"Check that the organisation's policy and practice meet {candidate['reference']} of the Data Protection Act.",
            check_config=None, enabled=True, origin="extracted",
        ))
    db.session.add(CandidateReview(candidate_code=code, decision="approved" if decision == "approve" else "rejected", reviewed_by=current_user.user_id))
    log_event("candidate_" + ("approved" if decision == "approve" else "rejected"), code)
    db.session.commit()
    flash(f"{code} was {'approved and added as a rule' if decision == 'approve' else 'rejected'}.", "success")
    return redirect(url_for("admin.rules"))


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------

@admin_bp.route("/users")
@role_required("Administrator")
def users():
    return render_template("admin_users.html", users=User.query.order_by(User.user_id).all(), roles=ROLES)


def read_user_form(user=None):
    """Validate the user form (new or edit). Returns (values, error)."""
    values = {
        "username": request.form.get("username", "").strip(),
        "email": request.form.get("email", "").strip().lower(),
        "full_name": " ".join(request.form.get("full_name", "").split()),
        "role": request.form.get("role", ""),
        "password": request.form.get("password", ""),
    }
    other = lambda q: q.filter(User.user_id != user.user_id) if user else q
    error = None
    if not USERNAME_PATTERN.match(values["username"]):
        error = "The username must be 3 to 50 characters: letters, numbers, dots, dashes or underscores."
    elif not EMAIL_PATTERN.match(values["email"]) or len(values["email"]) > 255:
        error = "Please enter a valid email address."
    elif len(values["full_name"]) > 150:
        error = "The full name is too long (150 characters at most)."
    elif values["role"] not in ROLES:
        error = "Choose a role."
    elif (user is None or values["password"]) and len(values["password"]) < MIN_PASSWORD_LENGTH:
        error = f"The password must be at least {MIN_PASSWORD_LENGTH} characters long."
    elif other(User.query.filter(func.lower(User.username) == values["username"].lower())).first():
        error = "That username is already taken."
    elif other(User.query.filter(func.lower(User.email) == values["email"])).first():
        error = "That email address belongs to another account."
    return values, error


def active_administrators(excluding=None):
    query = User.query.filter_by(role="Administrator", active=True)
    if excluding is not None:
        query = query.filter(User.user_id != excluding)
    return query.count()


@admin_bp.route("/users/new", methods=["GET", "POST"])
@role_required("Administrator")
def new_user():
    values = {"username": "", "email": "", "full_name": "", "role": "ComplianceOfficer", "password": ""}
    if request.method == "POST":
        values, error = read_user_form()
        if error:
            flash(error, "error")
        else:
            user = User(username=values["username"], email=values["email"], role=values["role"],
                        full_name=values["full_name"] or None, active=True)
            user.set_password(values["password"])
            db.session.add(user)
            db.session.flush()
            log_event("user_created", f"{user.username} ({user.role})")
            db.session.commit()
            flash(f"The account '{user.username}' was created.", "success")
            return redirect(url_for("admin.users"))
        values["password"] = ""
    return render_template("admin_user_form.html", user=None, values=values, roles=ROLES)


@admin_bp.route("/users/<int:user_id>/edit", methods=["GET", "POST"])
@role_required("Administrator")
def edit_user(user_id):
    user = db.get_or_404(User, user_id)
    values = {"username": user.username, "email": user.email or "", "full_name": user.full_name or "",
              "role": user.role, "password": ""}
    if request.method == "POST":
        values, error = read_user_form(user)
        if not error and user.role == "Administrator" and values["role"] != "Administrator" and active_administrators(excluding=user.user_id) == 0:
            error = "There must always be at least one active Administrator."
        if error:
            flash(error, "error")
        else:
            changes = []
            if user.username != values["username"]:
                changes.append(f"username {user.username} -> {values['username']}")
            if user.role != values["role"]:
                changes.append(f"role {user.role} -> {values['role']}")
            user.username, user.email, user.role = values["username"], values["email"], values["role"]
            user.full_name = values["full_name"] or None
            if values["password"]:
                user.set_password(values["password"])
                changes.append("password reset")
            log_event("user_edited", f"{user.username}: " + (", ".join(changes) or "details"))
            db.session.commit()
            flash(f"The account '{user.username}' was updated.", "success")
            return redirect(url_for("admin.users"))
        values["password"] = ""
    return render_template("admin_user_form.html", user=user, values=values, roles=ROLES)


@admin_bp.route("/users/<int:user_id>/status", methods=["POST"])
@role_required("Administrator")
def toggle_user(user_id):
    user = db.get_or_404(User, user_id)
    if user.user_id == current_user.user_id:
        flash("You cannot deactivate your own account.", "error")
    elif user.active and user.role == "Administrator" and active_administrators(excluding=user.user_id) == 0:
        flash("There must always be at least one active Administrator.", "error")
    else:
        user.active = not user.active
        log_event("user_activated" if user.active else "user_deactivated", user.username)
        db.session.commit()
        flash(f"The account '{user.username}' was {'reactivated' if user.active else 'deactivated'}.", "success")
    return redirect(url_for("admin.users"))


# ---------------------------------------------------------------------------
# System log
# ---------------------------------------------------------------------------

@admin_bp.route("/logs")
@role_required("Administrator")
def logs():
    action = request.args.get("action", "")
    page = request.args.get("page", 1, type=int)
    query = ActivityLog.query
    if action:
        query = query.filter(ActivityLog.action == action)
    entries = query.order_by(ActivityLog.log_id.desc()).paginate(page=page, per_page=30, error_out=False)
    actions = [a for (a,) in db.session.query(ActivityLog.action).distinct().order_by(ActivityLog.action).all()]
    return render_template("admin_logs.html", entries=entries, actions=actions, selected=action)
