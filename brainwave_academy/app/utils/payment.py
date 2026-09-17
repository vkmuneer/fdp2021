"""UPI/GPay payment link helpers for fee reminders.

A parent-facing WhatsApp message includes a normal https:// link (so it is
reliably tappable inside WhatsApp) to our own /pay/<token> page. That page
then offers a upi://pay deep link pre-filled with the administrator's UPI ID
(GPay, PhonePe, etc. all register as handlers for this scheme on Android),
the amount due and a note - the parent just taps "Pay via GPay/UPI".
"""
import urllib.parse

from flask import current_app, url_for
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired

TOKEN_SALT = "brainwave-pay-link"
TOKEN_MAX_AGE_SECONDS = 60 * 60 * 24 * 60  # 60 days


def _serializer():
    return URLSafeTimedSerializer(current_app.config["SECRET_KEY"])


def generate_pay_token(student_id: int) -> str:
    return _serializer().dumps(student_id, salt=TOKEN_SALT)


def verify_pay_token(token: str):
    """Returns the student_id, or None if the token is invalid/expired."""
    try:
        return _serializer().loads(token, salt=TOKEN_SALT, max_age=TOKEN_MAX_AGE_SECONDS)
    except (BadSignature, SignatureExpired):
        return None


def build_pay_url(student_id: int) -> str:
    token = generate_pay_token(student_id)
    return url_for("public.pay", token=token, _external=True)


def build_upi_link(upi_id: str, payee_name: str, amount: float, note: str) -> str:
    params = {
        "pa": upi_id,
        "pn": payee_name or "Brainwave Academy",
        "am": f"{amount:.2f}",
        "cu": "INR",
        "tn": note,
    }
    return "upi://pay?" + urllib.parse.urlencode(params)


def fee_reminder_message(student, pay_url):
    pending = student.pending_fee
    return (
        f"Dear Parent, this is a reminder from Brainwave Academy that a fee of "
        f"₹{pending:,.0f} is pending for {student.name} "
        f"(Class {student.school_class.name}-{student.division.name}). "
        f"Please pay conveniently here: {pay_url} Thank you."
    )
