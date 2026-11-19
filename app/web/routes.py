from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from .. import security

router = APIRouter(tags=["web"])
templates = Jinja2Templates(directory="app/templates")


@router.get("/", response_class=HTMLResponse)
def index(request: Request):
    return templates.TemplateResponse(
        request,
        "placeholder.html",
        {"heading": "Halcyon Protocol", "message": "Register or log in to play."},
    )


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
    # Full challenge list lands in Phase B (needs the orchestrator
    # integration + player API) -- placeholder so the register/login
    # redirect target isn't a 404 in the meantime.
    return templates.TemplateResponse(
        request,
        "placeholder.html",
        {"heading": "Challenges", "message": "You're logged in. The challenge list is coming in Phase B."},
    )


@router.get("/admin/games", response_class=HTMLResponse)
def admin_games_page(request: Request):
    return templates.TemplateResponse(
        request,
        "placeholder.html",
        {"heading": "Admin: Games", "message": "Admin logged in. The games/challenges management UI is coming in Phase C/D."},
    )
