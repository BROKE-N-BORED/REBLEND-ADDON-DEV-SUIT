#!/usr/bin/env bash
# Launch the Reblend Add-on Dev Suite — the tree launcher
# (DOSSIER.md §9.1). The normal path is the menu entry the
# installer writes; this script is for the extracted tree.
# It runs the installed suite when there is one, and the tree's
# own copy otherwise. BASH, never sh (AGENTS.md).
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALLED="$HOME/.local/share/reblend-addon-dev-suite/venv/bin/devsuite"

if [ -x "$INSTALLED" ]; then
  exec "$INSTALLED"
fi

if [ -f "$DIR/devsuite/main.py" ]; then
  if python3 -c "import PySide6" 2>/dev/null; then
    cd "$DIR"
    exec python3 -m devsuite.main
  fi
  echo "PySide6 is not installed for this Python, so the suite cannot start from the tree."
  echo "Double-click Install Reblend Add-on Dev Suite to install it properly."
  exit 1
fi

echo "The suite is not installed yet. Double-click Install Reblend Add-on Dev Suite first."
exit 1
