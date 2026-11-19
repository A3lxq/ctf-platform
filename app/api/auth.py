"""Team self-registration (open to anyone -- this is a public event, not
invite-only, per explicit decision) + team/admin login. Anti-abuse on
registration is deliberately zero-cost: no paid CAPTCHA/reCAPTCHA
service, no budget for one. Three independent, free checks instead:
a honeypot field, a signed minimum-fill-time token, and an in-memory
per-IP sliding-window rate limit."""
import secrets
import time

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import config, models, schemas, security

router = APIRouter(prefix="/api/auth", tags=["auth"])

# In-memory sliding window, keyed by source IP. Fine for a single
# process with no --workers (same constraint the orchestrator's own
# reaper imposes on itself) -- no new infra needed at this scale.
_register_attempts: dict[str, list[float]] = {}


def _check_register_rate_limit(client_ip: str) -> None:
    now = time.monotonic()
    window_start = now - config.REGISTER_RATE_LIMIT_WINDOW_SECONDS
    attempts = [t for t in _register_attempts.get(client_ip, []) if t >= window_start]
    if len(attempts) >= config.REGISTER_RATE_LIMIT_MAX_ATTEMPTS:
        raise HTTPException(status_code=429, detail="too many registration attempts, try again later")
    attempts.append(now)
    _register_attempts[client_ip] = attempts


@router.get("/register/form-token")
def get_register_form_token() -> dict:
    """The register page (web/routes.py) calls this -- or embeds the
    token server-side directly when rendering the template -- to get a
    signed, timestamped token for the minimum-fill-time check below."""
    return {"form_token": security.make_form_token()}


@router.post("/register", response_model=schemas.TeamResponse)
def register_team(req: schemas.TeamRegisterRequest, request: Request, db: Session = Depends(security.get_db)):
    if req.password != req.confirm_password:
        raise HTTPException(status_code=400, detail="passwords do not match")

    # Honeypot: real users never see or fill this field (hidden via
    # CSS in the template). Any value present means a generic bot
    # form-filler touched it.
    if req.website.strip():
        raise HTTPException(status_code=400, detail="registration rejected")

    # Minimum-fill-time: reject a submission that arrives faster than a
    # human plausibly could have read the form and typed a password.
    try:
        age = security.form_token_age_seconds(req.form_token)
    except ValueError:
        raise HTTPException(status_code=400, detail="registration form expired, please reload and try again")
    if age < config.REGISTER_MIN_FILL_SECONDS:
        raise HTTPException(status_code=400, detail="registration rejected")

    client_ip = request.client.host if request.client else "unknown"
    _check_register_rate_limit(client_ip)

    existing = db.execute(select(models.Team).where(models.Team.name == req.name)).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(status_code=409, detail="team name already taken")

    password_hash, password_salt = security.hash_password(req.password)
    team = models.Team(
        name=req.name,
        password_hash=password_hash,
        password_salt=password_salt,
        team_secret=secrets.token_hex(32),
    )
    db.add(team)
    db.commit()
    db.refresh(team)

    request.session["team_id"] = team.id
    return team


@router.post("/team/login", response_model=schemas.TeamResponse)
def login_team(req: schemas.TeamLoginRequest, request: Request, db: Session = Depends(security.get_db)):
    team = db.execute(select(models.Team).where(models.Team.name == req.name)).scalar_one_or_none()
    if team is None or not security.verify_password(req.password, team.password_hash, team.password_salt):
        raise HTTPException(status_code=401, detail="invalid name or password")
    if team.disabled:
        raise HTTPException(status_code=403, detail="this team has been disabled")
    request.session["team_id"] = team.id
    return team


@router.post("/admin/login")
def login_admin(req: schemas.AdminLoginRequest, request: Request, db: Session = Depends(security.get_db)):
    admin = db.execute(select(models.Admin).where(models.Admin.username == req.username)).scalar_one_or_none()
    if admin is None or not security.verify_password(req.password, admin.password_hash, admin.password_salt):
        raise HTTPException(status_code=401, detail="invalid username or password")
    request.session["admin_id"] = admin.id
    return {"username": admin.username}


@router.post("/logout")
def logout(request: Request) -> dict:
    request.session.clear()
    return {"ok": True}


@router.get("/me")
def me(request: Request, db: Session = Depends(security.get_db)) -> dict:
    team_id = request.session.get("team_id")
    admin_id = request.session.get("admin_id")
    if team_id is not None:
        team = db.get(models.Team, team_id)
        if team is not None:
            return {"role": "team", "id": team.id, "name": team.name}
    if admin_id is not None:
        admin = db.get(models.Admin, admin_id)
        if admin is not None:
            return {"role": "admin", "id": admin.id, "username": admin.username}
    raise HTTPException(status_code=401, detail="not logged in")
