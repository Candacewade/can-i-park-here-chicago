"""Central configuration.

Every knob the app needs lives here so the rest of the code never reads os.environ
directly. Defaults are chosen so the project runs with zero configuration.
"""

from __future__ import annotations

import glob
import os
import shutil
from pathlib import Path
from zoneinfo import ZoneInfo

# --- Geography / time -------------------------------------------------------

CHICAGO_TZ = ZoneInfo("America/Chicago")

# --- Authoritative data source --------------------------------------------

# City of Chicago Open Data Portal (Socrata / SODA). Public, free, no key required.
# A Socrata app token raises rate limits but is optional; we read it if present.
SOCRATA_DOMAIN = os.environ.get("SOCRATA_DOMAIN", "data.cityofchicago.org")
SOCRATA_APP_TOKEN = os.environ.get("SOCRATA_APP_TOKEN") or None

# Per-request HTTP timeout (seconds) when talking to the City portal.
SOCRATA_TIMEOUT_SECONDS = float(os.environ.get("SOCRATA_TIMEOUT_SECONDS", "10"))

# Dataset identifiers (Socrata "4x4" ids). Documented in docs/data-sources.md.
DATASET_RESIDENTIAL_ZONES = "qiag-khha"   # Permit Parking Zones (street segments)
DATASET_STREET_SWEEPING = "u5ai-3efk"     # Street Sweeping Schedule - 2026

# --- Runtime AI agent ----------------------------------------------------

# The runtime agent uses the Claude Agent SDK, authenticated through the local
# Claude subscription (the Claude Code CLI credentials) -- NOT a paid API key.
# See docs/agent-design.md. We deliberately do not read ANTHROPIC_API_KEY here.
AGENT_MODEL = os.environ.get("AGENT_MODEL", "claude-sonnet-4-5")


def resolve_claude_cli() -> str | None:
    """Locate the Claude Code CLI the Agent SDK shells out to for subscription auth.

    Order: explicit env var, then PATH, then the binary bundled with the VS Code /
    JetBrains extension. Returns None if not found (caller surfaces a clear error).
    """
    explicit = os.environ.get("CLAUDE_CODE_CLI_PATH")
    if explicit and Path(explicit).exists():
        return explicit
    on_path = shutil.which("claude")
    if on_path:
        return on_path
    patterns = [
        os.path.expanduser("~/.vscode*/extensions/anthropic.claude-code-*/resources/native-binary/claude"),
        os.path.expanduser("~/.claude/local/claude"),
        "/usr/local/bin/claude",
    ]
    for pat in patterns:
        hits = sorted(glob.glob(pat))
        if hits:
            return hits[-1]
    return None

# --- Paths --------------------------------------------------------------

BACKEND_ROOT = Path(__file__).resolve().parent.parent
LOCATIONS_FIXTURE_PATH = BACKEND_ROOT / "app" / "locations" / "fixtures.json"
