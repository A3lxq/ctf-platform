"""Thin HTTP client for ctf-orchestrator's REST API -- the only way this
platform ever provisions, renews, or destroys a team's box instances.
Sync (httpx.Client, not AsyncClient) to match the rest of this app: every
route handler here is a plain `def`, run in FastAPI's threadpool, not a
coroutine, so there's nothing async to gain from an async client."""
import httpx

from . import config


class OrchestratorError(Exception):
    """Raised for any non-2xx response the orchestrator returns (a 404
    on a truly unknown instance_id is handled separately below, not
    raised as an error -- see get_instance)."""

    def __init__(self, status_code: int, detail: str):
        self.status_code = status_code
        self.detail = detail
        super().__init__(f"orchestrator returned {status_code}: {detail}")


def _headers() -> dict:
    if config.ORCHESTRATOR_AUTH_TOKEN:
        return {"Authorization": f"Bearer {config.ORCHESTRATOR_AUTH_TOKEN}"}
    return {}


def _client() -> httpx.Client:
    return httpx.Client(base_url=config.ORCHESTRATOR_URL, headers=_headers(), timeout=60.0)


def _raise_for_error(resp: httpx.Response) -> None:
    if resp.status_code >= 400:
        detail = resp.text
        try:
            detail = resp.json().get("detail", detail)
        except ValueError:
            pass
        raise OrchestratorError(resp.status_code, detail)


def create_instance(team_id: int, box_id: str, team_secret: str, ttl_minutes: int | None = None) -> dict:
    with _client() as client:
        resp = client.post(
            "/instances",
            json={"team_id": team_id, "box_id": box_id, "team_secret": team_secret, "ttl_minutes": ttl_minutes},
        )
        _raise_for_error(resp)
        return resp.json()


def get_instance(instance_id: str) -> dict | None:
    """None means the orchestrator genuinely has no record of this
    instance_id (404) -- the normal outcome once its own reaper destroys
    an expired instance out from under this platform's local cache, not
    an error."""
    with _client() as client:
        resp = client.get(f"/instances/{instance_id}")
        if resp.status_code == 404:
            return None
        _raise_for_error(resp)
        return resp.json()


def renew_instance(instance_id: str, extra_minutes: int) -> dict:
    with _client() as client:
        resp = client.post(f"/instances/{instance_id}/renew", json={"extra_minutes": extra_minutes})
        _raise_for_error(resp)
        return resp.json()


def destroy_instance(instance_id: str) -> None:
    """Idempotent: the orchestrator's own DELETE already no-ops (200,
    not 404) for an already-destroyed instance -- a 404 here only means
    this exact instance_id was never known to it at all, which is still
    fine to treat as "already gone"."""
    with _client() as client:
        resp = client.delete(f"/instances/{instance_id}")
        if resp.status_code == 404:
            return
        _raise_for_error(resp)


def list_boxes() -> list[dict]:
    with _client() as client:
        resp = client.get("/boxes")
        _raise_for_error(resp)
        return resp.json()


def upload_box(spec_json: str, tarball: bytes) -> dict:
    """Admin-only custom box upload -- a real `docker build` on the
    orchestrator host, can take a while, hence the longer timeout than
    every other call in this module. `spec_json` is forwarded as-is
    (already a JSON string from the admin's own form submission) -- the
    orchestrator's own UploadBoxSpec does all the real validation, no
    need to parse/re-serialize it here too."""
    with httpx.Client(base_url=config.ORCHESTRATOR_URL, headers=_headers(), timeout=300.0) as client:
        resp = client.post(
            "/boxes",
            data={"spec": spec_json},
            files={"context": ("context.tar", tarball, "application/x-tar")},
        )
        _raise_for_error(resp)
        return resp.json()
