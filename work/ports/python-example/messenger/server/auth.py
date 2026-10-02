from __future__ import annotations
import base64
import hashlib
import hmac
import json
import re
import secrets
import time
from typing import Optional

from sqlalchemy import select, delete, update

from .config import settings
from .db import db_session, User, EmailCode
from .mailer import send_verification_email, send_reset_email


USERNAME_RE = re.compile(r"^[\w\-. ]{3,32}$", re.UNICODE)
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class AuthError(Exception):
    pass


# ==================== Валидация ====================

def validate_username(u: str) -> str:
    u = (u or "").strip()
    if not USERNAME_RE.match(u):
        raise AuthError("Имя: 3–32 символа, буквы/цифры/пробел/точка/дефис")
    return u


def validate_email(e: str) -> str:
    e = (e or "").strip().lower()
    if not EMAIL_RE.match(e) or len(e) > 254:
        raise AuthError("Некорректный email")
    return e


def validate_password(p: str) -> str:
    if not p or len(p) < 6:
        raise AuthError("Пароль минимум 6 символов")
    return p


# ==================== Пароли ====================

def hash_password(p: str) -> str:
    import bcrypt  # not a dependency; fallback below
    return bcrypt.hashpw(p.encode(), bcrypt.gensalt()).decode()


def verify_password(p: str, h: str) -> bool:
    import bcrypt
    try:
        return bcrypt.checkpw(p.encode(), h.encode())
    except Exception:
        return False
import hashlib, secrets, base64

def hash_password(p: str) -> str:
    salt = secrets.token_bytes(16)
    dk = hashlib.scrypt(p.encode(), salt=salt, n=2**14, r=8, p=1, dklen=32)
    return "scrypt$" + base64.b64encode(salt).decode() + "$" + base64.b64encode(dk).decode()

def verify_password(p: str, h: str) -> bool:
    try:
        algo, salt_b64, dk_b64 = h.split("$")
        if algo != "scrypt":
            return False
        salt = base64.b64decode(salt_b64)
        expected = base64.b64decode(dk_b64)
        actual = hashlib.scrypt(p.encode(), salt=salt, n=2**14, r=8, p=1, dklen=32)
        return hmac.compare_digest(expected, actual)
    except Exception:
        return False
# ==================== Токены ====================

def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def _b64d(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def issue_token(user_id: int) -> str:
    payload = {"uid": user_id, "exp": int(time.time()) + settings.TOKEN_TTL}
    raw = json.dumps(payload, separators=(",", ":")).encode()
    sig = hmac.new(settings.TOKEN_SECRET.encode(), raw, hashlib.sha256).digest()
    return f"{_b64(raw)}.{_b64(sig)}"


def verify_token(token: str) -> Optional[int]:
    try:
        p, s = token.split(".")
        raw = _b64d(p)
        sig = _b64d(s)
        expected = hmac.new(settings.TOKEN_SECRET.encode(), raw, hashlib.sha256).digest()
        if not hmac.compare_digest(sig, expected):
            return None
        data = json.loads(raw)
        if data.get("exp", 0) < time.time():
            return None
        return int(data["uid"])
    except Exception:
        return None


# ==================== Коды ====================

def _issue_code(session, user_id: int, purpose: str) -> str:
    assert purpose in ("verify", "reset")

    last = session.execute(
        select(EmailCode).where(
            EmailCode.user_id == user_id,
            EmailCode.purpose == purpose,
        ).order_by(EmailCode.id.desc()).limit(1)
    ).scalar_one_or_none()

    if last:
        age = time.time() - last.created_at.timestamp()
        if age < settings.RESEND_DELAY:
            raise AuthError("Подождите минуту перед повторной отправкой")

    session.execute(
        update(EmailCode)
        .where(EmailCode.user_id == user_id,
               EmailCode.purpose == purpose,
               EmailCode.used == False)
        .values(used=True)
    )

    code = f"{secrets.randbelow(1_000_000):06d}"
    session.add(EmailCode(
        user_id=user_id, code=code, purpose=purpose,
        expires_at=int(time.time()) + settings.CODE_TTL,
    ))
    session.flush()
    return code


def _verify_code(session, user_id: int, code: str, purpose: str) -> bool:
    row = session.execute(
        select(EmailCode).where(
            EmailCode.user_id == user_id,
            EmailCode.purpose == purpose,
            EmailCode.used == False,
        ).order_by(EmailCode.id.desc()).limit(1)
    ).scalar_one_or_none()
    if not row:
        return False
    if row.expires_at < time.time():
        return False
    if not hmac.compare_digest(row.code, code):
        return False
    row.used = True
    return True


# ==================== Регистрация / логин ====================

async def register(username: str, email: str, password: str) -> dict:
    username = validate_username(username)
    email = validate_email(email)
    validate_password(password)

    with db_session() as s:
        if s.execute(select(User).where(User.username == username)).scalar_one_or_none():
            raise AuthError("Имя уже занято")

        existing = s.execute(select(User).where(User.email == email)).scalar_one_or_none()
        if existing and existing.email_verified:
            raise AuthError("Этот email уже зарегистрирован")
        if existing:
            s.delete(existing)
            s.flush()

        user = User(
            username=username, email=email,
            password_hash=hash_password(password),
            email_verified=False,
        )
        s.add(user)
        s.flush()

        code = _issue_code(s, user.id, "verify")
        s.commit()

    await send_verification_email(email, username, code)
    return {"id": user.id, "username": username, "email": email, "needsVerify": True}


def login(login_value: str, password: str) -> dict:
    login_value = (login_value or "").strip()
    if not login_value or not password:
        raise AuthError("Введите логин и пароль")

    with db_session() as s:
        user = s.execute(
            select(User).where(
                (User.username == login_value) | (User.email == login_value.lower())
            ).limit(1)
        ).scalar_one_or_none()

        if not user or not verify_password(password, user.password_hash):
            raise AuthError("Неверный логин или пароль")

        return {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "verified": bool(user.email_verified),
            "token": issue_token(user.id),
        }


async def confirm_email(login_value: str, code: str) -> dict:
    with db_session() as s:
        user = s.execute(
            select(User).where(
                (User.username == login_value) | (User.email == (login_value or "").lower())
            ).limit(1)
        ).scalar_one_or_none()
        if not user:
            raise AuthError("Пользователь не найден")

        if not _verify_code(s, user.id, code, "verify"):
            raise AuthError("Неверный или просроченный код")

        user.email_verified = True
        s.flush()
        result = {"id": user.id, "username": user.username,
                  "email": user.email, "token": issue_token(user.id)}
        s.commit()
        return result


async def resend_verify_code(login_value: str) -> None:
    with db_session() as s:
        user = s.execute(
            select(User).where(
                (User.username == login_value) | (User.email == (login_value or "").lower())
            ).limit(1)
        ).scalar_one_or_none()
        if not user:
            raise AuthError("Пользователь не найден")
        if user.email_verified:
            raise AuthError("Email уже подтверждён")

        code = _issue_code(s, user.id, "verify")
        email, username = user.email, user.username
        s.commit()

    await send_verification_email(email, username, code)


async def send_reset_code(email: str) -> None:
    email = validate_email(email)

    with db_session() as s:
        user = s.execute(
            select(User).where(User.email == email, User.email_verified == True)
        ).scalar_one_or_none()
        if not user:
            return   # не раскрываем, есть ли email

        code = _issue_code(s, user.id, "reset")
        s.commit()

    await send_reset_email(email, user.username, code)


def reset_password(email: str, code: str, new_password: str) -> None:
    email = validate_email(email)
    validate_password(new_password)

    with db_session() as s:
        user = s.execute(
            select(User).where(User.email == email, User.email_verified == True)
        ).scalar_one_or_none()
        if not user:
            raise AuthError("Пользователь не найден")
        if not _verify_code(s, user.id, code, "reset"):
            raise AuthError("Неверный или просроченный код")

        user.password_hash = hash_password(new_password)
        s.commit()


def get_user(user_id: int) -> Optional[dict]:
    with db_session() as s:
        u = s.get(User, user_id)
        if not u:
            return None
        return {"id": u.id, "username": u.username, "email": u.email,
                "verified": bool(u.email_verified)}