"""Phase B verification: ctf-platform's real orchestrator integration --
instance start/stop talking to a real orchestrator and a real
noob-orientation-server container, flag verification against each
team's own team_secret (never exposed via any API, so this test reads
it the only way a player legitimately can: off the box's own front
door). Real HTTP, no mocks. Requires:

- a running ctf-platform instance at PLATFORM_TEST_URL (default
  http://127.0.0.1:9200), configured (at its own startup, via
  PLATFORM_ORCHESTRATOR_URL) to talk to...
- a running ctf-orchestrator instance, with noob-orientation-server's
  image already built -- same real-Docker-no-mocks philosophy as
  ctf-orchestrator's own test suite.

Slow: provisions and destroys real containers. Run deliberately, not as
part of a fast unit-test loop.
"""
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
    return f"test-b-{_RUN_ID}-{suffix}"


def _get_form_token() -> str:
    r = requests.get(f"{BASE_URL}/api/auth/register/form-token")
    r.raise_for_status()
    return r.json()["form_token"]


def _register(name: str, password: str) -> tuple[requests.Session, dict]:
    token = _get_form_token()
    time.sleep(2.1)  # clear the server's min-fill-time threshold
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


def _extract_flag(page_text: str) -> str:
    m = _FLAG_RE.search(page_text)
    assert m is not None, "expected an HLC{...} flag somewhere on the box's front page"
    return m.group(0)


def _container_gone(box_id: str, team_id: int, service_name: str) -> bool:
    name = f"ctf-{box_id}-{team_id}-{service_name}"
    result = subprocess.run(["docker", "inspect", name], capture_output=True)
    return result.returncode != 0


def test_two_team_isolation_and_flag_submission():
    admin = _admin_session()

    # Defensive: end any game left RUNNING by a crashed/previous run, so
    # "at most one RUNNING game" doesn't block this run before it starts.
    games = admin.get(f"{BASE_URL}/api/admin/games")
    games.raise_for_status()
    for g in games.json():
        if g["status"] == "running":
            admin.post(f"{BASE_URL}/api/admin/games/{g['id']}/end")

    game = admin.post(f"{BASE_URL}/api/admin/games", json={"name": f"test-b-game-{_RUN_ID}"})
    game.raise_for_status()
    game_id = game.json()["id"]

    chal = admin.post(
        f"{BASE_URL}/api/admin/games/{game_id}/challenges",
        json={"box_id": "noob-orientation-server", "flag_number": 1, "title": "Welcome", "points": 100},
    )
    chal.raise_for_status()
    challenge_id = chal.json()["id"]

    started = admin.post(f"{BASE_URL}/api/admin/games/{game_id}/start")
    assert started.status_code == 200, started.text

    session_a, team_a = _register(_team_name("alpha"), "alphapassword1")
    session_b, team_b = _register(_team_name("bravo"), "bravopassword1")

    try:
        inst_a_resp = session_a.post(f"{BASE_URL}/api/player/instances", json={"box_id": "noob-orientation-server"})
        assert inst_a_resp.status_code == 200, inst_a_resp.text
        inst_b_resp = session_b.post(f"{BASE_URL}/api/player/instances", json={"box_id": "noob-orientation-server"})
        assert inst_b_resp.status_code == 200, inst_b_resp.text
        inst_a, inst_b = inst_a_resp.json(), inst_b_resp.json()
        assert inst_a["id"] != inst_b["id"]

        page_a = requests.get(f"http://{inst_a['entry_host']}:{inst_a['entry_port']}/").text
        page_b = requests.get(f"http://{inst_b['entry_host']}:{inst_b['entry_port']}/").text
        flag_a = _extract_flag(page_a)
        flag_b = _extract_flag(page_b)
        assert flag_a != flag_b, "two different teams must get different flags for the same box_id:flag_number"

        # Team B submitting team A's real flag must be rejected (wrong
        # team_secret used server-side for team B's expected-flag check).
        wrong = session_b.post(f"{BASE_URL}/api/player/submissions", json={"challenge_id": challenge_id, "value": flag_a})
        assert wrong.status_code == 200, wrong.text
        assert wrong.json()["correct"] is False

        # Team A submitting its own real flag must be accepted.
        right = session_a.post(f"{BASE_URL}/api/player/submissions", json={"challenge_id": challenge_id, "value": flag_a})
        assert right.status_code == 200, right.text
        assert right.json()["correct"] is True

        # Resubmitting an already-solved challenge is rejected with 409,
        # not silently re-accepted.
        dup = session_a.post(f"{BASE_URL}/api/player/submissions", json={"challenge_id": challenge_id, "value": flag_a})
        assert dup.status_code == 409, dup.text

        # DELETE actually tears the real container down, not just marks
        # it destroyed in this platform's own DB.
        stop = session_a.delete(f"{BASE_URL}/api/player/instances/noob-orientation-server")
        assert stop.status_code == 204, stop.text
        time.sleep(1)
        assert _container_gone("noob-orientation-server", team_a["id"], "orientation-server")

        # Idempotent: a second DELETE for an already-stopped box is a
        # harmless no-op, not an error.
        stop_again = session_a.delete(f"{BASE_URL}/api/player/instances/noob-orientation-server")
        assert stop_again.status_code == 204, stop_again.text
    finally:
        session_a.delete(f"{BASE_URL}/api/player/instances/noob-orientation-server")
        session_b.delete(f"{BASE_URL}/api/player/instances/noob-orientation-server")
        admin.post(f"{BASE_URL}/api/admin/games/{game_id}/end")


def test_per_team_quota_enforced_through_the_platform():
    """The orchestrator's own quota (Phase B, ctf-orchestrator side)
    must surface through the platform as a clean error, not a raw 500 --
    confirms services/instances.py's 429 passthrough actually works."""
    max_per_team = int(os.environ.get("ORCHESTRATOR_MAX_INSTANCES_PER_TEAM", "4"))
    fill_boxes = ["noob-orientation-server", "beginner-reading-room", "intermediate-portside", "veteran-aftermath"]
    assert len(fill_boxes) == max_per_team, (
        "this test's fill list must match the orchestrator's configured cap -- "
        "if ORCHESTRATOR_MAX_INSTANCES_PER_TEAM was overridden, override fill_boxes too"
    )

    session, _team = _register(_team_name("quota"), "quotapassword1")
    try:
        for box_id in fill_boxes:
            r = session.post(f"{BASE_URL}/api/player/instances", json={"box_id": box_id})
            assert r.status_code == 200, r.text

        blocked = session.post(f"{BASE_URL}/api/player/instances", json={"box_id": "master-two-offices"})
        assert blocked.status_code == 429, blocked.text
    finally:
        for box_id in fill_boxes:
            session.delete(f"{BASE_URL}/api/player/instances/{box_id}")
