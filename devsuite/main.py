"""Start the suite: open the chat window (Phase 2b).

The chat window is the first window; the other windows join in
later items. Run from the project root:

    python3 -m devsuite.main

After the window shows, the silent update check starts
(``devsuite.update``): it asks GitHub for a newer Release in a
worker thread, so the window is already open and usable while
the check runs. Up to date, unreachable, or no repo yet is
silence. ``DEVSUITE_NO_UPDATE_CHECK=1`` skips it — the
installer's smoke check sets it, so verifying an install never
starts an update check of its own.
"""

from __future__ import annotations

import os
import sys

from PySide6.QtWidgets import QApplication

from devsuite.ui.chat_window import ChatWindow


def main() -> int:
    app = QApplication(sys.argv)
    window = ChatWindow()
    window.show()
    if not os.environ.get("DEVSUITE_NO_UPDATE_CHECK"):
        window.start_update_check()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
