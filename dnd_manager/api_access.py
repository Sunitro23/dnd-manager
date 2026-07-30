import hmac

from flask import current_app, request


def authentication_required():
    return not current_app.config["API_PUBLIC"] and request.method != "OPTIONS"


def token_is_valid():
    expected = current_app.config.get("API_TOKEN") or ""
    return bool(expected) and hmac.compare_digest(bearer_token(), expected)


def bearer_token():
    scheme, separator, token = request.headers.get("Authorization", "").partition(" ")
    return token if separator and scheme.lower() == "bearer" else ""
