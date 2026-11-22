"""Periodic sweep that re-syncs every non-DESTROYED TeamInstance's local
cache (status, entry_host/port, ports, expires_at) against the
orchestrator's own authoritative state. Catches an instance the
orchestrator's own reaper destroyed for expiring independently of this
platform's API ever being told -- same defense-in-depth role as the
orchestrator's own reaper.py relative to GZCTF's TTL handling."""
import asyncio
import logging
from datetime import datetime

from sqlalchemy import select

from . import config, orchestrator_client
from .models import TeamInstance, TeamInstanceStatus, get_session, utcnow

logger = logging.getLogger("ctf_platform.reconciliation")


def sweep_once() -> int:
    db = get_session()
    synced = 0
    try:
        rows = list(
            db.execute(select(TeamInstance).where(TeamInstance.status != TeamInstanceStatus.DESTROYED)).scalars()
        )
        for row in rows:
            try:
                remote = orchestrator_client.get_instance(row.id)
            except orchestrator_client.OrchestratorError:
                logger.exception("reconciliation: failed to fetch instance %s from orchestrator", row.id)
                continue
            if remote is None:
                row.status = TeamInstanceStatus.DESTROYED
            else:
                row.status = TeamInstanceStatus(remote["status"])
                row.entry_host = remote["entry_host"]
                row.entry_port = remote["entry_port"]
                row.ports = remote["ports"]
                row.expires_at = datetime.fromisoformat(remote["expires_at"])
            row.last_synced_at = utcnow()
            synced += 1
        db.commit()
    finally:
        db.close()
    return synced


async def run_forever() -> None:
    while True:
        try:
            count = await asyncio.to_thread(sweep_once)
            if count:
                logger.info("reconciled %d instance(s) against the orchestrator", count)
        except Exception:
            logger.exception("reconciliation sweep failed")
        await asyncio.sleep(config.RECONCILIATION_INTERVAL_SECONDS)
