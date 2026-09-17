from datetime import date, datetime, timedelta

from flask import Blueprint, render_template, redirect, url_for, flash, request
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
)
from ..utils.decorators import admin_required

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")


def _classes_sorted():
    return sorted(SchoolClass.query.all(), key=lambda c: c.sort_key)


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
            return render_template("admin/student_form.html", student=student, classes=_classes_sorted())

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

    return render_template("admin/student_form.html", student=student, classes=_classes_sorted())


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
        subject = request.form.get("subject", "").strip()
        password = request.form.get("password", "")
        division_ids = request.form.getlist("division_ids", type=int)

        existing_user = User.query.filter_by(username=username).first()
        if existing_user and (not teacher or existing_user.id != teacher.user_id):
            flash("That username is already taken.", "danger")
            return render_template(
                "admin/teacher_form.html", teacher=teacher, classes=_classes_sorted()
            )

        if teacher is None:
            if not password:
                flash("Password is required for a new teacher account.", "danger")
                return render_template(
                    "admin/teacher_form.html", teacher=teacher, classes=_classes_sorted()
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
        teacher.subject = subject
        teacher.divisions = Division.query.filter(Division.id.in_(division_ids)).all()

        db.session.commit()
        flash(f"Teacher {teacher.name} saved.", "success")
        return redirect(url_for("admin.teachers"))

    return render_template("admin/teacher_form.html", teacher=teacher, classes=_classes_sorted())


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
@admin_bp.route("/reports/daily")
@login_required
@admin_required
def daily_report():
    report_date_raw = request.args.get("date")
    report_date = (
        datetime.strptime(report_date_raw, "%Y-%m-%d").date() if report_date_raw else date.today()
    )

    payments = (
        FeePayment.query.filter_by(payment_date=report_date).order_by(FeePayment.created_at).all()
    )
    total = sum(p.amount for p in payments)

    by_mode = {}
    for p in payments:
        by_mode[p.mode] = by_mode.get(p.mode, 0) + p.amount

    by_class = {}
    for p in payments:
        class_name = p.student.school_class.name
        by_class[class_name] = by_class.get(class_name, 0) + p.amount

    return render_template(
        "admin/daily_report.html",
        report_date=report_date,
        payments=payments,
        total=total,
        by_mode=by_mode,
        by_class=by_class,
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
    return render_template(
        "admin/attendance_report.html",
        report_date=report_date,
        present=present,
        absent=absent,
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
