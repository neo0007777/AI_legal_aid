import os
import uuid
from datetime import datetime, timedelta
import hashlib
from typing import Optional
from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from models.database import get_db, User, UserSession, LoginAttempt

# Loophole fix #1: this used to silently fall back to the literal string
# "change_this_in_production" when the env var was unset -- a real, guessable
# secret visible in this very file. Anyone reading the source could forge a
# valid JWT for any user (including admin) against a deployment that forgot
# to set this. Same pattern utils/encryption.py already used correctly for
# ENCRYPTION_KEY: fail loudly at import time instead of silently running
# insecure. Run `python utils/generate_keys.py` to generate a real one.
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "")
if not JWT_SECRET_KEY or JWT_SECRET_KEY == "change_this_in_production":
    raise RuntimeError(
        "JWT_SECRET_KEY not set (or still the placeholder). "
        "Run python utils/generate_keys.py and paste JWT_SECRET_KEY into your .env file."
    )
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
JWT_EXPIRE_MINUTES = int(os.getenv("JWT_ACCESS_TOKEN_EXPIRE_MINUTES", "60"))

pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")
bearer_scheme = HTTPBearer()


def normalize_password(password: str) -> bytes:
    return hashlib.sha256(password.encode("utf-8")).digest()

def hash_password(password: str) -> str:
    return pwd_context.hash(normalize_password(password))

def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(normalize_password(plain), hashed)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> tuple:
    """Returns (token, jti, expires_at). jti is a unique ID embedded in the token
    AND recorded in UserSession -- this is what makes revocation possible at
    all (loophole fix #2). A bare JWT has no server-side record to revoke;
    checking exp alone can prove a token has expired, never that it's been
    killed early."""
    payload = data.copy()
    jti = str(uuid.uuid4())
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=JWT_EXPIRE_MINUTES))
    payload.update({"exp": expire, "jti": jti})
    token = jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)
    return token, jti, expire


def record_session(db: Session, user_id: str, jti: str, expires_at: datetime, user_agent: str = None, ip_address: str = None) -> None:
    db.add(UserSession(id=jti, user_id=user_id, expires_at=expires_at, user_agent=user_agent, ip_address=ip_address))
    db.commit()


def revoke_session(db: Session, jti: str) -> bool:
    """Used by /logout. Returns False if the session was already gone/revoked
    (still a safe, idempotent no-op -- not an error)."""
    session = db.query(UserSession).filter(UserSession.id == jti, UserSession.revoked_at.is_(None)).first()
    if not session:
        return False
    session.revoked_at = datetime.utcnow()
    db.commit()
    return True


def revoke_all_sessions(db: Session, user_id: str) -> int:
    """'Log out of all devices' -- one UPDATE, now that sessions are real rows
    instead of ungoverned stateless tokens."""
    now = datetime.utcnow()
    count = (
        db.query(UserSession)
        .filter(UserSession.user_id == user_id, UserSession.revoked_at.is_(None))
        .update({"revoked_at": now}, synchronize_session=False)
    )
    db.commit()
    return count


def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: Session = Depends(get_db)
) -> User:
    payload = decode_token(credentials.credentials)
    user_id = payload.get("sub")
    jti = payload.get("jti")

    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token payload")

    # Loophole fix #2: a token that decodes fine (valid signature, not yet
    # expired) can still have been explicitly revoked -- logout, or an admin
    # force-logging-out a compromised account. Older tokens issued before this
    # fix have no jti and no matching session row; they're rejected too,
    # rather than silently trusting them as an exception.
    if not jti:
        raise HTTPException(status_code=401, detail="Session not found. Please log in again.")
    session = db.query(UserSession).filter(UserSession.id == jti).first()
    if not session or session.revoked_at is not None:
        raise HTTPException(status_code=401, detail="Session has been revoked. Please log in again.")

    user = db.query(User).filter(
        User.id == user_id,
        User.is_active == True
    ).first()

    if not user:
        raise HTTPException(status_code=401, detail="User not found or deactivated")

    return user


optional_bearer_scheme = HTTPBearer(auto_error=False)


def get_optional_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(optional_bearer_scheme),
    db: Session = Depends(get_db)
) -> Optional[User]:
    """Retrieves authenticated user if valid token is provided, or returns None without failing."""
    if not credentials or not credentials.credentials:
        return None
    token = str(credentials.credentials).strip()
    if not token or token in ("null", "undefined", "None", ""):
        return None
    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
        user_id = payload.get("sub")
        if not user_id:
            return None
        return db.query(User).filter(User.id == user_id, User.is_active == True).first()
    except Exception:
        return None


# Loophole fix #5: a precomputed dummy hash means the login route can always
# call verify_password with a real hash argument -- never None, which would
# raise inside passlib rather than failing gracefully -- so a nonexistent
# email still pays the same argon2 cost as a real one. Without this, "no such
# user" returns near-instantly while "wrong password" takes as long as a real
# hash verification, and that gap alone lets an attacker enumerate which
# emails are registered without ever seeing an error message that says so.
_DUMMY_HASH = pwd_context.hash(normalize_password("this-is-not-a-real-password"))


def verify_password_safe(plain: str, user: Optional[User]) -> bool:
    """Always does real hash-verification work, whether or not `user` exists."""
    return verify_password(plain, user.hashed_password if user else _DUMMY_HASH)


_MAX_FAILED_ATTEMPTS = 5
_LOCKOUT_WINDOW_MINUTES = 15


def check_login_rate_limit(db: Session, email: str) -> None:
    """Call BEFORE checking the password. Raises 429 if this email has had too
    many failed attempts recently -- regardless of whether the CURRENT attempt
    would have succeeded, so a correct password can't be used to probe past
    the lockout."""
    window_start = datetime.utcnow() - timedelta(minutes=_LOCKOUT_WINDOW_MINUTES)
    recent_failures = (
        db.query(LoginAttempt)
        .filter(
            LoginAttempt.email == email,
            LoginAttempt.success.is_(False),
            LoginAttempt.attempted_at >= window_start,
        )
        .count()
    )
    if recent_failures >= _MAX_FAILED_ATTEMPTS:
        raise HTTPException(
            status_code=429,
            detail=f"Too many failed login attempts. Please try again in {_LOCKOUT_WINDOW_MINUTES} minutes.",
        )


def record_login_attempt(db: Session, email: str, success: bool, ip_address: str = None) -> None:
    db.add(LoginAttempt(email=email, success=success, ip_address=ip_address))
    db.commit()



def get_current_admin_user(current_user: User = Depends(get_current_user)) -> User:
    if current_user.role not in ("admin", "advocate"):
        raise HTTPException(status_code=403, detail="Admin access required")
    return current_user

