from flask import Blueprint, render_template, abort

from ..models import Student, Settings
from ..utils.payment import verify_pay_token, build_upi_link

public_bp = Blueprint("public", __name__)


@public_bp.route("/pay/<token>")
def pay(token):
    student_id = verify_pay_token(token)
    if student_id is None:
        abort(404)

    student = Student.query.get_or_404(student_id)
    settings = Settings.get()
    pending = student.pending_fee

    upi_link = None
    if pending > 0 and settings.upi_id:
        note = f"Brainwave Academy fee - {student.name} ({student.admission_no})"
        upi_link = build_upi_link(settings.upi_id, settings.upi_payee_name, pending, note)

    return render_template(
        "public/pay.html",
        student=student,
        settings=settings,
        pending=pending,
        upi_link=upi_link,
    )
