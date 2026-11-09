"""
Sign in with Google (OAuth 2.0 "authorization code" flow).

How it works, in four steps:
  1. We send the user to Google with our client ID and a random `state` value.
  2. The user picks their Google account and agrees.
  3. Google sends them back to us with a one-time `code` (and our `state`).
  4. Our SERVER swaps the code for an access token, then asks Google who the user is.

Only Python's built-in urllib is used, so nothing extra needs installing.
"""
import json
import urllib.error
import urllib.parse
import urllib.request

from flask import current_app


class GoogleAuthError(Exception):
    """Something went wrong talking to Google. The message is safe to show the user."""


def is_configured():
    config = current_app.config
    return bool(config["GOOGLE_CLIENT_ID"] and config["GOOGLE_CLIENT_SECRET"])


def build_login_url(redirect_uri, state):
    """The Google page where the user chooses an account."""
    params = {
        "client_id": current_app.config["GOOGLE_CLIENT_ID"],
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
        "prompt": "select_account",  # always let the user choose, even if one account is signed in
    }
    return current_app.config["GOOGLE_AUTH_URL"] + "?" + urllib.parse.urlencode(params)


def _request_json(url, form=None, headers=None):
    data = urllib.parse.urlencode(form).encode() if form else None
    request = urllib.request.Request(url, data=data, headers=headers or {})
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            return json.load(response)
    except (urllib.error.URLError, TimeoutError, ValueError) as error:
        # URLError also covers "Google said no" (HTTP 400) and "no internet".
        current_app.logger.warning("Google request to %s failed: %s", url, error)
        raise GoogleAuthError("Google sign-in could not be completed. Please try again.") from error


def fetch_google_user(code, redirect_uri):
    """Swap the one-time code for the user's Google profile (email, email_verified, name)."""
    config = current_app.config
    token = _request_json(
        config["GOOGLE_TOKEN_URL"],
        form={
            "code": code,
            "client_id": config["GOOGLE_CLIENT_ID"],
            "client_secret": config["GOOGLE_CLIENT_SECRET"],
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
        },
    )
    access_token = token.get("access_token")
    if not access_token:
        raise GoogleAuthError("Google sign-in could not be completed. Please try again.")
    return _request_json(
        config["GOOGLE_USERINFO_URL"], headers={"Authorization": f"Bearer {access_token}"}
    )
