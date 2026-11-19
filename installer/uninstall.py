"""Uninstall the suite from a PC: remove what the installer put there.

Headless and stdlib only — the tkinter window (``installer.gui``,
the Uninstall button) and ``uninstall.sh`` are thin front ends
over ``uninstall()``, so the steps can never drift apart.

What the uninstall removes, and nothing else (DOSSIER.md §13:
"uninstall leaves nothing behind"):

1. The install folder (the private venv and everything in it).
2. The menu launchers (``.desktop``) from the applications
   folder — the app entry and the Uninstall entry.
3. Only when asked (``remove_app_data=True``): the app data — the
   library shelf and its folder, and the suite's remembered
   settings file. The default keeps them: a reinstall finds the
   shelf and the remembered folders waiting (U6, and destructive
   choices default to keeping).

What it never touches: projects (they live wherever Joshua put
them, outside the install folder), and anything outside the three
scopes above. The organization folders (``Broke n Bored`` under
``.local/share`` and ``.config``) are removed only when they are
empty afterwards — other BNB apps may share them.

An install counts as present when the install folder exists, the
install record (``install-info.json``) exists, or either menu
launcher exists. When none of those exist, there is nothing to
uninstall: the call says so plainly and removes nothing. A stale
launcher with no install folder behind it is still removed — that
is the "nothing behind" case, and leaving the menu entry would
break it. Either launcher alone counts: the Uninstall entry
surviving on its own is still cleaned up.

A removal that fails partway is reported, not hidden: the result
names what was removed, what is still there, and how to remove the
leftovers by hand. Read-only files and folders inside the install
do not strand an uninstall — the removal makes the failing path
(and its parent, when the parent is inside the tree) writable and
retries. It only ever chmods paths inside the folder being
removed, never the folder's own parent: a read-only parent is a
real leftover, and the uninstaller says so instead of forcing it.

Everything returns plain words: ``uninstall()`` returns
``(ok, message)`` and never raises on a bad input or a failed
step. ``progress`` is an optional callable taking one string, run
on the calling thread as each step starts. There is no cancel:
an uninstall is seconds of file deletion, and a half-removed
install is worse than a finished one.

The app-data paths are computed by hand here, the way
``devsuite.library.shelf`` computes the shelf path — this module
cannot import the suite (the suite lives in the venv being
removed). The settings path is the Linux location QSettings
writes for organization "Broke n Bored", application "Reblend
Add-on Dev Suite" (verified against ``QSettings.fileName()`` in
the sandbox, 2026-11-17). Tests pass explicit paths instead
(``shelf_path`` / ``settings_path``), so they never touch the
real home.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import stat
import subprocess
from pathlib import Path

from installer.install import (
    APP_NAME,
    DESKTOP_FILENAME,
    UNINSTALL_DESKTOP_FILENAME,
    default_applications_dir,
    default_install_dir,
)

#: The install record the installer leaves in the install folder.
INFO_FILENAME = "install-info.json"

#: The organization and application names the suite's QSettings
#: and shelf use (devsuite/library/shelf.py, devsuite/ui/*).
ORGANIZATION = "Broke n Bored"
APPLICATION = "Reblend Add-on Dev Suite"


def default_shelf_path() -> Path:
    """Where the library shelf lives (mirrors
    ``devsuite.library.shelf.default_shelf_path`` — computed by
    hand here because this module cannot import the suite)."""
    return (
        Path.home()
        / ".local"
        / "share"
        / ORGANIZATION
        / APPLICATION
        / "shelf.json"
    )


def default_settings_path() -> Path:
    """Where the suite's remembered settings live: the file
    QSettings writes for this organization and application on
    Linux."""
    return (
        Path.home()
        / ".config"
        / ORGANIZATION
        / f"{APPLICATION}.conf"
    )


def find_install(install_dir=None, applications_dir=None):
    """What of the install is present.

    Returns a dict: ``install_dir`` (the folder, or None when it
    does not exist), ``record`` (the install record's contents, or
    None), ``launcher`` (the app menu launcher's path, or None
    when it does not exist), ``uninstall_launcher`` (the
    Uninstall menu launcher's path, or None). Never raises.
    """
    target = Path(install_dir) if install_dir is not None \
        else default_install_dir()
    apps = Path(applications_dir) if applications_dir is not None \
        else default_applications_dir()
    found = {
        "install_dir": target if target.exists() else None,
        "record": None,
        "launcher": None,
        "uninstall_launcher": None,
    }
    record_path = target / INFO_FILENAME
    if record_path.is_file():
        try:
            found["record"] = json.loads(
                record_path.read_text(encoding="utf-8")
            )
        except (OSError, ValueError):
            # A damaged record still counts as an install present;
            # the uninstall does not need to read it.
            found["record"] = {}
    launcher = apps / DESKTOP_FILENAME
    if launcher.exists():
        found["launcher"] = launcher
    uninstall_launcher = apps / UNINSTALL_DESKTOP_FILENAME
    if uninstall_launcher.exists():
        found["uninstall_launcher"] = uninstall_launcher
    return found


def _is_safe_to_remove(target: Path) -> bool:
    """True when ``target`` is safe to delete as an install
    folder: it must not be the home folder itself, or an ancestor
    of it. A custom install folder is fine; deleting home is not.
    """
    try:
        resolved = target.resolve()
        home = Path.home().resolve()
    except OSError:
        return False
    # Refuse home itself, and any ancestor of home (a folder home
    # sits under): removing one of those would take home with it.
    return resolved != home and resolved not in home.parents


def _remove_tree(path: Path) -> bool:
    """Remove a file, a symlink, or a whole folder tree. Returns
    True when the path is gone afterwards. Never raises.

    A read-only file or folder inside the tree does not stop the
    removal: the error handler makes the failing path — and its
    parent, when the parent is inside the tree — writable and
    retries once. Deleting a file needs write permission on its
    folder, not on the file, so chmodding the file alone never
    helps; the parent is what matters. The tree's own parent is
    never chmodded: when it is read-only, the top folder stays
    and the caller reports it as a leftover.
    """
    root = path

    def _chmod_and_retry(func, failed, exc_info):
        for candidate in (failed, os.path.dirname(failed)):
            try:
                candidate_path = Path(candidate)
                if (candidate_path == root
                        or root in candidate_path.parents):
                    os.chmod(candidate_path, stat.S_IRWXU)
            except OSError:
                pass
        try:
            func(failed)
        except OSError:
            pass

    try:
        if path.is_symlink() or path.is_file():
            path.unlink()
        elif path.is_dir():
            shutil.rmtree(path, onerror=_chmod_and_retry)
        else:
            return True  # Nothing there to remove.
    except OSError:
        pass
    return not path.exists() and not path.is_symlink()


def _remove_dir_if_empty(path: Path) -> None:
    """Remove a folder when it is empty afterwards — the shared
    organization folders go only when no other app uses them.
    Never raises."""
    try:
        path.rmdir()
    except OSError:
        pass


def uninstall(install_dir=None, applications_dir=None,
              remove_app_data=False, progress=None,
              shelf_path=None, settings_path=None) -> tuple[bool, str]:
    """Uninstall the suite.

    ``install_dir`` defaults to the installer's
    ``default_install_dir()``; ``applications_dir`` to its
    ``default_applications_dir()``. ``remove_app_data`` also
    removes the library shelf and the remembered settings file
    (default False — the data stays unless Joshua opts in).
    ``shelf_path`` / ``settings_path`` override the app-data
    locations (tests pass temp paths; the suite itself always
    uses the defaults). ``progress`` is called with one
    plain-words string as each step starts.

    Returns ``(ok, message)``: ``ok`` is True only when everything
    asked for is gone; ``message`` names each thing removed, or —
    when something could not be removed — what is still there and
    how to remove it by hand. Never raises.
    """
    def say(text):
        if progress is not None:
            try:
                progress(text)
            except Exception:
                pass

    try:
        return _uninstall(
            install_dir, applications_dir, remove_app_data, say,
            shelf_path, settings_path,
        )
    except Exception:
        # A bad input must never crash the uninstaller. Anything
        # unexpected lands here as one sentence.
        return False, (
            "I could not uninstall the suite. The install folder "
            "may not be readable. Check it exists and can be "
            "read, then run the uninstaller again."
        )


def _uninstall(install_dir, applications_dir, remove_app_data, say,
               shelf_path, settings_path):
    target = Path(install_dir) if install_dir is not None \
        else default_install_dir()
    apps = Path(applications_dir) if applications_dir is not None \
        else default_applications_dir()
    shelf = Path(shelf_path) if shelf_path is not None \
        else default_shelf_path()
    settings = Path(settings_path) if settings_path is not None \
        else default_settings_path()
    found = find_install(target, apps)

    if (found["install_dir"] is None
            and found["record"] is None
            and found["launcher"] is None
            and found["uninstall_launcher"] is None):
        return False, (
            "The suite is not installed, so there is nothing to "
            "uninstall. If it was installed somewhere else, run "
            "the uninstaller with that install folder."
        )

    if found["install_dir"] is not None and not _is_safe_to_remove(target):
        return False, (
            "I will not remove this install folder, because it is "
            f"your home folder or above it: {target}. Remove it by "
            "hand if that is really what you want."
        )

    removed: list[str] = []
    left: list[str] = []

    # 1. The install folder (the venv and everything in it).
    if found["install_dir"] is not None:
        say("Removing the suite's folder...")
        if _remove_tree(target):
            removed.append(f"the suite's folder ({target})")
        else:
            left.append(str(target))

    # 2. The menu launchers (the app entry and the Uninstall entry).
    launchers = []
    if found["launcher"] is not None:
        launchers.append((found["launcher"], "the menu entry"))
    if found["uninstall_launcher"] is not None:
        launchers.append(
            (found["uninstall_launcher"], "the uninstall menu entry")
        )
    if launchers:
        say("Removing the menu entries...")
        for launcher, label in launchers:
            if _remove_tree(launcher):
                removed.append(f"{label} ({launcher})")
            else:
                left.append(str(launcher))
        if shutil.which("update-desktop-database"):
            try:
                subprocess.run(
                    ["update-desktop-database", str(apps)],
                    capture_output=True, timeout=60,
                )
            except OSError:
                pass  # Best effort, as in the installer.

    # 3. The app data, only when asked.
    if remove_app_data:
        say("Removing the suite's saved data...")
        shelf_folder = shelf.parent
        if shelf.exists() or shelf_folder.is_dir():
            if _remove_tree(shelf_folder):
                removed.append(
                    f"the library shelf ({shelf_folder})"
                )
            else:
                left.append(str(shelf_folder))
            _remove_dir_if_empty(shelf_folder.parent)
        if settings.exists():
            if _remove_tree(settings):
                removed.append(
                    f"the remembered settings ({settings})"
                )
            else:
                left.append(str(settings))
            _remove_dir_if_empty(settings.parent)

    if not left:
        lines = ["Uninstalled. Removed:"]
        lines.extend(f"  - {item}" for item in removed)
        if not remove_app_data:
            lines.append(
                "The library shelf and remembered settings were "
                "kept, so a reinstall finds them waiting. Run the "
                "uninstaller with app data removal to remove "
                "them too."
            )
        return True, "\n".join(lines)

    # Something is still there: say what, and how to remove it.
    lines = ["The uninstall could not finish. Removed:"]
    lines.extend(f"  - {item}" for item in removed)
    lines.append("Still there:")
    lines.extend(f"  - {item}" for item in left)
    lines.append(
        "Remove what is left by hand: delete the folder or file "
        "above, or run this in a terminal for each one:"
    )
    for item in left:
        lines.append(f"  rm -rf {item}")
    return False, "\n".join(lines)


def main(argv=None) -> int:
    """The terminal front end (``uninstall.sh`` calls this):
    uninstall, printing plain-words progress, exit 0 when
    everything asked for is gone, exit 1 otherwise. No
    confirmation here — the front ends (the shell script, the
    GUI) ask before calling."""
    parser = argparse.ArgumentParser(
        description="Uninstall the Reblend Add-on Dev Suite.",
    )
    parser.add_argument(
        "--install-dir", default=None,
        help="the install folder "
        f"(default: {default_install_dir()})",
    )
    parser.add_argument(
        "--applications-dir", default=None,
        help="where the menu entry lives "
        f"(default: {default_applications_dir()})",
    )
    parser.add_argument(
        "--remove-app-data", action="store_true",
        help="also remove the library shelf and the remembered "
        "settings file (default: keep them)",
    )
    args = parser.parse_args(argv)

    def say(text):
        print(text, flush=True)

    ok, message = uninstall(
        install_dir=args.install_dir,
        applications_dir=args.applications_dir,
        remove_app_data=args.remove_app_data,
        progress=say,
    )
    print()
    print(message)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
