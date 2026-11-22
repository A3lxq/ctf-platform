"""Phase C verification: scoreboard, admin monitoring dashboard, CSV
export, and the game-end mass-teardown sweep. Real HTTP against a
running ctf-platform + ctf-orchestrator, real containers -- same
philosophy as every other test file in this project. Requires:
- PLATFORM_TEST_URL (default http://127.0.0.1:9200)
- PLATFORM_ADMIN_USERNAME/PASSWORD matching the running server
- the orchestrator it's configured to talk to, with
  noob-orientation-server / beginner-reading-room / intermediate-portside
  images already built

Slow: provisions and destroys real containers. Run deliberately.
"""
import csv
import io
import os
import re
import secrets as pysecrets
import subprocess
import time

import requests

BASE_URL = os.environ.get("PLATFORM_TEST_URL", "http://127.0.0.1:9200")
ADMIN_USERNAME = os.environ.get("PLATFORM_ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.environ.get("PLATFORM_ADMIN_PASSWORD", "testpass123")

_RUN_ID = pysecrets.token_hex(4)
_FLAG_RE = re.compile(r"HLC\{[0-9a-f]{10}\}")


def _team_name(suffix: str) -> str:
    return f"test-c-{_RUN_ID}-{suffix}"


def _get_form_token() -> str:
    r = requests.get(f"{BASE_URL}/api/auth/register/form-token")
    r.raise_for_status()
    return r.json()["form_token"]


def _register(name: str, password: str) -> tuple[requests.Session, dict]:
    token = _get_form_token()
    time.sleep(2.1)
    session = requests.Session()
    resp = session.post(
        f"{BASE_URL}/api/auth/register",
        json={"name": name, "password": password, "confirm_password": password, "website": "", "form_token": token},
    )
    resp.raise_for_status()
    return session, resp.json()


def _admin_session() -> requests.Session:
    session = requests.Session()
    r = session.post(f"{BASE_URL}/api/auth/admin/login", json={"username": ADMIN_USERNAME, "password": ADMIN_PASSWORD})
    r.raise_for_status()
    return session


def _end_any_running_game(admin: requests.Session) -> None:
    games = admin.get(f"{BASE_URL}/api/admin/games")
    games.raise_for_status()
    for g in games.json():
        if g["status"] == "running":
            admin.post(f"{BASE_URL}/api/admin/games/{g['id']}/end")


def _extract_flag(page_text: str) -> str:
    m = _FLAG_RE.search(page_text)
    assert m is not None, "expected an HLC{...} flag on the box's front page"
    return m.group(0)


def _container_gone(box_id: str, team_id: int, service_name: str) -> bool:
    name = f"ctf-{box_id}-{team_id}-{service_name}"
    result = subprocess.run(["docker", "inspect", name], capture_output=True)
    return result.returncode != 0


def test_scoreboard_and_csv_export_reflect_a_real_solve():
    admin = _admin_session()
    _end_any_running_game(admin)

    game = admin.post(f"{BASE_URL}/api/admin/games", json={"name": f"test-c-game-{_RUN_ID}"})
    game.raise_for_status()
    game_id = game.json()["id"]

    chal = admin.post(
        f"{BASE_URL}/api/admin/games/{game_id}/challenges",
        json={"box_id": "noob-orientation-server", "flag_number": 1, "title": "Welcome", "points": 150},
    )
    chal.raise_for_status()
    challenge_id = chal.json()["id"]

    started = admin.post(f"{BASE_URL}/api/admin/games/{game_id}/start")
    assert started.status_code == 200, started.text

    session, team = _register(_team_name("solver"), "solverpassword1")
    try:
        inst_resp = session.post(f"{BASE_URL}/api/player/instances", json={"box_id": "noob-orientation-server"})
        assert inst_resp.status_code == 200, inst_resp.text
        inst = inst_resp.json()

        page = requests.get(f"http://{inst['entry_host']}:{inst['entry_port']}/").text
        flag = _extract_flag(page)

        submit = session.post(f"{BASE_URL}/api/player/submissions", json={"challenge_id": challenge_id, "value": flag})
        assert submit.status_code == 200, submit.text
        assert submit.json()["correct"] is True

        sb = session.get(f"{BASE_URL}/api/player/scoreboard")
        assert sb.status_code == 200, sb.text
        entries = {e["team_id"]: e for e in sb.json()}
        assert entries[team["id"]]["score"] == 150
        assert entries[team["id"]]["rank"] == 1

        admin_sb = admin.get(f"{BASE_URL}/api/admin/games/{game_id}/scoreboard")
        assert admin_sb.status_code == 200, admin_sb.text
        admin_entries = {e["team_id"]: e for e in admin_sb.json()}
        assert admin_entries[team["id"]]["score"] == 150

        csv_resp = admin.get(f"{BASE_URL}/api/admin/games/{game_id}/export/results.csv")
        assert csv_resp.status_code == 200, csv_resp.text
        assert csv_resp.headers["content-type"].startswith("text/csv")
        rows = list(csv.DictReader(io.StringIO(csv_resp.text)))
        row = next(r for r in rows if int(r["team_id"]) == team["id"])
        assert row["team_name"] == team["name"]
        assert int(row["score"]) == 150
    finally:
        session.delete(f"{BASE_URL}/api/player/instances/noob-orientation-server")
        admin.post(f"{BASE_URL}/api/admin/games/{game_id}/end")


def test_admin_instances_dashboard_and_force_stop():
    admin = _admin_session()
    session, team = _register(_team_name("monitored"), "monitoredpassword1")
    try:
        inst_resp = session.post(f"{BASE_URL}/api/player/instances", json={"box_id": "beginner-reading-room"})
        assert inst_resp.status_code == 200, inst_resp.text
        inst = inst_resp.json()

        listing = admin.get(f"{BASE_URL}/api/admin/instances")
        assert listing.status_code == 200, listing.text
        rows = {r["id"]: r for r in listing.json()}
        assert inst["id"] in rows
        assert rows[inst["id"]]["team_name"] == team["name"]
        assert rows[inst["id"]]["box_id"] == "beginner-reading-room"
        assert rows[inst["id"]]["status"] == "running"

        force = admin.post(f"{BASE_URL}/api/admin/instances/{inst['id']}/force-stop")
        assert force.status_code == 200, force.text
        assert force.json()["status"] == "destroyed"
        time.sleep(1)
        assert _container_gone("beginner-reading-room", team["id"], "reading-room")
    finally:
        session.delete(f"{BASE_URL}/api/player/instances/beginner-reading-room")


def test_game_end_tears_down_instances_for_its_boxes():
    admin = _admin_session()
    _end_any_running_game(admin)

    game = admin.post(f"{BASE_URL}/api/admin/games", json={"name": f"test-c-teardown-{_RUN_ID}"})
    game.raise_for_status()
    game_id = game.json()["id"]
    chal = admin.post(
        f"{BASE_URL}/api/admin/games/{game_id}/challenges",
        json={"box_id": "intermediate-portside", "flag_number": 1, "title": "x", "points": 10},
    )
    chal.raise_for_status()
    started = admin.post(f"{BASE_URL}/api/admin/games/{game_id}/start")
    assert started.status_code == 200, started.text

    session, team = _register(_team_name("teardown"), "teardownpassword1")
    inst_resp = session.post(f"{BASE_URL}/api/player/instances", json={"box_id": "intermediate-portside"})
    assert inst_resp.status_code == 200, inst_resp.text
    instance_id = inst_resp.json()["id"]

    ended = admin.post(f"{BASE_URL}/api/admin/games/{game_id}/end")
    assert ended.status_code == 200, ended.text

    time.sleep(1)
    assert _container_gone("intermediate-portside", team["id"], "portside")

    listing = admin.get(f"{BASE_URL}/api/admin/instances")
    assert listing.status_code == 200, listing.text
    rows = {r["id"]: r for r in listing.json()}
    assert rows[instance_id]["status"] == "destroyed"
