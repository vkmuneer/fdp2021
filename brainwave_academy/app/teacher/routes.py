from datetime import date, datetime

from flask import Blueprint, render_template, redirect, url_for, flash, request, abort, send_file
from flask_login import login_required, current_user

from ..extensions import db
from ..models import Division, Student, Attendance, MessageLog, Exam, ExamSubject, ExamMark, Settings
from ..utils.decorators import teacher_required
from ..utils.whatsapp import send_whatsapp_message, absence_message
from ..utils.pdf import render_pdf
from ..utils.exam_analysis import compute_exam_results, build_report_context

teacher_bp = Blueprint("teacher", __name__, url_prefix="/teacher")


def _my_divisions():
    return sorted(current_user.teacher.divisions, key=lambda d: (d.school_class.sort_key, d.name))


def _get_authorized_division(division_id):
    division = Division.query.get_or_404(division_id)
    if division not in current_user.teacher.divisions:
        abort(403)
    return division


def _pdf_response(template_name, filename, **context):
    context.setdefault("settings", Settings.get())
    buffer = render_pdf(template_name, **context)
    return send_file(buffer, mimetype="application/pdf", as_attachment=True, download_name=filename)


@teacher_bp.route("/search")
@login_required
@teacher_required
def search():
    q = request.args.get("q", "").strip()
    division_ids = [d.id for d in current_user.teacher.divisions]
    results = []
    if q and division_ids:
        like = f"%{q}%"
        results = (
            Student.query.filter(
                Student.active == True,  # noqa: E712
                Student.division_id.in_(division_ids),
                db.or_(
                    Student.name.ilike(like),
                    Student.admission_no.ilike(like),
                    Student.parent_name.ilike(like),
                    Student.parent_whatsapp.ilike(like),
                ),
            )
            .order_by(Student.name)
            .all()
        )
    return render_template("teacher/search_results.html", q=q, results=results)


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


# -------------------------------------------------------------------- exams
def _my_exams():
    class_ids = {d.class_id for d in current_user.teacher.divisions}
    if not class_ids:
        return []
    return Exam.query.filter(Exam.class_id.in_(class_ids)).order_by(Exam.exam_date.desc()).all()


def _my_divisions_for_class(class_id):
    return [d for d in current_user.teacher.divisions if d.class_id == class_id]


def _get_authorized_exam(exam_id):
    exam = Exam.query.get_or_404(exam_id)
    if exam.class_id not in {d.class_id for d in current_user.teacher.divisions}:
        abort(403)
    return exam


@teacher_bp.route("/exams")
@login_required
@teacher_required
def exams():
    return render_template("teacher/exams.html", exams=_my_exams())


@teacher_bp.route("/exams/<int:exam_id>/marks", methods=["GET", "POST"])
@login_required
@teacher_required
def exam_marks(exam_id):
    exam = _get_authorized_exam(exam_id)
    my_divisions = _my_divisions_for_class(exam.class_id)
    if not my_divisions:
        abort(403)

    my_subject_ids = {s.id for s in current_user.teacher.subjects}
    eligible_subjects = [es for es in exam.exam_subjects if es.subject_id in my_subject_ids]
    if not eligible_subjects:
        flash("You are not assigned to teach any subject in this exam. Contact the admin.", "warning")
        return render_template(
            "teacher/exam_marks.html",
            exam=exam, exam_subject=None, eligible_subjects=[],
            divisions=my_divisions, students=[], existing_marks={},
        )

    division_id = request.values.get("division_id", type=int) or my_divisions[0].id
    division = next((d for d in my_divisions if d.id == division_id), None)
    if division is None:
        abort(403)

    exam_subject_id = request.values.get("exam_subject_id", type=int) or eligible_subjects[0].id
    exam_subject = next((es for es in eligible_subjects if es.id == exam_subject_id), None)
    if exam_subject is None:
        abort(403)

    students = sorted([s for s in division.students if s.active], key=lambda s: s.name)

    if request.method == "POST":
        for student in students:
            raw = request.form.get(f"marks_{student.id}", "").strip()
            existing = ExamMark.query.filter_by(exam_subject_id=exam_subject.id, student_id=student.id).first()
            if raw == "":
                if existing:
                    db.session.delete(existing)
                continue
            try:
                value = float(raw)
            except ValueError:
                flash(f"Ignored invalid marks for {student.name}.", "warning")
                continue
            value = max(0, min(value, exam_subject.max_marks))
            if existing:
                existing.marks_obtained = value
                existing.entered_by = current_user.name
            else:
                db.session.add(
                    ExamMark(
                        exam_subject_id=exam_subject.id,
                        student_id=student.id,
                        marks_obtained=value,
                        entered_by=current_user.name,
                    )
                )
        db.session.commit()
        flash(f"Marks saved for {exam_subject.subject.name}.", "success")
        return redirect(
            url_for("teacher.exam_marks", exam_id=exam.id, division_id=division.id, exam_subject_id=exam_subject.id)
        )

    existing_marks = {
        m.student_id: m.marks_obtained for m in ExamMark.query.filter_by(exam_subject_id=exam_subject.id).all()
    }

    return render_template(
        "teacher/exam_marks.html",
        exam=exam,
        exam_subject=exam_subject,
        eligible_subjects=eligible_subjects,
        divisions=my_divisions,
        selected_division_id=division.id,
        students=students,
        existing_marks=existing_marks,
    )


def _exam_report_students(exam):
    """Returns (division, my_divisions) for the requested/default division,
    scoped to the teacher's own divisions in this exam's class - or aborts
    with 403 if the teacher isn't assigned to any division of that class."""
    my_divisions = _my_divisions_for_class(exam.class_id)
    if not my_divisions:
        abort(403)
    division_id = request.args.get("division_id", type=int) or my_divisions[0].id
    division = next((d for d in my_divisions if d.id == division_id), None)
    if division is None:
        abort(403)
    return division, my_divisions


@teacher_bp.route("/exams/<int:exam_id>/report")
@login_required
@teacher_required
def exam_report(exam_id):
    exam = _get_authorized_exam(exam_id)
    division, my_divisions = _exam_report_students(exam)
    students = sorted([s for s in division.students if s.active], key=lambda s: s.name)
    context = build_report_context(exam, students)
    context.update({"exam": exam, "division": division, "divisions": my_divisions})
    return render_template("teacher/exam_report.html", **context)


@teacher_bp.route("/exams/<int:exam_id>/report/pdf")
@login_required
@teacher_required
def exam_report_pdf(exam_id):
    exam = _get_authorized_exam(exam_id)
    division, _ = _exam_report_students(exam)
    students = sorted([s for s in division.students if s.active], key=lambda s: s.name)
    context = build_report_context(exam, students)
    context["exam"] = exam
    return _pdf_response(
        "pdf/exam_analysis_pdf.html",
        f"exam_analysis_{exam.name.replace(' ', '_')}_{division.name}.pdf",
        **context,
    )


@teacher_bp.route("/exams/<int:exam_id>/students/<int:student_id>/report-card")
@login_required
@teacher_required
def exam_report_card_pdf(exam_id, student_id):
    exam = _get_authorized_exam(exam_id)
    student = Student.query.get_or_404(student_id)
    if student.division not in current_user.teacher.divisions:
        abort(403)
    result = compute_exam_results(exam, [student])[0]
    return _pdf_response(
        "pdf/report_card_pdf.html",
        f"report_card_{student.admission_no}_{exam.name.replace(' ', '_')}.pdf",
        exam=exam,
        student=student,
        result=result,
    )
