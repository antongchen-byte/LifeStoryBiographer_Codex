import hashlib
import hmac
import secrets
from datetime import timedelta

from redis import Redis
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..config import settings
from ..domain.errors import DomainError
from ..models import AuthSession, User, now
from ..schemas import Login, Register


def password_hash(password: str, salt: str | None = None) -> str:
    salt = salt or secrets.token_hex(16)
    key = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1)
    return f"scrypt${salt}${key.hex()}"


def password_matches(password: str, stored: str) -> bool:
    try:
        _, salt, _ = stored.split("$")
        return hmac.compare_digest(password_hash(password, salt), stored)
    except (ValueError, TypeError):
        return False


DUMMY_HASH = password_hash("invalid-account-password")


def rate_limit(key: str) -> None:
    redis = Redis.from_url(settings.redis_url, socket_connect_timeout=2, socket_timeout=2)
    redis_key = "auth-attempts:" + hashlib.sha256(key.encode()).hexdigest()
    count = redis.eval(
        "local n=redis.call('INCR',KEYS[1]); if n==1 then redis.call('EXPIRE',KEYS[1],300) end; return n",
        1,
        redis_key,
    )
    if count > 20:
        raise DomainError(429, "Too many sign-in attempts. Try again in five minutes.")


def register(db: Session, data: Register) -> User:
    if not settings.allow_registration:
        raise DomainError(403, "Registration is disabled")
    user = User(email=data.email, name=data.name, password_hash=password_hash(data.password))
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise DomainError(409, "Unable to register this email address") from None
    return user


def login(db: Session, data: Login) -> tuple[str, User]:
    user = db.scalar(select(User).where(User.email == data.email))
    valid = password_matches(data.password, user.password_hash if user else DUMMY_HASH)
    if not user or not valid:
        raise DomainError(401, "Email or password is incorrect")
    token = secrets.token_urlsafe(32)
    db.add(
        AuthSession(
            token_hash=hashlib.sha256(token.encode()).hexdigest(),
            user_id=user.id,
            expires_at=now() + timedelta(days=settings.session_days),
        )
    )
    db.execute(delete(AuthSession).where(AuthSession.expires_at < now()))
    db.commit()
    return token, user


def authenticate(db: Session, token: str) -> User:
    session = db.scalar(
        select(AuthSession).where(
            AuthSession.token_hash == hashlib.sha256(token.encode()).hexdigest(),
            AuthSession.expires_at > now(),
        )
    )
    user = db.get(User, session.user_id) if session else None
    if not user:
        raise DomainError(401, "Your session has expired. Please sign in again.")
    return user


def logout(db: Session, token: str) -> None:
    db.execute(
        delete(AuthSession).where(AuthSession.token_hash == hashlib.sha256(token.encode()).hexdigest())
    )
    db.commit()
