"""
Upload Data page (Figure 4.7, FR-01 / IR-02 / NFR-03).

Flow:  GET  /upload        -> show the upload form
       POST /upload        -> receive the CSV, validate it, save it, redirect
       GET  /upload/<id>   -> show the validation result for that dataset

Redirecting after a POST (the "Post/Redirect/Get" pattern) means refreshing the
result page never re-submits the file.
"""
from flask import (
    Blueprint, current_app, flash, redirect, render_template, request, url_for,
)
from flask_login import current_user
from werkzeug.utils import secure_filename

from app.auditing.dataset_schema import REQUIRED_COLUMNS, validate_dataset
from app.auditing.runner import run_audit
from app.decorators import role_required
from app.extensions import db
from app.models import Dataset

upload_bp = Blueprint("upload", __name__)


def stored_path(dataset_id):
    """Where a dataset's file lives on disk: uploads/datasets/<id>.csv"""
    return current_app.config["UPLOAD_FOLDER"] / f"{dataset_id}.csv"


@upload_bp.route("/upload", methods=["GET", "POST"])
@role_required("ComplianceOfficer")
def index():
    if request.method == "POST":
        return handle_upload()
    return render_page()

def format_size(num_bytes):
    """12345678 -> '11.8 MB' (for display on the page)."""
    if num_bytes < 1024:
        return f"{num_bytes} B"
    if num_bytes < 1024 * 1024:
        return f"{num_bytes / 1024:.1f} KB"
    return f"{num_bytes / (1024 * 1024):.1f} MB"

def render_page(dataset=None, validation=None, file_size=None):
    """The same template shows the empty form, or the form plus a result."""
    recent = Dataset.query.order_by(Dataset.upload_date.desc()).limit(5).all()
    return render_template(
        "upload.html",
        dataset=dataset,
        validation=validation,
        file_size=file_size,
        recent=recent,
        columns=REQUIRED_COLUMNS,
    )


def handle_upload():
    """Receive the file, validate it, store it, and redirect to the result page."""
    uploaded = request.files.get("dataset")

    # 1. Did the user actually choose a file?
    if uploaded is None or uploaded.filename == "":
        flash("Please choose a CSV file to upload.", "error")
        return redirect(url_for("upload.index"))

    # 2. Is it a CSV? (IR-02) We only check the ending here; the real test is
    #    whether validate_dataset() can read it.
    original_name = secure_filename(uploaded.filename) or "dataset.csv"
    if not original_name.lower().endswith(".csv"):
        flash("Only CSV files are accepted. Save your spreadsheet as CSV (UTF-8) and try again.", "error")
        return redirect(url_for("upload.index"))

    # 3. Create the database row first, so we know the dataset's ID.
    dataset = Dataset(
        file_name=original_name[:255],
        schema_validated=False,
        uploaded_by=current_user.user_id,
    )
    db.session.add(dataset)
    db.session.flush()  # asks the database for the new ID without finishing the save

    # 4. Save the file under that ID, then validate the saved copy.
    try:
        folder = current_app.config["UPLOAD_FOLDER"]
        folder.mkdir(parents=True, exist_ok=True)
        path = stored_path(dataset.dataset_id)
        uploaded.save(path)
        result = validate_dataset(path)
    except OSError:
        db.session.rollback()
        flash("The file could not be saved on the server. Please try again.", "error")
        return redirect(url_for("upload.index"))

    # 5. Record whether the dataset passed, and finish the save.
    dataset.schema_validated = result.passed
    db.session.commit()

    return redirect(url_for("upload.result", dataset_id=dataset.dataset_id))


@upload_bp.route("/upload/<int:dataset_id>")
@role_required("ComplianceOfficer")
def result(dataset_id):
    dataset = db.get_or_404(Dataset, dataset_id)
    path = stored_path(dataset_id)

    # The check results are not stored in the database; running the checks again
    # on the saved file is quick and always gives the current answer.
    if not path.exists():
        flash("The stored file for this dataset is missing. Please upload it again.", "error")
        return redirect(url_for("upload.index"))

    return render_page(dataset=dataset, validation=validate_dataset(path), file_size=format_size(path.stat().st_size))

@upload_bp.route("/upload/<int:dataset_id>/proceed", methods=["POST"])
@role_required("ComplianceOfficer")
def proceed(dataset_id):
    """
    "Proceed to Automated Compliance Audit". The rule is enforced HERE, on the
    server, because a disabled button in the browser can be bypassed.
    """
    dataset = db.get_or_404(Dataset, dataset_id)

    if not dataset.schema_validated:
        flash(
            "This dataset failed validation, so it cannot be audited. "
            "Fix the file and upload it again.",
            "error",
        )
        return redirect(url_for("upload.result", dataset_id=dataset_id))

    # Run the audit. Whatever goes wrong, the user gets a message, not a crash.
    try:
        audit, outcome = run_audit(dataset, current_user, stored_path(dataset_id))
    except Exception:
        db.session.rollback()
        current_app.logger.exception("Audit failed for dataset %s", dataset_id)
        flash("The audit could not be completed. Please try again.", "error")
        return redirect(url_for("upload.result", dataset_id=dataset_id))

    flash(
        f"Audit complete: compliance score {audit.compliance_score}%, "
        f"{len(outcome.findings)} violations found in {outcome.violating_records} records.",
        "success",
    )
    return redirect(url_for("upload.result", dataset_id=dataset_id))