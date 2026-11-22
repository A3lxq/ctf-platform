from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from .. import boxes_catalog, security
from ..services import games as games_service
from ..services import scoreboard as scoreboard_service

router = APIRouter(tags=["web"])
templates = Jinja2Templates(directory="app/templates")


@router.get("/", response_class=HTMLResponse)
def index(request: Request):
    return templates.TemplateResponse(request, "index.html", {})


@router.get("/register", response_class=HTMLResponse)
def register_page(request: Request):
    return templates.TemplateResponse(request, "register.html", {"form_token": security.make_form_token()})


@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    return templates.TemplateResponse(request, "login.html", {})


@router.get("/admin/login", response_class=HTMLResponse)
def admin_login_page(request: Request):
    return templates.TemplateResponse(request, "admin/login.html", {})


@router.get("/challenges", response_class=HTMLResponse)
def challenges_page(request: Request):
    return templates.TemplateResponse(request, "challenges.html", {})


@router.get("/scoreboard", response_class=HTMLResponse)
def scoreboard_page(request: Request):
    return templates.TemplateResponse(request, "scoreboard.html", {})


@router.get("/scoreboard/fragment", response_class=HTMLResponse)
def scoreboard_fragment(request: Request, db: Session = Depends(security.get_db)):
    """Polled by scoreboard.html via htmx every 10s -- server-rendered,
    not a JSON API call, per this project's own stack decision (htmx
    polling for the scoreboard, no websockets)."""
    if request.session.get("team_id") is None:
        return templates.TemplateResponse(
            request, "_scoreboard_fragment.html", {"logged_in": False, "no_game": False, "entries": None}
        )
    game = games_service.get_running_game(db)
    if game is None:
        return templates.TemplateResponse(
            request, "_scoreboard_fragment.html", {"logged_in": True, "no_game": True, "entries": None}
        )
    entries = scoreboard_service.compute_scoreboard(db, game.id)
    return templates.TemplateResponse(
        request, "_scoreboard_fragment.html", {"logged_in": True, "no_game": False, "entries": entries}
    )


@router.get("/admin/games", response_class=HTMLResponse)
def admin_games_page(request: Request):
    box_tiers = [
        (box_id, boxes_catalog.BOXES[box_id].display_name) for box_id in boxes_catalog.box_ids_sorted_by_tier()
    ]
    return templates.TemplateResponse(request, "admin/games.html", {"box_tiers": box_tiers})
