from flask import (Blueprint, render_template, redirect, url_for,
                   request, flash, session)
from flask_login import login_user, logout_user, login_required, current_user
from datetime import datetime, timedelta
import smtplib
import os
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from models import db, User, AuditLog, PasswordResetToken

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


# ── Email helper ──────────────────────────────────────────────────────────────

def _send_email(to: str, subject: str, html_body: str) -> bool:
    """Send email via SMTP. Returns True on success."""
    host     = os.environ.get("SMTP_HOST",      "smtp.hostinger.com")
    port     = int(os.environ.get("SMTP_PORT",  "587"))
    user     = os.environ.get("SMTP_USER",      "support@vilchesab.se")
    password = os.environ.get("SMTP_PASS",      "PugA#V24!Wr#")
    from_name= os.environ.get("SMTP_FROM_NAME", "ApplyMind AI")
    from_email = os.environ.get("SMTP_FROM_EMAIL", "support@vilchesab.se")

    if not host or not user or not password:
        return False

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = f"{from_name} <{from_email}>"
    msg["To"]      = to
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    try:
        with smtplib.SMTP(host, port, timeout=15) as s:
            s.ehlo()
            s.starttls()
            s.login(user, password)
            s.sendmail(from_email, [to], msg.as_string())
        return True
    except Exception as e:
        print(f"[SMTP error] {e}")
        return False


# ── Forgot password ───────────────────────────────────────────────────────────

@auth_bp.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    if current_user.is_authenticated:
        return redirect(url_for("index"))

    sent = False
    error = None

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        user  = User.query.filter_by(email=email, is_active=True).first()

        if user:
            token_obj = PasswordResetToken.create_for_user(user.id)
            reset_url = url_for("auth.reset_password",
                                token=token_obj.token, _external=True)
            html = f"""
            <div style="font-family:Arial,sans-serif;max-width:560px;margin:0 auto;background:#111;color:#e8e8e8;padding:32px;border-radius:12px;border:1px solid #2a2a2a;">
              <div style="margin-bottom:24px;">
                <span style="color:#4AE54A;font-weight:700;font-size:18px;">⚡ ApplyMind AI</span>
              </div>
              <h2 style="color:#fff;font-size:22px;margin:0 0 12px;">Återställ ditt lösenord</h2>
              <p style="color:#888;margin:0 0 24px;">
                Vi fick en förfrågan om att återställa lösenordet för <strong style="color:#e8e8e8;">{user.email}</strong>.<br>
                Länken är giltig i <strong style="color:#e8e8e8;">1 timme</strong>.
              </p>
              <a href="{reset_url}"
                 style="display:inline-block;background:#4AE54A;color:#111;font-weight:700;padding:14px 28px;border-radius:8px;text-decoration:none;font-size:15px;margin-bottom:24px;">
                Återställ lösenord
              </a>
              <p style="color:#555;font-size:12px;margin:24px 0 0;border-top:1px solid #2a2a2a;padding-top:16px;">
                Om du inte bad om detta kan du ignorera mailet. Länken är engångsgiltig.<br>
                © 2026 ApplyMind AI · vilchesapp.com
              </p>
            </div>
            """
            _send_email(user.email, "Återställ ditt lösenord — ApplyMind AI", html)

        # Always show success to prevent user enumeration
        sent = True

    return render_template("auth/forgot_password.html", sent=sent, error=error)


@auth_bp.route("/reset-password/<token>", methods=["GET", "POST"])
def reset_password(token: str):
    if current_user.is_authenticated:
        return redirect(url_for("index"))

    token_obj = PasswordResetToken.query.filter_by(token=token).first()

    if not token_obj or not token_obj.is_valid:
        return render_template("auth/reset_password.html",
                               invalid=True, token=token)

    error = None
    if request.method == "POST":
        password = request.form.get("password", "")
        confirm  = request.form.get("confirm", "")

        if len(password) < 8:
            error = "Lösenordet måste vara minst 8 tecken."
        elif password != confirm:
            error = "Lösenorden matchar inte."
        else:
            token_obj.user.set_password(password)
            token_obj.used = True
            db.session.commit()
            return render_template("auth/reset_password.html",
                                   success=True, token=token)

    return render_template("auth/reset_password.html",
                           invalid=False, token=token, error=error)


# ── Change password (logged in) ───────────────────────────────────────────────

@auth_bp.route("/change-password", methods=["POST"])
@login_required
def change_password():
    current_pw = request.form.get("current_password", "")
    new_pw     = request.form.get("new_password", "")
    confirm_pw = request.form.get("confirm_password", "")

    if not current_user.check_password(current_pw):
        flash("Nuvarande lösenord är fel.", "error")
    elif len(new_pw) < 8:
        flash("Nytt lösenord måste vara minst 8 tecken.", "error")
    elif new_pw != confirm_pw:
        flash("Lösenorden matchar inte.", "error")
    else:
        current_user.set_password(new_pw)
        db.session.commit()
        flash("Lösenordet har ändrats.", "success")

    return redirect(url_for("settings"))
