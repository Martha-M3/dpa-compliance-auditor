"""Audit pages, reports, dashboard and profile: FR-13, FR-14, FR-15 and the account features."""
import io
import re

from app.extensions import db
from app.models import User
from helpers import POLICY_TEXT, captured_context, csv_bytes, good_rows, run_audit_via_web


def bad_rows(count_bad=2, total=8):
    rows = good_rows(total)
    for row in rows[:count_bad]:
        row[1] = "No"
    return rows


def test_audit_page_lists_findings_and_recommendations(officer, admin, record):
    _, audit_id = run_audit_via_web(officer, csv_bytes(bad_rows()), "a.csv")
    for client in (officer, admin):
        page = client.get(f"/reports/{audit_id}")
        assert page.status_code == 200
        text = page.get_data(as_text=True)
        assert "Customer00001" in text and "Customer00002" in text and "Stop processing the record" in text
    record("TC-R01", "Both roles opened the audit page. It listed the 2 affected records (Customer00001, Customer00002), their rule and the recommended action.")


def test_summary_page_content(officer, record):
    _, audit_id = run_audit_via_web(officer, csv_bytes(bad_rows()), "a.csv")
    text = officer.get(f"/reports/{audit_id}/summary").get_data(as_text=True)
    for needle in ("Executive Summary", "Score Breakdown", "Key Recommendations", "75%", "Consent Management"):
        assert needle in text, needle
    record("TC-R02", "The printable summary contained the executive summary, score breakdown, severity table, recommendations and the score 75% (2 of 8 records violating).")


def test_reports_list_filters_and_unknown_ids(officer, record):
    run_audit_via_web(officer, csv_bytes(bad_rows(0)), "clean.csv")       # score 100
    run_audit_via_web(officer, csv_bytes(bad_rows(6)), "dirty.csv")       # score 25
    everything = officer.get("/reports").get_data(as_text=True)
    only_dirty = officer.get("/reports?dataset=dirty.csv").get_data(as_text=True)
    critical = officer.get("/reports?level=critical").get_data(as_text=True)
    compliant = officer.get("/reports?level=compliant").get_data(as_text=True)
    assert "clean.csv" in everything and "dirty.csv" in everything
    assert "clean.csv</strong>" not in only_dirty and "dirty.csv" in only_dirty
    assert "dirty.csv" in critical and "clean.csv</strong>" not in critical
    assert "clean.csv" in compliant and "dirty.csv</strong>" not in compliant
    assert officer.get("/reports/9999").status_code == 404
    assert officer.get("/reports/9999/summary").status_code == 404
    record("TC-R03", "Without filters both audits were listed. Filtering by dataset name, by 'Critical Violations' and by 'Compliant' each returned only the matching audit. Unknown report numbers returned 404.")


def test_empty_system_dashboard(officer, record):
    with captured_context(officer.application) as contexts:
        page = officer.get("/dashboard")
    context = contexts[0]
    assert page.status_code == 200 and context["total_audits"] == 0 and context["overall_health"] is None
    assert "No audits have been run yet" in page.get_data(as_text=True)
    record("TC-D01", "With no audits: 0 audits, no score, and the page said 'No audits have been run yet'.")


def test_dashboard_figures_match_stored_results(officer, record):
    run_audit_via_web(officer, csv_bytes(bad_rows(2, 8)), "one.csv")      # 75%
    with captured_context(officer.application) as contexts:
        officer.get("/dashboard")
    c = contexts[0]
    assert c["total_audits"] == 1 and c["active_violations"] == 2 and c["critical_violations"] == 2
    assert c["overall_health"] == 75 and c["category_breakdown"][0]["label"] == "Consent Management"
    record("TC-D02", f"1 audit; {c['active_violations']} violations (all Critical); health score {c['overall_health']}%; top category {c['category_breakdown'][0]['label']}.")


def test_dashboard_counts_each_dataset_once(officer, record):
    """Regression test for defect DEF-01: re-auditing a dataset must not double its violations."""
    dataset_id, _ = run_audit_via_web(officer, csv_bytes(bad_rows(2, 8)), "same.csv")
    officer.post(f"/upload/{dataset_id}/proceed")
    officer.post(f"/upload/{dataset_id}/proceed")           # the same dataset audited 3 times
    run_audit_via_web(officer, csv_bytes(bad_rows(4, 8)), "other.csv")   # 50%, 4 violations
    with captured_context(officer.application) as contexts:
        officer.get("/dashboard")
    c = contexts[0]
    assert c["total_audits"] == 4 and c["audited_datasets"] == 2
    assert c["active_violations"] == 6, c["active_violations"]       # 2 + 4, not 2+2+2+4
    assert c["overall_health"] == 62, c["overall_health"]            # mean of 75 and 50, rounded
    assert c["category_breakdown"][0]["pct"] == 100
    assert c["total_category_violations"] == 6
    record("TC-D03", "Dataset 'same.csv' was audited 3 times and 'other.csv' once (4 audit runs). The dashboard showed 6 current violations (2 + 4), not 10; health 62% (mean of 75 and 50); 6 violations in the category chart.")


def test_profile_details_and_validation(officer, app, record):
    ok = officer.post("/profile/details", data={
        "full_name": "  Martha   Muinde ", "email": "officer@example.com", "phone": "+254 712 345 678",
        "job_title": "Compliance Officer", "department": "ICT",
    }, follow_redirects=True)
    assert b"Your details have been updated" in ok.data
    with app.app_context():
        user = User.query.filter_by(username="officer").one()
        assert user.full_name == "Martha Muinde" and user.display_name == "Martha Muinde" and user.first_name == "Martha"
    refused = []
    for label, change in {"bad phone": {"phone": "abc"}, "bad email": {"email": "nope"},
                          "email of another user": {"email": "ADMIN@example.com"}, "name too long": {"full_name": "x" * 151}}.items():
        data = {"full_name": "A", "email": "officer@example.com", "phone": "", "job_title": "", "department": "", **change}
        response = officer.post("/profile/details", data=data)
        assert response.status_code == 200, label
        refused.append(label)
    officer.post("/profile/details", data={"full_name": "", "email": "officer@example.com", "phone": "", "job_title": "", "department": ""})
    with app.app_context():
        user = User.query.filter_by(username="officer").one()
        assert user.full_name is None and user.display_name == "officer"
    record("TC-P01", "Details saved with spaces tidied. Refused: " + ", ".join(refused) + ". Empty boxes were stored as no value and the name fell back to the username.")


def test_password_change_rules(officer, app, record):
    def change(current, new, confirm):
        return officer.post("/profile/password", data={"current_password": current, "new_password": new, "confirm_password": confirm}, follow_redirects=True).data
    assert b"current password is not correct" in change("wrong", "NewPass123", "NewPass123")
    assert b"at least 8" in change("OfficerPass1", "abc", "abc")
    assert b"do not match" in change("OfficerPass1", "NewPass123", "Other12345")
    assert b"must be different" in change("OfficerPass1", "OfficerPass1", "OfficerPass1")
    assert b"password has been changed" in change("OfficerPass1", "NewPass123", "NewPass123")
    with app.app_context():
        user = User.query.filter_by(username="officer").one()
        assert user.check_password("NewPass123") and not user.check_password("OfficerPass1")
    record("TC-P02", "Wrong current password, short password, mismatch and unchanged password were each refused; a valid change was saved and the old password stopped working.")


def png(size=2000):
    return b"\x89PNG\r\n\x1a\n" + b"0" * size


def post_photo(client, content, name):
    return client.post("/profile/photo", data={"photo": (io.BytesIO(content), name)},
                       content_type="multipart/form-data", follow_redirects=True).data


def test_profile_photo_accepts_real_images_only(officer, app, record):
    accepted = []
    for content, name in ((png(), "a.png"), (b"\xff\xd8\xff" + b"0" * 500, "a.jpg"), (b"RIFF\x00\x00\x00\x00WEBPVP8 " + b"0" * 100, "a.webp")):
        assert b"picture has been updated" in post_photo(officer, content, name), name
        accepted.append(name.split(".")[1].upper())
    refused = []
    for label, content, name in (
        ("text renamed .png", b"<script>alert(1)</script>", "evil.png"),
        ("SVG", b'<svg xmlns="http://www.w3.org/2000/svg"/>', "x.svg"),
        ("GIF", b"GIF89a" + b"0" * 100, "x.gif"),
        ("3 MB image", png(3 * 1024 * 1024), "big.png"),
    ):
        assert (b"not a PNG, JPG or WebP" in post_photo(officer, content, name)) or (b"too large" in post_photo(officer, content, name)), label
        refused.append(label)
    folder = app.config["PHOTO_FOLDER"]
    assert len(list(folder.iterdir())) == 1  # each new photo replaced (deleted) the previous one
    record("TC-P03", "Accepted " + ", ".join(accepted) + " (by file content, not by name). Refused " + ", ".join(refused) + ". Only 1 photo file remained on disk after 3 replacements.")


def test_photo_access_and_removal(officer, anon, app, record):
    post_photo(officer, png(), "a.png")
    with app.app_context():
        user_id = User.query.filter_by(username="officer").one().user_id
    assert officer.get(f"/photos/{user_id}").status_code == 200
    assert anon.get(f"/photos/{user_id}").status_code == 302
    assert officer.get("/photos/9999").status_code == 404
    officer.post("/profile/photo/remove")
    assert officer.get(f"/photos/{user_id}").status_code == 404
    assert list(app.config["PHOTO_FOLDER"].iterdir()) == []
    record("TC-P04", "The photo was served to a signed-in user (200), redirected to login for an anonymous visitor, 404 for an unknown user; after 'Remove picture' it returned 404 and the file was deleted from disk.")
