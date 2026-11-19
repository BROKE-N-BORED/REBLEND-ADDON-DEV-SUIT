#!/usr/bin/env bash
# Reblend Add-on Dev Suite installer — terminal fallback.
# The normal path is the double-click GUI installer: extract the
# release, then double-click "Install Reblend Add-on Dev Suite".
# This script runs the same steps (installer/install.py) for a
# terminal, and takes the same options:
#     bash install.sh [--install-dir DIR] [--applications-dir DIR]
#                     [--tmpdir DIR] [--source-dir DIR]
# BASH, never sh: this script uses `set -euo pipefail` (AGENTS.md).
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Exec bits — a fresh clone has every file 100644 (the GitHub push
# path can't set file modes), so fix the scripts' bits here. The
# Release zip already carries 0o100755 for these; this only matters
# for clones. Never fatal: the tree may be read-only.
chmod +x "$DIR/install.sh" "$DIR/uninstall.sh" "$DIR/run.sh" "$DIR/Install Reblend Add-on Dev Suite.desktop" 2>/dev/null || true

if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 is not installed. Install it first, then re-run this."
  exit 1
fi

exec python3 "$DIR/installer/install.py" "$@"
