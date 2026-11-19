"""Install the suite onto a PC: venv, packages, menu launcher, verify.

Headless and stdlib only — the tkinter window (``installer.gui``)
and ``install.sh`` are thin front ends over ``install()``, so the
steps can never drift apart.

The install, in order:

1. Check the machine can install: python3 with the venv tool.
   When venv is missing the failure names the fix
   (``sudo apt install python3-venv python3-pip``).
2. Make a private venv in the install folder (reused when it is
   already there, so a re-run after a cancelled or failed install
   resumes instead of starting over — U24).
3. Pip-install the suite from the release tree into the venv.
   This is the step that needs the network: the PySide6 download
   (and the setuptools build backend pip fetches). After the first
   install the suite works offline.
4. Write the menu launchers (``.desktop``) into the applications
   folder — the app entry and the Uninstall entry (the
   ``devsuite-uninstall`` console script, so the suite can be
   removed from the menu even after the release tree is deleted).
   The Exec lines bake the app dir in at install (DOSSIER.md
   U4 — the ``%k`` pattern is not used for the app launcher).
   No Icon line yet: the icon is designed with Joshua (Phase 6),
   and the installer invents no placeholder art.
5. Verify before reporting success. The package check is fatal:
   the installed distribution and PySide6 must be present, and
   the ``devsuite`` and ``installer`` packages must import (the
   installer ships inside the distribution — the Uninstall menu
   entry runs it) — when any of those fail the install has
   failed, in plain words, never a false success.
   The GUI smoke check (open the chat window briefly, offscreen)
   is a warning, not a failure: starting the GUI depends on the
   machine's system Qt libraries, which the installer cannot fix,
   so a GUI that cannot start is reported with the reason and the
   fix instead of silence (the MIMIK v0.1.x lesson).

Everything returns plain words: ``install()`` returns
``(ok, message)`` and never raises on a bad input or a failed
step. ``progress`` is an optional callable taking one string, run
on the calling thread as each step starts. ``cancelled`` is an
optional callable returning True to stop; it is checked between
steps (a step already running finishes first), and a cancelled
install reports plainly that a re-run finishes it.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from datetime import date
from pathlib import Path

#: The app's display name, as the menu entry and the installer
#: window show it.
APP_NAME = "Reblend Add-on Dev Suite"

#: The installed distribution name (pyproject.toml) and the menu
#: launcher's file name.
PACKAGE_NAME = "reblend-addon-dev-suite"
DESKTOP_FILENAME = "reblend-addon-dev-suite.desktop"

#: The Uninstall menu entry: its file name, its display name, and
#: the console script it runs (pyproject.toml [project.scripts]).
#: Same shape as the app entry — absolute Exec path baked in at
#: install, no Icon line yet.
UNINSTALL_DESKTOP_FILENAME = "reblend-addon-dev-suite-uninstall.desktop"
UNINSTALL_APP_NAME = f"Uninstall {APP_NAME}"
UNINSTALL_CONSOLE_SCRIPT = "devsuite-uninstall"

#: The console script the install creates (pyproject.toml
#: [project.scripts]).
CONSOLE_SCRIPT = "devsuite"

#: How long each step may take before it is a failure. Pip gets
#: the longest: the PySide6 download on a slow connection.
TIMEOUT_VENV = 120
TIMEOUT_PIP = 600
TIMEOUT_VERIFY = 60
TIMEOUT_GUI_SMOKE = 90

#: The GUI smoke check opens the chat window and quits after this
#: long — long enough to prove the window starts, short enough to
#: never be noticed.
GUI_SMOKE_MS = 500


def default_install_dir() -> Path:
    """Where the suite lives when no folder is picked: a private
    folder under the user's home, holding the venv."""
    return Path.home() / ".local" / "share" / PACKAGE_NAME


def default_applications_dir() -> Path:
    """Where the menu launcher goes: the user's applications
    folder, so the suite appears in the Mint menu."""
    return Path.home() / ".local" / "share" / "applications"


def build_desktop_entry(install_dir) -> str:
    """The menu launcher's text for an install in ``install_dir``.

    The Exec line is the venv's console script, as an absolute
    path baked in at install (DOSSIER.md U4). It carries no ``%k``
    and no nested quotes — GLib rejects nested escaped quotes in
    Exec lines (AGENTS.md). No Icon line: the icon is designed
    with Joshua (Phase 6), and the installer invents no
    placeholder art.
    """
    exe = Path(install_dir) / "venv" / "bin" / CONSOLE_SCRIPT
    return (
        "[Desktop Entry]\n"
        "Type=Application\n"
        f"Name={APP_NAME}\n"
        "Comment=Build add-on packs for Reblend and Blender\n"
        f"Exec={exe}\n"
        "Terminal=false\n"
        "Categories=Development;\n"
        "StartupNotify=true\n"
    )


def build_uninstall_desktop_entry(install_dir) -> str:
    """The Uninstall menu launcher's text for an install in
    ``install_dir``. Mirrors ``build_desktop_entry``: the Exec
    line is the venv's ``devsuite-uninstall`` console script, as
    an absolute path baked in at install (DOSSIER.md U4), no
    ``%k``, no nested quotes, no Icon line yet."""
    exe = Path(install_dir) / "venv" / "bin" / UNINSTALL_CONSOLE_SCRIPT
    return (
        "[Desktop Entry]\n"
        "Type=Application\n"
        f"Name={UNINSTALL_APP_NAME}\n"
        "Comment=Remove Reblend Add-on Dev Suite from this computer\n"
        f"Exec={exe}\n"
        "Terminal=false\n"
        "Categories=Development;\n"
        "StartupNotify=true\n"
    )


def _venv_python(install_dir) -> Path:
    return Path(install_dir) / "venv" / "bin" / "python"


def _last_line(output: str) -> str:
    """The last non-empty line of ``output``, for naming an error
    in one line. Empty when there is nothing to quote. The line
    ends with a period when it has no terminal punctuation of its
    own — every message that quotes it goes on to another sentence,
    and without the period the two run together ("...time limit
    Check the folder...")."""
    lines = [line for line in output.splitlines() if line.strip()]
    if not lines:
        return ""
    detail = lines[-1].strip()
    if detail[-1] not in ".!?":
        detail += "."
    return detail


def _run(cmd, env, timeout):
    """Run ``cmd`` (a list, no shell) and return
    ``(returncode, combined_output)``. A timeout or a failure to
    start comes back as ``(None, plain-words reason)``."""
    try:
        proc = subprocess.run(
            [str(part) for part in cmd],
            capture_output=True, text=True, timeout=timeout, env=env,
        )
    except subprocess.TimeoutExpired:
        return None, "the step ran past its time limit"
    except OSError as exc:
        return None, f"could not start the step ({exc})"
    return proc.returncode, (proc.stdout or "") + (proc.stderr or "")


def _env_for(tmpdir, extra_env):
    """The environment for a step: the caller's, plus TMPDIR when
    one is given (pip's temp defaults to /tmp, a 512 MB tmpfs in
    the sandbox — PySide6 installs die there with ENOSPC), plus
    any extra variables (the sandbox Qt library paths in tests)."""
    env = dict(os.environ)
    if tmpdir is not None:
        env["TMPDIR"] = str(tmpdir)
    if extra_env:
        env.update(extra_env)
    return env


def install(source_dir, install_dir=None, applications_dir=None,
            tmpdir=None, extra_env=None, python_exe=None,
            progress=None, cancelled=None) -> tuple[bool, str]:
    """Install the suite from ``source_dir`` (the release tree).

    ``install_dir`` defaults to ``default_install_dir()``;
    ``applications_dir`` to ``default_applications_dir()``.
    ``tmpdir`` is pip's temp folder when given. ``extra_env`` adds
    variables to every step's environment. ``python_exe`` is the
    Python that makes the venv (the running interpreter by
    default). ``progress`` is called with one plain-words string
    as each step starts; ``cancelled`` is checked between steps.

    Returns ``(ok, message)``: ``ok`` is True only when the
    install is verified; ``message`` is the plain-words result —
    on success, with a warning block appended when the GUI smoke
    check failed. Never raises.
    """
    def say(text):
        if progress is not None:
            try:
                progress(text)
            except Exception:
                pass

    def stopped():
        try:
            return bool(cancelled and cancelled())
        except Exception:
            return False

    try:
        return _install(
            source_dir, install_dir, applications_dir, tmpdir,
            extra_env, python_exe, say, stopped,
        )
    except Exception:
        # A bad input must never crash the installer. Anything
        # unexpected lands here as one sentence.
        return False, (
            "I could not install the suite. The install folder "
            "may not be writable. Check it exists and can be "
            "written to, then run the installer again."
        )


def _install(source_dir, install_dir, applications_dir, tmpdir,
             extra_env, python_exe, say, stopped):
    source = Path(source_dir)
    target = Path(install_dir) if install_dir is not None \
        else default_install_dir()
    apps = Path(applications_dir) if applications_dir is not None \
        else default_applications_dir()
    python = str(python_exe) if python_exe is not None \
        else sys.executable
    env = _env_for(tmpdir, extra_env)
    venv_python = _venv_python(target)

    if stopped():
        return False, (
            "Install cancelled. Run the installer again to "
            "finish it."
        )
    if not source.is_dir() or not (source / "pyproject.toml").is_file():
        return False, (
            "I could not install the suite because the release "
            f"folder is missing its project file: {source}. "
            "Download the release again, extract it, and run the "
            "installer from the extracted folder."
        )

    # 1. The machine must be able to install.
    say("Checking this computer can install the suite...")
    code, _ = _run(
        [python, "-m", "venv", "--help"], env, TIMEOUT_VERIFY,
    )
    if code != 0:
        return False, (
            "Python's venv tool is missing, so the installer "
            "cannot make the suite's private Python environment. "
            "Install it first with: sudo apt install python3-venv "
            "python3-pip, then run the installer again."
        )

    if stopped():
        return False, (
            "Install cancelled. Run the installer again to "
            "finish it."
        )

    # 2. The private venv (reused when it is already there).
    try:
        target.mkdir(parents=True, exist_ok=True)
    except OSError:
        return False, (
            "I could not make the install folder "
            f"{target}. Check it can be written to, then run the "
            "installer again."
        )
    if venv_python.is_file():
        say("Reusing the suite's private Python environment...")
    else:
        say("Creating the suite's private Python environment...")
        code, output = _run(
            [python, "-m", "venv", str(target / "venv")],
            env, TIMEOUT_VENV,
        )
        if code != 0 or not venv_python.is_file():
            detail = _last_line(output)
            return False, (
                "I could not make the suite's private Python "
                f"environment in {target}."
                + (f" The error was: {detail}" if detail else "")
                + " Check the folder can be written to, then run "
                "the installer again."
            )

    if stopped():
        return False, (
            "Install cancelled. Run the installer again to "
            "finish it."
        )

    # 3. The packages (the step that needs the network).
    say(
        "Downloading and installing the suite and its parts "
        "(this takes a few minutes the first time)..."
    )
    code, output = _run(
        [str(venv_python), "-m", "pip", "install", "--quiet",
         "--upgrade", "pip"],
        env, TIMEOUT_PIP,
    )
    if code != 0:
        detail = _last_line(output)
        return False, (
            "Installing the suite's packages failed while "
            "updating pip."
            + (f" The error was: {detail}" if detail else "")
            + " This usually means the network dropped during the "
            "download. Check the connection and run the installer "
            "again."
        )
    code, output = _run(
        [str(venv_python), "-m", "pip", "install", "--quiet",
         str(source)],
        env, TIMEOUT_PIP,
    )
    if code != 0:
        detail = _last_line(output)
        return False, (
            "Installing the suite's packages failed."
            + (f" The error was: {detail}" if detail else "")
            + " This usually means the network dropped during the "
            "download. Check the connection and run the installer "
            "again."
        )

    if stopped():
        return False, (
            "Install cancelled. The packages are in, but the menu "
            "entries are not written yet. Run the installer again "
            "to finish it."
        )

    # 4. The menu launchers (the app entry and the Uninstall entry).
    say("Adding the menu entries...")
    launchers = [
        (DESKTOP_FILENAME, build_desktop_entry(target)),
        (
            UNINSTALL_DESKTOP_FILENAME,
            build_uninstall_desktop_entry(target),
        ),
    ]
    try:
        apps.mkdir(parents=True, exist_ok=True)
        for filename, text in launchers:
            desktop_path = apps / filename
            desktop_path.write_text(text, encoding="utf-8")
            os.chmod(desktop_path, 0o644)
    except OSError:
        return False, (
            "I could not write the menu entries in "
            f"{apps}. Check the folder can be written to, then "
            "run the installer again."
        )
    if shutil.which("update-desktop-database"):
        _run(
            ["update-desktop-database", str(apps)],
            env, TIMEOUT_VERIFY,
        )  # Best effort: a stale menu cache is not an install failure.

    # A small record of what was installed, for the uninstaller
    # and for debugging later.
    try:
        code, output = _run(
            [str(venv_python), "-c",
             "import importlib.metadata as m; "
             f"print(m.version({PACKAGE_NAME!r}))"],
            env, TIMEOUT_VERIFY,
        )
        version = output.strip() if code == 0 else "unknown"
        (target / "install-info.json").write_text(
            json.dumps({
                "app": APP_NAME,
                "version": version,
                "installed": date.today().isoformat(),
                "source": str(source),
            }, indent=2) + "\n",
            encoding="utf-8",
        )
    except OSError:
        pass  # The record is a note, not the install.

    if stopped():
        return False, (
            "Install cancelled. The menu entries are written, but "
            "the install is not checked yet. Run the installer "
            "again to finish it."
        )

    # 5. Verify before reporting success. The package check is
    # fatal; the GUI smoke check is a warning (see the module
    # docstring).
    say("Checking the install works...")
    code, output = _run(
        [str(venv_python), "-c",
         "import importlib.metadata as m; "
         f"m.version({PACKAGE_NAME!r}); m.version('PySide6'); "
         "import devsuite; import installer.gui"],
        env, TIMEOUT_VERIFY,
    )
    if code != 0:
        detail = _last_line(output)
        return False, (
            "The install finished, but the check failed: the "
            "suite or its PySide6 toolkit did not install."
            + (f" The error was: {detail}" if detail else "")
            + " Run the installer again."
        )

    say("Checking the suite's window opens...")
    smoke_env = dict(env)
    smoke_env["QT_QPA_PLATFORM"] = "offscreen"
    # Verifying an install must never start an update check of
    # its own (the window's launch check is skipped when this is
    # set — see devsuite.main).
    smoke_env["DEVSUITE_NO_UPDATE_CHECK"] = "1"
    smoke = (
        "import sys\n"
        "from PySide6.QtCore import QTimer\n"
        "from PySide6.QtWidgets import QApplication\n"
        "from devsuite.ui.chat_window import ChatWindow\n"
        "app = QApplication(sys.argv)\n"
        "window = ChatWindow()\n"
        "window.show()\n"
        f"QTimer.singleShot({GUI_SMOKE_MS}, app.quit)\n"
        "sys.exit(app.exec())\n"
    )
    code, output = _run(
        [str(venv_python), "-c", smoke], smoke_env, TIMEOUT_GUI_SMOKE,
    )
    message = (
        "Installed. Open Reblend Add-on Dev Suite from the menu."
    )
    if code != 0:
        detail = _last_line(output)
        message += (
            "\n\nWarning: the suite installed, but its window "
            "could not open on this machine yet. This usually "
            "means a system Qt library is missing."
            + (f" The error was: {detail}" if detail else "")
            + " Install the missing system library, then run the "
            "installer again."
        )
    return True, message


def main(argv=None) -> int:
    """The terminal front end (``install.sh`` calls this):
    install, printing plain-words progress, exit 0 on success
    (a GUI smoke warning still exits 0 — the install itself
    worked), exit 1 on failure."""
    parser = argparse.ArgumentParser(
        description="Install the Reblend Add-on Dev Suite.",
    )
    parser.add_argument(
        "--source-dir", default=None,
        help="the release folder (default: the folder holding "
        "this installer)",
    )
    parser.add_argument(
        "--install-dir", default=None,
        help="where to install "
        f"(default: {default_install_dir()})",
    )
    parser.add_argument(
        "--applications-dir", default=None,
        help="where the menu entry goes "
        f"(default: {default_applications_dir()})",
    )
    parser.add_argument(
        "--tmpdir", default=None,
        help="pip's temp folder (default: the system temp)",
    )
    args = parser.parse_args(argv)

    source = (
        Path(args.source_dir) if args.source_dir is not None
        else Path(__file__).resolve().parent.parent
    )

    def say(text):
        print(text, flush=True)

    ok, message = install(
        source,
        install_dir=args.install_dir,
        applications_dir=args.applications_dir,
        tmpdir=args.tmpdir,
        progress=say,
    )
    print()
    print(message)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
