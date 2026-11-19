"""Tests for the suite's own uninstaller (Phase 6, DOSSIER.md §13).

The uninstaller for the Dev Suite itself — the follow-up to the
GUI installer (tests/test_gui_installer.py). It covers the
headless uninstall logic (installer/uninstall.py), the
uninstall.sh front end, and the tkinter uninstall window
(installer/gui.py).

The fast tests build a fake install by hand (an install folder
with an install record, a menu launcher, a fake shelf and fake
settings) in temp folders — no pip, no network. The ONE full
cycle test runs the real install into workspace temp dirs and
then uninstalls it, proving end to end that uninstall leaves
nothing behind (§13). It is the only slow test here: the install
sim takes minutes the first time (the PySide6 download), and the
suite is already slow enough with one of them — later runs reuse
the pip cache.

Scratch lives under ~/workspace (NOT /tmp — /tmp is a 512 MB
tmpfs and the venv needs real room, AGENTS.md). Every path is a
parameter, so no test touches the real home applications folder,
the real shelf, or the real settings file.

The tkinter tests need a display: they skip with a plain reason
when there is none (the normal suite run has no display). Run
them under Xvfb to see them pass:

    xvfb-run -a ~/workspace/tmp/qt-venv/bin/python -m unittest \\
        tests.test_uninstaller.UninstallerWindowTest \\
        tests.test_uninstaller.UninstallerStandaloneEntryTest
"""

import json
import os
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

#: The sandbox Qt library paths, for the cycle test's install
#: (his PC has system Qt libs; the sandbox needs these).
QT_LIBS = Path.home() / "workspace" / "qt-libs" / "root"

sys.path.insert(0, str(ROOT))

from installer.install import (  # noqa: E402
    DESKTOP_FILENAME,
    UNINSTALL_DESKTOP_FILENAME,
    install,
)
from installer.uninstall import (  # noqa: E402
    find_install,
    uninstall,
)


def _sandbox_env():
    """Extra environment for the cycle test's subprocesses: the
    sandbox Qt library paths, when they exist."""
    env = {"QT_QPA_PLATFORM": "offscreen"}
    lib_dir = QT_LIBS / "usr" / "lib" / "x86_64-linux-gnu"
    if lib_dir.is_dir():
        env["LD_LIBRARY_PATH"] = str(lib_dir)
    vendor_dir = QT_LIBS / "usr" / "share" / "glvnd" / "egl_vendor.d"
    if vendor_dir.is_dir():
        env["__EGL_VENDOR_LIBRARY_DIRS"] = str(vendor_dir)
    return env


class UninstallerLogicTest(unittest.TestCase):
    def setUp(self):
        WORKSPACE_TMP.mkdir(parents=True, exist_ok=True)
        self._tmp = tempfile.mkdtemp(
            prefix="uninstaller-", dir=str(WORKSPACE_TMP)
        )
        self.tmp = Path(self._tmp)
        self.install_dir = self.tmp / "install"
        self.apps_dir = self.tmp / "applications"
        # Fake app data, in the same shape as the real paths
        # (org dir / app dir / file), so the empty-org-dir rules
        # are tested honestly.
        self.shelf_path = (
            self.tmp / "share" / "Broke n Bored"
            / "Reblend Add-on Dev Suite" / "shelf.json"
        )
        self.settings_path = (
            self.tmp / "config" / "Broke n Bored"
            / "Reblend Add-on Dev Suite.conf"
        )

    def tearDown(self):
        # A test may have left a folder read-only: make the tree
        # writable again so the cleanup can remove it.
        for path in sorted(
            self.tmp.rglob("*"), key=lambda p: len(str(p)),
            reverse=True,
        ):
            try:
                os.chmod(path, stat.S_IRWXU)
            except OSError:
                pass
        try:
            os.chmod(self.tmp, stat.S_IRWXU)
        except OSError:
            pass
        shutil.rmtree(self._tmp, ignore_errors=True)

    # -- helpers --------------------------------------------------

    def _fake_install(self, with_app_data=True):
        """A hand-built install: the folder with a venv and a
        record, the menu launcher, and (usually) the app data."""
        venv_bin = self.install_dir / "venv" / "bin"
        venv_bin.mkdir(parents=True)
        (venv_bin / "python").write_text("", encoding="utf-8")
        (venv_bin / "devsuite").write_text("", encoding="utf-8")
        (self.install_dir / "install-info.json").write_text(
            json.dumps({
                "app": "Reblend Add-on Dev Suite",
                "version": "0.1.0",
            }),
            encoding="utf-8",
        )
        self.apps_dir.mkdir(parents=True, exist_ok=True)
        (self.apps_dir / DESKTOP_FILENAME).write_text(
            "[Desktop Entry]\nName=Reblend Add-on Dev Suite\n",
            encoding="utf-8",
        )
        (self.apps_dir / UNINSTALL_DESKTOP_FILENAME).write_text(
            "[Desktop Entry]\n"
            "Name=Uninstall Reblend Add-on Dev Suite\n",
            encoding="utf-8",
        )
        if with_app_data:
            self.shelf_path.parent.mkdir(parents=True)
            self.shelf_path.write_text("[]", encoding="utf-8")
            self.settings_path.parent.mkdir(parents=True)
            self.settings_path.write_text(
                "[General]\n", encoding="utf-8"
            )

    def _uninstall(self, remove_app_data=False):
        return uninstall(
            install_dir=self.install_dir,
            applications_dir=self.apps_dir,
            remove_app_data=remove_app_data,
            shelf_path=self.shelf_path,
            settings_path=self.settings_path,
        )

    # -- nothing installed ----------------------------------------

    def test_nothing_installed_says_so_plainly(self):
        ok, message = self._uninstall()
        self.assertFalse(ok)
        self.assertIn("not installed", message.lower())
        self.assertFalse(self.install_dir.exists())
        self.assertFalse(self.apps_dir.exists())

    def test_find_install_reports_what_is_present(self):
        empty = find_install(self.install_dir, self.apps_dir)
        self.assertIsNone(empty["install_dir"])
        self.assertIsNone(empty["record"])
        self.assertIsNone(empty["launcher"])
        self.assertIsNone(empty["uninstall_launcher"])
        self._fake_install()
        found = find_install(self.install_dir, self.apps_dir)
        self.assertEqual(found["install_dir"], self.install_dir)
        self.assertEqual(found["record"]["version"], "0.1.0")
        self.assertEqual(
            found["launcher"], self.apps_dir / DESKTOP_FILENAME
        )
        self.assertEqual(
            found["uninstall_launcher"],
            self.apps_dir / UNINSTALL_DESKTOP_FILENAME,
        )

    # -- the removal itself ---------------------------------------

    def test_uninstall_removes_install_and_launcher(self):
        self._fake_install()
        ok, message = self._uninstall()
        self.assertTrue(ok, f"the uninstall failed: {message}")
        self.assertFalse(self.install_dir.exists())
        self.assertFalse(
            (self.apps_dir / DESKTOP_FILENAME).exists()
        )
        self.assertFalse(
            (self.apps_dir / UNINSTALL_DESKTOP_FILENAME).exists()
        )
        self.assertIn("Removed", message)
        self.assertIn(str(self.install_dir), message)
        self.assertIn("menu entry", message.lower())
        self.assertIn("uninstall menu entry", message.lower())

    def test_uninstall_keeps_app_data_by_default(self):
        """The shelf and settings stay unless Joshua opts in —
        a reinstall finds them waiting."""
        self._fake_install()
        ok, message = self._uninstall(remove_app_data=False)
        self.assertTrue(ok, f"the uninstall failed: {message}")
        self.assertTrue(self.shelf_path.is_file())
        self.assertTrue(self.settings_path.is_file())
        self.assertIn("kept", message.lower())

    def test_uninstall_with_app_data_removes_shelf_and_settings(self):
        self._fake_install()
        ok, message = self._uninstall(remove_app_data=True)
        self.assertTrue(ok, f"the uninstall failed: {message}")
        self.assertFalse(self.shelf_path.exists())
        self.assertFalse(self.shelf_path.parent.exists())
        self.assertFalse(self.settings_path.exists())
        # The shared org folders go too, when nothing else uses
        # them — that is the "nothing behind" rule.
        self.assertFalse(self.shelf_path.parent.parent.exists())
        self.assertFalse(self.settings_path.parent.exists())
        self.assertIn("library shelf", message.lower())
        self.assertIn("remembered settings", message.lower())

    def test_shared_org_folder_stays_when_not_empty(self):
        """Another app's file under the same organization folder
        keeps the folder standing — the uninstaller never removes
        another app's home."""
        self._fake_install()
        other = (
            self.settings_path.parent / "Another App.conf"
        )
        other.write_text("", encoding="utf-8")
        ok, _ = self._uninstall(remove_app_data=True)
        self.assertTrue(ok)
        self.assertFalse(self.settings_path.exists())
        self.assertTrue(other.is_file())
        self.assertTrue(self.settings_path.parent.is_dir())

    def test_launcher_only_state_removes_the_launcher(self):
        """A stale menu entry with no install folder behind it is
        still removed — leaving it would break §13."""
        self.apps_dir.mkdir(parents=True)
        (self.apps_dir / DESKTOP_FILENAME).write_text(
            "[Desktop Entry]\n", encoding="utf-8"
        )
        ok, message = self._uninstall()
        self.assertTrue(ok, f"the uninstall failed: {message}")
        self.assertFalse(
            (self.apps_dir / DESKTOP_FILENAME).exists()
        )
        self.assertIn("menu entry", message.lower())

    def test_uninstall_launcher_only_state_removes_the_launcher(self):
        """Only the Uninstall menu entry survives, with no install
        folder and no app entry behind it: the uninstall still
        removes it instead of saying nothing is installed."""
        self.apps_dir.mkdir(parents=True)
        (self.apps_dir / UNINSTALL_DESKTOP_FILENAME).write_text(
            "[Desktop Entry]\n", encoding="utf-8"
        )
        ok, message = self._uninstall()
        self.assertTrue(ok, f"the uninstall failed: {message}")
        self.assertFalse(
            (self.apps_dir / UNINSTALL_DESKTOP_FILENAME).exists()
        )
        self.assertIn("uninstall menu entry", message.lower())

    def test_home_as_install_dir_is_refused(self):
        """The safety guard: the uninstaller never removes the
        home folder itself, whatever path it is given."""
        ok, message = uninstall(
            install_dir=Path.home(),
            applications_dir=self.apps_dir,
        )
        self.assertFalse(ok)
        self.assertIn("will not remove", message.lower())
        self.assertTrue(Path.home().is_dir())

    # -- partial failures -----------------------------------------

    def test_read_only_subdir_does_not_strand_the_uninstall(self):
        """Read-only files and folders inside the install are made
        writable and removed — they must not leave an uninstall
        half done."""
        self._fake_install()
        locked = self.install_dir / "venv" / "lib" / "locked"
        locked.mkdir(parents=True)
        (locked / "file.txt").write_text("x", encoding="utf-8")
        os.chmod(locked / "file.txt", stat.S_IRUSR)
        os.chmod(locked, stat.S_IRUSR | stat.S_IXUSR)
        ok, message = self._uninstall()
        self.assertTrue(ok, f"the uninstall failed: {message}")
        self.assertFalse(self.install_dir.exists())

    def test_partial_removal_reports_what_is_left(self):
        """When the install folder itself cannot be removed (its
        parent is read-only), the uninstall says what is left and
        how to remove it by hand — and still removes the launcher
        it could reach."""
        self._fake_install()
        parent = self.install_dir.parent
        os.chmod(parent, stat.S_IRUSR | stat.S_IXUSR)
        try:
            ok, message = self._uninstall()
        finally:
            os.chmod(parent, stat.S_IRWXU)
        self.assertFalse(ok)
        self.assertIn(str(self.install_dir), message)
        self.assertIn("rm -rf", message)
        # The launchers were still removed: a failure in one step
        # does not stop the others.
        self.assertFalse(
            (self.apps_dir / DESKTOP_FILENAME).exists()
        )
        self.assertFalse(
            (self.apps_dir / UNINSTALL_DESKTOP_FILENAME).exists()
        )

    # -- the shell front end --------------------------------------

    def test_uninstall_script_is_bash_and_executable(self):
        """uninstall.sh starts with a bash shebang (never sh —
        AGENTS.md), carries the exec bit in the tree, and asks
        both questions defaulting to No ([y/N])."""
        path = ROOT / "uninstall.sh"
        self.assertTrue(path.is_file(), "uninstall.sh is missing")
        text = path.read_text(encoding="utf-8")
        self.assertIn("bash", text.splitlines()[0])
        self.assertTrue(
            path.stat().st_mode & stat.S_IXUSR,
            "uninstall.sh is not executable",
        )
        self.assertIn("Uninstall the suite? [y/N]", text)
        self.assertIn(
            "Also remove the library shelf and remembered "
            "settings? [y/N]",
            text,
        )

    def test_uninstall_script_declines_by_default(self):
        """Answering nothing (the default) uninstalls nothing and
        exits 0 — the destructive default is No (U23/U31)."""
        script = subprocess.run(
            ["bash", str(ROOT / "uninstall.sh")],
            input="\n", capture_output=True, text=True,
            timeout=60,
        )
        self.assertEqual(script.returncode, 0)
        self.assertIn("Nothing was uninstalled", script.stdout)


class UninstallerCycleTest(unittest.TestCase):
    """The ONE full cycle: the real install, then the real
    uninstall, proving §13 end to end. Slow (the install sim),
    so there is exactly one of these."""

    def test_install_then_uninstall_leaves_nothing_behind(self):
        WORKSPACE_TMP.mkdir(parents=True, exist_ok=True)
        tmp = Path(
            tempfile.mkdtemp(
                prefix="uninstaller-cycle-", dir=str(WORKSPACE_TMP)
            )
        )
        try:
            install_dir = tmp / "install"
            apps_dir = tmp / "applications"
            pip_tmp = tmp / "pip-tmp"
            pip_tmp.mkdir(parents=True, exist_ok=True)
            shelf_path = (
                tmp / "share" / "Broke n Bored"
                / "Reblend Add-on Dev Suite" / "shelf.json"
            )
            settings_path = (
                tmp / "config" / "Broke n Bored"
                / "Reblend Add-on Dev Suite.conf"
            )
            python_exe = shutil.which("python3") or sys.executable
            ok, message = install(
                ROOT, install_dir=install_dir,
                applications_dir=apps_dir, tmpdir=pip_tmp,
                extra_env=_sandbox_env(), python_exe=python_exe,
            )
            self.assertTrue(ok, f"the install failed: {message}")
            self.assertTrue(
                (install_dir / "install-info.json").is_file()
            )
            self.assertTrue(
                (apps_dir / DESKTOP_FILENAME).is_file()
            )
            self.assertTrue(
                (apps_dir / UNINSTALL_DESKTOP_FILENAME).is_file()
            )

            # The install does not create app data (the app does,
            # when it runs), so the cycle seeds it by hand.
            shelf_path.parent.mkdir(parents=True)
            shelf_path.write_text("[]", encoding="utf-8")
            settings_path.parent.mkdir(parents=True)
            settings_path.write_text(
                "[General]\n", encoding="utf-8"
            )

            seen = []
            ok, message = uninstall(
                install_dir=install_dir,
                applications_dir=apps_dir,
                remove_app_data=True,
                progress=seen.append,
                shelf_path=shelf_path,
                settings_path=settings_path,
            )
            self.assertTrue(
                ok, f"the uninstall failed: {message}"
            )
            self.assertGreater(len(seen), 0)
            self.assertFalse(install_dir.exists())
            self.assertFalse(
                (apps_dir / DESKTOP_FILENAME).exists()
            )
            self.assertFalse(
                (apps_dir / UNINSTALL_DESKTOP_FILENAME).exists()
            )
            self.assertFalse(shelf_path.exists())
            self.assertFalse(settings_path.exists())
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class UninstallerGuiCopyTest(unittest.TestCase):
    """The uninstaller's visible words carry no em-dashes and no
    bare "&" (the suite's guard rules) — checked here without a
    display, over the copy constants the windows show."""

    def test_visible_copy_has_no_em_dash_or_bare_ampersand(self):
        import installer.gui as gui

        for text in gui._VISIBLE_COPY:
            self.assertNotIn("—", text, f"em-dash in: {text!r}")
            self.assertNotIn("&", text, f"bare & in: {text!r}")


class UninstallerWindowTest(unittest.TestCase):
    """The tkinter uninstall window itself. Needs a display —
    skips plainly without one (run under Xvfb to see it pass)."""

    def setUp(self):
        import tkinter as tk

        WORKSPACE_TMP.mkdir(parents=True, exist_ok=True)
        self._tmp = tempfile.mkdtemp(
            prefix="uninstaller-gui-", dir=str(WORKSPACE_TMP)
        )
        self.tmp = Path(self._tmp)
        self.install_dir = self.tmp / "install"
        self.apps_dir = self.tmp / "applications"
        (self.install_dir).mkdir(parents=True)
        (self.install_dir / "install-info.json").write_text(
            json.dumps({"app": "Reblend Add-on Dev Suite"}),
            encoding="utf-8",
        )
        self.apps_dir.mkdir(parents=True, exist_ok=True)
        (self.apps_dir / DESKTOP_FILENAME).write_text(
            "[Desktop Entry]\n", encoding="utf-8"
        )
        try:
            import installer.gui as gui

            self._tk_root = tk.Tk()
            self._tk_root.withdraw()
            self.window = gui.UninstallerWindow(
                self._tk_root, self.install_dir, self.apps_dir
            )
        except tk.TclError:
            raise unittest.SkipTest("no display for tkinter")

    def tearDown(self):
        try:
            self.window._root.destroy()
        except Exception:
            pass
        try:
            self._tk_root.destroy()
        except Exception:
            pass
        shutil.rmtree(self._tmp, ignore_errors=True)

    def test_uninstall_needs_the_confirm_box(self):
        """The Uninstall button starts disabled with both boxes
        unticked (U6, U23/U31); ticking the confirm box enables
        it; the app-data box starts unticked."""
        import tkinter as tk

        self.assertEqual(
            self.window._root.title(),
            "Uninstall Reblend Add-on Dev Suite",
        )
        self.assertEqual(
            self.window._uninstall_button["state"], tk.DISABLED
        )
        self.assertEqual(self.window._confirm_var.get(), 0)
        self.assertEqual(self.window._app_data_var.get(), 0)
        self.assertIn(
            str(self.install_dir),
            self.window._will_remove_label["text"],
        )
        self.window._confirm_var.set(1)
        self.window._on_confirm_toggled()
        self.assertEqual(
            self.window._uninstall_button["state"], tk.NORMAL
        )
        self.window._confirm_var.set(0)
        self.window._on_confirm_toggled()
        self.assertEqual(
            self.window._uninstall_button["state"], tk.DISABLED
        )

    def test_nothing_installed_shows_plainly(self):
        """With no install behind it, the window says so and
        keeps everything disabled."""
        import tkinter as tk

        import installer.gui as gui

        empty_dir = self.tmp / "empty-install"
        empty_apps = self.tmp / "empty-applications"
        window = gui.UninstallerWindow(
            self._tk_root, empty_dir, empty_apps
        )
        try:
            self.assertIn(
                "not installed",
                window._progress_label["text"].lower(),
            )
            self.assertEqual(
                window._confirm_box["state"], tk.DISABLED
            )
            self.assertEqual(
                window._app_data_box["state"], tk.DISABLED
            )
            self.assertEqual(
                window._uninstall_button["state"], tk.DISABLED
            )
        finally:
            window._root.destroy()


class UninstallerStandaloneEntryTest(unittest.TestCase):
    """The standalone uninstall entry (``devsuite-uninstall``):
    the uninstall window on its own, with no installer window
    behind it. Needs a display — skips plainly without one (run
    under Xvfb to see it pass)."""

    def setUp(self):
        import tkinter as tk

        WORKSPACE_TMP.mkdir(parents=True, exist_ok=True)
        self._tmp = tempfile.mkdtemp(
            prefix="uninstaller-standalone-", dir=str(WORKSPACE_TMP)
        )
        self.tmp = Path(self._tmp)
        self.install_dir = self.tmp / "install"
        self.apps_dir = self.tmp / "applications"
        self.install_dir.mkdir(parents=True)
        (self.install_dir / "install-info.json").write_text(
            json.dumps({"app": "Reblend Add-on Dev Suite"}),
            encoding="utf-8",
        )
        self.apps_dir.mkdir(parents=True, exist_ok=True)
        (self.apps_dir / DESKTOP_FILENAME).write_text(
            "[Desktop Entry]\n", encoding="utf-8"
        )
        (self.apps_dir / UNINSTALL_DESKTOP_FILENAME).write_text(
            "[Desktop Entry]\n", encoding="utf-8"
        )
        try:
            import installer.gui as gui

            # _mainloop=False: the entry builds the window and
            # returns it, so this thread can drive it.
            self.window = gui.main_uninstall(
                install_dir=self.install_dir,
                applications_dir=self.apps_dir,
                _mainloop=False,
            )
        except tk.TclError:
            raise unittest.SkipTest("no display for tkinter")

    def tearDown(self):
        # The hidden root owns the window: destroying it ends the
        # entry. It may already be gone (the close test destroys
        # it on purpose).
        try:
            self.window._root.master.destroy()
        except Exception:
            pass
        shutil.rmtree(self._tmp, ignore_errors=True)

    def test_standalone_entry_opens_the_window(self):
        """The window appears with both boxes unticked and
        Uninstall disabled, and the will-remove list names both
        menu entries; ticking the confirm box enables Uninstall."""
        import tkinter as tk

        self.assertEqual(
            self.window._root.title(),
            "Uninstall Reblend Add-on Dev Suite",
        )
        self.assertEqual(
            self.window._uninstall_button["state"], tk.DISABLED
        )
        self.assertEqual(self.window._confirm_var.get(), 0)
        self.assertEqual(self.window._app_data_var.get(), 0)
        self.assertIn(
            "menu entry",
            self.window._will_remove_label["text"].lower(),
        )
        self.assertIn(
            "uninstall menu entry",
            self.window._will_remove_label["text"].lower(),
        )
        self.window._confirm_var.set(1)
        self.window._on_confirm_toggled()
        self.assertEqual(
            self.window._uninstall_button["state"], tk.NORMAL
        )

    def test_closing_the_window_ends_the_program(self):
        """The uninstall window is the only window: its Close
        button destroys the hidden root too, or the process would
        sit invisible with nothing on screen. The window's close
        box is bound to the same quit."""
        import tkinter as tk

        root = self.window._root.master
        self.assertTrue(
            self.window._root.protocol("WM_DELETE_WINDOW"),
            "the close box is not bound to quit",
        )
        self.window._close_button.invoke()
        try:
            exists = root.winfo_exists()
        except tk.TclError:
            exists = 0
        self.assertEqual(exists, 0)


if __name__ == "__main__":
    unittest.main()
