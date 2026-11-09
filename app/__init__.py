from datetime import datetime

from flask import Flask, flash, redirect, url_for
from flask_login import current_user, logout_user
from config import Config
from app.extensions import db, login_manager


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    if app.config["BEHIND_PROXY"]:
        # A live site must never run with the public, well-known development key.
        if app.config["SECRET_KEY"] == "dev-only-change-me":
            raise RuntimeError("Set a real SECRET_KEY before running the site online.")
        from werkzeug.middleware.proxy_fix import ProxyFix
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)
    db.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = "auth.login"
    login_manager.login_message = "Please log in to access this page."
    login_manager.login_message_category = "error"
    from app.models import User

    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(User, int(user_id))

    from app.routes.auth import auth_bp
    from app.routes.dashboard import dashboard_bp
    from app.routes.upload import upload_bp
    from app.routes.reports import reports_bp
    from app.routes.account import account_bp
    from app.routes.admin import admin_bp
    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(upload_bp)
    app.register_blueprint(reports_bp)
    app.register_blueprint(account_bp)
    app.register_blueprint(admin_bp)
    app.config["STARTED_AT"] = datetime.utcnow()

    @app.before_request
    def sign_out_deactivated_users():
        # An administrator can deactivate an account while its owner is still signed in.
        if current_user.is_authenticated and not current_user.is_active:
            logout_user()
            flash("This account has been deactivated. Contact an administrator.", "error")
            return redirect(url_for("auth.login"))
    from app.alerts import build_alerts

    @app.context_processor
    def inject_alerts():
        # Only logged-in users have a bell, so the login page skips the queries.
        if current_user.is_authenticated:
            return {"alerts": build_alerts()}
        return {}

    @app.errorhandler(413)
    def file_too_large(error):
        flash("That file is larger than the 50 MB limit.", "error")
        return redirect(url_for("upload.index"))

    @app.errorhandler(403)
    def forbidden(error):
        flash("You do not have permission to open that page.", "error")
        return redirect(url_for("dashboard.index"))

    return app
