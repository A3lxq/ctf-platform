# ctf-platform

The player- and admin-facing side of The Halcyon Protocol CTF: team
self-registration, games/challenges, flag submission, the live
scoreboard, and an admin dashboard. It never touches Docker directly —
it talks over plain HTTP to a sibling service,
[`ctf-orchestrator`](https://github.com/A3lxq/CTF-orchestrator), which
owns provisioning each team's per-box container instances.

Anyone can register a team (solo play is fine — a "team" can be one
person) and start playing immediately, no invite or approval step.

## Status

All of it works: self-registration with zero-cost anti-abuse (honeypot,
minimum-fill-time, per-IP rate limit), admin-managed games/challenges,
real orchestrator-backed instance start/renew/stop, flag verification,
a live scoreboard, an admin instances dashboard with CSV export,
game-end teardown, admin custom box upload (no restart needed), and
admin-editable event/box branding (name, description, banner images).

## Setting this up

See **[SETUP.md](SETUP.md)** — one command gets both this service and
`ctf-orchestrator` running together, either via Docker Compose or a
native script; you don't need to separately clone the orchestrator
repo either way.

## Layout

```
app/
  main.py                FastAPI app
  config.py               env-driven settings
  models.py                 Team / Admin / Game / Challenge / Submission /
                              Solve / TeamInstance / EventSettings / BoxDisplay
  security.py                 PBKDF2 password hashing, session auth
  flags.py                     independent HMAC-SHA256 flag verification
  orchestrator_client.py         HTTP client for ctf-orchestrator's API
  boxes_catalog.py                 static fallback catalog mirroring the
                                     orchestrator's own box specs
  reconciliation.py                  background sweep syncing local instance
                                       state against the orchestrator
  api/
    auth.py                 registration, team/admin login
    player.py                  challenges, instances, submissions, scoreboard
    admin.py                     games/challenges/teams/instances/boxes/settings
    public.py                      no-auth settings + box display
  services/                 business logic, called by both api/ and web/
  web/routes.py            Jinja2 page shells + the scoreboard htmx fragment
  templates/, static/     server-rendered Jinja2 + htmx + Alpine.js, no
                            build pipeline, no SPA framework
tests/
scripts/                 quickstart.sh / start-compose.sh / stop.sh
deploy/                  systemd unit template for persistent hosting
```

## Why not GZCTF

An earlier plan wired this project's boxes into GZCTF instead of
building a new platform. GZCTF (even upstream, not just a fork) pins a
version of `SixLabors.ImageSharp` that requires a paid commercial
license just to build — no free path around it. This repo is a
from-scratch replacement, borrowing GZCTF's *concepts* (teams, games,
challenges, scoreboard, admin tooling) but containing none of its code.
