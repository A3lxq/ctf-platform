"""Scoreboard computation -- SUM(Challenge.points) JOIN Solve, O(1)
regardless of how large the Submission audit log grows (see models.py's
own docstrings on why Submission/Solve are separate tables). Scoped to
one game's own challenges, since a team's score only ever means
something relative to a specific game. Ties broken by last_solve_at
ascending -- the standard CTF convention: whoever's last solve first
put them at their current score ranks above a later arrival at the
same score."""
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import models


def compute_scoreboard(db: Session, game_id: int) -> list[dict]:
    game_challenge_ids = select(models.Challenge.id).where(models.Challenge.game_id == game_id)
    rows = db.execute(
        select(
            models.Team.id,
            models.Team.name,
            func.coalesce(func.sum(models.Challenge.points), 0).label("score"),
            func.max(models.Solve.solved_at).label("last_solve_at"),
        )
        .select_from(models.Team)
        .outerjoin(
            models.Solve,
            (models.Solve.team_id == models.Team.id) & (models.Solve.challenge_id.in_(game_challenge_ids)),
        )
        .outerjoin(models.Challenge, models.Challenge.id == models.Solve.challenge_id)
        .where(models.Team.disabled.is_(False))
        .group_by(models.Team.id, models.Team.name)
    ).all()

    entries = [
        {"team_id": r.id, "team_name": r.name, "score": r.score, "last_solve_at": r.last_solve_at} for r in rows
    ]
    # Despite DateTime(timezone=True), SQLite round-trips naive
    # datetimes (confirmed empirically) -- the "no solves yet"
    # placeholder must be naive too, or comparing it against a real
    # timestamp raises TypeError.
    entries.sort(key=lambda e: (-e["score"], e["last_solve_at"] or datetime.max))
    for i, entry in enumerate(entries, start=1):
        entry["rank"] = i
    return entries
