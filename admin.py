from flask import Blueprint, render_template, redirect, url_for, request, flash, abort
from flask_login import login_required, current_user
from functools import wraps
from datetime import datetime
from models import db, User, AuditLog

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")


def admin_required(f):
    @wraps(f)
    @login_required
    def decorated(*args, **kwargs):
        if not current_user.is_admin:
            abort(403)
        return f(*args, **kwargs)
    return decorated


def _log(action: str, target_id: int | None = None, detail: str | None = None):
    entry = AuditLog(
        admin_id  = current_user.id,
        action    = action,
        target_id = target_id,
        detail    = detail,
    )
    db.session.add(entry)
    db.session.commit()


@admin_bp.route("/")
@admin_required
def dashboard():
    users      = User.query.order_by(User.created_at.desc()).all()
    audit_logs = AuditLog.query.order_by(AuditLog.timestamp.desc()).limit(20).all()
    return render_template("admin/dashboard.html", users=users, audit_logs=audit_logs)


@admin_bp.route("/users/create", methods=["POST"])
@admin_required
def create_user():
    username = request.form.get("username", "").strip()
    email    = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "").strip()
    role     = request.form.get("role", "user")

    if not username or not email or not password:
        flash("Alla fält krävs.", "error")
        return redirect(url_for("admin.dashboard"))

    if len(password) < 8:
        flash("Lösenordet måste vara minst 8 tecken.", "error")
        return redirect(url_for("admin.dashboard"))

    if User.query.filter_by(email=email).first():
        flash(f"E-postadressen {email} används redan.", "error")
        return redirect(url_for("admin.dashboard"))

    if User.query.filter_by(username=username).first():
        flash(f"Användarnamnet {username} används redan.", "error")
        return redirect(url_for("admin.dashboard"))

    user = User(username=username, email=email, role=role, is_active=True)
    user.set_password(password)
    db.session.add(user)
    db.session.commit()

    _log("create_user", target_id=user.id, detail=f"email={email} role={role}")
    flash(f"Konto skapat för {username} ({email}).", "success")
    return redirect(url_for("admin.dashboard"))


@admin_bp.route("/users/<int:user_id>/toggle-role", methods=["POST"])
@admin_required
def toggle_role(user_id: int):
    user = User.query.get_or_404(user_id)
    if user.id == current_user.id:
        flash("Du kan inte ändra din egen roll.", "error")
        return redirect(url_for("admin.dashboard"))
    user.role = "user" if user.role == "admin" else "admin"
    db.session.commit()
    _log("toggle_role", target_id=user.id, detail=f"username={user.username} new_role={user.role}")
    flash(f"{user.username} är nu {user.role}.", "success")
    return redirect(url_for("admin.dashboard"))


@admin_bp.route("/users/<int:user_id>/toggle", methods=["POST"])
@admin_required
def toggle_user(user_id: int):
    user = User.query.get_or_404(user_id)
    if user.id == current_user.id:
        flash("Du kan inte inaktivera ditt eget konto.", "error")
        return redirect(url_for("admin.dashboard"))
    user.is_active = not user.is_active
    db.session.commit()
    action = "activate_user" if user.is_active else "deactivate_user"
    _log(action, target_id=user.id, detail=f"username={user.username}")
    state = "aktiverat" if user.is_active else "inaktiverat"
    flash(f"Kontot för {user.username} är nu {state}.", "success")
    return redirect(url_for("admin.dashboard"))


@admin_bp.route("/users/<int:user_id>/delete", methods=["POST"])
@admin_required
def delete_user(user_id: int):
    user = User.query.get_or_404(user_id)
    if user.id == current_user.id:
        flash("Du kan inte radera ditt eget konto.", "error")
        return redirect(url_for("admin.dashboard"))
    username = user.username
    # Delete user's uploaded files
    import shutil
    from pathlib import Path
    from flask import current_app
    user_dir = Path(current_app.instance_path) / "uploads" / f"user_{user_id}"
    if user_dir.exists():
        shutil.rmtree(user_dir)
    db.session.delete(user)
    db.session.commit()
    _log("delete_user", target_id=user_id, detail=f"username={username}")
    flash(f"Kontot för {username} och all tillhörande data har raderats.", "success")
    return redirect(url_for("admin.dashboard"))
