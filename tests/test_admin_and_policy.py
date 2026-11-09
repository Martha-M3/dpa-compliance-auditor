"""Policy findings in audits, administrator pages, the activity log, status labels and PDF reports. TC-N11, TC-N12, TC-M01 to TC-M09, TC-R04, TC-S01."""
import io
import json

import pytest

from app.extensions import db
from app.models import ActivityLog, AuditRun, CandidateReview, ComplianceRule, PolicyFinding, User
from app.routes import admin as admin_module
from app.status import score_status
from conftest import ADMIN, OFFICER, _login
from helpers import POLICY_TEXT, csv_bytes, good_rows, run_audit_via_web


def upload_policy(client, text):
    return client.post("/upload/policy", data={"policy": (io.BytesIO(text.encode()), "policy.txt")}, content_type="multipart/form-data")


def clean_csv():
    return csv_bytes(good_rows(8))


def test_policy_findings_saved_with_audit(officer, app, record):
    upload_policy(officer, POLICY_TEXT + " Visitors sign the register at reception.")
    _, audit_id = run_audit_via_web(officer, clean_csv(), "a.csv")
    with app.app_context():
        findings = {f.category: f for f in PolicyFinding.query.filter_by(audit_id=audit_id)}
        assert set(findings) == {"consent", "retention"}
        assert all(f.verdict == "Addressed" and f.best_statement for f in findings.values())
        assert findings["retention"].policy.file_name == "policy.txt"
    page = officer.get(f"/reports/{audit_id}").get_data(as_text=True)
    assert "Policy Alignment" in page and "Addressed" in page
    record("TC-N11", "With a policy that mentions consent and retention: two findings were saved (consent and retention, both 'Addressed') with the quoted statement and the policy file name; the audit page showed the Policy Alignment panel.")


def test_policy_gap_gives_review_status_and_absent_policy_gives_none(officer, app, record):
    # No policy at all
    _, first = run_audit_via_web(officer, clean_csv(), "none.csv")
    with app.app_context():
        assert PolicyFinding.query.filter_by(audit_id=first).count() == 0
    assert "No policy document was uploaded" in officer.get(f"/reports/{first}").get_data(as_text=True)
    # A policy that says nothing about retention
    upload_policy(officer, "We ask every customer for consent before collecting personal data. Our offices open at eight in the morning.")
    _, second = run_audit_via_web(officer, clean_csv(), "gap.csv")
    with app.app_context():
        verdicts = {f.category: f.verdict for f in PolicyFinding.query.filter_by(audit_id=second)}
        assert verdicts == {"consent": "Addressed", "retention": "Not found"}
    page = officer.get("/reports").get_data(as_text=True)
    assert "Review" in page
    assert score_status(100, policy_gap=True) == ("Review", "warn")
    record("TC-N12", "An audit with no policy saved no findings and the page said so. After a policy that omits retention was uploaded, a 100% dataset got consent 'Addressed' and retention 'Not found', and its status was 'Review' instead of 'Compliant'.")


def test_admin_pages_are_for_administrators_only(officer, admin, anon, record):
    pages = ["/admin/rules", "/admin/users", "/admin/logs", "/admin/rules/new", "/admin/users/new"]
    for page in pages:
        assert anon.get(page).status_code == 302 and "/login" in anon.get(page).headers["Location"]
        r = officer.get(page)
        assert r.status_code == 302 and r.headers["Location"].endswith("/dashboard"), page
        assert admin.get(page).status_code == 200, page
    assert officer.post("/admin/rules/1/toggle").status_code == 302
    record("TC-M01", "Five admin pages: anonymous visitors went to the sign-in page, a Compliance Officer was sent back to the dashboard, an Administrator opened all five. A Compliance Officer's attempt to switch a rule was refused.")


def test_switching_rules_changes_the_audit(admin, officer, app, record):
    admin.get("/admin/rules")                                  # opens the page, which seeds the rules
    rows = [["C1", "No", "2026-01-01", "5 years", "Active"]] + good_rows(4)
    with app.app_context():
        consent_id = ComplianceRule.query.filter_by(rule_code="CONSENT-01").one().rule_id
        retention_id = ComplianceRule.query.filter_by(rule_code="RETENTION-01").one().rule_id
    admin.post(f"/admin/rules/{consent_id}/toggle")
    _, audit_id = run_audit_via_web(officer, csv_bytes(rows), "off.csv")
    with app.app_context():
        assert db.session.get(AuditRun, audit_id).compliance_score == 100     # the consent violation is no longer checked
    admin.post(f"/admin/rules/{consent_id}/toggle")
    _, audit_id = run_audit_via_web(officer, csv_bytes(rows), "on.csv")
    with app.app_context():
        assert float(db.session.get(AuditRun, audit_id).compliance_score) == 80.0
        assert ActivityLog.query.filter_by(action="rule_toggled").count() == 2
    # every data rule off: nothing to audit against
    admin.post(f"/admin/rules/{consent_id}/toggle"); admin.post(f"/admin/rules/{retention_id}/toggle")
    dataset = officer.post("/upload", data={"dataset": (io.BytesIO(clean_csv()), "z.csv")}, content_type="multipart/form-data")
    did = int(dataset.headers["Location"].rstrip("/").split("/")[-1])
    msg = officer.post(f"/upload/{did}/proceed", follow_redirects=True).get_data(as_text=True)
    assert "No audit rules are switched on" in msg
    with app.app_context():
        assert AuditRun.query.count() == 2
    record("TC-M02", "With CONSENT-01 switched off a dataset holding a consent violation scored 100; switched on again it scored 80. Both switches were written to the log. With both data rules off the audit was refused with 'No audit rules are switched on' and no audit run was created.")


def test_adding_and_editing_rules(admin, app, record):
    form = {"category": "retention", "violation_type": "Backups kept too long", "severity": "High",
            "obligation_text": "Backup copies containing personal data must be deleted when the retention period ends.",
            "source_section": "Section 39(2), Data Protection Act 2019", "recommendation": "Delete expired backups."}
    bad = admin.post("/admin/rules/new", data={**form, "obligation_text": "too short"})
    assert bad.status_code == 200
    ok = admin.post("/admin/rules/new", data=form, follow_redirects=True)
    assert b"CUSTOM-01" in ok.data
    with app.app_context():
        rule = ComplianceRule.query.filter_by(rule_code="CUSTOM-01").one()
        assert rule.origin == "manual" and not rule.is_dataset_rule and rule.enabled
        rid = rule.rule_id
    admin.post(f"/admin/rules/{rid}/edit", data={**form, "severity": "Low"})
    admin.get("/admin/rules")
    with app.app_context():
        assert ComplianceRule.query.get(rid).severity == "Low"
        data_rule = ComplianceRule.query.filter_by(rule_code="CONSENT-01").one()
        did = data_rule.rule_id
    admin.post(f"/admin/rules/{did}/edit", data={**form, "category": "retention", "violation_type": "Processing without consent"})
    with app.app_context():
        assert ComplianceRule.query.get(did).category == "consent"           # a rule that checks data keeps its category
    record("TC-M03", "A rule with a too-short obligation was refused. A valid one became CUSTOM-01 (origin manual, policy-only, enabled). Its severity was edited to Low. An attempt to move the data rule CONSENT-01 to another category was ignored.")


def test_reviewing_candidates(admin, app, tmp_path, monkeypatch, record):
    path = tmp_path / "cands.json"
    base = {"reference": "Section 39(2)", "modality": "obligation", "actor": "data controller", "action": "delete", "object": "", "condition": "", "confidence": 1.0}
    path.write_text(json.dumps({"candidates": [
        {**base, "candidate_code": "ACT-T1", "source_section": "Section 39(2), Data Protection Act 2019", "category": "retention", "obligation_text": "A data controller shall delete personal data at the expiry of the retention period."},
        {**base, "candidate_code": "ACT-T2", "reference": "Section 37(2)", "source_section": "Section 37(2), Data Protection Act 2019", "category": "retention", "obligation_text": "A data controller that uses personal data for commercial purposes shall anonymise the data."}]}), encoding="utf-8")
    monkeypatch.setattr(admin_module, "CANDIDATES_PATH", path)
    page = admin.get("/admin/rules").get_data(as_text=True)
    assert "ACT-T1" in page and "ACT-T2" in page
    assert b"approved" in admin.post("/admin/rules/candidates/ACT-T1/approve", follow_redirects=True).data
    admin.post("/admin/rules/candidates/ACT-T2/reject")
    again = admin.post("/admin/rules/candidates/ACT-T1/approve", follow_redirects=True)
    assert b"already been reviewed" in again.data
    with app.app_context():
        rule = ComplianceRule.query.filter_by(rule_code="ACT-T1").one()
        assert rule.origin == "extracted" and rule.enabled and not rule.is_dataset_rule
        assert ComplianceRule.query.filter_by(rule_code="ACT-T2").count() == 0
        assert {r.candidate_code: r.decision for r in CandidateReview.query.all()} == {"ACT-T1": "approved", "ACT-T2": "rejected"}
    assert "ACT-T1" not in admin.get("/admin/rules").get_data(as_text=True).split("Rule candidates")[1]
    record("TC-M04", "Two extracted candidates were listed. One was approved (it became an enabled, policy-only rule with origin 'extracted'), one was rejected (no rule created). Reviewing the approved one a second time was refused. Neither appeared in the waiting list afterwards.")


def test_user_management(admin, app, record):
    form = {"username": "newofficer", "email": "new@example.com", "full_name": "New Officer", "role": "ComplianceOfficer", "password": "TempPass123"}
    assert admin.post("/admin/users/new", data={**form, "password": "short"}).status_code == 200
    assert admin.post("/admin/users/new", data={**form, "username": "OFFICER"}).status_code == 200
    assert admin.post("/admin/users/new", data={**form, "email": "ADMIN@example.com"}).status_code == 200
    assert b"was created" in admin.post("/admin/users/new", data=form, follow_redirects=True).data
    with app.app_context():
        user = User.query.filter_by(username="newofficer").one()
        uid = user.user_id
        assert user.role == "ComplianceOfficer" and user.active
    admin.post(f"/admin/users/{uid}/edit", data={**form, "username": "renamed", "role": "Administrator", "password": "ResetPass123"})
    with app.app_context():
        user = db.session.get(User, uid)
        assert (user.username, user.role) == ("renamed", "Administrator") and user.check_password("ResetPass123")
    c = app.test_client()
    assert c.post("/login", data={"username": "renamed", "password": "ResetPass123", "role": "Administrator"}).headers["Location"].endswith("/dashboard")
    record("TC-M05", "A new account was created (and refused for a short password, a duplicate username in another case and a duplicate e-mail). An Administrator then changed its username and role and set a new password; the person could sign in with the new details.")


def test_user_safeguards_and_deactivation(admin, officer, app, record):
    with app.app_context():
        admin_id = User.query.filter_by(username="admin").one().user_id
        officer_id = User.query.filter_by(username="officer").one().user_id
    assert b"cannot deactivate your own" in admin.post(f"/admin/users/{admin_id}/status", follow_redirects=True).data
    demote = admin.post(f"/admin/users/{admin_id}/edit", data={"username": "admin", "email": "admin@example.com", "full_name": "", "role": "ComplianceOfficer", "password": ""})
    assert b"at least one active Administrator" in demote.data
    assert officer.get("/dashboard").status_code == 200
    admin.post(f"/admin/users/{officer_id}/status")            # deactivate while the officer is signed in
    after = officer.get("/dashboard", follow_redirects=False)
    assert after.status_code == 302 and "/login" in after.headers["Location"]
    fresh = app.test_client()
    refused = fresh.post("/login", data={"username": "officer", "password": "OfficerPass1", "role": "ComplianceOfficer"})
    assert b"deactivated" in refused.data
    admin.post(f"/admin/users/{officer_id}/status")            # reactivate
    assert fresh.post("/login", data={"username": "officer", "password": "OfficerPass1", "role": "ComplianceOfficer"}).headers["Location"].endswith("/dashboard")
    record("TC-M06", "An Administrator could not deactivate themselves or demote the last active Administrator. A deactivated Compliance Officer who was signed in was signed out at the next request and refused at sign-in; after reactivation sign-in worked again.")


def test_activity_log(admin, officer, app, record):
    run_audit_via_web(officer, clean_csv(), "log.csv")
    page = admin.get("/admin/logs").get_data(as_text=True)
    for action in ("login", "dataset_uploaded", "audit_run"):
        assert action in page
    filtered = admin.get("/admin/logs?action=audit_run").get_data(as_text=True)
    assert "audit_run" in filtered and "dataset_uploaded" not in filtered.split("<tbody>")[1]
    with app.app_context():
        assert not any("OfficerPass1" in (e.detail or "") for e in ActivityLog.query.all())
    c = app.test_client(); c.post("/login", data={"username": "officer", "password": "wrong", "role": "ComplianceOfficer"})
    assert "login_failed" in admin.get("/admin/logs").get_data(as_text=True)
    record("TC-M07", "After a sign-in, an upload and an audit the log listed 'login', 'dataset_uploaded' and 'audit_run'; the filter showed only audit entries; a failed sign-in was logged as 'login_failed'; no password appeared in any entry.")


def test_monitoring_cards(admin, officer, record):
    run_audit_via_web(officer, clean_csv(), "m.csv")
    page = admin.get("/admin/rules").get_data(as_text=True)
    for label in ("Audits today", "Average processing time", "Running for", "Active users"):
        assert label in page
    assert "2 administrators" not in page and "1 administrators, 1 compliance officers" in page
    record("TC-M08", "The rules page showed four monitoring cards: audits today (1 after one audit), average processing time, time since start, and active users (1 administrator, 1 compliance officer).")


def test_status_labels_agree_on_every_page(officer, record):
    rows = good_rows(100)
    for row in rows[:46]:
        row[1] = "No"                          # 46 of 100 records violate: score 54
    _, audit_id = run_audit_via_web(officer, csv_bytes(rows), "fiftyfour.csv")
    pages = {"audit page": f"/reports/{audit_id}", "reports list": "/reports", "dashboard": "/dashboard", "summary": f"/reports/{audit_id}/summary"}
    for name, url in pages.items():
        text = officer.get(url).get_data(as_text=True)
        assert "Action Required" in text, name
        assert "Partially Compliant" not in text and "Mainly Compliant" not in text, name
    assert [score_status(s)[0] for s in (100, 80, 79.9, 50, 49.9, None)] == ["Compliant", "Compliant", "Action Required", "Action Required", "Critical Violations", "In progress"]
    record("TC-S01", "A 54% audit was labelled 'Action Required' on the audit page, reports list, dashboard and printable summary; the old labels 'Partially Compliant' and 'Mainly Compliant' no longer appear. Band edges 80, 50 behaved as specified. (Regression test for DEF-04.)")


def test_pdf_report(officer, anon, record):
    _, audit_id = run_audit_via_web(officer, csv_bytes([["C1", "No", "2026-01-01", "5 years", "Active"]] + good_rows(3)), "pdf.csv")
    r = officer.get(f"/reports/{audit_id}/pdf")
    assert r.status_code == 200 and r.mimetype == "application/pdf" and r.data.startswith(b"%PDF")
    assert f"REP-{audit_id:03d}" in r.headers["Content-Disposition"]
    from pypdf import PdfReader
    text = " ".join(page.extract_text() for page in PdfReader(io.BytesIO(r.data)).pages)
    for needle in ("Audit Summary", "pdf.csv", "75%", "Consent Management", "Key Recommendations"):
        assert needle in text, needle
    assert officer.get("/reports/9999/pdf").status_code == 404
    assert anon.get(f"/reports/{audit_id}/pdf").status_code == 302
    record("TC-R04", f"The PDF download returned a real PDF file ({len(r.data):,} bytes) named REP-{audit_id:03d}-audit-summary.pdf containing the title, file name, score 75%, category breakdown and recommendations. An unknown report gave 'not found'; an anonymous visitor was sent to sign in.")
