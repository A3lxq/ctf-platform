from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models


class GameServiceError(Exception):
    pass


def get_running_game(db: Session) -> models.Game | None:
    return db.execute(select(models.Game).where(models.Game.status == models.GameStatus.RUNNING)).scalar_one_or_none()


def create_game(db: Session, name: str, start_at=None, end_at=None) -> models.Game:
    game = models.Game(name=name, start_at=start_at, end_at=end_at)
    db.add(game)
    db.commit()
    db.refresh(game)
    return game


def start_game(db: Session, game: models.Game) -> models.Game:
    """App-level invariant: at most one RUNNING game at a time."""
    if get_running_game(db) is not None:
        raise GameServiceError("another game is already running -- end it first")
    game.status = models.GameStatus.RUNNING
    db.commit()
    db.refresh(game)
    return game


def end_game(db: Session, game: models.Game) -> models.Game:
    """Flips status to ENDED -- the complement start_game needs to exist
    at all, since "at most one RUNNING game" is unusable without a way
    to release it. The mass-teardown sweep (DELETE every still-running
    TeamInstance tied to this game's challenges) is added in Phase C
    once the orchestrator integration exists; this is deliberately just
    the local status flip for now."""
    game.status = models.GameStatus.ENDED
    if game.end_at is None:
        game.end_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(game)
    return game
