"""
release.py — Bump version, push to GitHub, and update Supabase in one command.

Usage:
    python scripts/release.py          # bumps patch  (2.0.0 → 2.0.1)
    python scripts/release.py minor    # bumps minor  (2.0.1 → 2.1.0)
    python scripts/release.py major    # bumps major  (2.1.0 → 3.0.0)
"""

import re
import sys
import subprocess
from pathlib import Path

from supabase import create_client

# ── Config ────────────────────────────────────────────────────────────────────
CONSTANTS_FILE = Path(__file__).parent.parent / "modules" / "constants.py"
BUMP_TYPE = sys.argv[1].lower() if len(sys.argv) > 1 else "patch"

# ── Read current version ───────────────────────────────────────────────────────
text = CONSTANTS_FILE.read_text(encoding="utf-8")
m = re.search(r'APP_VERSION\s*=\s*["\']([^"\']+)["\']', text)
if not m:
    print("ERROR: Could not find APP_VERSION in constants.py")
    sys.exit(1)

current = m.group(1).lstrip("v")
parts = current.split(".")
if len(parts) != 3:
    print(f"ERROR: APP_VERSION '{current}' is not semver (X.Y.Z)")
    sys.exit(1)

major, minor, patch = int(parts[0]), int(parts[1]), int(parts[2])

if BUMP_TYPE == "major":
    major += 1; minor = 0; patch = 0
elif BUMP_TYPE == "minor":
    minor += 1; patch = 0
else:
    patch += 1

new_version = f"{major}.{minor}.{patch}"
print(f"Bumping {current} → {new_version} ({BUMP_TYPE})")

# ── Write new version to constants.py ─────────────────────────────────────────
new_text = re.sub(
    r'(APP_VERSION\s*=\s*["\'])[^"\']+(["\'])',
    lambda mo: f'{mo.group(1)}{new_version}{mo.group(2)}',
    text,
)
CONSTANTS_FILE.write_text(new_text, encoding="utf-8")
print(f"  ✓ constants.py updated")

# ── Git commit & push (rebase workflow) ───────────────────────────────────────
root = CONSTANTS_FILE.parent.parent

def run(cmd, allow_fail=False):
    r = subprocess.run(cmd, cwd=root, capture_output=True, text=True)
    if r.returncode != 0 and not allow_fail:
        print(f"ERROR running {' '.join(cmd)}:\n{r.stderr.strip()}")
        sys.exit(1)
    return r

# 1. Stage your module updates AND the version bump
run(["git", "add", "."])
run(["git", "commit", "-m", f"release: v{new_version} (includes module updates)"])
print(f"  ✓ Committed version bump and module updates")

# 2. Fetch latest from remote
run(["git", "fetch", "origin"])
print(f"  ✓ Fetched origin")

# 3. Rebase our commit on top of whatever they pushed
r = run(["git", "rebase", "origin/main"], allow_fail=True)
if r.returncode != 0:
    # Rebase hit a conflict — abort and report cleanly
    run(["git", "rebase", "--abort"], allow_fail=True)
    print(
        "\nREBASE CONFLICT — your teammate pushed changes that clash.\n"
        "Run these steps manually:\n"
        "  git fetch origin\n"
        "  git rebase origin/main\n"
        "  # resolve conflicts, then:\n"
        "  git rebase --continue\n"
        "  git push\n"
        f"\nRemember to set app_config.latest_version = '{new_version}' in Supabase once pushed."
    )
    sys.exit(1)
print(f"  ✓ Rebased on origin/main")

# 4. Push
run(["git", "push"])
print(f"  ✓ Pushed to GitHub")

# ── Update Supabase app_config ─────────────────────────────────────────────────
# Reads secrets from .streamlit/secrets.toml in the project root
import tomllib
secrets_path = root / ".streamlit" / "secrets.toml"
if not secrets_path.exists():
    print("WARNING: .streamlit/secrets.toml not found — Supabase NOT updated.")
    print(f"  Manually set app_config.latest_version = '{new_version}' in Supabase.")
    sys.exit(0)

with open(secrets_path, "rb") as f:
    secrets = tomllib.load(f)

url = secrets.get("SUPABASE_URL")
key = secrets.get("SUPABASE_KEY")
if not url or not key:
    print("WARNING: SUPABASE_URL / SUPABASE_KEY missing in secrets.toml — Supabase NOT updated.")
    sys.exit(0)

sb = create_client(url, key)
# Upsert so it works even if the row doesn't exist yet
sb.table("app_config").upsert({"key": "latest_version", "value": new_version}).execute()
print(f"  ✓ Supabase app_config.latest_version = '{new_version}'")

print(f"\nRelease v{new_version} complete.")
