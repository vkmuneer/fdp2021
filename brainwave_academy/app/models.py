from datetime import date, datetime

from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

from .extensions import db

CLASS_ORDER = ["9", "SSLC", "+1", "+2"]

teacher_divisions = db.Table(
    "teacher_divisions",
    db.Column("teacher_id", db.Integer, db.ForeignKey("teachers.id"), primary_key=True),
    db.Column("division_id", db.Integer, db.ForeignKey("divisions.id"), primary_key=True),
)

teacher_subjects = db.Table(
    "teacher_subjects",
    db.Column("teacher_id", db.Integer, db.ForeignKey("teachers.id"), primary_key=True),
    db.Column("subject_id", db.Integer, db.ForeignKey("subjects.id"), primary_key=True),
)


class Subject(db.Model):
    """Admin-managed master list of subjects teachers can be assigned to."""

    __tablename__ = "subjects"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), unique=True, nullable=False)

    def __repr__(self):
        return f"<Subject {self.name}>"


class Place(db.Model):
    """Admin-managed master list of places/localities students are from."""

    __tablename__ = "places"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), unique=True, nullable=False)

    def __repr__(self):
        return f"<Place {self.name}>"


class SchoolMaster(db.Model):
    """Admin-managed master list of (regular) schools students study in."""

    __tablename__ = "school_masters"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), unique=True, nullable=False)

    def __repr__(self):
        return f"<SchoolMaster {self.name}>"


class SchoolClass(db.Model):
    __tablename__ = "school_classes"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(20), unique=True, nullable=False)
    base_fee = db.Column(db.Float, nullable=False, default=0)

    divisions = db.relationship(
        "Division", backref="school_class", cascade="all, delete-orphan", order_by="Division.name"
    )
    students = db.relationship("Student", backref="school_class")

    @property
    def sort_key(self):
        return CLASS_ORDER.index(self.name) if self.name in CLASS_ORDER else 99

    def __repr__(self):
        return f"<SchoolClass {self.name}>"


class Division(db.Model):
    __tablename__ = "divisions"
    __table_args__ = (db.UniqueConstraint("name", "class_id", name="uq_division_class"),)

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(10), nullable=False)
    class_id = db.Column(db.Integer, db.ForeignKey("school_classes.id"), nullable=False)

    students = db.relationship("Student", backref="division")

    @property
    def display_name(self):
        return f"{self.school_class.name} - {self.name}"

    def __repr__(self):
        return f"<Division {self.display_name}>"


class User(db.Model, UserMixin):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(10), nullable=False)  # 'admin' or 'teacher'
    name = db.Column(db.String(120), nullable=False)
    active = db.Column(db.Boolean, default=True, nullable=False)

    teacher = db.relationship("Teacher", backref="user", uselist=False, cascade="all, delete-orphan")

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    @property
    def is_active(self):
        return self.active

    @property
    def is_admin(self):
        return self.role == "admin"

    def __repr__(self):
        return f"<User {self.username} ({self.role})>"


class Teacher(db.Model):
    __tablename__ = "teachers"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    name = db.Column(db.String(120), nullable=False)
    phone = db.Column(db.String(20))
    active = db.Column(db.Boolean, default=True, nullable=False)

    divisions = db.relationship("Division", secondary=teacher_divisions, backref="teachers")
    subjects = db.relationship("Subject", secondary=teacher_subjects, backref="teachers")

    @property
    def subject_names(self):
        return ", ".join(s.name for s in sorted(self.subjects, key=lambda s: s.name))

    def __repr__(self):
        return f"<Teacher {self.name}>"


class Student(db.Model):
    __tablename__ = "students"

    id = db.Column(db.Integer, primary_key=True)
    admission_no = db.Column(db.String(20), unique=True, nullable=False)
    name = db.Column(db.String(120), nullable=False)
    class_id = db.Column(db.Integer, db.ForeignKey("school_classes.id"), nullable=False)
    division_id = db.Column(db.Integer, db.ForeignKey("divisions.id"), nullable=False)

    parent_name = db.Column(db.String(120))
    parent_whatsapp = db.Column(db.String(20), nullable=False)
    address = db.Column(db.String(255))
    place = db.Column(db.String(120))
    school_name = db.Column(db.String(150))

    dob = db.Column(db.Date, nullable=True)
    admission_date = db.Column(db.Date, default=date.today, nullable=False)

    base_fee_override = db.Column(db.Float, nullable=True)
    discount_amount = db.Column(db.Float, default=0, nullable=False)
    discount_reason = db.Column(db.String(255))

    active = db.Column(db.Boolean, default=True, nullable=False)

    payments = db.relationship(
        "FeePayment", backref="student", cascade="all, delete-orphan", order_by="FeePayment.payment_date"
    )
    attendances = db.relationship("Attendance", backref="student", cascade="all, delete-orphan")

    @property
    def class_fee(self):
        return self.base_fee_override if self.base_fee_override is not None else self.school_class.base_fee

    @property
    def total_fee(self):
        return max(self.class_fee - (self.discount_amount or 0), 0)

    @property
    def total_paid(self):
        return sum(p.amount for p in self.payments)

    @property
    def pending_fee(self):
        return round(self.total_fee - self.total_paid, 2)

    @property
    def payment_status(self):
        if self.pending_fee <= 0:
            return "Paid"
        if self.total_paid > 0:
            return "Partial"
        return "Unpaid"

    def __repr__(self):
        return f"<Student {self.admission_no} {self.name}>"


class FeePayment(db.Model):
    __tablename__ = "fee_payments"

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey("students.id"), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    payment_date = db.Column(db.Date, default=date.today, nullable=False)
    mode = db.Column(db.String(20), default="Cash", nullable=False)
    receipt_no = db.Column(db.String(30))
    remarks = db.Column(db.String(255))
    recorded_by = db.Column(db.String(120))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<FeePayment {self.student_id} {self.amount}>"


class Attendance(db.Model):
    __tablename__ = "attendance"
    __table_args__ = (db.UniqueConstraint("student_id", "date", name="uq_attendance_student_date"),)

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey("students.id"), nullable=False)
    division_id = db.Column(db.Integer, db.ForeignKey("divisions.id"), nullable=False)
    date = db.Column(db.Date, nullable=False, default=date.today)
    status = db.Column(db.String(10), nullable=False)  # 'present' / 'absent'
    marked_by = db.Column(db.String(120))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<Attendance {self.student_id} {self.date} {self.status}>"


class MessageLog(db.Model):
    __tablename__ = "message_logs"

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey("students.id"), nullable=False)
    date = db.Column(db.Date, default=date.today)
    category = db.Column(db.String(20), default="attendance", nullable=False)  # attendance / fee_reminder
    message = db.Column(db.Text, nullable=False)
    phone = db.Column(db.String(20))
    status = db.Column(db.String(20), default="pending")  # sent / failed / manual
    detail = db.Column(db.String(255))
    manual_link = db.Column(db.String(500))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    student = db.relationship("Student")

    def __repr__(self):
        return f"<MessageLog {self.student_id} {self.status}>"


class Settings(db.Model):
    """Singleton row (id=1) holding academy-wide, admin-editable settings."""

    __tablename__ = "settings"

    id = db.Column(db.Integer, primary_key=True)
    academy_name = db.Column(db.String(120), default="Brainwave Academy", nullable=False)
    upi_id = db.Column(db.String(120))
    upi_payee_name = db.Column(db.String(120))

    @classmethod
    def get(cls):
        settings = cls.query.get(1)
        if settings is None:
            settings = cls(id=1, academy_name="Brainwave Academy")
            db.session.add(settings)
            db.session.commit()
        return settings

    def __repr__(self):
        return f"<Settings {self.academy_name}>"
