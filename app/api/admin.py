from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models, schemas, security
from ..services import challenges as challenges_service
from ..services import games as games_service
from ..services import teams as teams_service

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.post("/games", response_model=schemas.GameResponse)
def create_game(
    req: schemas.GameCreateRequest,
    admin: models.Admin = Depends(security.current_admin),
    db: Session = Depends(security.get_db),
):
    return games_service.create_game(db, req.name, req.start_at, req.end_at)


@router.get("/games", response_model=list[schemas.GameResponse])
def list_games(admin: models.Admin = Depends(security.current_admin), db: Session = Depends(security.get_db)):
    return list(db.execute(select(models.Game)).scalars())


@router.post("/games/{game_id}/start", response_model=schemas.GameResponse)
def start_game(
    game_id: int, admin: models.Admin = Depends(security.current_admin), db: Session = Depends(security.get_db)
):
    game = db.get(models.Game, game_id)
    if game is None:
        raise HTTPException(status_code=404, detail="game not found")
    try:
        return games_service.start_game(db, game)
    except games_service.GameServiceError as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.post("/games/{game_id}/end", response_model=schemas.GameResponse)
def end_game(
    game_id: int, admin: models.Admin = Depends(security.current_admin), db: Session = Depends(security.get_db)
):
    game = db.get(models.Game, game_id)
    if game is None:
        raise HTTPException(status_code=404, detail="game not found")
    return games_service.end_game(db, game)


@router.post("/games/{game_id}/challenges", response_model=schemas.ChallengeResponse)
def create_challenge(
    game_id: int,
    req: schemas.ChallengeCreateRequest,
    admin: models.Admin = Depends(security.current_admin),
    db: Session = Depends(security.get_db),
):
    game = db.get(models.Game, game_id)
    if game is None:
        raise HTTPException(status_code=404, detail="game not found")
    try:
        return challenges_service.create_challenge(
            db, game, req.box_id, req.flag_number, req.title, req.points, req.description
        )
    except challenges_service.ChallengeServiceError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/games/{game_id}/challenges", response_model=list[schemas.ChallengeResponse])
def list_challenges(
    game_id: int, admin: models.Admin = Depends(security.current_admin), db: Session = Depends(security.get_db)
):
    return challenges_service.list_challenges(db, game_id)


@router.get("/teams", response_model=list[schemas.TeamResponse])
def list_teams(admin: models.Admin = Depends(security.current_admin), db: Session = Depends(security.get_db)):
    return teams_service.list_teams(db)


class _DisabledBody(BaseModel):
    disabled: bool


@router.patch("/teams/{team_id}/disabled", response_model=schemas.TeamResponse)
def set_team_disabled(
    team_id: int,
    body: _DisabledBody,
    admin: models.Admin = Depends(security.current_admin),
    db: Session = Depends(security.get_db),
):
    team = db.get(models.Team, team_id)
    if team is None:
        raise HTTPException(status_code=404, detail="team not found")
    return teams_service.set_disabled(db, team, body.disabled)


class _ResetPasswordBody(BaseModel):
    new_password: str


@router.post("/teams/{team_id}/reset-password", response_model=schemas.TeamResponse)
def reset_team_password(
    team_id: int,
    body: _ResetPasswordBody,
    admin: models.Admin = Depends(security.current_admin),
    db: Session = Depends(security.get_db),
):
    team = db.get(models.Team, team_id)
    if team is None:
        raise HTTPException(status_code=404, detail="team not found")
    if len(body.new_password) < 8:
        raise HTTPException(status_code=400, detail="password must be at least 8 characters")
    return teams_service.reset_password(db, team, body.new_password)
