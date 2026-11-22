"""Player-facing API: challenge list (scoped to the one RUNNING game),
instance start/renew/stop (talks to the real orchestrator via
orchestrator_client.py, through services/instances.py), and flag
submission (pure local DB -- see services/submissions.py)."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import boxes_catalog, models, schemas, security
from ..services import games as games_service
from ..services import instances as instances_service
from ..services import submissions as submissions_service

router = APIRouter(prefix="/api/player", tags=["player"])


@router.get("/challenges", response_model=list[schemas.ChallengeWithSolveResponse])
def list_challenges(team: models.Team = Depends(security.current_team), db: Session = Depends(security.get_db)):
    game = games_service.get_running_game(db)
    if game is None:
        return []
    challenges = list(
        db.execute(select(models.Challenge).where(models.Challenge.game_id == game.id)).scalars()
    )
    solved_ids = {
        s.challenge_id
        for s in db.execute(select(models.Solve).where(models.Solve.team_id == team.id)).scalars()
    }
    return [
        schemas.ChallengeWithSolveResponse(
            id=c.id,
            game_id=c.game_id,
            box_id=c.box_id,
            flag_number=c.flag_number,
            title=c.title,
            points=c.points,
            description=c.description,
            solved=c.id in solved_ids,
        )
        for c in challenges
    ]


@router.get("/instances", response_model=list[schemas.TeamInstanceResponse])
def list_instances(team: models.Team = Depends(security.current_team), db: Session = Depends(security.get_db)):
    return instances_service.list_team_instances(db, team.id)


@router.post("/instances", response_model=schemas.TeamInstanceResponse)
def start_instance(
    req: schemas.StartInstanceRequest,
    team: models.Team = Depends(security.current_team),
    db: Session = Depends(security.get_db),
):
    if not boxes_catalog.is_known_box_id(req.box_id):
        raise HTTPException(status_code=404, detail="unknown box_id")
    try:
        return instances_service.start_instance(db, team, req.box_id)
    except instances_service.InstanceServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail) from e


@router.post("/instances/{box_id}/renew", response_model=schemas.TeamInstanceResponse)
def renew_instance(
    box_id: str,
    req: schemas.RenewInstanceRequest,
    team: models.Team = Depends(security.current_team),
    db: Session = Depends(security.get_db),
):
    try:
        return instances_service.renew_instance(db, team, box_id, req.extra_minutes)
    except instances_service.InstanceServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail) from e


@router.delete("/instances/{box_id}", status_code=204)
def stop_instance(
    box_id: str, team: models.Team = Depends(security.current_team), db: Session = Depends(security.get_db)
):
    instances_service.stop_instance(db, team, box_id)


@router.post("/submissions", response_model=schemas.SubmissionResult)
def submit(
    req: schemas.SubmissionRequest,
    team: models.Team = Depends(security.current_team),
    db: Session = Depends(security.get_db),
):
    challenge = db.get(models.Challenge, req.challenge_id)
    if challenge is None:
        raise HTTPException(status_code=404, detail="challenge not found")
    game = db.get(models.Game, challenge.game_id)
    if game is None or game.status != models.GameStatus.RUNNING:
        raise HTTPException(status_code=403, detail="game is not running")
    try:
        correct = submissions_service.submit_flag(db, team, challenge, req.value)
    except submissions_service.SubmissionServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail) from e
    return schemas.SubmissionResult(correct=correct)
