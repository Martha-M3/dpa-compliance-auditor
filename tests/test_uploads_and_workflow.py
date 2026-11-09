"""Dataset and policy uploads, and the complete audit workflow: FR-02, FR-05, FR-07, FR-09, FR-12, IR-02, NFR-03."""
import io

from app.auditing import runner
from app.extensions import db
from app.models import AuditResult, AuditRun, ComplianceReport, ComplianceRule, Dataset, PolicyDocument
from helpers import POLICY_TEXT, csv_bytes, finish_upload, good_rows, make_docx, make_pdf, run_audit_via_web, upload_csv


def post_policy(client, content, name):
    return client.post("/upload/policy", data={"policy": (io.BytesIO(content), name)},
                       content_type="multipart/form-data", follow_redirects=True)


def violating_rows():
    rows = good_rows(6)
    rows[0][1] = "No"                                # consent violation
    rows[1][2], rows[1][3] = "2015-01-01", "1 year"  # retention violation
    rows[2][1], rows[2][2], rows[2][3] = "No", "2015-01-01", "1 year"  # both
    return rows


def test_valid_upload_is_stored_as_validated(officer, app, record):
    dataset_id = finish_upload(officer, csv_bytes(good_rows(10)), "customers.csv")
    page = officer.get(f"/upload/{dataset_id}")
    assert page.status_code == 200
    with app.app_context():
        dataset = db.session.get(Dataset, dataset_id)
        assert dataset.schema_validated is True and dataset.file_name == "customers.csv"
        assert (app.config["UPLOAD_FOLDER"] / f"{dataset_id}.csv").exists()
    record("TC-U01", f"Dataset {dataset_id} stored with schema_validated = True; file saved as {dataset_id}.csv; the result page opened (200).")


def test_invalid_upload_cannot_be_audited(officer, app, record):
    bad = good_rows(3)
    bad[1][1] = "Maybe"
    dataset_id = finish_upload(officer, csv_bytes(bad))
    response = officer.post(f"/upload/{dataset_id}/proceed", follow_redirects=True)
    assert b"failed validation, so it cannot be audited" in response.data
    with app.app_context():
        assert db.session.get(Dataset, dataset_id).schema_validated is False
        assert AuditRun.query.count() == 0
    record("TC-U02", "Stored with schema_validated = False. Forcing the 'proceed' request was refused by the server with 'failed validation, so it cannot be audited'; 0 audit runs exist.")


def test_non_csv_and_missing_file_are_rejected(officer, app, record):
    wrong = upload_csv(officer, b"hello", "notes.xlsx")
    wrong_page = officer.get(wrong.headers["Location"]).data
    none = officer.post("/upload", data={}, content_type="multipart/form-data", follow_redirects=True)
    assert b"Only CSV files are accepted" in wrong_page and b"choose a CSV file" in none.data
    with app.app_context():
        assert Dataset.query.count() == 0
    record("TC-U03", "A .xlsx file was refused ('Only CSV files are accepted'); a submission with no file was refused ('Please choose a CSV file'); 0 datasets stored.")


def test_oversized_upload_is_refused(officer, app, record):
    app.config["MAX_CONTENT_LENGTH"] = 1024  # shrink the 50 MB limit for the test
    response = upload_csv(officer, csv_bytes(good_rows(200)), "big.csv")
    page = officer.get(response.headers["Location"]).data
    assert response.status_code == 302 and b"larger than the 50 MB limit" in page
    with app.app_context():
        assert Dataset.query.count() == 0
    record("TC-U04", "With the limit lowered to 1 KB, a larger file was refused with 'larger than the 50 MB limit' and nothing was stored.")


def test_full_audit_workflow_is_saved(officer, app, record):
    dataset_id, audit_id = run_audit_via_web(officer, csv_bytes(violating_rows()), "mixed.csv")
    with app.app_context():
        audit = db.session.get(AuditRun, audit_id)
        results = AuditResult.query.filter_by(audit_id=audit_id).all()
        assert audit.dataset_id == dataset_id and audit.end_time is not None
        assert float(audit.compliance_score) == 50.0   # 3 of the 6 records have a violation
        assert len(results) == 4
        assert {r.violation_type for r in results} == {"Processing without consent", "Retained beyond retention period"}
        assert ComplianceReport.query.filter_by(audit_id=audit_id).count() == 1
        assert ComplianceRule.query.count() == 2
        assert all(r.rule_id and r.audit_id == audit_id for r in results)
    page = officer.get(f"/reports/{audit_id}")
    assert page.status_code == 200
    record("TC-W01", "Upload, validation and audit completed. Stored: 1 audit run (score 50.00, end time set), 4 audit results linked to the run and to a rule, 1 report record, 2 rules synchronised from the knowledge base. The audit page opened (200).")


def test_failed_audit_leaves_nothing_half_saved(officer, app, monkeypatch, record):
    dataset_id = finish_upload(officer, csv_bytes(violating_rows()))

    def explode(*args, **kwargs):
        raise RuntimeError("simulated failure")

    monkeypatch.setattr(runner, "audit_file", explode)
    response = officer.post(f"/upload/{dataset_id}/proceed", follow_redirects=True)
    assert b"The audit could not be completed" in response.data
    with app.app_context():
        assert AuditRun.query.count() == 0 and AuditResult.query.count() == 0 and ComplianceReport.query.count() == 0
    record("TC-W02", "A failure was forced inside the engine. The user saw 'The audit could not be completed'; 0 audit runs, 0 results and 0 reports were left in the database.")


def test_repeat_audit_keeps_history(officer, app, record):
    content = csv_bytes(violating_rows())
    dataset_id = finish_upload(officer, content)
    first = officer.post(f"/upload/{dataset_id}/proceed").headers["Location"]
    second = officer.post(f"/upload/{dataset_id}/proceed").headers["Location"]
    assert first != second
    with app.app_context():
        assert AuditRun.query.filter_by(dataset_id=dataset_id).count() == 2
    record("TC-W03", "Auditing the same dataset twice created 2 separate audit runs with different ids.")


def test_policy_documents_in_three_formats(officer, app, record):
    for content, name in ((POLICY_TEXT.encode(), "policy.txt"), (make_docx(POLICY_TEXT), "policy.docx"), (make_pdf(POLICY_TEXT), "policy.pdf")):
        page = post_policy(officer, content, name)
        assert b"Policy document uploaded" in page.data, name
    with app.app_context():
        documents = PolicyDocument.query.order_by(PolicyDocument.document_id).all()
        assert len(documents) == 3
        for doc in documents:
            assert "Consent is recorded before any personal data" in doc.content_text, doc.file_name
    record("TC-U05", "A .txt, a .docx and a .pdf policy were accepted; the text stored for each contained the policy sentence ('Consent is recorded before any personal data...').")


def test_unusable_policy_files_are_refused(officer, app, record):
    cases = {
        "scanned PDF with no text": (make_pdf(""), "scan.pdf", b"No readable text"),
        "too short text file": (b"short", "tiny.txt", b"No readable text"),
        "unsupported type": (b"MZ" + b"0" * 100, "program.exe", b"Only PDF, Word"),
        "damaged Word file": (b"this is not a zip file" * 10, "broken.docx", b"not a valid .docx"),
        "damaged PDF": (b"%PDF-1.4 garbage" * 10, "broken.pdf", b"could not be opened"),
    }
    seen = []
    for label, (content, name, expected) in cases.items():
        page = post_policy(officer, content, name)
        assert expected in page.data, (label, page.data[:300])
        seen.append(label)
    with app.app_context():
        assert PolicyDocument.query.count() == 0
    leftovers = list(app.config["POLICY_FOLDER"].glob("*")) if app.config["POLICY_FOLDER"].exists() else []
    assert leftovers == []
    record("TC-U06", "All 5 refused with a specific message (" + "; ".join(seen) + "); no database row and no file was left behind.")
