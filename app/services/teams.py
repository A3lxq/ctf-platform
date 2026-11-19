from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models, security


class TeamServiceError(Exception):
    pass


def list_teams(db: Session) -> list[models.Team]:
    return list(db.execute(select(models.Team)).scalars())


def set_disabled(db: Session, team: models.Team, disabled: bool) -> models.Team:
    team.disabled = disabled
    db.commit()
    db.refresh(team)
    return team


def reset_password(db: Session, team: models.Team, new_password: str) -> models.Team:
    """Admin-initiated reset for a locked-out team -- never touches
    team_secret, only the login password."""
    password_hash, password_salt = security.hash_password(new_password)
    team.password_hash = password_hash
    team.password_salt = password_salt
    db.commit()
    db.refresh(team)
    return team
