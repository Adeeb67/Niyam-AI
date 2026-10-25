"""Cookie based authentication helpers. Session secrets are random and stored hashed."""
import hashlib
import hmac
import os
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException, Request, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from .database import get_db
from .models import User, UserSession

COOKIE_NAME = "niyam_session"
SESSION_DAYS = 7
PASSWORD_ITERATIONS = 600_000


def cookie_samesite() -> str:
    setting = os.getenv("COOKIE_SAMESITE", "lax").lower()
    return setting if setting in {"lax", "strict", "none"} else "lax"


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PASSWORD_ITERATIONS)
    return f"pbkdf2_sha256${PASSWORD_ITERATIONS}${salt.hex()}${digest.hex()}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, rounds, salt_hex, expected_hex = encoded.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), int(rounds))
        return hmac.compare_digest(actual.hex(), expected_hex)
    except (ValueError, TypeError):
        return False


def public_user(user: User) -> dict:
    return {"id": user.id, "name": user.name, "email": user.email, "role": user.role, "created_at": user.created_at.isoformat()}


def start_session(user: User, response: Response, db: Session) -> None:
    raw = secrets.token_urlsafe(32)
    db.add(UserSession(token_hash=hashlib.sha256(raw.encode()).hexdigest(), user_id=user.id, expires_at=datetime.now(timezone.utc) + timedelta(days=SESSION_DAYS)))
    db.commit()
    secure = os.getenv("COOKIE_SECURE", "false").lower() == "true"
    same_site = cookie_samesite()
    response.set_cookie(COOKIE_NAME, raw, httponly=True, secure=secure or same_site == "none", samesite=same_site, max_age=SESSION_DAYS * 86400, path="/")


def current_user(request: Request, db: Session = Depends(get_db)) -> User:
    raw = request.cookies.get(COOKIE_NAME)
    if not raw:
        raise HTTPException(401, "Sign in required")
    session = db.scalar(select(UserSession).where(UserSession.token_hash == hashlib.sha256(raw.encode()).hexdigest()))
    if not session or session.expires_at.replace(tzinfo=timezone.utc) <= datetime.now(timezone.utc):
        raise HTTPException(401, "Session expired; sign in again")
    user = db.get(User, session.user_id)
    if not user:
        raise HTTPException(401, "Sign in required")
    return user


def admin_user(user: User = Depends(current_user)) -> User:
    if user.role != "admin":
        raise HTTPException(403, "Administrator access required")
    return user


def end_session(request: Request, response: Response, db: Session) -> None:
    raw = request.cookies.get(COOKIE_NAME)
    if raw:
        row = db.scalar(select(UserSession).where(UserSession.token_hash == hashlib.sha256(raw.encode()).hexdigest()))
        if row:
            db.delete(row)
            db.commit()
    secure = os.getenv("COOKIE_SECURE", "false").lower() == "true"
    same_site = cookie_samesite()
    response.delete_cookie(COOKIE_NAME, path="/", httponly=True, secure=secure or same_site == "none", samesite=same_site)


def bootstrap_admin(email: str, db: Session) -> User:
    """Promote only an explicitly configured existing account; never creates credentials."""
    normalized = email.strip().lower()
    if not normalized:
        raise ValueError("ADMIN_BOOTSTRAP_EMAIL is required")
    user = db.scalar(select(User).where(User.email == normalized))
    if not user:
        raise ValueError("Register the configured admin email first, then rerun bootstrap")
    user.role = "admin"
    db.commit()
    return user
