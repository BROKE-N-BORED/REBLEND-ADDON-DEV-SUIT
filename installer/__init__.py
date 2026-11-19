"""The suite's own installer (DOSSIER.md §9.1, §12 Phase 6, §13).

This is the installer for the Dev Suite itself — not the pack
installer in ``devsuite.packing`` (that one installs packs into
Reblend and Blender; this one installs the suite onto a PC).

The shape is the BNB release shape (AGENTS.md, MIMIK's proven
installer): double-click ``Install Reblend Add-on Dev Suite.desktop``
in the extracted release folder, and the suite installs with no
terminal. The .desktop file finds the release folder with the
``python3 -c ... %k`` pattern and starts the tkinter installer
window (``installer.gui``); ``install.sh`` is the terminal fallback
for the same steps.

What the install does, in order (``installer.install``): check the
machine can install (python3 + venv), make a private venv in the
install folder, pip-install the suite from the release tree into
it, write the menu launcher, and verify the install works before
reporting success — the package check is fatal, the GUI smoke
check is a warning naming the missing system library (the MIMIK
v0.1.x lesson: a GUI app must never report success when its
toolkit is missing).

The uninstaller (``installer.uninstall``) removes what the
installer put there — the install folder and the menu launcher —
and, only when asked, the app data (the library shelf and the
remembered settings). It never touches projects, and a removal
that fails partway says what is left and how to remove it by hand
(DOSSIER.md §13: "uninstall leaves nothing behind"). The
installer window's Uninstall button opens it; ``uninstall.sh`` is
the terminal front end, confirming first with the default No.

Two boundaries, stated here so they are not forgotten:

* The menu launcher bakes the app dir in at install (DOSSIER.md
  U4 — the ``%k`` pattern is not used for the app launcher; it is
  only how the *installer* launcher finds the release folder).
* The .desktop file carries no Icon line yet: the icon is designed
  with Joshua (Phase 6), and the installer invents no placeholder
  art. When the icon exists, the launcher gains an Icon line and
  the install copies the icon files in (non-fatal, the MIMIK way).

First double-click note: a freshly extracted .desktop file may
need a right-click, then Allow Launching, before the file manager
trusts it — that is the file manager's doing, not the installer's,
and it only happens once.
"""
