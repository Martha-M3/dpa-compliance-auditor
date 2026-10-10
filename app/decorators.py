"""
Access-control helpers (NFR-02, FR-01).

login_required only checks WHO you are (logged in or not).
role_required also checks WHAT you are allowed to do (your role).
"""
from functools import wraps

from flask import abort
from flask_login import current_user, login_required


def role_required(*allowed_roles):
    """
    Protect a view so only users with one of the given roles can open it.

    Usage:
        @upload_bp.route("/upload")
        @role_required("ComplianceOfficer")
        def upload_page():
            ...
    """
    def decorator(view):
        @wraps(view)
        def wrapper(*args, **kwargs):
            # By the time we get here, login_required has confirmed the user is
            # logged in, so current_user is a real User with a role.
            if current_user.role not in allowed_roles:
                abort(403)  # 403 = "Forbidden": we know who you are, but no.
            return view(*args, **kwargs)

        # Wrap with login_required so anonymous visitors are sent to the login
        # page first, and only logged-in users reach the role check above.
        return login_required(wrapper)

    return decorator