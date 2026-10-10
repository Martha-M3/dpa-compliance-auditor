import os
from urllib.parse import quote_plus
from dotenv import load_dotenv
from pathlib import Path

load_dotenv()

# The folder this file lives in = the project root. Building paths from it
# means uploads always go to the same place, no matter where you run Flask from.
BASE_DIR = Path(__file__).resolve().parent

class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-only-change-me")

    DB_NAME = os.environ.get("DB_NAME")
    DB_USER = os.environ.get("DB_USER")
    DB_PASSWORD = os.environ.get("DB_PASSWORD", "")
    DB_HOST = os.environ.get("DB_HOST", "localhost")
    DB_PORT = os.environ.get("DB_PORT", "5432")

    SQLALCHEMY_DATABASE_URI = (
        f"postgresql+psycopg2://{DB_USER}:{quote_plus(DB_PASSWORD)}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
        # Where uploaded datasets are stored: <project>/uploads/datasets/<dataset_id>.csv
    UPLOAD_FOLDER = BASE_DIR / "uploads" / "datasets"

    # Flask rejects any request bigger than this (50 MB) with an HTTP 413 error,
    # so a huge file can't use up the server's memory.
    MAX_CONTENT_LENGTH = 50 * 1024 * 1024

    # Stops the browser sending the login cookie along with requests that come from other websites (a basic defence against forged form submissions).
    SESSION_COOKIE_SAMESITE = "Lax"