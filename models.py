from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, VerificationError, InvalidHashError
from datetime import datetime, timedelta
import secrets

db = SQLAlchemy()
ph = PasswordHasher(memory_cost=65536, time_cost=3, parallelism=1)


class User(UserMixin, db.Model):
    __tablename__ = "user"

    id            = db.Column(db.Integer, primary_key=True)
    username      = db.Column(db.String(64), unique=True, nullable=False)
    email         = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.Text, nullable=False)
    role          = db.Column(db.String(16), default="user")   # 'admin' | 'user'
    is_active     = db.Column(db.Boolean, default=True)
    created_at    = db.Column(db.DateTime, default=datetime.utcnow)
    last_login    = db.Column(db.DateTime, nullable=True)

    # Per-user AI settings
    llm_provider  = db.Column(db.String(32), default="openai")
    llm_model     = db.Column(db.String(64), default="gpt-4o-mini")
    llm_api_key   = db.Column(db.Text, nullable=True)   # stored as-is; encrypt in prod
    language      = db.Column(db.String(8), default="sv")

    # LinkedIn (optional)
    linkedin_email    = db.Column(db.String(120), nullable=True)
    linkedin_password = db.Column(db.Text, nullable=True)

    def set_password(self, password: str) -> None:
        self.password_hash = ph.hash(password)

    def check_password(self, password: str) -> bool:
        try:
            ph.verify(self.password_hash, password)
            # Rehash if needed (argon2 parameter upgrade)
            if ph.check_needs_rehash(self.password_hash):
                self.password_hash = ph.hash(password)
                db.session.commit()
            return True
        except (VerifyMismatchError, VerificationError, InvalidHashError):
            return False

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"

    def get_data_dir(self, base_instance_path: str) -> str:
        from pathlib import Path
        path = Path(base_instance_path) / "uploads" / f"user_{self.id}" / "data"
        path.mkdir(parents=True, exist_ok=True)
        return str(path)

    def get_output_dir(self, base_instance_path: str) -> str:
        from pathlib import Path
        path = Path(base_instance_path) / "uploads" / f"user_{self.id}" / "output"
        path.mkdir(parents=True, exist_ok=True)
        return str(path)

    def __repr__(self) -> str:
        return f"<User {self.username} ({self.role})>"


class PasswordResetToken(db.Model):
    __tablename__ = "password_reset_token"

    id         = db.Column(db.Integer, primary_key=True)
    user_id    = db.Column(db.Integer, db.ForeignKey("user.id", ondelete="CASCADE"), nullable=False)
    token      = db.Column(db.String(64), unique=True, nullable=False)
    expires_at = db.Column(db.DateTime, nullable=False)
    used       = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship("User", foreign_keys=[user_id])

    @classmethod
    def create_for_user(cls, user_id: int) -> "PasswordResetToken":
        # Invalidate existing tokens for this user
        cls.query.filter_by(user_id=user_id, used=False).delete()
        token = cls(
            user_id    = user_id,
            token      = secrets.token_urlsafe(48),
            expires_at = datetime.utcnow() + timedelta(hours=1),
        )
        db.session.add(token)
        db.session.commit()
        return token

    @property
    def is_valid(self) -> bool:
        return not self.used and datetime.utcnow() < self.expires_at


class AuditLog(db.Model):
    __tablename__ = "audit_log"

    id        = db.Column(db.Integer, primary_key=True)
    admin_id  = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    action    = db.Column(db.String(64))
    target_id = db.Column(db.Integer, nullable=True)
    detail    = db.Column(db.Text, nullable=True)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

    admin = db.relationship("User", foreign_keys=[admin_id])
