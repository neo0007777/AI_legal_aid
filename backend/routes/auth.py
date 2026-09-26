from fastapi import APIRouter, HTTPException, Depends, status, Request
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from models.database import get_db, User
from models.schemas import UserRegister, UserLogin, TokenResponse, UserResponse, LanguagePreferenceRequest
from utils.auth import (
    hash_password, verify_password_safe, create_access_token, get_current_user,
    record_session, revoke_session, revoke_all_sessions,
    check_login_rate_limit, record_login_attempt, decode_token, bearer_scheme,
)

router = APIRouter()

VALID_ROLES = {"user", "advocate", "intern"}


def _issue_token(db: Session, user: User, request: Request) -> str:
    token, jti, expires_at = create_access_token({"sub": user.id, "role": user.role})
    record_session(
        db, user_id=user.id, jti=jti, expires_at=expires_at,
        user_agent=request.headers.get("user-agent"),
        ip_address=request.client.host if request.client else None,
    )
    return token


@router.post("/register", response_model=TokenResponse, status_code=201)
def register(payload: UserRegister, request: Request, db: Session = Depends(get_db)):
    if db.query(User).filter(User.email == payload.email).first():
        raise HTTPException(status_code=400, detail="Email already registered")

    user = User(
        email=payload.email,
        full_name=payload.full_name,
        hashed_password=hash_password(payload.password),
        role=payload.role if payload.role in VALID_ROLES else "user",
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    token = _issue_token(db, user, request)
    return TokenResponse(
        access_token=token,
        user_id=user.id,
        full_name=user.full_name,
        email=user.email,
        role=user.role,
    )


@router.post("/login", response_model=TokenResponse)
def login(payload: UserLogin, request: Request, db: Session = Depends(get_db)):
    ip = request.client.host if request.client else None

    # Loophole fix #3: checked BEFORE touching the password at all, so a
    # correct password on attempt #6 still doesn't bypass the lockout.
    check_login_rate_limit(db, payload.email)

    user = db.query(User).filter(User.email == payload.email).first()

    # Loophole fix #5: verify_password_safe always does real hash-verification
    # work, even when no such user exists -- see utils/auth.py for why.
    if not user or not verify_password_safe(payload.password, user):
        record_login_attempt(db, payload.email, success=False, ip_address=ip)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password"
        )

    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account is deactivated")

    record_login_attempt(db, payload.email, success=True, ip_address=ip)
    token = _issue_token(db, user, request)
    return TokenResponse(
        access_token=token,
        user_id=user.id,
        full_name=user.full_name,
        email=user.email,
        role=user.role,
    )


@router.get("/me", response_model=UserResponse)
def get_me(current_user: User = Depends(get_current_user)):
    return current_user


@router.patch("/me/language", response_model=UserResponse)
def set_preferred_language(
    payload: LanguagePreferenceRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Persists the app-wide language switcher choice (LanguageContext.jsx) to
    the user's profile so it follows them across devices/sessions, in
    addition to the localStorage copy that survives a plain refresh."""
    from services.translate_output import SUPPORTED_LANGUAGES
    valid_codes = {"en", *SUPPORTED_LANGUAGES.keys()}
    if payload.preferred_language not in valid_codes:
        raise HTTPException(status_code=400, detail=f"preferred_language must be one of {sorted(valid_codes)}.")

    current_user.preferred_language = payload.preferred_language
    db.commit()
    db.refresh(current_user)
    return current_user


@router.post("/logout")
def logout(db: Session = Depends(get_db), credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme)):
    # Loophole fix #2: this used to do nothing. Now it actually revokes the
    # session backing this specific token, so the token stops working
    # immediately instead of remaining valid until natural expiry.
    payload = decode_token(credentials.credentials)
    jti = payload.get("jti")
    if jti:
        revoke_session(db, jti)
    return {"message": "Logged out successfully"}


@router.post("/logout-all")
def logout_all(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Log out of every device/session at once -- e.g. after a suspected
    compromise. Only possible now that sessions are real rows, not bare tokens."""
    count = revoke_all_sessions(db, current_user.id)
    return {"message": f"Revoked {count} active session(s)."}
