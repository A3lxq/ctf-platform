"""Public (no-auth), read-only endpoints for the one-time "fetch on
page load" pattern already established by /api/auth/me -- event
branding (name/description/banner) and per-box display info, both
shown on every page without requiring a team or admin session."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from .. import schemas, security
from ..services import settings as settings_service

router = APIRouter(prefix="/api", tags=["public"])


@router.get("/settings", response_model=schemas.EventSettingsResponse)
def get_public_settings(db: Session = Depends(security.get_db)):
    row = settings_service.get_event_settings(db)
    return schemas.EventSettingsResponse(
        name=row.name, description=row.description, banner_url=settings_service.banner_url(row.banner_path)
    )


@router.get("/boxes-display/{box_id}", response_model=schemas.BoxDisplayResponse)
def get_public_box_display(box_id: str, db: Session = Depends(security.get_db)):
    data = settings_service.get_box_display(db, box_id)
    return schemas.BoxDisplayResponse(
        box_id=data["box_id"],
        display_name=data["display_name"],
        description=data["description"],
        banner_url=settings_service.banner_url(data["banner_path"]),
    )
