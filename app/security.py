"""Password hashing (stdlib PBKDF2, no bcrypt/passlib dependency -- see
the plan's Decisions section for why that's the right call at this
scale) and session-cookie auth dependencies for FastAPI routes."""
import hashlib
import hmac
import secrets
from datetime import datetime, timezone

from fastapi import Depends, HTTPException, Request
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from sqlalchemy.orm import Session

from . import config, models

_form_token_serializer = URLSafeTimedSerializer(config.SESSION_SECRET, salt="register-form-token")


def make_form_token() -> str:
    """Signed, timestamped token embedded as a hidden field when the
    registration page is served. Verified on submit to enforce the
    minimum-fill-time anti-bot check (api/auth.py) -- the timestamp is
    server-issued and cryptographically signed, so it can't be forged
    or backdated by the client."""
    return _form_token_serializer.dumps("register")


def form_token_age_seconds(token: str, max_age_seconds: int = 3600) -> float:
    """Returns how many seconds old the token is. Raises ValueError if
    the signature is invalid or the token is older than max_age_seconds
    (a stale/replayed token shouldn't be usable indefinitely)."""
    try:
        _, issued_at = _form_token_serializer.loads(token, max_age=max_age_seconds, return_timestamp=True)
    except SignatureExpired as e:
        raise ValueError("form token expired") from e
    except BadSignature as e:
        raise ValueError("invalid form token") from e
    return (datetime.now(timezone.utc) - issued_at.replace(tzinfo=timezone.utc)).total_seconds()


def hash_password(password: str, salt: str | None = None) -> tuple[str, str]:
    """Returns (hash_hex, salt_hex). Pass salt=None to generate a fresh
    one (registration / password reset); pass the stored salt to verify
    an existing password."""
    if salt is None:
        salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode(), bytes.fromhex(salt), config.PBKDF2_ITERATIONS
    )
    return digest.hex(), salt


def verify_password(password: str, stored_hash: str, stored_salt: str) -> bool:
    computed_hash, _ = hash_password(password, stored_salt)
    return hmac.compare_digest(computed_hash, stored_hash)


def get_db(request: Request):
    """Generator dependency so the session is always closed and its
    connection returned to the pool after the request, even on an
    exception. A plain callable returning get_session() (no close)
    leaked one pooled connection per request -- harmless for a single
    request, but exhausted the pool (5 + 10 overflow) after enough
    requests in one run and turned every subsequent request into a
    500 (QueuePool timeout)."""
    db = models.get_session()
    try:
        yield db
    finally:
        db.close()


def current_team(request: Request, db: Session = Depends(get_db)) -> models.Team:
    team_id = request.session.get("team_id")
    if team_id is None:
        raise HTTPException(status_code=401, detail="not logged in")
    team = db.get(models.Team, team_id)
    if team is None or team.disabled:
        raise HTTPException(status_code=401, detail="team not found or disabled")
    return team


def current_admin(request: Request, db: Session = Depends(get_db)) -> models.Admin:
    admin_id = request.session.get("admin_id")
    if admin_id is None:
        raise HTTPException(status_code=401, detail="admin login required")
    admin = db.get(models.Admin, admin_id)
    if admin is None:
        raise HTTPException(status_code=401, detail="admin not found")
    return admin
