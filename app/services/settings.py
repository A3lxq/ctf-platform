"""Site-wide event settings (singleton row) and per-box display
overrides -- the "make this feel lively, not generic" layer on top of
Phase A-F's functional pieces. Admin never has to touch any of this:
every read here has a safe fallback to today's existing behavior (the
hardcoded event name, boxes_catalog.py's static display names, or the
raw box_id for a freshly-uploaded custom box)."""
import os
import uuid

from sqlalchemy.orm import Session

from .. import boxes_catalog, config, models

_ALLOWED_IMAGE_TYPES = {"image/png": ".png", "image/jpeg": ".jpg", "image/webp": ".webp"}
_MAX_IMAGE_BYTES = 5 * 1024 * 1024


class SettingsServiceError(Exception):
    def __init__(self, status_code: int, detail: str):
        self.status_code = status_code
        self.detail = detail
        super().__init__(detail)


def banner_url(banner_path: str | None) -> str | None:
    return f"{config.UPLOADS_URL_PREFIX}/{banner_path}" if banner_path else None


def get_event_settings(db: Session) -> models.EventSettings:
    row = db.get(models.EventSettings, 1)
    if row is None:
        row = models.EventSettings(id=1)
        db.add(row)
        db.commit()
        db.refresh(row)
    return row


def update_event_settings(db: Session, name: str | None, description: str | None) -> models.EventSettings:
    row = get_event_settings(db)
    if name is not None:
        row.name = name
    if description is not None:
        row.description = description
    db.commit()
    db.refresh(row)
    return row


def _save_uploaded_image(content_type: str, data: bytes) -> str:
    """Validates and saves an uploaded banner/icon image, returns the
    filename (relative to config.UPLOADS_DIR) to store in a
    banner_path column."""
    if content_type not in _ALLOWED_IMAGE_TYPES:
        raise SettingsServiceError(400, f"unsupported image type {content_type!r} -- use PNG, JPEG, or WebP")
    if len(data) > _MAX_IMAGE_BYTES:
        raise SettingsServiceError(400, f"image too large ({len(data)} bytes, max {_MAX_IMAGE_BYTES})")
    filename = f"{uuid.uuid4().hex}{_ALLOWED_IMAGE_TYPES[content_type]}"
    os.makedirs(config.UPLOADS_DIR, exist_ok=True)
    with open(os.path.join(config.UPLOADS_DIR, filename), "wb") as f:
        f.write(data)
    return filename


def set_event_banner(db: Session, content_type: str, data: bytes) -> models.EventSettings:
    filename = _save_uploaded_image(content_type, data)
    row = get_event_settings(db)
    row.banner_path = filename
    db.commit()
    db.refresh(row)
    return row


def get_box_display(db: Session, box_id: str) -> dict:
    row = db.get(models.BoxDisplay, box_id)
    fallback_name = boxes_catalog.BOXES[box_id].display_name if boxes_catalog.is_known_box_id(box_id) else box_id
    return {
        "box_id": box_id,
        "display_name": (row.display_name if row and row.display_name else fallback_name),
        "description": row.description if row else None,
        "banner_path": row.banner_path if row else None,
    }


def update_box_display(db: Session, box_id: str, display_name: str | None, description: str | None) -> dict:
    row = db.get(models.BoxDisplay, box_id)
    if row is None:
        row = models.BoxDisplay(box_id=box_id)
        db.add(row)
    if display_name is not None:
        row.display_name = display_name
    if description is not None:
        row.description = description
    db.commit()
    return get_box_display(db, box_id)


def set_box_banner(db: Session, box_id: str, content_type: str, data: bytes) -> dict:
    filename = _save_uploaded_image(content_type, data)
    row = db.get(models.BoxDisplay, box_id)
    if row is None:
        row = models.BoxDisplay(box_id=box_id)
        db.add(row)
    row.banner_path = filename
    db.commit()
    return get_box_display(db, box_id)
