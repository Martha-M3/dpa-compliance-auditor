"""
Sending email (used for password-reset links).

Uses only Python's built-in smtplib, so nothing extra needs installing.
If MAIL_SERVER is not set (normal while developing), nothing is sent: the message
is printed in the terminal instead, so you can copy the link from there.
"""
import smtplib
import ssl
from email.message import EmailMessage

from flask import current_app


def send_email(to_address, subject, body):
    """Send a plain-text email. Returns True if it was sent, False if it was only printed."""
    config = current_app.config

    if not config["MAIL_SERVER"]:
        current_app.logger.warning(
            "Email is not set up, so this message was NOT sent.\n"
            "To: %s\nSubject: %s\n\n%s", to_address, subject, body
        )
        return False

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = config["MAIL_FROM"] or config["MAIL_USERNAME"]
    message["To"] = to_address
    message.set_content(body)

    with smtplib.SMTP(config["MAIL_SERVER"], config["MAIL_PORT"], timeout=15) as server:
        server.starttls(context=ssl.create_default_context())  # encrypt the connection first
        if config["MAIL_USERNAME"]:
            server.login(config["MAIL_USERNAME"], config["MAIL_PASSWORD"])
        server.send_message(message)
    return True