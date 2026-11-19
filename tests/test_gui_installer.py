"""Tests for the suite's own GUI installer (Phase 6, DOSSIER.md §9.1).

This is the installer for the Dev Suite itself — not the pack
installer in devsuite.packing (that one has tests/test_installer.py).
It covers the headless install logic (installer/install.py), the
menu launcher text, the double-click Install .desktop file, and
the tkinter window (installer/gui.py).

The install sim runs the real install: a throwaway venv under
~/workspace (NOT /tmp — /tmp is a 512 MB tmpfs and PySide6
installs die there with ENOSPC, AGENTS.md), a real pip install of
the suite from this tree, and the real verification, with the
sandbox Qt library paths passed through. It takes a few minutes
the first time (the PySide6 download); later runs reuse the pip
cache. The sim never touches the real home applications folder —
the .desktop destination is a parameter — and it cleans its temp
dirs up after itself.

The tkinter test needs a display: it skips with a plain reason
when there is none (the normal suite run has no display). Run it
under Xvfb to see it pass:

    xvfb-run -a ~/workspace/tmp/qt-venv/bin/python -m unittest \\
        tests.test_gui_installer.GuiInstallerWindowTest
"""

import json
import os
import shlex
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

#: Scratch lives under the workspace, never /tmp (AGENTS.md: /tmp
#: is a 512 MB tmpfs; pip's temp and the venv both need real room).
WORKSPACE_TMP = Path.home() / "workspace" / ".test-tmp"

#: The sandbox Qt library paths, for the verify step's GUI smoke
#: check (his PC has system Qt libs; the sandbox needs these).
QT_LIBS = Path.home() / "workspace" / "qt-libs" / "root"

sys.path.insert(0, str(ROOT))

from installer.install import (  # noqa: E402
    APP_NAME,
    DESKTOP_FILENAME,
    PACKAGE_NAME,
    UNINSTALL_APP_NAME,
    UNINSTALL_DESKTOP_FILENAME,
    _last_line,
    build_desktop_entry,
    build_uninstall_desktop_entry,
    default_install_dir,
    install,
)


def _sandbox_env():
    """Extra environment for the sim's subprocesses: the sandbox
    Qt library paths, when they exist."""
    env = {"QT_QPA_PLATFORM": "offscreen"}
    lib_dir = QT_LIBS / "usr" / "lib" / "x86_64-linux-gnu"
    if lib_dir.is_dir():
        env["LD_LIBRARY_PATH"] = str(lib_dir)
    vendor_dir = QT_LIBS / "usr" / "share" / "glvnd" / "egl_vendor.d"
    if vendor_dir.is_dir():
        env["__EGL_VENDOR_LIBRARY_DIRS"] = str(vendor_dir)
    return env


class LastLineTest(unittest.TestCase):
    def test_last_non_empty_line_is_quoted(self):
        self.assertEqual(
            _last_line("first\nsecond\n\n"), "second."
        )

    def test_missing_period_is_added(self):
        # Every message that quotes the detail goes on to another
        # sentence — without the period the two run together.
        self.assertEqual(
            _last_line("the step ran past its time limit"),
            "the step ran past its time limit.",
        )

    def test_existing_punctuation_is_kept(self):
        self.assertEqual(
            _last_line("ERROR: something failed."), "ERROR: something failed."
        )
        self.assertEqual(_last_line("what?"), "what?")
        self.assertEqual(_last_line("watch out!"), "watch out!")

    def test_empty_output_quotes_nothing(self):
        self.assertEqual(_last_line(""), "")
        self.assertEqual(_last_line("\n  \n"), "")


class InstallerLogicTest(unittest.TestCase):
    def setUp(self):
        WORKSPACE_TMP.mkdir(parents=True, exist_ok=True)
        self._tmp = tempfile.mkdtemp(
            prefix="gui-installer-", dir=str(WORKSPACE_TMP)
        )
        self.tmp = Path(self._tmp)
        self.install_dir = self.tmp / "install"
        self.apps_dir = self.tmp / "applications"
        # The named TMPDIR subdir must EXIST before pip runs
        # (AGENTS.md: mktemp fails outright on a missing TMPDIR).
        self.pip_tmp = self.tmp / "pip-tmp"
        self.pip_tmp.mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        shutil.rmtree(self._tmp, ignore_errors=True)

    # -- the menu launcher ----------------------------------------

    def test_desktop_entry_bakes_the_app_dir_in(self):
        """The app launcher's Exec is the venv console script as
        one absolute path (DOSSIER.md U4): no %k, no nested quotes,
        Terminal=false, and no Icon line until the icon exists."""
        text = build_desktop_entry(self.install_dir)
        self.assertIn(f"Name={APP_NAME}", text)
        self.assertIn("Terminal=false", text)
        self.assertNotIn("Icon=", text)
        self.assertNotIn("%k", text)
        self.assertNotIn('\\"', text)
        exec_lines = [
            line for line in text.splitlines()
            if line.startswith("Exec=")
        ]
        self.assertEqual(len(exec_lines), 1)
        parts = shlex.split(exec_lines[0][len("Exec="):])
        self.assertEqual(len(parts), 1)
        self.assertEqual(
            parts[0],
            str(self.install_dir / "venv" / "bin" / "devsuite"),
        )
        self.assertTrue(Path(parts[0]).is_absolute())

    def test_uninstall_desktop_entry_bakes_the_app_dir_in(self):
        """The Uninstall launcher mirrors the app launcher (U4):
        its Exec is the venv's `devsuite-uninstall` console
        script as one absolute path — no %k, no nested quotes,
        Terminal=false, and no Icon line until the icon exists."""
        text = build_uninstall_desktop_entry(self.install_dir)
        self.assertIn(f"Name={UNINSTALL_APP_NAME}", text)
        self.assertEqual(
            UNINSTALL_APP_NAME, "Uninstall Reblend Add-on Dev Suite"
        )
        self.assertIn("Terminal=false", text)
        self.assertNotIn("Icon=", text)
        self.assertNotIn("%k", text)
        self.assertNotIn('\\"', text)
        exec_lines = [
            line for line in text.splitlines()
            if line.startswith("Exec=")
        ]
        self.assertEqual(len(exec_lines), 1)
        parts = shlex.split(exec_lines[0][len("Exec="):])
        self.assertEqual(len(parts), 1)
        self.assertEqual(
            parts[0],
            str(
                self.install_dir / "venv" / "bin"
                / "devsuite-uninstall"
            ),
        )
        self.assertTrue(Path(parts[0]).is_absolute())

    def test_install_desktop_launcher_uses_the_proven_pattern(self):
        """The double-click Install launcher finds the release
        folder with the python3 -c %k pattern (AGENTS.md): %k is
        its own argv token, there are no nested escaped quotes,
        and it runs no terminal. The file is executable in the
        tree (the zip bit is a release-build concern)."""
        path = ROOT / "Install Reblend Add-on Dev Suite.desktop"
        self.assertTrue(path.is_file(), "the Install launcher is missing")
        text = path.read_text(encoding="utf-8")
        self.assertIn("Name=Install Reblend Add-on Dev Suite", text)
        self.assertIn("Terminal=false", text)
        self.assertNotIn('\\"', text)
        exec_lines = [
            line for line in text.splitlines()
            if line.startswith("Exec=")
        ]
        self.assertEqual(len(exec_lines), 1)
        parts = shlex.split(exec_lines[0][len("Exec="):])
        self.assertEqual(parts[0], "python3")
        self.assertEqual(parts[-1], "%k")
        self.assertIn("installer", parts[2])
        self.assertIn("gui.py", parts[2])
        mode = path.stat().st_mode
        self.assertTrue(
            mode & stat.S_IXUSR, "the Install launcher is not executable"
        )

    def test_shell_scripts_are_bash_and_executable(self):
        """install.sh and run.sh start with a bash shebang (never
        sh — AGENTS.md) and carry the exec bit in the tree."""
        for name in ("install.sh", "run.sh"):
            path = ROOT / name
            self.assertTrue(path.is_file(), f"{name} is missing")
            first = path.read_text(encoding="utf-8").splitlines()[0]
            self.assertIn("bash", first, f"{name} has no bash shebang")
            self.assertTrue(
                path.stat().st_mode & stat.S_IXUSR,
                f"{name} is not executable",
            )

    # -- failure paths (fast, no network) -------------------------

    def test_cancel_before_start_does_nothing(self):
        ok, message = install(
            ROOT, install_dir=self.install_dir,
            applications_dir=self.apps_dir,
            cancelled=lambda: True,
        )
        self.assertFalse(ok)
        self.assertIn("cancelled", message.lower())
        self.assertFalse((self.install_dir / "venv").exists())

    def test_missing_python_reports_plainly(self):
        ok, message = install(
            ROOT, install_dir=self.install_dir,
            applications_dir=self.apps_dir,
            python_exe="/nonexistent/python3",
        )
        self.assertFalse(ok)
        self.assertIn("venv", message.lower())
        self.assertIn("python3-venv", message)

    def test_missing_project_file_reports_plainly(self):
        empty = self.tmp / "empty-source"
        empty.mkdir()
        ok, message = install(
            empty, install_dir=self.install_dir,
            applications_dir=self.apps_dir,
        )
        self.assertFalse(ok)
        self.assertIn("project file", message)
        self.assertFalse((self.apps_dir / DESKTOP_FILENAME).exists())

    def test_pip_failure_reports_plainly_and_writes_no_launcher(self):
        """A source tree whose packages cannot install (an
        unsatisfiable dependency) fails plainly: no success, no
        menu launcher, and the message says what went wrong."""
        broken = self.tmp / "broken-source"
        broken.mkdir()
        (broken / "pyproject.toml").write_text(
            "[project]\n"
            "name = \"broken-test-pkg\"\n"
            "version = \"0.1.0\"\n"
            "requires-python = \">=3.10\"\n"
            "dependencies = "
            "[\"this-package-does-not-exist-xyz>=1\"]\n"
            "\n"
            "[build-system]\n"
            "requires = [\"setuptools>=64\"]\n"
            "build-backend = \"setuptools.build_meta\"\n",
            encoding="utf-8",
        )
        (broken / "broken_test_pkg").mkdir()
        (broken / "broken_test_pkg" / "__init__.py").write_text(
            "", encoding="utf-8"
        )
        python_exe = shutil.which("python3") or sys.executable
        ok, message = install(
            broken, install_dir=self.install_dir,
            applications_dir=self.apps_dir, tmpdir=self.pip_tmp,
            python_exe=python_exe,
        )
        self.assertFalse(ok)
        self.assertIn("failed", message.lower())
        self.assertFalse((self.apps_dir / DESKTOP_FILENAME).exists())

    # -- the real install -----------------------------------------

    def test_install_sim_full(self):
        """The real install, end to end: venv, pip install from
        this tree, menu launcher, verification. Then the installed
        copy proves itself: the venv python imports the suite, and
        the installed templates build a real project (the template
        files must ship as package data, or this fails)."""
        python_exe = shutil.which("python3") or sys.executable
        seen = []
        ok, message = install(
            ROOT, install_dir=self.install_dir,
            applications_dir=self.apps_dir, tmpdir=self.pip_tmp,
            extra_env=_sandbox_env(), python_exe=python_exe,
            progress=seen.append,
        )
        self.assertTrue(ok, f"the install failed: {message}")
        self.assertIn("Installed", message)
        self.assertGreater(len(seen), 2)

        venv_python = self.install_dir / "venv" / "bin" / "python"
        self.assertTrue(venv_python.is_file())
        console = self.install_dir / "venv" / "bin" / "devsuite"
        self.assertTrue(console.is_file())
        self.assertTrue(os.access(console, os.X_OK))

        desktop = self.apps_dir / DESKTOP_FILENAME
        self.assertTrue(desktop.is_file())
        entry = desktop.read_text(encoding="utf-8")
        self.assertIn(f"Exec={console}", entry)

        # The Uninstall menu entry and its console script: the
        # installer package ships inside the distribution, so the
        # suite can be removed from the menu after the release
        # tree is deleted.
        uninstall_console = (
            self.install_dir / "venv" / "bin" / "devsuite-uninstall"
        )
        self.assertTrue(uninstall_console.is_file())
        self.assertTrue(os.access(uninstall_console, os.X_OK))
        uninstall_desktop = (
            self.apps_dir / UNINSTALL_DESKTOP_FILENAME
        )
        self.assertTrue(uninstall_desktop.is_file())
        uninstall_entry = uninstall_desktop.read_text(
            encoding="utf-8"
        )
        self.assertIn(f"Exec={uninstall_console}", uninstall_entry)
        self.assertIn(
            f"Name={UNINSTALL_APP_NAME}", uninstall_entry
        )

        info = json.loads(
            (self.install_dir / "install-info.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(info["app"], APP_NAME)
        self.assertEqual(info["version"], "0.1.0")

        env = _sandbox_env()
        env["TMPDIR"] = str(self.pip_tmp)
        check = subprocess.run(
            [str(venv_python), "-c",
             "import importlib.metadata as m; "
             f"m.version({PACKAGE_NAME!r}); m.version('PySide6'); "
             "import devsuite; import installer.gui; "
             "from devsuite.templates import list_templates; "
             "names = [t['name'] for t in list_templates()]; "
             "assert 'surprise' in names, names"],
            capture_output=True, text=True, timeout=120, env=env,
        )
        self.assertEqual(
            check.returncode, 0,
            f"the installed copy failed its import check: "
            f"{check.stdout}{check.stderr}",
        )

        # The installed templates build a real project.
        project_dir = self.tmp / "sim-project"
        built = subprocess.run(
            [str(venv_python), "-c",
             "from devsuite.templates import "
             "create_project_from_template; "
             "p, e = create_project_from_template("
             "'surprise', "
             f"{str(project_dir)!r}, name='Surprise'); "
             "assert e is None, e"],
            capture_output=True, text=True, timeout=120, env=env,
        )
        self.assertEqual(
            built.returncode, 0,
            f"the installed templates failed to build a project: "
            f"{built.stdout}{built.stderr}",
        )
        self.assertTrue(
            (project_dir / "src" / "reblend" / "addon.py").is_file()
        )
        self.assertTrue(
            (project_dir / "src" / "shared" / "pick.py").is_file()
        )


class InstallerGuiCopyTest(unittest.TestCase):
    """The installer's visible words carry no em-dashes and no
    bare "&" (the suite's guard rules) — checked here without a
    display, over the copy constants the window shows."""

    def test_visible_copy_has_no_em_dash_or_bare_ampersand(self):
        import installer.gui as gui

        for text in gui._VISIBLE_COPY:
            self.assertNotIn("—", text, f"em-dash in: {text!r}")
            self.assertNotIn("&", text, f"bare & in: {text!r}")


class GuiInstallerWindowTest(unittest.TestCase):
    """The tkinter window itself. Needs a display — skips plainly
    without one (run under Xvfb to see it pass)."""

    def setUp(self):
        import tkinter as tk

        try:
            import installer.gui as gui

            self.window = gui.InstallerWindow()
        except tk.TclError:
            raise unittest.SkipTest("no display for tkinter")

    def tearDown(self):
        try:
            self.window._root.destroy()
        except Exception:
            pass

    def test_window_opens_with_defaults(self):
        import tkinter as tk

        root = self.window._root
        self.assertEqual(root.title(), f"Install {APP_NAME}")
        self.assertEqual(
            self.window._folder_entry.get(),
            str(default_install_dir()),
        )
        self.assertEqual(
            self.window._install_button["state"], tk.NORMAL
        )
        self.assertEqual(
            self.window._cancel_button["state"], tk.DISABLED
        )
        self.assertEqual(
            self.window._close_button["state"], tk.NORMAL
        )
        self.assertIn(
            "Pick a folder", self.window._progress_label["text"]
        )


if __name__ == "__main__":
    unittest.main()
