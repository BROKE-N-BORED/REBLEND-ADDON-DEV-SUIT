"""Tests for the measurements strip in the chat window (DOSSIER.md §6.10, U37).

Run offscreen with the Qt venv, from the project root (the EGL env
is a sandbox quirk — his PC has system Qt libs; never override HOME):

    LD_LIBRARY_PATH=$HOME/workspace/qt-libs/root/usr/lib/x86_64-linux-gnu \\
    __EGL_VENDOR_LIBRARY_DIRS=$HOME/workspace/qt-libs/root/usr/share/glvnd/egl_vendor.d \\
    QT_QPA_PLATFORM=offscreen TMPDIR=/tmp \\
    ~/workspace/tmp/qt-venv/bin/python -m unittest tests.test_measurements_strip

The strip shows the newest real numbers from the suite's own work,
live: the last model reply, the last build, the last pack build
and size, the last Blender test and its checks. The pack build and
the Blender test run for real here (the Blender test through the
fake Blender, the way the drive tests do). On a Python without
PySide6 the whole module skips, so the stdlib suite still passes
there.

The rules under test (DOSSIER.md §6.10, §9.5, U37):

* With nothing measured yet, the strip says so plainly — never a
  zero that was never measured.
* A measurement recorded anywhere in the suite shows up in the
  strip the moment it lands.
* A real pack build updates the strip with a duration and a size.
* A real Blender test updates the strip with a duration and its
  checks.
* A plan and a build in the chat update the strip with the model
  reply time and the build time.
* A reply that never came back records nothing.
"""

import json
import os
import shutil
import stat
import tempfile
import time
import unittest
from pathlib import Path

try:
    from PySide6.QtCore import QSettings, Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication
except ImportError:
    raise unittest.SkipTest("PySide6 is not installed")

from devsuite.measure.measurements import clear, record
from devsuite.packing.blender import build_blender_addon
from devsuite.templates import create_project_from_template
from devsuite.ui.blender_test_window import BlenderTestWindow
from devsuite.ui.chat_window import ChatWindow
from devsuite.ui.pack_window import PackWindow

FAKE_BLENDER = Path(__file__).resolve().parent / "fake_blender.py"


class FakeClient:
    """A stand-in for OllamaClient: answers chat() with a canned reply
    (or a canned error), and needs no server."""

    def __init__(self, reply=None, error=None):
        self.reply = reply
        self.error = error

    def chat(self, model, messages, timeout=None):
        return self.reply, self.error


def write_plan():
    """A plan that writes one new file."""
    return {
        "summary": "Write the addon file.",
        "target": "reblend",
        "steps": [
            {
                "action": "write_file",
                "path": "src/addon.py",
                "content": "VALUE = 1\n",
            }
        ],
    }


def make_fake_exe(directory):
    """A copy of the fake Blender that can be run directly (the
    same mechanism the drive tests use)."""
    directory.mkdir(parents=True, exist_ok=True)
    exe = directory / "blender"
    shutil.copy2(FAKE_BLENDER, exe)
    exe.chmod(exe.stat().st_mode | stat.S_IXUSR)
    return exe


class MeasurementsStripTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._app = QApplication.instance() or QApplication([])

    def setUp(self):
        # The store is session-global: every test starts empty, so
        # a measurement from an earlier test never leaks into the
        # next one.
        clear()
        self._tmp = tempfile.TemporaryDirectory()
        tmp = Path(self._tmp.name)
        self._saved_env = dict(os.environ)
        project, error = create_project_from_template(
            "surprise",
            tmp / "surprise",
            name="Surprise",
            targets=["reblend", "blender"],
            version="1.0.0",
        )
        self.assertIsNone(error)
        self.project = project
        self.client = FakeClient(reply=json.dumps(write_plan()))
        self.window = ChatWindow(client=self.client, project=self.project)
        self.window.show()
        self.exe = make_fake_exe(tmp / "bin")
        os.environ["DEVSUITE_BLENDER"] = str(self.exe)
        os.environ["FAKE_BLENDER_MODE"] = "pass"
        QTest.qWait(50)

    def tearDown(self):
        self.window.close()
        QTest.qWait(50)
        os.environ.clear()
        os.environ.update(self._saved_env)
        clear()
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

    def _strip_text(self):
        return self.window._measurements_label.text()

    def _chat_text(self):
        return "\n".join(text for _, text in self.window._message_texts)

    # -- the strip itself -----------------------------------------

    def test_fresh_window_shows_nothing_measured_yet(self):
        self.assertIn("Nothing measured yet", self._strip_text())
        self.assertIn(
            "Build or test something and the numbers show up here",
            self._strip_text(),
        )

    def test_recording_a_measurement_shows_it_in_the_strip(self):
        record("Last build", 2.3, "seconds")
        # The strip refreshes the moment the number lands — no
        # manual refresh, no waiting.
        self.assertIn("Last build: 2.3 seconds", self._strip_text())
        record("Last pack size", 12.4, "KB")
        self.assertIn("Last pack size: 12.4 KB", self._strip_text())
        # The earlier measurement is still there, in record order.
        self.assertLess(
            self._strip_text().index("Last build"),
            self._strip_text().index("Last pack size"),
        )

    # -- real work, measured --------------------------------------

    def test_real_pack_build_updates_the_strip(self):
        tmp = Path(self._tmp.name)
        settings = QSettings(
            str(tmp / "settings.ini"), QSettings.IniFormat
        )
        pack_window = PackWindow(
            project=self.project, settings=settings,
            shelf_path=tmp / "shelf.json",
        )
        try:
            pack_window.show()
            QTest.qWait(50)
            QTest.mouseClick(
                pack_window._build_reblend_button, Qt.LeftButton
            )
            built = self._wait_until(
                lambda: "surprise-1.0.0.rblpack"
                in pack_window._status_label.text()
            )
            self.assertTrue(
                built,
                "the build never finished: "
                f"{pack_window._status_label.text()}",
            )
            strip = self._strip_text()
            self.assertIn("Last pack build:", strip)
            self.assertIn("seconds", strip)
            self.assertIn("Last pack size:", strip)
            self.assertIn("KB", strip)
        finally:
            pack_window.close()

    def test_real_blender_test_updates_the_strip(self):
        zip_path, _, error = build_blender_addon(
            self.project, self.project.packs_dir
        )
        self.assertIsNone(error)
        test_window = BlenderTestWindow(project=self.project)
        try:
            test_window.show()
            QTest.qWait(50)
            test_window._zip_list.setCurrentRow(0)
            QTest.mouseClick(test_window._run_button, Qt.LeftButton)
            finished = self._wait_until(
                lambda: not test_window._running, timeout_ms=30000
            )
            self.assertTrue(finished, "the test run never finished")
            strip = self._strip_text()
            self.assertIn("Last Blender test:", strip)
            self.assertIn("seconds", strip)
            self.assertIn(
                "Last Blender checks: 5 of 5 checks", strip
            )
        finally:
            test_window.close()

    def test_chat_plan_and_build_update_the_strip(self):
        self.window._input.setText("Add a button")
        QTest.mouseClick(self.window._send_button, Qt.LeftButton)
        arrived = self._wait_until(
            lambda: self.window._plan_card.isVisible()
        )
        self.assertTrue(arrived, "the plan card never appeared")
        self.assertIn("Last model reply:", self._strip_text())
        QTest.mouseClick(self.window._build_button, Qt.LeftButton)
        built = self._wait_until(
            lambda: "Built it." in self._chat_text()
        )
        self.assertTrue(built, "the build never finished")
        self.assertIn("Last build:", self._strip_text())

    def test_a_failed_reply_records_nothing(self):
        window = ChatWindow(
            client=FakeClient(error="Ollama is not running."),
            project=self.project,
        )
        try:
            window.show()
            QTest.qWait(50)
            window._input.setText("Add a button")
            QTest.mouseClick(window._send_button, Qt.LeftButton)
            arrived = self._wait_until(
                lambda: "Ollama is not running" in "\n".join(
                    text for _, text in window._message_texts
                )
            )
            self.assertTrue(arrived, "the error never appeared")
            self.assertIn("Nothing measured yet", self._strip_text())
        finally:
            window.close()


if __name__ == "__main__":
    unittest.main()
