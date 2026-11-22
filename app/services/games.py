from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models
from . import instances as instances_service


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
    """Flips status to ENDED, then sweeps up: DELETEs every
    still-non-DESTROYED TeamInstance (any team) for a box_id this game
    actually used, so nothing accumulates unbounded in the orchestrator
    after the event -- see services/instances.py's mass_teardown_for_game."""
    game.status = models.GameStatus.ENDED
    if game.end_at is None:
        game.end_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(game)
    instances_service.mass_teardown_for_game(db, game)
    db.refresh(game)
    return game
