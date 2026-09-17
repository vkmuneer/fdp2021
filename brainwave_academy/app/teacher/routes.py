from datetime import date, datetime

from flask import Blueprint, render_template, redirect, url_for, flash, request, abort
from flask_login import login_required, current_user

from ..extensions import db
from ..models import Division, Student, Attendance, MessageLog
from ..utils.decorators import teacher_required
from ..utils.whatsapp import send_whatsapp_message, absence_message

teacher_bp = Blueprint("teacher", __name__, url_prefix="/teacher")


def _my_divisions():
    return sorted(current_user.teacher.divisions, key=lambda d: (d.school_class.sort_key, d.name))


def _get_authorized_division(division_id):
    division = Division.query.get_or_404(division_id)
    if division not in current_user.teacher.divisions:
        abort(403)
    return division


@teacher_bp.route("/dashboard")
@login_required
@teacher_required
def dashboard():
    divisions = _my_divisions()
    today = date.today()
    summary = []
    for division in divisions:
        student_ids = [s.id for s in division.students if s.active]
        marked_today = Attendance.query.filter(
            Attendance.division_id == division.id,
            Attendance.date == today,
            Attendance.student_id.in_(student_ids) if student_ids else False,
        ).count()
        summary.append(
            {
                "division": division,
                "student_count": len(student_ids),
                "marked_today": marked_today,
            }
        )
    return render_template("teacher/dashboard.html", summary=summary, today=today)


@teacher_bp.route("/attendance", methods=["GET", "POST"])
@login_required
@teacher_required
def attendance():
    divisions = _my_divisions()
    if not divisions:
        flash("You have not been assigned to any class/division yet. Contact the admin.", "warning")
        return render_template("teacher/attendance.html", divisions=[], division=None, students=[])

    division_id = request.values.get("division_id", type=int) or divisions[0].id
    division = _get_authorized_division(division_id)

    date_raw = request.values.get("att_date")
    att_date = datetime.strptime(date_raw, "%Y-%m-%d").date() if date_raw else date.today()

    students = sorted(
        [s for s in division.students if s.active], key=lambda s: s.name
    )

    if request.method == "POST":
        existing = {
            a.student_id: a
            for a in Attendance.query.filter_by(division_id=division.id, date=att_date).all()
        }
        absentees = []

        for student in students:
            is_present = request.form.get(f"present_{student.id}") == "on"
            status = "present" if is_present else "absent"
            record = existing.get(student.id)
            if record:
                record.status = status
                record.marked_by = current_user.name
            else:
                db.session.add(
                    Attendance(
                        student_id=student.id,
                        division_id=division.id,
                        date=att_date,
                        status=status,
                        marked_by=current_user.name,
                    )
                )
            if not is_present:
                absentees.append(student)

        db.session.commit()

        for student in absentees:
            message = absence_message(student, division.school_class.name, division.name, att_date)
            result = send_whatsapp_message(student.parent_whatsapp, message)
            db.session.add(
                MessageLog(
                    student_id=student.id,
                    date=att_date,
                    message=message,
                    phone=student.parent_whatsapp,
                    status=result["status"],
                    detail=result["detail"],
                    manual_link=result.get("link"),
                )
            )
        db.session.commit()

        flash(
            f"Attendance saved for {division.display_name} on {att_date.strftime('%d-%m-%Y')}. "
            f"{len(absentees)} absentee(s) - WhatsApp notifications queued.",
            "success",
        )
        return redirect(url_for("teacher.attendance", division_id=division.id, att_date=att_date.isoformat()))

    existing_map = {
        a.student_id: a.status
        for a in Attendance.query.filter_by(division_id=division.id, date=att_date).all()
    }

    return render_template(
        "teacher/attendance.html",
        divisions=divisions,
        division=division,
        students=students,
        att_date=att_date,
        existing_map=existing_map,
    )


@teacher_bp.route("/attendance/history")
@login_required
@teacher_required
def attendance_history():
    divisions = _my_divisions()
    if not divisions:
        return render_template("teacher/attendance_history.html", divisions=[], division=None, records=[])

    division_id = request.args.get("division_id", type=int) or divisions[0].id
    division = _get_authorized_division(division_id)

    date_raw = request.args.get("att_date")
    att_date = datetime.strptime(date_raw, "%Y-%m-%d").date() if date_raw else date.today()

    records = (
        Attendance.query.filter_by(division_id=division.id, date=att_date)
        .join(Student)
        .order_by(Student.name)
        .all()
    )

    return render_template(
        "teacher/attendance_history.html",
        divisions=divisions,
        division=division,
        att_date=att_date,
        records=records,
    )


@teacher_bp.route("/students")
@login_required
@teacher_required
def students():
    divisions = _my_divisions()
    division_id = request.args.get("division_id", type=int) or (divisions[0].id if divisions else None)
    division = _get_authorized_division(division_id) if division_id else None
    students_list = sorted([s for s in division.students if s.active], key=lambda s: s.name) if division else []
    return render_template(
        "teacher/students.html", divisions=divisions, division=division, students=students_list
    )
