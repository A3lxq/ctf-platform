"""Static catalog of the 8 box_ids ctf-orchestrator knows how to host --
mirrors orchestrator/boxes/registry.py + specs/*.yaml. Hardcoded here for
Phase A; once the orchestrator's Phase-B GET /boxes patch lands, this
becomes a fallback/cache rather than the only source, but validation
logic should keep working identically either way.

"front_door_ports" lists every port players connect to directly (not
just the one entry_port the orchestrator's /instances response returns
today) -- used for display ("ssh"/"http" badges) until the orchestrator's
own ports-field patch (Phase B) makes this redundant with live data.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class BoxCatalogEntry:
    box_id: str
    display_name: str
    tier: str  # for grouping in the UI: noob -> legendary
    front_door_ports: tuple[tuple[int, str], ...]  # (port, protocol_label)
    max_flag_number: int


BOXES: dict[str, BoxCatalogEntry] = {
    "noob-orientation-server": BoxCatalogEntry(
        "noob-orientation-server", "Orientation Server", "noob",
        ((80, "http"), (21, "ftp"), (22, "ssh")), 10,
    ),
    "beginner-reading-room": BoxCatalogEntry(
        "beginner-reading-room", "Reading Room", "beginner",
        ((80, "http"),), 10,
    ),
    "intermediate-portside": BoxCatalogEntry(
        "intermediate-portside", "Portside", "intermediate",
        ((5000, "http"),), 10,
    ),
    "veteran-aftermath": BoxCatalogEntry(
        "veteran-aftermath", "Aftermath", "veteran",
        ((80, "http"), (22, "ssh")), 10,
    ),
    "master-two-offices": BoxCatalogEntry(
        "master-two-offices", "Two Offices", "master",
        ((5000, "http"), (22, "ssh")), 10,
    ),
    "expert-the-annex": BoxCatalogEntry(
        "expert-the-annex", "The Annex", "expert",
        ((5000, "http"),), 10,
    ),
    "god-the-ferryman": BoxCatalogEntry(
        "god-the-ferryman", "The Ferryman", "god",
        ((5000, "http"),), 10,
    ),
    "legendary-ferrymans-relay": BoxCatalogEntry(
        "legendary-ferrymans-relay", "Ferryman's Relay", "legendary",
        ((5000, "http"), (22, "ssh")), 10,
    ),
}

TIER_ORDER = ["noob", "beginner", "intermediate", "veteran", "master", "expert", "god", "legendary"]


def is_known_box_id(box_id: str) -> bool:
    return box_id in BOXES


def box_ids_sorted_by_tier() -> list[str]:
    return sorted(BOXES, key=lambda b: TIER_ORDER.index(BOXES[b].tier))
