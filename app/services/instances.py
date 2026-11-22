"""Business logic for starting/renewing/stopping a team's orchestrator
instances, called by api/player.py and api/admin.py. The only place
this platform talks to orchestrator_client.py for instance lifecycle --
no handler makes that HTTP call directly."""
import logging
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models, orchestrator_client

logger = logging.getLogger("ctf_platform.services.instances")


class InstanceServiceError(Exception):
    def __init__(self, status_code: int, detail: str):
        self.status_code = status_code
        self.detail = detail
        super().__init__(detail)


def apply_remote(row: models.TeamInstance, remote: dict) -> None:
    row.status = models.TeamInstanceStatus(remote["status"])
    row.entry_host = remote["entry_host"]
    row.entry_port = remote["entry_port"]
    row.ports = remote["ports"]
    row.expires_at = datetime.fromisoformat(remote["expires_at"])
    row.last_synced_at = models.utcnow()


def get_team_instance(db: Session, team_id: int, box_id: str) -> models.TeamInstance | None:
    return db.execute(
        select(models.TeamInstance).where(
            models.TeamInstance.team_id == team_id,
            models.TeamInstance.box_id == box_id,
            models.TeamInstance.status != models.TeamInstanceStatus.DESTROYED,
        )
    ).scalar_one_or_none()


def list_team_instances(db: Session, team_id: int) -> list[models.TeamInstance]:
    return list(db.execute(select(models.TeamInstance).where(models.TeamInstance.team_id == team_id)).scalars())


def start_instance(db: Session, team: models.Team, box_id: str) -> models.TeamInstance:
    existing = get_team_instance(db, team.id, box_id)
    if existing is not None:
        # Re-sync against the orchestrator rather than trusting the
        # local cache -- the background reconciliation sweep (see
        # reconciliation.py) only runs periodically, so the cache could
        # be stale by up to its interval.
        try:
            remote = orchestrator_client.get_instance(existing.id)
        except orchestrator_client.OrchestratorError as e:
            raise InstanceServiceError(502, f"orchestrator error: {e.detail}") from e
        if remote is not None:
            apply_remote(existing, remote)
            db.commit()
            db.refresh(existing)
            return existing
        # The orchestrator has no record of it anymore (its own reaper
        # already destroyed it) -- mark it locally and fall through to
        # provision a fresh one instead of returning a stale row.
        existing.status = models.TeamInstanceStatus.DESTROYED
        db.commit()

    try:
        remote = orchestrator_client.create_instance(team.id, box_id, team.team_secret)
    except orchestrator_client.OrchestratorError as e:
        if e.status_code == 429:
            raise InstanceServiceError(429, e.detail) from e
        raise InstanceServiceError(502, f"orchestrator error: {e.detail}") from e

    row = models.TeamInstance(id=remote["instance_id"], team_id=team.id, box_id=box_id, expires_at=models.utcnow())
    apply_remote(row, remote)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def renew_instance(db: Session, team: models.Team, box_id: str, extra_minutes: int) -> models.TeamInstance:
    row = get_team_instance(db, team.id, box_id)
    if row is None:
        raise InstanceServiceError(404, "no active instance for this box")
    try:
        remote = orchestrator_client.renew_instance(row.id, extra_minutes)
    except orchestrator_client.OrchestratorError as e:
        raise InstanceServiceError(502, f"orchestrator error: {e.detail}") from e
    apply_remote(row, remote)
    db.commit()
    db.refresh(row)
    return row


def stop_instance(db: Session, team: models.Team, box_id: str) -> None:
    row = get_team_instance(db, team.id, box_id)
    if row is None:
        return  # idempotent, matches the orchestrator's own DELETE semantics
    orchestrator_client.destroy_instance(row.id)
    row.status = models.TeamInstanceStatus.DESTROYED
    db.commit()


def list_all_instances(db: Session, staleness_seconds: int) -> list[models.TeamInstance]:
    """Admin monitoring view across every team. Serves the local cache,
    refreshing only rows whose last_synced_at is older than
    staleness_seconds -- same "don't hit the orchestrator on every page
    load" reasoning as the plan's own admin-dashboard design, mirrored
    from reconciliation.py's periodic sweep but synchronous and
    on-demand here since an admin page load is already a request."""
    rows = list(db.execute(select(models.TeamInstance)).scalars())
    # Despite DateTime(timezone=True), SQLite round-trips naive
    # datetimes (confirmed empirically, see services/scoreboard.py's
    # own note) -- the threshold compared against a DB-loaded
    # last_synced_at must be naive too, or this raises TypeError.
    threshold = models.utcnow().replace(tzinfo=None) - timedelta(seconds=staleness_seconds)
    for row in rows:
        if row.status == models.TeamInstanceStatus.DESTROYED or row.last_synced_at >= threshold:
            continue
        try:
            remote = orchestrator_client.get_instance(row.id)
        except orchestrator_client.OrchestratorError:
            logger.exception("admin instance list: failed to refresh instance %s", row.id)
            continue
        if remote is None:
            row.status = models.TeamInstanceStatus.DESTROYED
            row.last_synced_at = models.utcnow()
        else:
            apply_remote(row, remote)
    db.commit()
    return rows


def force_stop_instance(db: Session, instance_id: str) -> models.TeamInstance:
    row = db.get(models.TeamInstance, instance_id)
    if row is None:
        raise InstanceServiceError(404, "instance not found")
    orchestrator_client.destroy_instance(row.id)
    row.status = models.TeamInstanceStatus.DESTROYED
    db.commit()
    db.refresh(row)
    return row


def mass_teardown_for_game(db: Session, game: models.Game) -> int:
    """Tears down every still-non-DESTROYED TeamInstance, across every
    team, for a box_id this game actually used -- called when a game
    ends (services/games.py's end_game), so nothing accumulates
    unbounded in the orchestrator after the event. Best-effort: a
    destroy failure for one instance is logged and skipped rather than
    aborting the whole sweep."""
    box_ids = {
        row[0] for row in db.execute(select(models.Challenge.box_id).where(models.Challenge.game_id == game.id)).all()
    }
    if not box_ids:
        return 0
    rows = list(
        db.execute(
            select(models.TeamInstance).where(
                models.TeamInstance.box_id.in_(box_ids),
                models.TeamInstance.status != models.TeamInstanceStatus.DESTROYED,
            )
        ).scalars()
    )
    torn_down = 0
    for row in rows:
        try:
            orchestrator_client.destroy_instance(row.id)
            row.status = models.TeamInstanceStatus.DESTROYED
            torn_down += 1
        except orchestrator_client.OrchestratorError:
            logger.exception("mass teardown: failed to destroy instance %s", row.id)
    db.commit()
    return torn_down
