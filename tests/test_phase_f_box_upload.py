"""Phase F verification: the admin box-upload UI's backend -- a pure
passthrough (GET/POST /api/admin/boxes) to the real orchestrator's own
POST /boxes. Builds a trivial real test box on the fly (mirrors
ctf-orchestrator's own tests/test_phase7_box_upload.py), uploads it
through the PLATFORM's admin API (not the orchestrator directly), and
confirms it shows up via GET /api/admin/boxes and can actually be
provisioned for a team through the normal player flow. Real HTTP, real
Docker, no mocks.

Cleans up everything it creates on disk in the orchestrator repo
(boxes-src/<box_id>/, boxes/specs/<box_id>.yaml) and the built image,
since those land in that repo's own git-tracked directories.

Requires: a running ctf-platform at PLATFORM_TEST_URL (default
http://127.0.0.1:9200), configured to talk to a real running
orchestrator with outbound access to pull python:3.11-alpine.
"""
import io
import json
import os
import secrets as pysecrets
import shutil
import subprocess
import tarfile

import requests

BASE_URL = os.environ.get("PLATFORM_TEST_URL", "http://127.0.0.1:9200")
ADMIN_USERNAME = os.environ.get("PLATFORM_ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.environ.get("PLATFORM_ADMIN_PASSWORD", "testpass123")
ORCHESTRATOR_ROOT = os.environ.get(
    "ORCHESTRATOR_ROOT", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "..", "ctf-orchestrator")
)

_RUN_ID = pysecrets.token_hex(4)


def _admin_session() -> requests.Session:
    session = requests.Session()
    r = session.post(f"{BASE_URL}/api/auth/admin/login", json={"username": ADMIN_USERNAME, "password": ADMIN_PASSWORD})
    r.raise_for_status()
    return session


def _make_tarball(box_id: str) -> bytes:
    entrypoint = f"""
import hashlib, hmac, http.server, os

SECRET = os.environ["CTF_SECRET"]
digest = hmac.new(SECRET.encode(), {box_id!r}.encode() + b":1", hashlib.sha256).hexdigest()
FLAG = "HLC{{" + digest[:10] + "}}"

class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(FLAG.encode())

http.server.HTTPServer(("0.0.0.0", 80), Handler).serve_forever()
"""
    dockerfile = "FROM python:3.11-alpine\nCOPY docker/entrypoint.py /entrypoint.py\nEXPOSE 80\nCMD [\"python3\", \"/entrypoint.py\"]\n"

    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tar:
        for name, content in [("docker/Dockerfile", dockerfile), ("docker/entrypoint.py", entrypoint)]:
            data = content.encode()
            info = tarfile.TarInfo(name=name)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    return buf.getvalue()


def _cleanup_box(box_id: str) -> None:
    shutil.rmtree(os.path.join(ORCHESTRATOR_ROOT, "boxes-src", box_id), ignore_errors=True)
    spec_path = os.path.join(ORCHESTRATOR_ROOT, "orchestrator", "boxes", "specs", f"{box_id}.yaml")
    if os.path.isfile(spec_path):
        os.remove(spec_path)
    subprocess.run(["docker", "rmi", "-f", f"ctf-boxes/{box_id}:latest"], capture_output=True)


def test_upload_through_admin_api_and_provision():
    box_id = f"test-platform-upload-{_RUN_ID}"
    admin = _admin_session()

    try:
        spec = {"box_id": box_id, "hosts": [{"name": "web", "front_door": True, "ports": [{"container_port": 80, "protocol": "tcp"}]}]}
        r = admin.post(
            f"{BASE_URL}/api/admin/boxes",
            data={"spec": json.dumps(spec)},
            files={"context": ("context.tar", _make_tarball(box_id), "application/x-tar")},
        )
        assert r.status_code == 200, r.text
        assert r.json()["box_id"] == box_id

        listed = admin.get(f"{BASE_URL}/api/admin/boxes")
        assert listed.status_code == 200, listed.text
        assert any(b["box_id"] == box_id for b in listed.json())
    finally:
        _cleanup_box(box_id)
