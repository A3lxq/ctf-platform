import os

DATABASE_URL = os.environ.get("PLATFORM_DATABASE_URL", "sqlite:///./platform.db")

# Where the orchestrator (ctf-orchestrator) is reachable. Never exposed
# publicly itself -- only this platform's own backend talks to it, same
# relationship GZCTF's BoxOrchestratorClient had.
ORCHESTRATOR_URL = os.environ.get("PLATFORM_ORCHESTRATOR_URL", "http://127.0.0.1:9100")
ORCHESTRATOR_AUTH_TOKEN = os.environ.get("PLATFORM_ORCHESTRATOR_AUTH_TOKEN")  # None = no auth header sent

SESSION_SECRET = os.environ.get("PLATFORM_SESSION_SECRET", "dev-only-insecure-secret-change-me")
SESSION_COOKIE_NAME = "ctf_platform_session"

# First admin account, bootstrapped at startup if the Admin table is
# empty -- no public admin-registration endpoint exists anywhere.
ADMIN_BOOTSTRAP_USERNAME = os.environ.get("PLATFORM_ADMIN_USERNAME")
ADMIN_BOOTSTRAP_PASSWORD = os.environ.get("PLATFORM_ADMIN_PASSWORD")

# Anti-abuse on team self-registration (see api/auth.py) -- zero-cost,
# no paid CAPTCHA service, no budget for one.
REGISTER_MIN_FILL_SECONDS = float(os.environ.get("PLATFORM_REGISTER_MIN_FILL_SECONDS", "2.0"))
REGISTER_RATE_LIMIT_MAX_ATTEMPTS = int(os.environ.get("PLATFORM_REGISTER_RATE_LIMIT_MAX_ATTEMPTS", "5"))
REGISTER_RATE_LIMIT_WINDOW_SECONDS = int(os.environ.get("PLATFORM_REGISTER_RATE_LIMIT_WINDOW_SECONDS", "600"))

PBKDF2_ITERATIONS = int(os.environ.get("PLATFORM_PBKDF2_ITERATIONS", "310000"))

DEFAULT_INSTANCE_TTL_MINUTES = int(os.environ.get("PLATFORM_DEFAULT_INSTANCE_TTL_MINUTES", "120"))

# How often the background sweep (reconciliation.py) re-syncs every
# non-DESTROYED TeamInstance against the orchestrator's own authoritative
# state -- catches an instance the orchestrator's own reaper destroyed
# for expiring, independently of this platform ever being told. Same
# role as the orchestrator's own REAPER_INTERVAL_SECONDS.
RECONCILIATION_INTERVAL_SECONDS = int(os.environ.get("PLATFORM_RECONCILIATION_INTERVAL_SECONDS", "60"))
