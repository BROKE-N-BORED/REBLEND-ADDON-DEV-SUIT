#!/usr/bin/env bash
# Reblend Add-on Dev Suite uninstaller — terminal front end.
# The GUI path is the Install window's Uninstall button. This
# script runs the same steps (installer/uninstall.py) for a
# terminal, and takes the same options:
#     bash uninstall.sh [--install-dir DIR] [--applications-dir DIR]
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

# Confirmation first, defaulting to No (U23/U31): uninstalling is
# destructive, and an empty answer means no.
echo "This uninstalls the Reblend Add-on Dev Suite: its folder and"
echo "its menu entry are removed."
read -r -p "Uninstall the suite? [y/N] " answer
case "$answer" in
  y|Y|yes|YES) ;;
  *)
    echo "Nothing was uninstalled."
    exit 0
    ;;
esac

# The saved data (the library shelf and the remembered settings)
# stays unless Joshua opts in: an empty answer keeps it.
read -r -p "Also remove the library shelf and remembered settings? [y/N] " data_answer
args=()
case "$data_answer" in
  y|Y|yes|YES) args+=(--remove-app-data) ;;
esac

exec python3 "$DIR/installer/uninstall.py" "${args[@]}" "$@"
