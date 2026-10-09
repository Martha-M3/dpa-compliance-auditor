from flask import Blueprint, render_template, redirect, url_for, request, flash
from flask_login import login_user, logout_user, login_required, current_user

from app.models import User

auth_bp = Blueprint("auth", __name__)

ROLE_NAMES = {
    "Administrator": "an Administrator",
    "ComplianceOfficer": "a Compliance Officer",
}


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
            return render_template("login.html", selected_role=selected_role)

        if user.role != selected_role:
            flash(
                f"This account is not registered as {ROLE_NAMES.get(selected_role, selected_role)}.",
                "error",
            )
            return render_template("login.html", selected_role=selected_role)

        login_user(user)
        return redirect(url_for("dashboard.index"))

    return render_template("login.html", selected_role=selected_role)


@auth_bp.route("/logout")
@login_required
def logout():
    logout_user()
    flash("You have been logged out.", "success")
    return redirect(url_for("auth.login"))