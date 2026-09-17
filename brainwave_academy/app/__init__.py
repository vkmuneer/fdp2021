import os
from datetime import date

from flask import Flask

from config import Config
from .extensions import db, login_manager


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    db.init_app(app)
    login_manager.init_app(app)

    from .models import User

    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(User, int(user_id))

    from .auth.routes import auth_bp
    from .admin.routes import admin_bp
    from .teacher.routes import teacher_bp
    from .public.routes import public_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(teacher_bp)
    app.register_blueprint(public_bp)

    from flask import redirect, url_for
    from flask_login import current_user

    @app.route("/")
    def index():
        if not current_user.is_authenticated:
            return redirect(url_for("auth.login"))
        if current_user.is_admin:
            return redirect(url_for("admin.dashboard"))
        return redirect(url_for("teacher.dashboard"))

    @app.context_processor
    def inject_globals():
        return {"today": date.today(), "app_name": "Brainwave Academy"}

    with app.app_context():
        db.create_all()
        _auto_migrate(app)
        _backfill_masters(app)
        _ensure_seed_data(app)

    register_cli(app)

    return app


def _auto_migrate(app):
    """Adds any model columns that are missing from already-existing tables.

    db.create_all() only creates tables that don't exist yet - it never alters
    ones that do, so a schema change (like adding Student.place) would crash
    an existing deployment's database on the next boot without this. This is
    a lightweight stand-in for a full migration tool, sufficient because our
    schema changes are additive-only (new nullable columns/tables)."""
    from sqlalchemy import inspect, text

    inspector = inspect(db.engine)
    existing_tables = set(inspector.get_table_names())

    for table in db.metadata.sorted_tables:
        if table.name not in existing_tables:
            continue  # a brand-new table - db.create_all() already built it
        existing_columns = {col["name"] for col in inspector.get_columns(table.name)}
        for column in table.columns:
            if column.name in existing_columns:
                continue
            col_type = column.type.compile(dialect=db.engine.dialect)
            with db.engine.begin() as conn:
                conn.execute(text(f'ALTER TABLE "{table.name}" ADD COLUMN "{column.name}" {col_type}'))
            app.logger.info("[auto-migrate] added column %s.%s", table.name, column.name)


def _backfill_masters(app):
    """One-time (idempotent) migration for the subject/place/school master
    lists: seeds Place/SchoolMaster from any values already on Student rows,
    and Subject from the legacy free-text teachers.subject column (which the
    model no longer declares), linking each teacher to its matching Subject
    so nothing is lost when upgrading a deployment that predates this."""
    from sqlalchemy import inspect, text
    from .models import Student, Teacher, Subject, Place, SchoolMaster

    for value, in db.session.query(Student.place).distinct():
        value = (value or "").strip()
        if value and not Place.query.filter_by(name=value).first():
            db.session.add(Place(name=value))

    for value, in db.session.query(Student.school_name).distinct():
        value = (value or "").strip()
        if value and not SchoolMaster.query.filter_by(name=value).first():
            db.session.add(SchoolMaster(name=value))

    db.session.commit()

    inspector = inspect(db.engine)
    teacher_columns = {c["name"] for c in inspector.get_columns("teachers")}
    if "subject" in teacher_columns:
        rows = db.session.execute(
            text("SELECT id, subject FROM teachers WHERE subject IS NOT NULL AND subject != ''")
        ).fetchall()
        for teacher_id, subject_name in rows:
            subject_name = (subject_name or "").strip()
            if not subject_name:
                continue
            subject = Subject.query.filter_by(name=subject_name).first()
            if subject is None:
                subject = Subject(name=subject_name)
                db.session.add(subject)
                db.session.flush()
            teacher = db.session.get(Teacher, teacher_id)
            if teacher and subject not in teacher.subjects:
                teacher.subjects.append(subject)
        db.session.commit()


def _ensure_seed_data(app):
    """Create default classes/divisions and an admin account the first time
    the app runs, so the school can log in immediately after installation."""
    from .models import SchoolClass, Division, User, Settings

    if SchoolClass.query.first() is None:
        for name, fee in app.config["DEFAULT_CLASS_FEES"].items():
            school_class = SchoolClass(name=name, base_fee=fee)
            school_class.divisions.append(Division(name="A"))
            db.session.add(school_class)
        db.session.commit()

    if User.query.filter_by(role="admin").first() is None:
        admin = User(
            username=app.config["DEFAULT_ADMIN_USERNAME"],
            name="Administrator",
            role="admin",
        )
        admin.set_password(app.config["DEFAULT_ADMIN_PASSWORD"])
        db.session.add(admin)
        db.session.commit()

    if Settings.query.get(1) is None:
        db.session.add(Settings(id=1, academy_name="Brainwave Academy"))
        db.session.commit()


def register_cli(app):
    @app.cli.command("seed-db")
    def seed_db():
        """Re-run the initial seed (safe to run multiple times)."""
        _ensure_seed_data(app)
        print("Seed data ensured.")
