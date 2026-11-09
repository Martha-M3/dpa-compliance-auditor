"""Writing to the system log. Call log_event(...) after something worth recording has happened."""
from flask import current_app
from flask_login import current_user

from app.extensions import db
from app.models import ActivityLog


def log_event(action, detail="", user=None):
    """
    Add one line to the log. It never raises: a problem with logging must not break the action
    being logged. `user` can be passed when nobody is signed in yet (for example at sign-in).
    """
    try:
        who = user or (current_user if current_user.is_authenticated else None)
        db.session.add(ActivityLog(
            user_id=who.user_id if who else None,
            username=who.username if who else None,
            action=action,
            detail=(detail or "")[:300],
        ))
        db.session.flush()
    except Exception:  # pragma: no cover - logging must never break the request
        current_app.logger.exception("Could not write to the activity log")
