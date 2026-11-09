import os
from pathlib import Path
from urllib.parse import quote_plus
from dotenv import load_dotenv

load_dotenv()


BASE_DIR = Path(__file__).resolve().parent


def database_uri():
    """
    Where the database is.
    - On a host such as Render, one setting called DATABASE_URL holds the whole address.
    - On your own computer, the address is built from the DB_* lines in your .env file.
    """
    url = os.environ.get("DATABASE_URL", "").strip()
    if url:
        # Hosts write "postgres://..." or "postgresql://..."; SQLAlchemy also wants the
        # name of the driver program (psycopg2) in front.
        for start in ("postgres://", "postgresql://"):
            if url.startswith(start):
                return "postgresql+psycopg2://" + url[len(start):]
        return url
    user = os.environ.get("DB_USER")
    password = os.environ.get("DB_PASSWORD", "")
    host = os.environ.get("DB_HOST", "localhost")
    port = os.environ.get("DB_PORT", "5432")
    name = os.environ.get("DB_NAME")
    return f"postgresql+psycopg2://{user}:{quote_plus(password)}@{host}:{port}/{name}"


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-only-change-me")
    SQLALCHEMY_DATABASE_URI = database_uri()
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    UPLOAD_FOLDER = BASE_DIR / "uploads" / "datasets"
    POLICY_FOLDER = BASE_DIR / "uploads" / "policies"
    PHOTO_FOLDER = BASE_DIR / "uploads" / "profile_photos"
    MAX_PHOTO_BYTES = 2 * 1024 * 1024  # profile pictures may be at most 2 MB
    MAX_CONTENT_LENGTH = 50 * 1024 * 1024
    SESSION_COOKIE_SAMESITE = "Lax"

    # --- Settings for a live website (all off by default, so your laptop is unaffected) ---
    # BEHIND_PROXY=1: the host puts its own front door (HTTPS) in front of the app, so we
    #   trust it to tell us the real address. Without this, links we build (password reset,
    #   Google sign-in) would start with http:// instead of https://.
    # COOKIE_SECURE=1: the login cookie is only ever sent over HTTPS.
    BEHIND_PROXY = os.environ.get("BEHIND_PROXY") == "1"
    SESSION_COOKIE_SECURE = os.environ.get("COOKIE_SECURE") == "1"

    # --- Password reset email ---
    # Leave MAIL_SERVER empty while developing: the reset link is then printed in the
    # terminal instead of being emailed.
    MAIL_SERVER = os.environ.get("MAIL_SERVER", "")
    MAIL_PORT = int(os.environ.get("MAIL_PORT", "587"))
    MAIL_USERNAME = os.environ.get("MAIL_USERNAME", "")
    MAIL_PASSWORD = os.environ.get("MAIL_PASSWORD", "")
    MAIL_FROM = os.environ.get("MAIL_FROM", "")
    RESET_TOKEN_MAX_AGE = 30 * 60  # a reset link works for 30 minutes

    # --- Sign in with Google (the button only appears when both are set) ---
    GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "")
    GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET", "")
    GOOGLE_REDIRECT_URI = os.environ.get("GOOGLE_REDIRECT_URI", "")  # optional, see google_callback
    GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
    GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
    GOOGLE_USERINFO_URL = "https://openidconnect.googleapis.com/v1/userinfo"
