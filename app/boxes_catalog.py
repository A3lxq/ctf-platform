"""Static catalog of the box_ids ctf-orchestrator knows how to host --
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
    # A crossover from a different fictional universe (Synnefo Academy,
    # not Halcyon Protocol) -- doesn't try to occupy a rung on the
    # 8-tier ladder above, hence its own "bonus" tier. Only 5 scoring
    # flags, not 10 -- it genuinely has 5 decoys alongside them, never
    # derived/scored, same category as every other box's own static
    # decoy files (Noob already ships a flag_fake.txt).
    "bonus-forgotten-administrator": BoxCatalogEntry(
        "bonus-forgotten-administrator", "The Forgotten Administrator", "bonus",
        ((5000, "http"), (22, "ssh")), 5,
    ),
    # A second crossover, from yet another standalone universe/scenario
    # (a corporate "Apex Cyber Defense" pentesting exam) -- rated
    # Beginner-equivalent, but still filed under "bonus" rather than
    # colliding with the existing "beginner" rung already occupied by
    # beginner-reading-room. 4 scoring flags: web recon, SSH user shell,
    # a third flag also surfaced over FTP (on the source OVA this
    # duplicated the root flag verbatim -- rebuilt here as a genuinely
    # distinct 4th-flag box instead), and root compromise.
    "bonus-apex-cyber-defense": BoxCatalogEntry(
        "bonus-apex-cyber-defense", "Apex Cyber Defense", "bonus",
        ((80, "http"), (21, "ftp"), (2222, "ssh")), 4,
    ),
    # First box of "Domain Zero Directory" -- a new 8-tier game (separate
    # from the Halcyon Protocol ladder above), a classic on-prem
    # corporate red-team engagement against the fictional "Meridian
    # Systems". Noob tier: SMB share enumeration, a leaked config-backup
    # credential, SSH foothold via password reuse, sudo/GTFOBins ('less')
    # privesc. 10 real flags, matching the Halcyon boxes' own convention.
    "domainzero-noob-reception": BoxCatalogEntry(
        "domainzero-noob-reception", "Reception", "noob",
        ((22, "ssh"), (445, "smb"), (139, "smb")), 10,
    ),
    # First box of "Cloudbreak Pipeline" -- the second new 8-tier game, a
    # cloud-native/DevOps-flavored engagement against the fictional
    # "Nimbus Freight" logistics startup. Noob tier: object-storage
    # bucket enumeration, a leaked cloud storage credential, SSH foothold
    # via password reuse, sudo/GTFOBins ('tar') privesc. Deliberately
    # distinct mechanics from domainzero-noob-reception above despite
    # being the same tier in a sibling game.
    "cloudbreak-noob-bucket": BoxCatalogEntry(
        "cloudbreak-noob-bucket", "Bucket", "noob",
        ((22, "ssh"), (9000, "http")), 10,
    ),
    # Beginner tier of Domain Zero Directory: a real, dependency-free
    # Node.js app with a genuine prototype-pollution auth bypass (naive
    # recursive merge, no __proto__/constructor/prototype key
    # filtering -- the same bug class as several real npm CVEs).
    "domainzero-beginner-helpdesk": BoxCatalogEntry(
        "domainzero-beginner-helpdesk", "Helpdesk", "beginner",
        ((22, "ssh"), (5000, "http")), 10,
    ),
    # Beginner tier of Cloudbreak Pipeline: a real exposed .git
    # directory (genuine `git clone` against it works, including
    # `git update-server-info`) leaking a secret removed from HEAD but
    # still recoverable from history -- the classic real-world
    # "exposed .git directory" bug class.
    "cloudbreak-beginner-gitleak": BoxCatalogEntry(
        "cloudbreak-beginner-gitleak", "Gitleak", "beginner",
        ((22, "ssh"), (80, "http")), 10,
    ),
    # Intermediate tier of Domain Zero Directory: a real Samba AD DC.
    # Password spraying the usernames leaked by Noob's SMB share finds
    # the foothold (AS-REP Roasting was dropped after a spike confirmed
    # Samba's KDC always enforces pre-auth); the authenticated LDAPS
    # bind then reads Administrator's own description attribute (a
    # default AD ACL) for the remaining flags.
    "domainzero-intermediate-domainedge": BoxCatalogEntry(
        "domainzero-intermediate-domainedge", "Domain Edge", "intermediate",
        ((445, "smb"), (139, "smb"), (389, "ldap"), (636, "ldaps"), (88, "kerberos"),
         (464, "kpasswd"), (53, "dns"), (135, "rpc"), (3268, "gc"), (3269, "gc-ssl")), 10,
    ),
    # Intermediate tier of Cloudbreak Pipeline: a real SSRF vulnerability
    # pivoted to a fake cloud instance metadata service (IMDS) to steal
    # temporary credentials, then a fake Secrets Manager to recover an
    # SSH credential. Distinct objective from intermediate-portside's
    # own SSRF (which targets an internal diagnostics API, not cloud
    # credentials).
    "cloudbreak-intermediate-metadata": BoxCatalogEntry(
        "cloudbreak-intermediate-metadata", "Metadata", "intermediate",
        ((5000, "http"), (22, "ssh")), 10,
    ),
    # Veteran tier of Cloudbreak Pipeline: Docker image layer
    # archaeology. A secret added in an early build layer, then
    # "deleted" in a later layer via a real OCI/OverlayFS whiteout
    # marker, is still fully recoverable from the early layer's own
    # tarball directory.
    "cloudbreak-veteran-layers": BoxCatalogEntry(
        "cloudbreak-veteran-layers", "Layers", "veteran",
        ((5000, "http"), (22, "ssh")), 10,
    ),
}

# God is each game's final/hardest capstone, Legendary one step below it
# -- confirmed explicitly by the user, not the order the original 8
# Halcyon boxes happened to be *built* in. Swapped from the original
# ["...", "god", "legendary", ...] (which predates that confirmation) so
# every game's display order is consistent, including Halcyon Protocol's
# own existing legendary-ferrymans-relay/god-the-ferryman pair.
TIER_ORDER = ["noob", "beginner", "intermediate", "veteran", "master", "expert", "legendary", "god", "bonus"]


def is_known_box_id(box_id: str) -> bool:
    return box_id in BOXES


def box_ids_sorted_by_tier() -> list[str]:
    return sorted(BOXES, key=lambda b: TIER_ORDER.index(BOXES[b].tier))
