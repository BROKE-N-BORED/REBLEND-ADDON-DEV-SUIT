"""Tests for devsuite.ui.blender_test_window — the Qt Blender test
window (§8.3, Phase 5).

Run offscreen with the Qt venv, from the project root (the EGL env
is a sandbox quirk — his PC has system Qt libs; never override HOME):

    LD_LIBRARY_PATH=$HOME/workspace/qt-libs/root/usr/lib/x86_64-linux-gnu \\
    __EGL_VENDOR_LIBRARY_DIRS=$HOME/workspace/qt-libs/root/usr/share/glvnd/egl_vendor.d \\
    QT_QPA_PLATFORM=offscreen TMPDIR=/tmp \\
    ~/workspace/tmp/qt-venv/bin/python -m unittest tests.test_blender_test_window

Blender is not installed in this sandbox, so the runs here go
through the fake Blender (``tests/fake_blender.py``), pointed at
with the DEVSUITE_BLENDER variable the way the drive tests do. A
real Blender run waits for his PC (Phase 5's done-when). On a
Python without PySide6 the whole module skips, so the stdlib suite
still passes there.

The rules under test (DOSSIER.md §8.3, §12 Phase 5, U6, U26):

* The window lists the built Blender add-ons and selects nothing
  by default; Run needs a pick.
* A passing run shows the checklist, the render, and the summary.
* A failing run reports plainly which checks failed, with the
  Blender log one click away.
* Cancel stops a run promptly and says so.
* A missing Blender is a plain message, not a crash; the Reblend
  side is unaffected.
* No project, no actions — the plain message instead.
"""

import os
import shutil
import stat
import tempfile
import time
import unittest
from pathlib import Path

try:
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication
except ImportError:
    raise unittest.SkipTest("PySide6 is not installed")

from devsuite.packing.blender import build_blender_addon
from devsuite.projects.project import create_project
from devsuite.templates import create_project_from_template
from devsuite.ui.blender_test_window import BlenderTestWindow
from devsuite.ui.chat_window import ChatWindow

FAKE_BLENDER = Path(__file__).resolve().parent / "fake_blender.py"


def make_fake_exe(tmp):
    """A runnable copy of the fake Blender in ``tmp``."""
    Path(tmp).mkdir(parents=True, exist_ok=True)
    exe = Path(tmp) / "blender"
    shutil.copy2(FAKE_BLENDER, exe)
    exe.chmod(exe.stat().st_mode | stat.S_IXUSR)
    return exe


class BlenderTestWindowTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._app = QApplication.instance() or QApplication([])

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        tmp = Path(self._tmp.name)
        self._saved_env = dict(os.environ)
        project, error = create_project_from_template(
            "surprise",
            tmp / "surprise",
            name="Surprise",
            targets=["blender"],
            version="1.0.0",
        )
        self.assertIsNone(error)
        project.contributions = {"wheel": [
            {"label": "Surprise", "action": "surprise.randomize"}
        ]}
        self.assertIsNone(project.save())
        self.project = project
        zip_path, _, error = build_blender_addon(
            project, project.packs_dir
        )
        self.assertIsNone(error)
        self.zip_path = zip_path
        self.exe = make_fake_exe(tmp / "bin")
        os.environ["DEVSUITE_BLENDER"] = str(self.exe)
        os.environ["FAKE_BLENDER_MODE"] = "pass"
        self.window = BlenderTestWindow(project=self.project)
        self.window.show()
        QTest.qWait(50)

    def tearDown(self):
        self.window.close()
        QTest.qWait(50)
        os.environ.clear()
        os.environ.update(self._saved_env)
        self._tmp.cleanup()

    # -- helpers --------------------------------------------------

    def _wait_until(self, predicate, timeout_ms=10000):
        """Pump events until ``predicate`` is true, or the timeout
        passes. Workers answer on the event loop, so the test has
        to wait the same way the user does."""
        deadline = time.monotonic() + timeout_ms / 1000
        while True:
            if predicate():
                return True
            if time.monotonic() >= deadline:
                return False
            QTest.qWait(20)

    def _status(self):
        return self.window._status_label.text()

    def _select_zip(self):
        """Pick the first (only) built add-on, the way the user
        does — the window selects nothing on its own."""
        self.window._zip_list.setCurrentRow(0)
        QTest.qWait(20)

    def _run_and_wait(self, timeout_ms=10000):
        QTest.mouseClick(self.window._run_button, Qt.LeftButton)
        done = self._wait_until(
            lambda: not self.window._running, timeout_ms=timeout_ms
        )
        self.assertTrue(done, f"the run never finished: {self._status()}")

    # -- the window itself ----------------------------------------

    def test_window_lists_the_built_addon_and_selects_nothing(self):
        self.assertEqual(self.window._zip_list.count(), 1)
        self.assertEqual(
            self.window._zip_list.item(0).text(),
            "surprise-1.0.0-blender.zip",
        )
        self.assertIsNone(self.window._zip_list.currentItem())
        self.assertFalse(self.window._run_button.isEnabled())
        self._select_zip()
        self.assertTrue(self.window._run_button.isEnabled())

    def test_no_blender_zip_says_so_plainly(self):
        project, error = create_project(
            Path(self._tmp.name) / "empty",
            name="Empty",
            targets=["blender"],
        )
        self.assertIsNone(error)
        window = BlenderTestWindow(project=project)
        try:
            window.show()
            QTest.qWait(50)
            self.assertTrue(window._no_zips_label.isVisible())
            self.assertIn(
                "Build the Blender add-on from the pack window",
                window._no_zips_label.text(),
            )
            self.assertFalse(window._run_button.isEnabled())
        finally:
            window.close()

    def test_no_project_state_shows_plain_message(self):
        window = BlenderTestWindow()
        try:
            window.show()
            QTest.qWait(50)
            self.assertTrue(window._no_project_label.isVisible())
            self.assertIn(
                "Open a project first", window._no_project_label.text()
            )
            self.assertFalse(window._run_button.isEnabled())
        finally:
            window.close()

    def test_blender_missing_state_shows_plain_message(self):
        # A HOME with no Blender in it, and a PATH with none — the
        # drive tests' isolation, applied to the window.
        home = Path(self._tmp.name) / "empty-home"
        home.mkdir()
        bindir = Path(self._tmp.name) / "empty-bin"
        bindir.mkdir()
        os.environ["HOME"] = str(home)
        os.environ["PATH"] = str(bindir)
        os.environ.pop("DEVSUITE_BLENDER", None)
        window = BlenderTestWindow(project=self.project)
        try:
            window.show()
            QTest.qWait(50)
            self.assertIn(
                "Blender is not installed",
                window._blender_label.text(),
            )
            self.assertIn(
                "Reblend side still works",
                window._blender_label.text(),
            )
            self.assertFalse(window._run_button.isEnabled())
        finally:
            window.close()

    # -- runs -----------------------------------------------------

    def test_run_against_fake_passes_and_shows_checks_and_render(self):
        self._select_zip()
        self._run_and_wait()
        self.assertIn("All 5 checks passed", self._status())
        self.assertEqual(len(self.window._check_lines), 5)
        self.assertTrue(
            all(line.startswith("Passed: ")
                for line in self.window._check_lines),
            self.window._check_lines,
        )
        self.assertIn("Loads without errors",
                      "\n".join(self.window._check_lines))
        self.assertIn("Finished in", self.window._elapsed_label.text())
        pixmap = self.window._render_label.pixmap()
        self.assertIsNotNone(pixmap)
        self.assertFalse(pixmap.isNull())
        self.assertIsNotNone(self.window._render_path)
        self.assertTrue(self.window._render_path.is_file())
        # The run record landed beside the render.
        record = self.window._run_dir / "result.json"
        self.assertTrue(record.is_file())

    def test_run_in_fail_mode_reports_plainly_and_log_is_one_click(self):
        os.environ["FAKE_BLENDER_MODE"] = "fail"
        self._select_zip()
        self._run_and_wait()
        self.assertIn("checks failed", self._status())
        self.assertIn(
            "Failed: Loads without errors",
            "\n".join(self.window._check_lines),
        )
        self.assertTrue(self.window._log_button.isEnabled())
        self.assertFalse(self.window._log_text_edit.isVisible())
        QTest.mouseClick(self.window._log_button, Qt.LeftButton)
        QTest.qWait(50)
        self.assertTrue(self.window._log_text_edit.isVisible())
        log = self.window._log_text_edit.toPlainText()
        self.assertIn("Traceback", log)
        self.assertIn("not enabled", log)

    def test_cancel_stops_a_sleeping_fake_promptly(self):
        os.environ["FAKE_BLENDER_MODE"] = "sleep"
        self._select_zip()
        QTest.mouseClick(self.window._run_button, Qt.LeftButton)
        started = self._wait_until(
            lambda: self.window._cancel_button.isEnabled()
        )
        self.assertTrue(started, "the run never started")
        began = time.monotonic()
        QTest.mouseClick(self.window._cancel_button, Qt.LeftButton)
        stopped = self._wait_until(
            lambda: not self.window._running, timeout_ms=10000
        )
        elapsed = time.monotonic() - began
        self.assertTrue(stopped, "the cancel never landed")
        self.assertLess(
            elapsed, 10,
            f"cancel took {elapsed:.1f}s — Blender kept running",
        )
        self.assertEqual(self.window._result_summary,
                         "The test was cancelled.")
        self.assertIn("cancelled", self._status().lower())
        self.assertTrue(self.window._run_button.isEnabled())

    # -- wiring ---------------------------------------------------

    def test_chat_window_menu_opens_blender_test_window(self):
        chat = ChatWindow(project=self.project)
        try:
            chat.show()
            QTest.qWait(50)
            chat._blender_test_window_action.trigger()
            QTest.qWait(100)
            test_window = chat._blender_test_window
            self.assertIsNotNone(test_window)
            self.assertTrue(test_window.isVisible())
            self.assertIn("Surprise", test_window.windowTitle())
            self.assertEqual(test_window._zip_list.count(), 1)
        finally:
            if chat._blender_test_window is not None:
                chat._blender_test_window.close()
            chat.close()

    def test_window_follows_project_switch(self):
        chat = ChatWindow(project=self.project)
        try:
            chat.show()
            QTest.qWait(50)
            chat._blender_test_window_action.trigger()
            QTest.qWait(100)
            test_window = chat._blender_test_window
            self.assertIn("Surprise", test_window.windowTitle())
            other, error = create_project(
                Path(self._tmp.name) / "other",
                name="Other",
                targets=["blender"],
            )
            self.assertIsNone(error)
            chat.set_project(other)
            QTest.qWait(50)
            self.assertIn("Other", test_window.windowTitle())
            self.assertEqual(test_window._zip_list.count(), 0)
            self.assertTrue(test_window._no_zips_label.isVisible())
        finally:
            if chat._blender_test_window is not None:
                chat._blender_test_window.close()
            chat.close()


if __name__ == "__main__":
    unittest.main()
