"""
The entry point for a live website. The host starts the app with:  gunicorn wsgi:app
(On your own computer you keep using:  python run.py)
"""
from app import create_app

app = create_app()
