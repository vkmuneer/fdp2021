from datetime import date, datetime, timedelta

from flask import Blueprint, render_template, redirect, url_for, flash, request, send_file
from flask_login import login_required, current_user
from sqlalchemy import func

from ..extensions import db
from ..models import (
    SchoolClass,
    Division,
    User,
    Teacher,
    Student,
    FeePayment,
    Attendance,
    MessageLog,
    Settings,
    Subject,
    Place,
    SchoolMaster,
)
from ..utils.decorators import admin_required
from ..utils.payment import build_pay_url, fee_reminder_message
from ..utils.whatsapp import send_whatsapp_message
from ..utils.excel import build_template, parse_upload

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")


def _classes_sorted():
    return sorted(SchoolClass.query.all(), key=lambda c: c.sort_key)


def _subjects_sorted():
    return Subject.query.order_by(Subject.name).all()


def _places_sorted():
    return Place.query.order_by(Place.name).all()


def _schools_sorted():
    return SchoolMaster.query.order_by(SchoolMaster.name).all()


def _place_options(student=None):
    """Master list of place names, plus the student's current value if it
    was since removed from the master (so saving unchanged never loses it)."""
    names = [p.name for p in _places_sorted()]
    if student and student.place and student.place not in names:
        names.append(student.place)
    return names


def _school_options(student=None):
    names = [s.name for s in _schools_sorted()]
    if student and student.school_name and student.school_name not in names:
        names.append(student.school_name)
    return names


# ---------------------------------------------------------------- dashboard
@admin_bp.route("/dashboard")
@login_required
@admin_required
def dashboard():
    students = Student.query.filter_by(active=True).all()
    total_expected = sum(s.total_fee for s in students)
    total_collected = sum(s.total_paid for s in students)
    total_pending = round(total_expected - total_collected, 2)

    today = date.today()
    today_collection = (
        db.session.query(func.coalesce(func.sum(FeePayment.amount), 0))
        .filter(FeePayment.payment_date == today)
        .scalar()
    )
    today_absentees = Attendance.query.filter_by(date=today, status="absent").count()
    today_present = Attendance.query.filter_by(date=today, status="present").count()

    pending_students = sorted(
        [s for s in students if s.pending_fee > 0], key=lambda s: s.pending_fee, reverse=True
    )[:8]

    return render_template(
        "admin/dashboard.html",
        student_count=len(students),
        teacher_count=Teacher.query.filter_by(active=True).count(),
        total_expected=total_expected,
        total_collected=total_collected,
        total_pending=total_pending,
        today_collection=today_collection,
        today_absentees=today_absentees,
        today_present=today_present,
        pending_students=pending_students,
        classes=_classes_sorted(),
    )


# ----------------------------------------------------------------- students
@admin_bp.route("/students")
@login_required
@admin_required
def students():
    class_id = request.args.get("class_id", type=int)
    division_id = request.args.get("division_id", type=int)
    q = request.args.get("q", "").strip()
    status = request.args.get("status", "")

    query = Student.query.filter_by(active=True)
    if class_id:
        query = query.filter_by(class_id=class_id)
    if division_id:
        query = query.filter_by(division_id=division_id)
    if q:
        like = f"%{q}%"
        query = query.filter(db.or_(Student.name.ilike(like), Student.admission_no.ilike(like)))

    student_list = query.order_by(Student.name).all()
    if status == "pending":
        student_list = [s for s in student_list if s.pending_fee > 0]
    elif status == "paid":
        student_list = [s for s in student_list if s.pending_fee <= 0]

    return render_template(
        "admin/students.html",
        students=student_list,
        classes=_classes_sorted(),
        selected_class_id=class_id,
        selected_division_id=division_id,
        q=q,
        status=status,
    )


@admin_bp.route("/students/new", methods=["GET", "POST"])
@admin_bp.route("/students/<int:student_id>/edit", methods=["GET", "POST"])
@login_required
@admin_required
def student_form(student_id=None):
    student = Student.query.get_or_404(student_id) if student_id else None

    if request.method == "POST":
        division_id = request.form.get("division_id", type=int)
        division = Division.query.get_or_404(division_id)

        admission_no = request.form.get("admission_no", "").strip()
        existing = Student.query.filter_by(admission_no=admission_no).first()
        if existing and (not student or existing.id != student.id):
            flash("That admission number is already in use.", "danger")
            return render_template(
                "admin/student_form.html",
                student=student,
                classes=_classes_sorted(),
                places=_place_options(student),
                school_names=_school_options(student),
            )

        override_raw = request.form.get("base_fee_override", "").strip()

        if student is None:
            student = Student(admission_no=admission_no)
            db.session.add(student)

        student.name = request.form.get("name", "").strip()
        student.class_id = division.class_id
        student.division_id = division.id
        student.parent_name = request.form.get("parent_name", "").strip()
        student.parent_whatsapp = request.form.get("parent_whatsapp", "").strip()
        student.address = request.form.get("address", "").strip()
        student.place = request.form.get("place", "").strip()
        student.school_name = request.form.get("school_name", "").strip()
        student.base_fee_override = float(override_raw) if override_raw else None
        student.discount_amount = float(request.form.get("discount_amount") or 0)
        student.discount_reason = request.form.get("discount_reason", "").strip()

        dob_raw = request.form.get("dob")
        student.dob = datetime.strptime(dob_raw, "%Y-%m-%d").date() if dob_raw else None
        admission_date_raw = request.form.get("admission_date")
        student.admission_date = (
            datetime.strptime(admission_date_raw, "%Y-%m-%d").date() if admission_date_raw else date.today()
        )

        db.session.commit()
        flash(f"Student {student.name} saved.", "success")
        return redirect(url_for("admin.student_detail", student_id=student.id))

    return render_template(
        "admin/student_form.html",
        student=student,
        classes=_classes_sorted(),
        places=_place_options(student),
        school_names=_school_options(student),
    )


@admin_bp.route("/students/<int:student_id>")
@login_required
@admin_required
def student_detail(student_id):
    student = Student.query.get_or_404(student_id)
    return render_template("admin/student_detail.html", student=student)


@admin_bp.route("/students/<int:student_id>/deactivate", methods=["POST"])
@login_required
@admin_required
def student_deactivate(student_id):
    student = Student.query.get_or_404(student_id)
    student.active = False
    db.session.commit()
    flash(f"{student.name} has been deactivated.", "info")
    return redirect(url_for("admin.students"))


# ------------------------------------------------------------ fee payments
@admin_bp.route("/students/<int:student_id>/payments/add", methods=["POST"])
@login_required
@admin_required
def add_payment(student_id):
    student = Student.query.get_or_404(student_id)
    amount = float(request.form.get("amount") or 0)

    if amount <= 0:
        flash("Payment amount must be greater than zero.", "danger")
        return redirect(url_for("admin.student_detail", student_id=student.id))
    if amount > student.pending_fee + 0.01:
        flash(
            f"Amount exceeds pending balance of ₹{student.pending_fee:,.2f}. Please re-check.",
            "danger",
        )
        return redirect(url_for("admin.student_detail", student_id=student.id))

    payment_date_raw = request.form.get("payment_date")
    payment = FeePayment(
        student_id=student.id,
        amount=amount,
        payment_date=datetime.strptime(payment_date_raw, "%Y-%m-%d").date() if payment_date_raw else date.today(),
        mode=request.form.get("mode", "Cash"),
        remarks=request.form.get("remarks", "").strip(),
        recorded_by=current_user.name,
    )
    db.session.add(payment)
    db.session.commit()

    payment.receipt_no = f"BW{payment.id:05d}"
    db.session.commit()

    flash(f"Payment of ₹{amount:,.2f} recorded for {student.name}.", "success")
    return redirect(url_for("admin.student_detail", student_id=student.id))


@admin_bp.route("/payments/<int:payment_id>/delete", methods=["POST"])
@login_required
@admin_required
def delete_payment(payment_id):
    payment = FeePayment.query.get_or_404(payment_id)
    student_id = payment.student_id
    db.session.delete(payment)
    db.session.commit()
    flash("Payment entry removed.", "info")
    return redirect(url_for("admin.student_detail", student_id=student_id))


# ----------------------------------------------------------------- teachers
@admin_bp.route("/teachers")
@login_required
@admin_required
def teachers():
    teacher_list = Teacher.query.order_by(Teacher.name).all()
    return render_template("admin/teachers.html", teachers=teacher_list)


@admin_bp.route("/teachers/new", methods=["GET", "POST"])
@admin_bp.route("/teachers/<int:teacher_id>/edit", methods=["GET", "POST"])
@login_required
@admin_required
def teacher_form(teacher_id=None):
    teacher = Teacher.query.get_or_404(teacher_id) if teacher_id else None

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        name = request.form.get("name", "").strip()
        phone = request.form.get("phone", "").strip()
        password = request.form.get("password", "")
        division_ids = request.form.getlist("division_ids", type=int)
        subject_ids = request.form.getlist("subject_ids", type=int)

        existing_user = User.query.filter_by(username=username).first()
        if existing_user and (not teacher or existing_user.id != teacher.user_id):
            flash("That username is already taken.", "danger")
            return render_template(
                "admin/teacher_form.html", teacher=teacher, classes=_classes_sorted(), subjects=_subjects_sorted()
            )

        if teacher is None:
            if not password:
                flash("Password is required for a new teacher account.", "danger")
                return render_template(
                    "admin/teacher_form.html", teacher=teacher, classes=_classes_sorted(), subjects=_subjects_sorted()
                )
            user = User(username=username, name=name, role="teacher")
            user.set_password(password)
            db.session.add(user)
            db.session.flush()
            teacher = Teacher(user_id=user.id, name=name)
            db.session.add(teacher)
        else:
            teacher.user.username = username
            teacher.user.name = name
            teacher.name = name
            if password:
                teacher.user.set_password(password)

        teacher.phone = phone
        teacher.divisions = Division.query.filter(Division.id.in_(division_ids)).all()
        teacher.subjects = Subject.query.filter(Subject.id.in_(subject_ids)).all()

        db.session.commit()
        flash(f"Teacher {teacher.name} saved.", "success")
        return redirect(url_for("admin.teachers"))

    return render_template(
        "admin/teacher_form.html", teacher=teacher, classes=_classes_sorted(), subjects=_subjects_sorted()
    )


@admin_bp.route("/teachers/<int:teacher_id>/deactivate", methods=["POST"])
@login_required
@admin_required
def teacher_deactivate(teacher_id):
    teacher = Teacher.query.get_or_404(teacher_id)
    teacher.active = False
    teacher.user.active = False
    db.session.commit()
    flash(f"{teacher.name} has been deactivated.", "info")
    return redirect(url_for("admin.teachers"))


@admin_bp.route("/teachers/<int:teacher_id>/activate", methods=["POST"])
@login_required
@admin_required
def teacher_activate(teacher_id):
    teacher = Teacher.query.get_or_404(teacher_id)
    teacher.active = True
    teacher.user.active = True
    db.session.commit()
    flash(f"{teacher.name} has been re-activated.", "info")
    return redirect(url_for("admin.teachers"))


# ------------------------------------------------------- classes/divisions
@admin_bp.route("/classes")
@login_required
@admin_required
def classes():
    return render_template("admin/classes.html", classes=_classes_sorted())


@admin_bp.route("/classes/<int:class_id>/update-fee", methods=["POST"])
@login_required
@admin_required
def update_class_fee(class_id):
    school_class = SchoolClass.query.get_or_404(class_id)
    school_class.base_fee = float(request.form.get("base_fee") or 0)
    db.session.commit()
    flash(f"Base fee for {school_class.name} updated to ₹{school_class.base_fee:,.2f}.", "success")
    return redirect(url_for("admin.classes"))


@admin_bp.route("/classes/<int:class_id>/divisions/add", methods=["POST"])
@login_required
@admin_required
def add_division(class_id):
    school_class = SchoolClass.query.get_or_404(class_id)
    name = request.form.get("name", "").strip().upper()
    if not name:
        flash("Division name is required.", "danger")
    elif Division.query.filter_by(class_id=class_id, name=name).first():
        flash(f"Division {name} already exists for {school_class.name}.", "danger")
    else:
        db.session.add(Division(name=name, class_id=class_id))
        db.session.commit()
        flash(f"Division {name} added to {school_class.name}.", "success")
    return redirect(url_for("admin.classes"))


@admin_bp.route("/divisions/<int:division_id>/delete", methods=["POST"])
@login_required
@admin_required
def delete_division(division_id):
    division = Division.query.get_or_404(division_id)
    if division.students:
        flash("Cannot delete a division that still has students.", "danger")
    else:
        db.session.delete(division)
        db.session.commit()
        flash("Division removed.", "info")
    return redirect(url_for("admin.classes"))


# --------------------------------------------------------------- reports
@admin_bp.route("/reports/finance")
@login_required
@admin_required
def finance_report():
    period = request.args.get("period", "daily")
    today = date.today()

    if period == "monthly":
        year = request.args.get("year", type=int) or today.year
        month = request.args.get("month", type=int) or today.month
        start = date(year, month, 1)
        end = date(year + (1 if month == 12 else 0), 1 if month == 12 else month + 1, 1) - timedelta(days=1)
        label = start.strftime("%B %Y")
    elif period == "range":
        start_raw = request.args.get("start")
        end_raw = request.args.get("end")
        start = datetime.strptime(start_raw, "%Y-%m-%d").date() if start_raw else today.replace(day=1)
        end = datetime.strptime(end_raw, "%Y-%m-%d").date() if end_raw else today
        year, month = start.year, start.month
        label = f"{start.strftime('%d-%m-%Y')} to {end.strftime('%d-%m-%Y')}"
    else:
        period = "daily"
        date_raw = request.args.get("date")
        start = end = datetime.strptime(date_raw, "%Y-%m-%d").date() if date_raw else today
        year, month = start.year, start.month
        label = start.strftime("%d-%m-%Y")

    payments = (
        FeePayment.query.filter(FeePayment.payment_date >= start, FeePayment.payment_date <= end)
        .order_by(FeePayment.payment_date, FeePayment.created_at)
        .all()
    )
    total = sum(p.amount for p in payments)

    by_mode = {}
    by_class = {}
    for p in payments:
        by_mode[p.mode] = by_mode.get(p.mode, 0) + p.amount
        class_name = p.student.school_class.name
        by_class[class_name] = by_class.get(class_name, 0) + p.amount

    return render_template(
        "admin/finance_report.html",
        period=period,
        start=start,
        end=end,
        label=label,
        year=year,
        month=month,
        payments=payments,
        total=total,
        by_mode=by_mode,
        by_class=by_class,
    )


@admin_bp.route("/reports/class-wise")
@login_required
@admin_required
def class_wise_report():
    today = date.today()
    rows = []
    for school_class in _classes_sorted():
        class_students = [s for s in school_class.students if s.active]
        student_ids = [s.id for s in class_students]
        expected = sum(s.total_fee for s in class_students)
        collected = sum(s.total_paid for s in class_students)
        if student_ids:
            present_today = Attendance.query.filter(
                Attendance.date == today,
                Attendance.status == "present",
                Attendance.student_id.in_(student_ids),
            ).count()
            absent_today = Attendance.query.filter(
                Attendance.date == today,
                Attendance.status == "absent",
                Attendance.student_id.in_(student_ids),
            ).count()
        else:
            present_today = absent_today = 0

        rows.append(
            {
                "school_class": school_class,
                "student_count": len(class_students),
                "expected": expected,
                "collected": collected,
                "pending": round(expected - collected, 2),
                "present_today": present_today,
                "absent_today": absent_today,
            }
        )

    return render_template("admin/class_report.html", rows=rows)


@admin_bp.route("/reports/student-wise")
@login_required
@admin_required
def student_wise_report():
    class_id = request.args.get("class_id", type=int)
    q = request.args.get("q", "").strip()

    query = Student.query.filter_by(active=True)
    if class_id:
        query = query.filter_by(class_id=class_id)
    if q:
        like = f"%{q}%"
        query = query.filter(db.or_(Student.name.ilike(like), Student.admission_no.ilike(like)))

    student_list = query.order_by(Student.name).all()
    totals = {
        "expected": sum(s.total_fee for s in student_list),
        "collected": sum(s.total_paid for s in student_list),
        "pending": sum(s.pending_fee for s in student_list),
    }

    return render_template(
        "admin/student_wise_report.html",
        students=student_list,
        classes=_classes_sorted(),
        selected_class_id=class_id,
        q=q,
        totals=totals,
    )


@admin_bp.route("/reports/pending-fees")
@login_required
@admin_required
def pending_fees_report():
    class_id = request.args.get("class_id", type=int)
    query = Student.query.filter_by(active=True)
    if class_id:
        query = query.filter_by(class_id=class_id)

    student_list = [s for s in query.all() if s.pending_fee > 0]
    student_list.sort(key=lambda s: s.pending_fee, reverse=True)
    total_pending = sum(s.pending_fee for s in student_list)

    return render_template(
        "admin/pending_fees.html",
        students=student_list,
        classes=_classes_sorted(),
        selected_class_id=class_id,
        total_pending=total_pending,
    )


def _queue_fee_reminder(student):
    pay_url = build_pay_url(student.id)
    message = fee_reminder_message(student, pay_url)
    result = send_whatsapp_message(student.parent_whatsapp, message)
    db.session.add(
        MessageLog(
            student_id=student.id,
            date=date.today(),
            category="fee_reminder",
            message=message,
            phone=student.parent_whatsapp,
            status=result["status"],
            detail=result["detail"],
            manual_link=result.get("link"),
        )
    )


@admin_bp.route("/students/<int:student_id>/send-fee-reminder", methods=["POST"])
@login_required
@admin_required
def send_fee_reminder(student_id):
    student = Student.query.get_or_404(student_id)
    if student.pending_fee <= 0:
        flash(f"{student.name} has no pending fee.", "info")
    else:
        _queue_fee_reminder(student)
        db.session.commit()
        flash(f"Fee reminder queued for {student.name}'s parent on WhatsApp.", "success")
    return redirect(request.referrer or url_for("admin.student_detail", student_id=student.id))


@admin_bp.route("/reports/pending-fees/send-reminders", methods=["POST"])
@login_required
@admin_required
def send_bulk_fee_reminders():
    class_id = request.form.get("class_id", type=int)
    query = Student.query.filter_by(active=True)
    if class_id:
        query = query.filter_by(class_id=class_id)
    pending_students = [s for s in query.all() if s.pending_fee > 0]

    for student in pending_students:
        _queue_fee_reminder(student)
    db.session.commit()

    flash(
        f"Fee reminders queued for {len(pending_students)} student(s). "
        f"Check the Messages page to send/verify each one on WhatsApp.",
        "success",
    )
    return redirect(url_for("admin.pending_fees_report", class_id=class_id) if class_id else url_for("admin.pending_fees_report"))


@admin_bp.route("/reports/discounts")
@login_required
@admin_required
def discount_report():
    student_list = (
        Student.query.filter(Student.active == True, Student.discount_amount > 0)  # noqa: E712
        .order_by(Student.discount_amount.desc())
        .all()
    )
    total_discount = sum(s.discount_amount for s in student_list)
    return render_template(
        "admin/discount_report.html", students=student_list, total_discount=total_discount
    )


@admin_bp.route("/reports/attendance")
@login_required
@admin_required
def attendance_report():
    report_date_raw = request.args.get("date")
    report_date = (
        datetime.strptime(report_date_raw, "%Y-%m-%d").date() if report_date_raw else date.today()
    )
    records = (
        Attendance.query.filter_by(date=report_date)
        .join(Student)
        .order_by(Student.name)
        .all()
    )
    present = [r for r in records if r.status == "present"]
    absent = [r for r in records if r.status == "absent"]

    by_division = {}
    for division in Division.query.all():
        active_count = sum(1 for s in division.students if s.active)
        if active_count == 0:
            continue
        marked = [r for r in records if r.student.division_id == division.id]
        by_division[division] = {
            "total": active_count,
            "present": sum(1 for r in marked if r.status == "present"),
            "absent": sum(1 for r in marked if r.status == "absent"),
            "unmarked": active_count - len(marked),
        }

    return render_template(
        "admin/attendance_report.html",
        report_date=report_date,
        present=present,
        absent=absent,
        by_division=by_division,
    )


# ---------------------------------------------------------------- messages
@admin_bp.route("/messages")
@login_required
@admin_required
def messages():
    logs = MessageLog.query.order_by(MessageLog.created_at.desc()).limit(200).all()
    pending_count = MessageLog.query.filter_by(status="manual").count()
    return render_template("admin/messages.html", logs=logs, pending_count=pending_count)


@admin_bp.route("/messages/<int:message_id>/mark-sent", methods=["POST"])
@login_required
@admin_required
def mark_message_sent(message_id):
    log = MessageLog.query.get_or_404(message_id)
    log.status = "sent"
    log.detail = f"Marked as sent manually by {current_user.name}"
    db.session.commit()
    return redirect(url_for("admin.messages"))


# ---------------------------------------------------------------- settings
@admin_bp.route("/settings", methods=["GET", "POST"])
@login_required
@admin_required
def settings():
    settings_obj = Settings.get()
    if request.method == "POST":
        settings_obj.academy_name = request.form.get("academy_name", "").strip() or "Brainwave Academy"
        settings_obj.upi_id = request.form.get("upi_id", "").strip()
        settings_obj.upi_payee_name = request.form.get("upi_payee_name", "").strip()
        db.session.commit()
        flash("Settings updated.", "success")
        return redirect(url_for("admin.settings"))
    return render_template("admin/settings.html", settings=settings_obj)


# ---------------------------------------------------------- bulk upload
@admin_bp.route("/students/bulk-upload", methods=["GET", "POST"])
@login_required
@admin_required
def students_bulk_upload():
    if request.method == "POST":
        file = request.files.get("file")
        if not file or file.filename == "":
            flash("Please choose an Excel (.xlsx) file to upload.", "danger")
            return redirect(url_for("admin.students_bulk_upload"))

        try:
            rows = parse_upload(file.stream)
        except ValueError as exc:
            flash(str(exc), "danger")
            return redirect(url_for("admin.students_bulk_upload"))

        classes_by_name = {c.name.strip().lower(): c for c in SchoolClass.query.all()}
        existing_admission_nos = {
            a.lower() for (a,) in db.session.query(Student.admission_no).all()
        }
        places_by_name = {p.name.lower(): p for p in Place.query.all()}
        schools_by_name = {s.name.lower(): s for s in SchoolMaster.query.all()}
        created = []
        errors = []

        for record in rows:
            row_no = record.get("_row")
            missing = [
                field
                for field in ("admission_no", "name", "class", "division", "parent_whatsapp")
                if not str(record.get(field) or "").strip()
            ]
            if missing:
                errors.append(f"Row {row_no}: missing required field(s) - {', '.join(missing)}.")
                continue

            admission_no = str(record["admission_no"]).strip()
            if admission_no.lower() in existing_admission_nos:
                errors.append(f"Row {row_no}: admission number '{admission_no}' already exists or is repeated in the sheet.")
                continue

            class_name = str(record["class"]).strip()
            school_class = classes_by_name.get(class_name.lower())
            if not school_class:
                valid = ", ".join(c.name for c in _classes_sorted())
                errors.append(f"Row {row_no}: unknown class '{class_name}'. Valid classes: {valid}.")
                continue

            division_name = str(record["division"]).strip().upper()
            division = next((d for d in school_class.divisions if d.name.upper() == division_name), None)
            if division is None:
                division = Division(name=division_name, class_id=school_class.id)
                db.session.add(division)
                db.session.flush()
                school_class.divisions.append(division)

            place_name = str(record.get("place") or "").strip()
            if place_name and place_name.lower() not in places_by_name:
                new_place = Place(name=place_name)
                db.session.add(new_place)
                db.session.flush()
                places_by_name[place_name.lower()] = new_place

            school_name = str(record.get("school_name") or "").strip()
            if school_name and school_name.lower() not in schools_by_name:
                new_school = SchoolMaster(name=school_name)
                db.session.add(new_school)
                db.session.flush()
                schools_by_name[school_name.lower()] = new_school

            student = Student(
                admission_no=admission_no,
                name=str(record["name"]).strip(),
                class_id=school_class.id,
                division_id=division.id,
                parent_name=str(record.get("parent_name") or "").strip(),
                parent_whatsapp=str(record["parent_whatsapp"]).strip(),
                address=str(record.get("address") or "").strip(),
                place=place_name,
                school_name=school_name,
                dob=_parse_flexible_date(record.get("dob")),
                admission_date=_parse_flexible_date(record.get("admission_date")) or date.today(),
                discount_reason=str(record.get("discount_reason") or "").strip(),
            )

            try:
                student.discount_amount = float(record.get("discount_amount") or 0)
            except (TypeError, ValueError):
                errors.append(f"Row {row_no}: invalid discount_amount, defaulted to 0.")
                student.discount_amount = 0

            override_raw = record.get("base_fee_override")
            if override_raw not in (None, ""):
                try:
                    student.base_fee_override = float(override_raw)
                except (TypeError, ValueError):
                    errors.append(f"Row {row_no}: invalid base_fee_override, ignored.")

            db.session.add(student)
            existing_admission_nos.add(admission_no.lower())
            created.append(student)

        if created:
            db.session.commit()
        else:
            db.session.rollback()

        flash(
            f"{len(created)} student(s) added successfully." if created else "No students were added - see the errors below.",
            "success" if created else "warning",
        )
        return render_template(
            "admin/students_bulk_upload.html",
            classes=_classes_sorted(),
            results=True,
            created=created,
            errors=errors,
        )

    return render_template("admin/students_bulk_upload.html", classes=_classes_sorted(), results=False)


def _parse_flexible_date(value):
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return datetime.strptime(str(value).strip(), "%Y-%m-%d").date()
    except ValueError:
        return None


@admin_bp.route("/students/bulk-upload/template")
@login_required
@admin_required
def students_bulk_upload_template():
    class_names = [c.name for c in _classes_sorted()]
    buffer = build_template(class_names)
    return send_file(
        buffer,
        as_attachment=True,
        download_name="brainwave_students_template.xlsx",
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


# ----------------------------------------------------------------- masters
@admin_bp.route("/masters")
@login_required
@admin_required
def masters():
    return render_template(
        "admin/masters.html",
        subjects=_subjects_sorted(),
        places=_places_sorted(),
        schools=_schools_sorted(),
    )


@admin_bp.route("/masters/subjects/add", methods=["POST"])
@login_required
@admin_required
def add_subject():
    name = request.form.get("name", "").strip()
    if not name:
        flash("Subject name is required.", "danger")
    elif Subject.query.filter(db.func.lower(Subject.name) == name.lower()).first():
        flash(f"Subject '{name}' already exists.", "danger")
    else:
        db.session.add(Subject(name=name))
        db.session.commit()
        flash(f"Subject '{name}' added.", "success")
    return redirect(url_for("admin.masters"))


@admin_bp.route("/masters/subjects/<int:subject_id>/delete", methods=["POST"])
@login_required
@admin_required
def delete_subject(subject_id):
    subject = Subject.query.get_or_404(subject_id)
    if subject.teachers:
        flash(f"Cannot delete '{subject.name}' - it is assigned to {len(subject.teachers)} teacher(s).", "danger")
    else:
        db.session.delete(subject)
        db.session.commit()
        flash(f"Subject '{subject.name}' removed.", "info")
    return redirect(url_for("admin.masters"))


@admin_bp.route("/masters/places/add", methods=["POST"])
@login_required
@admin_required
def add_place():
    name = request.form.get("name", "").strip()
    if not name:
        flash("Place name is required.", "danger")
    elif Place.query.filter(db.func.lower(Place.name) == name.lower()).first():
        flash(f"Place '{name}' already exists.", "danger")
    else:
        db.session.add(Place(name=name))
        db.session.commit()
        flash(f"Place '{name}' added.", "success")
    return redirect(url_for("admin.masters"))


@admin_bp.route("/masters/places/<int:place_id>/delete", methods=["POST"])
@login_required
@admin_required
def delete_place(place_id):
    place = Place.query.get_or_404(place_id)
    db.session.delete(place)
    db.session.commit()
    flash(f"Place '{place.name}' removed from the list.", "info")
    return redirect(url_for("admin.masters"))


@admin_bp.route("/masters/schools/add", methods=["POST"])
@login_required
@admin_required
def add_school():
    name = request.form.get("name", "").strip()
    if not name:
        flash("School name is required.", "danger")
    elif SchoolMaster.query.filter(db.func.lower(SchoolMaster.name) == name.lower()).first():
        flash(f"School '{name}' already exists.", "danger")
    else:
        db.session.add(SchoolMaster(name=name))
        db.session.commit()
        flash(f"School '{name}' added.", "success")
    return redirect(url_for("admin.masters"))


@admin_bp.route("/masters/schools/<int:school_id>/delete", methods=["POST"])
@login_required
@admin_required
def delete_school(school_id):
    school = SchoolMaster.query.get_or_404(school_id)
    db.session.delete(school)
    db.session.commit()
    flash(f"School '{school.name}' removed from the list.", "info")
    return redirect(url_for("admin.masters"))
