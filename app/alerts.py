"""
Notifications for the bell menu in the top bar.

The bell appears on every page, so these alerts are worked out in one place and
injected into every template (see the context processor in app/__init__.py).
"""
from sqlalchemy import func

from app.extensions import db
from app.models import AuditRun, Dataset


def _plural(n, one, many):
    return f"{n} {one if n == 1 else many}"


def build_alerts():
    """Return a list of plain-text alert messages (empty if all is well)."""
    # Datasets with at least one audit scoring below 50% need urgent review.
    needs_review = (
        db.session.query(func.count(func.distinct(AuditRun.dataset_id)))
        .filter(AuditRun.compliance_score < 50)
        .scalar()
        or 0
    )

    # Datasets whose file failed (or has not yet passed) schema validation.
    unvalidated = (
        db.session.query(func.count(Dataset.dataset_id))
        .filter(Dataset.schema_validated.is_(False))
        .scalar()
        or 0
    )

    alerts = []
    if needs_review:
        alerts.append(
            f"{_plural(needs_review, 'dataset scored', 'datasets scored')} "
            "below 50% and needs immediate review."
        )
    if unvalidated:
        alerts.append(
            f"{_plural(unvalidated, 'dataset has', 'datasets have')} "
            "not passed schema validation."
        )
    return alerts