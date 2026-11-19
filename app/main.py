import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from . import config, security
from .api import admin, auth
from .models import Admin, get_session, init_db
from .web import routes as web_routes

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def bootstrap_admin() -> None:
    """The only way an Admin row ever gets created -- no public
    admin-registration endpoint exists anywhere. Runs once at startup;
    no-ops once any Admin row exists."""
    if not config.ADMIN_BOOTSTRAP_USERNAME or not config.ADMIN_BOOTSTRAP_PASSWORD:
        logger.warning("PLATFORM_ADMIN_USERNAME/PLATFORM_ADMIN_PASSWORD not set -- no admin account bootstrapped")
        return
    db = get_session()
    try:
        if db.query(Admin).count() > 0:
            return
        password_hash, password_salt = security.hash_password(config.ADMIN_BOOTSTRAP_PASSWORD)
        db.add(Admin(username=config.ADMIN_BOOTSTRAP_USERNAME, password_hash=password_hash, password_salt=password_salt))
        db.commit()
        logger.info("bootstrapped admin account %r", config.ADMIN_BOOTSTRAP_USERNAME)
    finally:
        db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    bootstrap_admin()
    yield


app = FastAPI(title="ctf-platform", lifespan=lifespan)
app.add_middleware(SessionMiddleware, secret_key=config.SESSION_SECRET, session_cookie=config.SESSION_COOKIE_NAME)
app.include_router(auth.router)
app.include_router(admin.router)
app.include_router(web_routes.router)
app.mount("/static", StaticFiles(directory="app/static"), name="static")
