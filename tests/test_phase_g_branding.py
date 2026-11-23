"""Phase G verification: event settings (singleton, site-wide) and
per-box display overrides. Real HTTP against a running ctf-platform
instance, no mocks. Uses random suffixes throughout (same convention as
every other test file here) so repeated runs never collide on the same
state -- the event settings row in particular is a true singleton that
persists across runs, so assertions never depend on its value before
this test's own writes.
"""
import io
import os
import secrets as pysecrets

import requests

BASE_URL = os.environ.get("PLATFORM_TEST_URL", "http://127.0.0.1:9200")
ADMIN_USERNAME = os.environ.get("PLATFORM_ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.environ.get("PLATFORM_ADMIN_PASSWORD", "testpass123")

_RUN_ID = pysecrets.token_hex(4)

# 1x1 transparent PNG, valid enough for the content-type/size checks.
_PNG_BYTES = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4890000000a49444154"
    "789c6360000000020001e221bc330000000049454e44ae426082"
)


def _admin_session() -> requests.Session:
    session = requests.Session()
    r = session.post(f"{BASE_URL}/api/auth/admin/login", json={"username": ADMIN_USERNAME, "password": ADMIN_PASSWORD})
    r.raise_for_status()
    return session


def test_event_settings_update_is_public_readable():
    admin = _admin_session()
    name = f"Test Event {_RUN_ID}"
    desc = f"description-{_RUN_ID}"

    updated = admin.put(f"{BASE_URL}/api/admin/settings", json={"name": name, "description": desc})
    assert updated.status_code == 200, updated.text
    assert updated.json()["name"] == name
    assert updated.json()["description"] == desc

    public = requests.get(f"{BASE_URL}/api/settings")
    assert public.status_code == 200, public.text
    assert public.json()["name"] == name
    assert public.json()["description"] == desc


def test_event_settings_requires_admin():
    r = requests.put(f"{BASE_URL}/api/admin/settings", json={"name": "unauthorized"})
    assert r.status_code == 401, r.text


def test_event_banner_upload_and_served():
    admin = _admin_session()
    r = admin.post(f"{BASE_URL}/api/admin/settings/banner", files={"image": ("banner.png", _PNG_BYTES, "image/png")})
    assert r.status_code == 200, r.text
    banner_url = r.json()["banner_url"]
    assert banner_url is not None

    served = requests.get(f"{BASE_URL}{banner_url}")
    assert served.status_code == 200
    assert served.content == _PNG_BYTES

    public = requests.get(f"{BASE_URL}/api/settings")
    assert public.json()["banner_url"] == banner_url


def test_event_banner_rejects_non_image():
    admin = _admin_session()
    r = admin.post(
        f"{BASE_URL}/api/admin/settings/banner", files={"image": ("not-an-image.txt", b"hello", "text/plain")}
    )
    assert r.status_code == 400, r.text


def test_box_display_falls_back_to_raw_box_id_when_unknown():
    box_id = f"test-fallback-{_RUN_ID}"
    public = requests.get(f"{BASE_URL}/api/boxes-display/{box_id}")
    assert public.status_code == 200, public.text
    body = public.json()
    assert body["display_name"] == box_id
    assert body["description"] is None
    assert body["banner_url"] is None


def test_box_display_update_and_public_read():
    box_id = f"test-display-{_RUN_ID}"
    admin = _admin_session()
    display_name = f"Friendly Name {_RUN_ID}"
    description = f"a nicer description {_RUN_ID}"

    updated = admin.put(
        f"{BASE_URL}/api/admin/boxes/{box_id}/display",
        json={"display_name": display_name, "description": description},
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["display_name"] == display_name
    assert updated.json()["description"] == description

    public = requests.get(f"{BASE_URL}/api/boxes-display/{box_id}")
    assert public.status_code == 200, public.text
    assert public.json()["display_name"] == display_name
    assert public.json()["description"] == description


def test_box_display_known_builtin_falls_back_to_catalog_name_when_untouched():
    # noob-orientation-server's catalog display_name -- fetched fresh
    # rather than hardcoded, so this doesn't silently rot if the catalog
    # entry's wording ever changes. Only meaningful if no earlier test
    # (or prior run) has set a custom display_name for this exact
    # box_id -- true for noob-orientation-server in this suite.
    public = requests.get(f"{BASE_URL}/api/boxes-display/noob-orientation-server")
    assert public.status_code == 200, public.text
    body = public.json()
    assert body["display_name"] != "noob-orientation-server", "should be the friendly catalog name, not the raw id"


def test_box_banner_upload_and_served():
    box_id = f"test-banner-{_RUN_ID}"
    admin = _admin_session()
    r = admin.post(f"{BASE_URL}/api/admin/boxes/{box_id}/banner", files={"image": ("banner.png", _PNG_BYTES, "image/png")})
    assert r.status_code == 200, r.text
    banner_url = r.json()["banner_url"]
    assert banner_url is not None

    served = requests.get(f"{BASE_URL}{banner_url}")
    assert served.status_code == 200
    assert served.content == _PNG_BYTES
