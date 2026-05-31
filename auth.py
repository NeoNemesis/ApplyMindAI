from flask import (Blueprint, render_template, redirect, url_for,
                   request, flash, session)
from flask_login import login_user, logout_user, login_required, current_user
from datetime import datetime, timedelta
from models import db, User, AuditLog

auth_bp = Blueprint("auth", __name__, url_prefix="/auth")

# Simple in-memory rate limiter: {ip: [timestamp, ...]}
_login_attempts: dict = {}
MAX_ATTEMPTS = 5
WINDOW_SECONDS = 60


def _is_rate_limited(ip: str) -> tuple[bool, int]:
    """Returns (is_limited, seconds_until_reset)."""
    now = datetime.utcnow()
    cutoff = now - timedelta(seconds=WINDOW_SECONDS)
    attempts = [t for t in _login_attempts.get(ip, []) if t > cutoff]
    _login_attempts[ip] = attempts
    if len(attempts) >= MAX_ATTEMPTS:
        oldest = min(attempts)
        wait = int(WINDOW_SECONDS - (now - oldest).total_seconds()) + 1
        return True, max(wait, 1)
    return False, 0


def _record_attempt(ip: str) -> None:
    _login_attempts.setdefault(ip, []).append(datetime.utcnow())


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("index"))

    error = None
    rate_wait = 0

    if request.method == "POST":
        ip = request.remote_addr or "unknown"
        limited, rate_wait = _is_rate_limited(ip)

        if limited:
            error = f"För många försök. Försök igen om {rate_wait} sekunder."
        else:
            identifier = request.form.get("email", "").strip().lower()
            password   = request.form.get("password", "")
            remember   = bool(request.form.get("remember"))

            user = (User.query
                    .filter(db.or_(
                        User.email == identifier,
                        User.username == identifier
                    ))
                    .first())

            if user and user.is_active and user.check_password(password):
                login_user(user, remember=remember,
                           duration=timedelta(days=30) if remember else None)
                user.last_login = datetime.utcnow()
                db.session.commit()
                next_page = request.args.get("next") or url_for("index")
                # Safety: only redirect to relative URLs
                if next_page.startswith("http"):
                    next_page = url_for("index")
                return redirect(next_page)
            else:
                _record_attempt(ip)
                error = "Fel e-post/användarnamn eller lösenord."

    return render_template("auth/login.html", error=error, rate_wait=rate_wait)


@auth_bp.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("auth.login"))
