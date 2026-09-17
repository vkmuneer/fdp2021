import os
from datetime import timedelta

basedir = os.path.abspath(os.path.dirname(__file__))


def _database_uri():
    # Render/Heroku-style hosts sometimes inject an empty DATABASE_URL env var
    # (rather than omitting it) and use the legacy "postgres://" scheme, which
    # SQLAlchemy 1.4+ rejects, so normalize both cases here.
    uri = os.environ.get("DATABASE_URL") or f"sqlite:///{os.path.join(basedir, 'brainwave.db')}"
    if uri.startswith("postgres://"):
        uri = uri.replace("postgres://", "postgresql://", 1)
    return uri


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-key-change-me")
    SQLALCHEMY_DATABASE_URI = _database_uri()
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    PERMANENT_SESSION_LIFETIME = timedelta(days=7)

    DEFAULT_ADMIN_USERNAME = os.environ.get("DEFAULT_ADMIN_USERNAME") or "admin"
    DEFAULT_ADMIN_PASSWORD = os.environ.get("DEFAULT_ADMIN_PASSWORD") or "admin123"

    TWILIO_ACCOUNT_SID = os.environ.get("TWILIO_ACCOUNT_SID", "")
    TWILIO_AUTH_TOKEN = os.environ.get("TWILIO_AUTH_TOKEN", "")
    TWILIO_WHATSAPP_FROM = os.environ.get("TWILIO_WHATSAPP_FROM", "")

    DEFAULT_COUNTRY_CODE = os.environ.get("DEFAULT_COUNTRY_CODE", "91")

    # Base tuition fees per class, as requested for Brainwave Academy.
    DEFAULT_CLASS_FEES = {
        "9": 10000,
        "SSLC": 12500,
        "+1": 20000,
        "+2": 20000,
    }
