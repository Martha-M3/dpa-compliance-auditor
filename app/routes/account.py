"""
"My profile" page (every signed-in user).

Here a person can see their own account, update their personal details, add or remove a
profile picture, and change their password. The page always shows the account that is
signed in: there is no user ID in the address, so nobody can open someone else's profile
by editing the link. (Usernames can only be changed by an administrator.)
"""
import re
import secrets

from flask import (
    Blueprint, abort, current_app, flash, redirect, render_template, request,
    send_from_directory, url_for,
)
from flask_login import current_user, login_required
from sqlalchemy import func

from app.extensions import db
from app.models import AuditRun, Dataset, User
from app.routes.auth import EMAIL_PATTERN, MIN_PASSWORD_LENGTH

account_bp = Blueprint("account", __name__)

PHONE_PATTERN = re.compile(r"^\+?[0-9][0-9 ()-]{5,18}$")  # e.g. +254 712 345 678 or 0712 345678


def build_stats():
    """The three small figures shown on the profile. They differ by role."""
    if current_user.role == "Administrator":
        return [
            ("Users in the system", User.query.count()),
            ("Audits in the system", AuditRun.query.count()),
            ("Datasets uploaded", Dataset.query.count()),
        ]
    last = (
        db.session.query(func.max(AuditRun.start_time))
        .filter(AuditRun.run_by == current_user.user_id)
        .scalar()
    )
    return [
        ("Datasets uploaded", Dataset.query.filter_by(uploaded_by=current_user.user_id).count()),
        ("Audits run", AuditRun.query.filter_by(run_by=current_user.user_id).count()),
        ("Last audit", last.strftime("%d %b %Y") if last else "None yet"),
    ]


def render_profile(form=None):
    """Show the page. `form` holds what the person just typed, so a mistake does not wipe it."""
    if form is None:
        form = {
            "full_name": current_user.full_name or "",
            "email": current_user.email or "",
            "phone": current_user.phone or "",
            "job_title": current_user.job_title or "",
            "department": current_user.department or "",
        }
    return render_template(
        "profile.html",
        form=form,
        stats=build_stats(),
        member_since=current_user.created_at.strftime("%d %B %Y"),
        min_length=MIN_PASSWORD_LENGTH,
    )


@account_bp.route("/profile")
@login_required
def profile():
    return render_profile()


# ---------------------------------------------------------------------------
# Personal details
# ---------------------------------------------------------------------------

@account_bp.route("/profile/details", methods=["POST"])
@login_required
def change_details():
    form = {
        "full_name": " ".join(request.form.get("full_name", "").split()),  # tidy stray spaces
        "email": request.form.get("email", "").strip().lower(),
        "phone": request.form.get("phone", "").strip(),
        "job_title": request.form.get("job_title", "").strip(),
        "department": request.form.get("department", "").strip(),
    }

    error = None
    if len(form["full_name"]) > 150:
        error = "The full name is too long (150 characters at most)."
    elif not EMAIL_PATTERN.match(form["email"]) or len(form["email"]) > 255:
        error = "Please enter a valid email address."
    elif form["phone"] and not PHONE_PATTERN.match(form["phone"]):
        error = "Please enter a valid phone number, for example +254 712 345 678."
    elif len(form["job_title"]) > 100 or len(form["department"]) > 100:
        error = "The job title and department must each be 100 characters or fewer."
    elif User.query.filter(
        func.lower(User.email) == form["email"], User.user_id != current_user.user_id
    ).first():
        error = "That email address belongs to another account."

    if error:
        flash(error, "error")
        return render_profile(form)

    # An empty box is saved as "nothing" (NULL), not as an empty piece of text.
    current_user.full_name = form["full_name"] or None
    current_user.email = form["email"]
    current_user.phone = form["phone"] or None
    current_user.job_title = form["job_title"] or None
    current_user.department = form["department"] or None
    db.session.commit()
    flash("Your details have been updated.", "success")
    return redirect(url_for("account.profile"))


# ---------------------------------------------------------------------------
# Profile picture
# ---------------------------------------------------------------------------
# We never trust the file name or the "type" the browser claims. The first few bytes of
# a real picture identify its format, so we read those. SVG is not allowed, because an
# SVG file can carry scripts.

def detect_image_type(data):
    """'png', 'jpg' or 'webp' if the bytes really are that kind of picture, else None."""
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if data.startswith(b"\xff\xd8\xff"):
        return "jpg"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    return None


def delete_photo_file(filename):
    if not filename:
        return
    try:
        (current_app.config["PHOTO_FOLDER"] / filename).unlink()
    except OSError:
        pass  # already gone: nothing to do


@account_bp.route("/profile/photo", methods=["POST"])
@login_required
def upload_photo():
    uploaded = request.files.get("photo")
    if uploaded is None or not uploaded.filename:
        flash("Choose a picture first.", "error")
        return redirect(url_for("account.profile"))

    limit = current_app.config["MAX_PHOTO_BYTES"]
    data = uploaded.read(limit + 1)  # read one byte too many, to notice a file that is too big
    if len(data) > limit:
        flash(f"That picture is too large. The limit is {limit // (1024 * 1024)} MB.", "error")
        return redirect(url_for("account.profile"))
    extension = detect_image_type(data)
    if extension is None:
        flash("That file is not a PNG, JPG or WebP picture.", "error")
        return redirect(url_for("account.profile"))

    folder = current_app.config["PHOTO_FOLDER"]
    folder.mkdir(parents=True, exist_ok=True)
    # A random name: it cannot be guessed, and a new picture is never mistaken for the
    # old one by the browser's cache.
    filename = f"user{current_user.user_id}_{secrets.token_hex(8)}.{extension}"
    (folder / filename).write_bytes(data)

    old = current_user.photo_filename
    current_user.photo_filename = filename
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        delete_photo_file(filename)
        raise
    delete_photo_file(old)
    flash("Your profile picture has been updated.", "success")
    return redirect(url_for("account.profile"))


@account_bp.route("/profile/photo/remove", methods=["POST"])
@login_required
def remove_photo():
    old = current_user.photo_filename
    if old:
        current_user.photo_filename = None
        db.session.commit()
        delete_photo_file(old)
        flash("Your profile picture has been removed.", "success")
    return redirect(url_for("account.profile"))


@account_bp.route("/photos/<int:user_id>")
@login_required
def photo(user_id):
    """Send a user's picture. The file name comes from the database, never from the address."""
    user = db.session.get(User, user_id)
    if user is None or not user.photo_filename:
        abort(404)
    response = send_from_directory(current_app.config["PHOTO_FOLDER"], user.photo_filename)
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


# ---------------------------------------------------------------------------
# Password
# ---------------------------------------------------------------------------

@account_bp.route("/profile/password", methods=["POST"])
@login_required
def change_password():
    current = request.form.get("current_password", "")
    new = request.form.get("new_password", "")
    confirm = request.form.get("confirm_password", "")

    # The current password is asked for so that someone who finds an unlocked,
    # signed-in computer cannot quietly lock the real owner out.
    if not current_user.check_password(current):
        flash("Your current password is not correct.", "error")
    elif len(new) < MIN_PASSWORD_LENGTH:
        flash(f"The new password must be at least {MIN_PASSWORD_LENGTH} characters long.", "error")
    elif new != confirm:
        flash("The two new passwords do not match.", "error")
    elif new == current:
        flash("The new password must be different from the current one.", "error")
    else:
        current_user.set_password(new)
        db.session.commit()
        flash("Your password has been changed.", "success")
        return redirect(url_for("account.profile"))
    return render_profile()
