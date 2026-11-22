"""Independent reimplementation of every box's own flag-derivation
scheme -- HMAC-SHA256(team_secret, f"{box_id}:{flag_number}")[:10],
wrapped in HLC{...}. The orchestrator never computes or stores flags;
this platform is what verifies a player's submission, so it must derive
the same value independently from the team's own team_secret rather than
asking the orchestrator (which has no verification endpoint at all)."""
import hashlib
import hmac


def expected_flag(box_id: str, team_secret: str, flag_number: int) -> str:
    digest = hmac.new(team_secret.encode(), f"{box_id}:{flag_number}".encode(), hashlib.sha256).hexdigest()
    return f"HLC{{{digest[:10]}}}"
