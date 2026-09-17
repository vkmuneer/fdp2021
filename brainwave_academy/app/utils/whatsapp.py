"""WhatsApp absence-notification helper.

If Twilio WhatsApp credentials are configured (TWILIO_ACCOUNT_SID,
TWILIO_AUTH_TOKEN, TWILIO_WHATSAPP_FROM) the message is sent automatically.
Otherwise a tap-to-send https://wa.me/ link is generated so a staff member
can send it manually from their phone with one tap - this needs no paid
API and works everywhere.
"""
import urllib.parse

from flask import current_app


def normalize_phone(phone: str) -> str:
    """Keep digits only and prefix the default country code for 10-digit
    local numbers (e.g. Indian mobile numbers)."""
    digits = "".join(ch for ch in (phone or "") if ch.isdigit())
    country_code = current_app.config.get("DEFAULT_COUNTRY_CODE", "91")
    if len(digits) == 10:
        digits = f"{country_code}{digits}"
    return digits


def build_manual_link(phone: str, message: str) -> str:
    digits = normalize_phone(phone)
    return f"https://wa.me/{digits}?text={urllib.parse.quote(message)}"


def send_whatsapp_message(phone: str, message: str):
    """Try to send automatically via Twilio; fall back to a manual link.

    Returns a dict: {status: 'sent'|'failed'|'manual', detail: str, link: str|None}
    """
    sid = current_app.config.get("TWILIO_ACCOUNT_SID")
    token = current_app.config.get("TWILIO_AUTH_TOKEN")
    from_number = current_app.config.get("TWILIO_WHATSAPP_FROM")
    manual_link = build_manual_link(phone, message)

    if sid and token and from_number:
        try:
            from twilio.rest import Client

            client = Client(sid, token)
            to_number = f"whatsapp:+{normalize_phone(phone)}"
            client.messages.create(body=message, from_=from_number, to=to_number)
            return {"status": "sent", "detail": "Sent automatically via Twilio WhatsApp API", "link": manual_link}
        except Exception as exc:  # noqa: BLE001 - surface any provider error to the caller
            return {"status": "failed", "detail": str(exc), "link": manual_link}

    return {
        "status": "manual",
        "detail": "Twilio not configured - tap the link to send via WhatsApp",
        "link": manual_link,
    }


def absence_message(student, class_name, division_name, on_date):
    return (
        f"Dear Parent, this is to inform you that your child {student.name} "
        f"(Class {class_name} - {division_name}) was ABSENT today, "
        f"{on_date.strftime('%d-%m-%Y')}, at Brainwave Academy. "
        f"If this is unexpected, please contact the academy office. Thank you."
    )
