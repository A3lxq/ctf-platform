from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import boxes_catalog, models


class ChallengeServiceError(Exception):
    pass


def create_challenge(
    db: Session, game: models.Game, box_id: str, flag_number: int, title: str, points: int, description: str | None
) -> models.Challenge:
    if not boxes_catalog.is_known_box_id(box_id):
        raise ChallengeServiceError(f"unknown box_id {box_id!r} -- not in the orchestrator's box catalog")

    existing = db.execute(
        select(models.Challenge).where(
            models.Challenge.game_id == game.id,
            models.Challenge.box_id == box_id,
            models.Challenge.flag_number == flag_number,
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise ChallengeServiceError(f"a challenge for {box_id} flag {flag_number} already exists in this game")

    challenge = models.Challenge(
        game_id=game.id, box_id=box_id, flag_number=flag_number, title=title, points=points, description=description
    )
    db.add(challenge)
    db.commit()
    db.refresh(challenge)
    return challenge


def list_challenges(db: Session, game_id: int) -> list[models.Challenge]:
    return list(db.execute(select(models.Challenge).where(models.Challenge.game_id == game_id)).scalars())
