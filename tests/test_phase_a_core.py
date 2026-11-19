"""Phase A verification: data model + auth (incl. self-registration) +
admin CRUD, zero orchestrator integration. Real HTTP against a running
platform instance -- no mocks, same philosophy as ctf-orchestrator's own
test suite. Requires PLATFORM_TEST_URL (default http://127.0.0.1:9200)
to already be running, with PLATFORM_ADMIN_USERNAME/PASSWORD matching
whatever the server was started with -- this suite does not start its
own server, mirroring ctf-orchestrator's tests/test_phase2_boxes.py's
own real (not aspirational) pattern of requiring one already running.

Team names are randomized per process (same reasoning as
ctf-orchestrator's own test files, see their _TEAM_ID_BASE comments) so
concurrent/sequential runs of this file never collide on a unique
constraint.
"""
import os
import secrets as pysecrets
import time

import requests

BASE_URL = os.environ.get("PLATFORM_TEST_URL", "http://127.0.0.1:9200")
ADMIN_USERNAME = os.environ.get("PLATFORM_ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.environ.get("PLATFORM_ADMIN_PASSWORD", "testpass123")

_RUN_ID = pysecrets.token_hex(4)


def _team_name(suffix: str) -> str:
    return f"test-{_RUN_ID}-{suffix}"


def _get_form_token() -> str:
    r = requests.get(f"{BASE_URL}/api/auth/register/form-token")
    r.raise_for_status()
    return r.json()["form_token"]


def _register(name: str, password: str, *, website: str = "", wait: bool = True) -> requests.Response:
    token = _get_form_token()
    if wait:
        time.sleep(2.1)  # clear the server's min-fill-time threshold (default 2.0s)
    session = requests.Session()
    resp = session.post(
        f"{BASE_URL}/api/auth/register",
        json={
            "name": name,
            "password": password,
            "confirm_password": password,
            "website": website,
            "form_token": token,
        },
    )
    resp._session = session  # stash for the caller to reuse cookies
    return resp


def _admin_session() -> requests.Session:
    session = requests.Session()
    r = session.post(f"{BASE_URL}/api/auth/admin/login", json={"username": ADMIN_USERNAME, "password": ADMIN_PASSWORD})
    r.raise_for_status()
    return session


def test_registration_rejects_too_fast_submission():
    token = _get_form_token()
    r = requests.post(
        f"{BASE_URL}/api/auth/register",
        json={
            "name": _team_name("toofast"),
            "password": "longenoughpassword",
            "confirm_password": "longenoughpassword",
            "website": "",
            "form_token": token,
        },
    )
    assert r.status_code == 400, r.text


def test_registration_rejects_honeypot_filled():
    r = _register(_team_name("honeypot"), "longenoughpassword", website="http://spam.example")
    assert r.status_code == 400, r.text


def test_registration_rejects_mismatched_passwords():
    token = _get_form_token()
    time.sleep(2.1)
    r = requests.post(
        f"{BASE_URL}/api/auth/register",
        json={
            "name": _team_name("mismatch"),
            "password": "longenoughpassword",
            "confirm_password": "differentpassword",
            "website": "",
            "form_token": token,
        },
    )
    assert r.status_code == 400, r.text


def test_registration_succeeds_and_logs_in():
    name = _team_name("alpha")
    r = _register(name, "alphapassword1")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["name"] == name
    assert body["disabled"] is False

    # Session cookie set on registration -- confirm /me reflects it.
    me = r._session.get(f"{BASE_URL}/api/auth/me")
    assert me.status_code == 200
    assert me.json() == {"role": "team", "id": body["id"], "name": name}


def test_duplicate_team_name_rejected():
    name = _team_name("dup")
    r1 = _register(name, "firstpassword1")
    assert r1.status_code == 200, r1.text
    r2 = _register(name, "secondpassword1")
    assert r2.status_code == 409, r2.text


def test_wrong_password_rejected():
    name = _team_name("wrongpw")
    r = _register(name, "correctpassword1")
    assert r.status_code == 200, r.text

    bad = requests.post(f"{BASE_URL}/api/auth/team/login", json={"name": name, "password": "incorrectpassword"})
    assert bad.status_code == 401, bad.text

    good = requests.post(f"{BASE_URL}/api/auth/team/login", json={"name": name, "password": "correctpassword1"})
    assert good.status_code == 200, good.text


def test_admin_login_and_team_management():
    name = _team_name("managed")
    reg = _register(name, "managedpassword1")
    assert reg.status_code == 200, reg.text
    team_id = reg.json()["id"]

    admin = _admin_session()

    teams = admin.get(f"{BASE_URL}/api/admin/teams")
    assert teams.status_code == 200
    assert any(t["id"] == team_id for t in teams.json())

    disabled = admin.patch(f"{BASE_URL}/api/admin/teams/{team_id}/disabled", json={"disabled": True})
    assert disabled.status_code == 200
    assert disabled.json()["disabled"] is True

    blocked = requests.post(f"{BASE_URL}/api/auth/team/login", json={"name": name, "password": "managedpassword1"})
    assert blocked.status_code == 403, blocked.text

    re_enabled = admin.patch(f"{BASE_URL}/api/admin/teams/{team_id}/disabled", json={"disabled": False})
    assert re_enabled.status_code == 200

    reset = admin.post(f"{BASE_URL}/api/admin/teams/{team_id}/reset-password", json={"new_password": "newpassword1"})
    assert reset.status_code == 200

    relogin = requests.post(f"{BASE_URL}/api/auth/team/login", json={"name": name, "password": "newpassword1"})
    assert relogin.status_code == 200, relogin.text


def test_game_and_challenge_crud():
    admin = _admin_session()

    # Defensive: end any game left RUNNING by a crashed/previous run of
    # this same test, so "at most one RUNNING game" doesn't spuriously
    # block this run before it even starts its own game. Mirrors the
    # orchestrator test suite's own "clean up leftover state before
    # asserting on fresh state" convention.
    games = admin.get(f"{BASE_URL}/api/admin/games")
    assert games.status_code == 200
    for g in games.json():
        if g["status"] == "running":
            admin.post(f"{BASE_URL}/api/admin/games/{g['id']}/end")

    game = admin.post(f"{BASE_URL}/api/admin/games", json={"name": f"test-game-{_RUN_ID}"})
    assert game.status_code == 200, game.text
    game_id = game.json()["id"]
    assert game.json()["status"] == "draft"

    try:
        unknown_box = admin.post(
            f"{BASE_URL}/api/admin/games/{game_id}/challenges",
            json={"box_id": "not-a-real-box", "flag_number": 1, "title": "x", "points": 100},
        )
        assert unknown_box.status_code == 400, unknown_box.text

        chal = admin.post(
            f"{BASE_URL}/api/admin/games/{game_id}/challenges",
            json={"box_id": "noob-orientation-server", "flag_number": 1, "title": "Welcome", "points": 50},
        )
        assert chal.status_code == 200, chal.text

        dup = admin.post(
            f"{BASE_URL}/api/admin/games/{game_id}/challenges",
            json={"box_id": "noob-orientation-server", "flag_number": 1, "title": "Welcome again", "points": 50},
        )
        assert dup.status_code == 400, dup.text

        listed = admin.get(f"{BASE_URL}/api/admin/games/{game_id}/challenges")
        assert listed.status_code == 200
        assert len(listed.json()) == 1

        started = admin.post(f"{BASE_URL}/api/admin/games/{game_id}/start")
        assert started.status_code == 200, started.text
        assert started.json()["status"] == "running"

        second_game = admin.post(f"{BASE_URL}/api/admin/games", json={"name": f"test-game-2-{_RUN_ID}"})
        assert second_game.status_code == 200
        second_id = second_game.json()["id"]
        blocked_start = admin.post(f"{BASE_URL}/api/admin/games/{second_id}/start")
        assert blocked_start.status_code == 409, blocked_start.text
    finally:
        # Always release the RUNNING slot, pass or fail, so the next
        # run of this file (or any other test) isn't left blocked.
        admin.post(f"{BASE_URL}/api/admin/games/{game_id}/end")


def test_unauthenticated_requests_rejected():
    assert requests.get(f"{BASE_URL}/api/admin/teams").status_code == 401
    assert requests.get(f"{BASE_URL}/api/auth/me").status_code == 401
