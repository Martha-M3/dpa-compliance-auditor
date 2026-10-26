"""
Sign in, sign out, sign up, "forgot password" (FR-01) and sign in with Google.

Every sign-in method ends the same way: login_user(user). The role always comes
from the account stored in the database, never from the browser.
"""
import hashlib
import hmac
import re
import secrets

from flask import (
    Blueprint, current_app, flash, redirect, render_template, request, session, url_for,
)
from flask_login import current_user, login_required, login_user, logout_user
from itsdangerous import BadSignature, URLSafeTimedSerializer
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError

from app import google_auth
from app.extensions import db
from app.mailer import send_email
from app.models import User

auth_bp = Blueprint("auth", __name__)
ROLE_NAMES = {"Administrator": "an Administrator", "ComplianceOfficer": "a Compliance Officer"}
MIN_PASSWORD_LENGTH = 8
USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9._-]{3,50}$")  # letters, digits, . _ - only
EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")  # something@something.something


def render_login(selected_role):
    # The Google button only appears once the Google settings have been filled in.
    return render_template(
        "login.html", selected_role=selected_role, google_enabled=google_auth.is_configured()
    )


@auth_bp.route("/")
def index():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard.index"))
    return redirect(url_for("auth.login"))


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard.index"))
    selected_role = request.form.get("role", "ComplianceOfficer")
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        user = User.query.filter_by(username=username).first()
        if user is None or not user.check_password(password):
            flash("Incorrect username or password.", "error")
            return render_login(selected_role)
        if user.role != selected_role:
            flash(f"This account is not registered as {ROLE_NAMES.get(selected_role, selected_role)}.", "error")
            return render_login(selected_role)
        login_user(user)
        return redirect(url_for("dashboard.index"))
    return render_login(selected_role)


@auth_bp.route("/logout")
@login_required
def logout():
    logout_user()
    flash("You have been logged out.", "success")
    return redirect(url_for("auth.login"))


# ---------------------------------------------------------------------------
# Sign up
# ---------------------------------------------------------------------------
# Anyone can create an account, but only as a Compliance Officer. The role is set here
# on the server and is never read from the form, so nobody can sign themselves up as an
# Administrator. Administrators are created by the person running the system
# (python scripts/add_user.py).

@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard.index"))

    form = {"username": "", "email": ""}  # remembered so the page is not wiped after a mistake
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        confirm = request.form.get("confirm", "")
        form = {"username": username, "email": email}

        error = None
        if not USERNAME_PATTERN.match(username):
            error = "The username must be 3 to 50 characters: letters, numbers, dots, dashes or underscores."
        elif not EMAIL_PATTERN.match(email) or len(email) > 255:
            error = "Please enter a valid email address."
        elif len(password) < MIN_PASSWORD_LENGTH:
            error = f"The password must be at least {MIN_PASSWORD_LENGTH} characters long."
        elif password != confirm:
            error = "The two passwords do not match."
        elif User.query.filter(func.lower(User.username) == username.lower()).first():
            error = "That username is already taken. Please choose another."
        elif User.query.filter(func.lower(User.email) == email).first():
            error = "An account with that email already exists. Try signing in, or use Forgot password."

        if error is None:
            user = User(username=username, email=email, role="ComplianceOfficer")
            user.set_password(password)
            db.session.add(user)
            try:
                db.session.commit()
            except IntegrityError:
                # Two people took the same name at the same moment: the database said no.
                db.session.rollback()
                error = "That username or email is already in use. Please try different ones."
            else:
                flash("Your account has been created. You can now sign in.", "success")
                return redirect(url_for("auth.login"))

        flash(error, "error")
    return render_template("register.html", form=form, min_length=MIN_PASSWORD_LENGTH)


# ---------------------------------------------------------------------------
# Forgot password
# ---------------------------------------------------------------------------
# The reset link contains a signed token. "Signed" means nobody can invent or edit
# one without our SECRET_KEY. It stops working after 30 minutes, and also as soon as
# the password changes (the token holds a fingerprint of the old password), so a
# link can only be used once.

def _serializer():
    return URLSafeTimedSerializer(current_app.config["SECRET_KEY"], salt="password-reset")


def _fingerprint(user):
    return hashlib.sha256(user.password_hash.encode()).hexdigest()[:16]


def make_reset_token(user):
    return _serializer().dumps({"uid": user.user_id, "fp": _fingerprint(user)})


def user_from_reset_token(token):
    """The user a reset link belongs to, or None if it is invalid, expired or already used."""
    try:
        data = _serializer().loads(token, max_age=current_app.config["RESET_TOKEN_MAX_AGE"])
    except BadSignature:  # also covers an expired link
        return None
    if not isinstance(data, dict):
        return None
    user = db.session.get(User, data.get("uid"))
    if user is None or not hmac.compare_digest(str(data.get("fp")), _fingerprint(user)):
        return None
    return user


@auth_bp.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard.index"))
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        user = User.query.filter(func.lower(User.email) == email).first() if email else None
        if user is not None:
            link = url_for("auth.reset_password", token=make_reset_token(user), _external=True)
            minutes = current_app.config["RESET_TOKEN_MAX_AGE"] // 60
            try:
                send_email(
                    user.email,
                    "Reset your KenyaDPA Audit password",
                    f"Hello {user.username},\n\n"
                    f"Use this link to choose a new password. It works for {minutes} minutes "
                    f"and can be used once:\n\n{link}\n\n"
                    "If you did not ask for this, ignore this email. Your password has not changed.\n",
                )
            except Exception:
                current_app.logger.exception("Could not send the reset email for user %s", user.user_id)
        # The same answer whether or not the email exists, so this page cannot be used
        # to find out who has an account.
        flash("If an account exists for that email address, a reset link has been sent to it.", "success")
        return redirect(url_for("auth.forgot_password"))
    return render_template("forgot_password.html")


@auth_bp.route("/reset-password/<token>", methods=["GET", "POST"])
def reset_password(token):
    user = user_from_reset_token(token)
    if user is None:
        flash("This reset link is invalid or has expired. Please request a new one.", "error")
        return redirect(url_for("auth.forgot_password"))

    if request.method == "POST":
        password = request.form.get("password", "")
        confirm = request.form.get("confirm", "")
        if len(password) < MIN_PASSWORD_LENGTH:
            flash(f"The password must be at least {MIN_PASSWORD_LENGTH} characters long.", "error")
        elif password != confirm:
            flash("The two passwords do not match.", "error")
        else:
            user.set_password(password)
            db.session.commit()
            flash("Your password has been updated. You can now sign in.", "success")
            return redirect(url_for("auth.login"))
    return render_template("reset_password.html", min_length=MIN_PASSWORD_LENGTH)


# ---------------------------------------------------------------------------
# Sign in with Google
# ---------------------------------------------------------------------------
# Google only proves WHO the person is. We still decide whether they may enter: their
# verified Google email must match an account an administrator has already created.

def google_redirect_uri():
    # Must match, character for character, a "redirect URI" registered in Google Cloud.
    return current_app.config["GOOGLE_REDIRECT_URI"] or url_for("auth.google_callback", _external=True)


@auth_bp.route("/auth/google")
def google_login():
    if not google_auth.is_configured():
        flash("Google sign-in is not set up on this server.", "error")
        return redirect(url_for("auth.login"))
    state = secrets.token_urlsafe(32)  # a random value that proves the reply is to OUR request
    session["google_state"] = state
    return redirect(google_auth.build_login_url(google_redirect_uri(), state))


@auth_bp.route("/auth/google/callback")
def google_callback():
    expected = session.pop("google_state", None)
    if not expected or not hmac.compare_digest(expected, request.args.get("state", "")):
        flash("Google sign-in could not be verified. Please try again.", "error")
        return redirect(url_for("auth.login"))
    if request.args.get("error") or not request.args.get("code"):
        flash("Google sign-in was cancelled.", "error")
        return redirect(url_for("auth.login"))

    try:
        profile = google_auth.fetch_google_user(request.args["code"], google_redirect_uri())
    except google_auth.GoogleAuthError as error:
        flash(str(error), "error")
        return redirect(url_for("auth.login"))

    email = (profile.get("email") or "").strip().lower()
    if not email or profile.get("email_verified") is not True:
        flash("Your Google email address is not verified, so it cannot be used to sign in.", "error")
        return redirect(url_for("auth.login"))

    user = User.query.filter(func.lower(User.email) == email).first()
    if user is None:
        flash(f"No account is registered for {email}. Ask an administrator to add you.", "error")
        return redirect(url_for("auth.login"))

    login_user(user)
    return redirect(url_for("dashboard.index"))