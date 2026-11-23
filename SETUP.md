# Setup Guide — ctf-platform

## 0. What you're setting up

`ctf-platform` is the player- and admin-facing side of a CTF event:
team self-registration, games/challenges, flag submission, the live
scoreboard, and an admin dashboard. It never touches Docker directly --
it talks over plain HTTP to a sibling service,
[`ctf-orchestrator`](https://github.com/A3lxq/CTF-orchestrator), which
owns actually provisioning each team's per-box container instances.
You don't need to understand or even clone that repo yourself for
either setup path below -- both handle it for you.

Two ways to get both services running, pick whichever fits:

| | Option A: Docker | Option B: Native script |
|---|---|---|
| What you need installed | Docker + Compose, **Linux** | Python 3.11+, git, Docker |
| What it does | Builds + runs both services as containers, both on `network_mode: host` | Clones the orchestrator repo as a sibling, sets up two venvs, runs both as background processes |
| Good for | Most people, a fresh Linux VPS | Already have a Python workflow, don't want the orchestrator container holding real `docker.sock` access, or aren't on Linux |

**Why `network_mode: host`, and why Option A is Linux-only**: the
orchestrator's own readiness check connects to each new box instance's
published port to confirm it's actually answering before calling it
"running" -- on the default bridge network, the orchestrator
container's own `127.0.0.1` is itself, not the real host, so every box
instance (a sibling container on the real host daemon, created via the
socket mount) would be unreachable from inside it and every single
provision would fail. Host networking makes the container's network
stack identical to the real host's, exactly matching how this same code
already behaves when run natively. Docker Desktop (Mac/Windows) doesn't
support true host networking the same way Linux does -- use Option B on
those platforms.

Both generate random admin credentials and a session secret for you on
first run, build every box image, start both services, and print a URL
+ login when they're ready. Neither needs you to separately clone
`ctf-orchestrator` -- Option A builds it straight from its own GitHub
repo as a Docker build context; Option B clones it as a sibling
directory automatically.

## 1a. Option A: Docker

```bash
git clone https://github.com/A3lxq/ctf-platform.git
cd ctf-platform
./scripts/start-compose.sh
```

First run builds everything (including all 8 box images) and can take
several minutes. Rerunning is fast -- it reuses the Docker build cache
and the same generated credentials. Stop everything with
`docker compose down` (your data stays in the named volumes; add `-v`
to also wipe it).

**What this grants the orchestrator container**: the real host's
`/var/run/docker.sock`, bind-mounted in. Every container it creates
(box instances, Legendary's nested Docker daemons) lands on your real
host's Docker daemon, not inside the container -- `docker ps` on the
host will show them. This is effectively root-equivalent host access
for that one container, the same trade-off any Docker-in-Docker CI
runner already accepts. If that's not a trade-off you want to make,
use Option B instead.

## 1b. Option B: native script

```bash
git clone https://github.com/A3lxq/ctf-platform.git
cd ctf-platform
./scripts/quickstart.sh
```

This clones `ctf-orchestrator` as `../ctf-orchestrator` (a sibling of
this repo) if it isn't already there, sets up a venv for each, builds
every box image, and starts both as background processes. Stop
everything with `./scripts/stop.sh`.

## 1c. Firewall: open the box instance port range

Either setup path binds each player's box instance directly on this
host's network interface, in the range `ORCHESTRATOR_PORT_POOL_START`-
`ORCHESTRATOR_PORT_POOL_END` (default **20000-29999**) -- this happens
the same way whether the orchestrator itself is containerized or
native, and is **not** something Docker Compose's own port publishing
controls (box containers are created directly on the real host daemon,
each with its own `-p` binding, independent of whatever the orchestrator
service itself declares). If this host has a firewall, open that range:

```bash
sudo ufw allow 20000:29999/tcp   # or your firewall's equivalent
```

## 2. The one setting you must get right: the public address

Both scripts try to auto-detect this host's public IP (`curl
ifconfig.me`) and fall back to `127.0.0.1` with a warning if that
fails. **If players will connect from anywhere other than this exact
machine, make sure it's actually set correctly** -- Option A in
`.env`'s `PUBLIC_ADDRESS`, Option B in `.quickstart-secrets`'s
`PUBLIC_ADDRESS` -- then rerun the script. Getting this wrong doesn't
error anywhere obvious: every player's browser just silently tries to
reach their own box instance at *their own* localhost instead of your
server, breaking every single box connection at once.

## 3. First login

Both scripts print the admin username/password once, at the end of a
successful run, and again on every rerun (same credentials, read back
from the saved secrets file / `.env`). Log in at `http://<your
address>:9200/admin/login`, create a game, add a challenge or two, hit
Start. Players register themselves at `/register` -- no invite or
approval step, by design (see the main project history for why).

## 4. (Optional) Persistent production hosting with systemd

The quickstart scripts above are meant for "try it" / "demo it" --
background processes tied to your shell session (Option B) or a
Compose stack you manage by hand. For a VPS you want to keep running
after you log out:

- **Docker path**: `docker compose up -d` already runs detached and
  each service has `restart: unless-stopped` -- enabling Docker itself
  to start on boot (`sudo systemctl enable docker`) is enough.
- **Native path**: install the two systemd unit templates, one per
  repo -- `ctf-orchestrator/deploy/ctf-orchestrator.service` and
  `ctf-platform/deploy/ctf-platform.service`. Each has `<USER>` and
  path placeholders to fill in, plus a `deploy.env` file you create
  yourself (same variables `.quickstart-secrets` already generated for
  you -- copy them over). Then:
  ```bash
  sudo cp ctf-orchestrator/deploy/ctf-orchestrator.service /etc/systemd/system/
  sudo cp ctf-platform/deploy/ctf-platform.service /etc/systemd/system/
  sudo systemctl daemon-reload
  sudo systemctl enable --now ctf-orchestrator ctf-platform
  ```
  A real public deployment also wants a reverse proxy (nginx/Caddy)
  terminating TLS in front of port 9200, and the box instance port
  range (default 20000-29999) open in your firewall for direct player
  connections -- both outside the scope of these two unit files.

## 5. Running the test suites

See `tests/` -- `test_phase_a_core.py` through `test_phase_c_scoreboard_admin.py`
need a running `ctf-platform` instance (`PLATFORM_TEST_URL`, default
`http://127.0.0.1:9200`); `test_phase_b_orchestrator_integration.py`
additionally needs a real orchestrator with `noob-orientation-server`
built. All of them register real teams -- bump
`PLATFORM_REGISTER_RATE_LIMIT_MAX_ATTEMPTS` if running them repeatedly
against the same server within a few minutes (the default anti-abuse
rate limit is 5 registrations per 10 minutes per IP, and the test
suites' own registrations count against it same as any real one).

## Resetting between runs

```bash
# Docker path
docker compose down -v   # -v also wipes the named volumes (both DBs + uploaded images)

# Native path
./scripts/stop.sh
rm -f platform.db ../ctf-orchestrator/orchestrator.db
rm -f .quickstart-secrets   # also forces fresh admin credentials next run
```

## Something went wrong

- **"ctf-platform did not come up" / "orchestrator did not come up"**:
  check `.quickstart-orchestrator.log` / `.quickstart-platform.log`
  (native) or `docker compose logs` (Docker) for the actual error.
- **Every box connection fails for players but works for you**: almost
  always the public-address setting above.
- **`docker compose up` build fails pulling from GitHub**: the
  orchestrator image builds directly from
  `https://github.com/A3lxq/CTF-orchestrator.git#master` as a live git
  context -- needs outbound HTTPS access to github.com from wherever
  you're running `docker compose build`, and the orchestrator repo's
  own `Dockerfile` present on that branch.
- Anything box-specific (stale containers, disk space,
  `docker:27-dind-rootless` failing) -- see
  `ctf-orchestrator/SETUP.md`'s own Troubleshooting section, which this
  platform inherits unchanged since it's the same underlying boxes.
