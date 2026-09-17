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

    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(teacher_bp)

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
        _ensure_seed_data(app)

    register_cli(app)

    return app


def _ensure_seed_data(app):
    """Create default classes/divisions and an admin account the first time
    the app runs, so the school can log in immediately after installation."""
    from .models import SchoolClass, Division, User

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


def register_cli(app):
    @app.cli.command("seed-db")
    def seed_db():
        """Re-run the initial seed (safe to run multiple times)."""
        _ensure_seed_data(app)
        print("Seed data ensured.")
