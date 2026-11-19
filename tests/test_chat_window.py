"""Tests for devsuite.ui.chat_window — the Qt chat window (Phase 2b).

Run offscreen with the Qt venv, from the project root (the EGL env
is a sandbox quirk — his PC has system Qt libs; never override HOME):

    LD_LIBRARY_PATH=$HOME/workspace/qt-libs/root/usr/lib/x86_64-linux-gnu \\
    __EGL_VENDOR_LIBRARY_DIRS=$HOME/workspace/qt-libs/root/usr/share/glvnd/egl_vendor.d \\
    QT_QPA_PLATFORM=offscreen TMPDIR=/tmp \\
    ~/workspace/tmp/qt-venv/bin/python -m unittest tests.test_chat_window

The window takes a fake Ollama client, so no server is needed. On a
Python without PySide6 the whole module skips, so the stdlib suite
still passes there.

The rules under test (DOSSIER.md §6.3, §7.2, §7.4, §9.6):

* Sending a message asks the model for a plan and shows the plan
  card; nothing is built before approval.
* Build it applies exactly the plan shown; Not this changes
  nothing.
* Undo restores the project to how it was before the last build.
* Ollama down shows a plain-words error, never a crash.
* With no project open, sending says plainly to open one first.
"""

import json
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

from devsuite.chat.ollama import OllamaClient
from devsuite.projects.project import create_project
from devsuite.ui.chat_window import ChatWindow


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


def slow_plan():
    """A plan that writes one file, then runs a check that sleeps
    for 30 seconds — long enough to cancel mid-build."""
    return {
        "summary": "Write the file, then run a slow check.",
        "target": "reblend",
        "steps": [
            {
                "action": "write_file",
                "path": "src/addon.py",
                "content": "VALUE = 1\n",
            },
            {
                "action": "run_check",
                "name": "A slow check",
                "command": [
                    "python3", "-c",
                    "import time; time.sleep(30)",
                ],
            },
        ],
    }


def edit_plan():
    """A plan that changes the value in the addon file."""
    return {
        "summary": "Change the value in the addon file.",
        "target": "reblend",
        "steps": [
            {
                "action": "edit_file",
                "path": "src/addon.py",
                "old": "VALUE = 1",
                "new": "VALUE = 2",
            }
        ],
    }


class ChatWindowTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._app = QApplication.instance() or QApplication([])

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        project, error = create_project(
            Path(self._tmp.name) / "test-addon", name="Test Addon"
        )
        self.assertIsNone(error)
        self.project = project
        self.client = FakeClient(reply=json.dumps(write_plan()))
        self.window = ChatWindow(client=self.client, project=self.project)
        self.window.show()
        QTest.qWait(50)

    def tearDown(self):
        self.window.close()
        QTest.qWait(50)
        self._tmp.cleanup()

    # -- helpers --------------------------------------------------

    def _wait_until(self, predicate, timeout_ms=5000):
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

    def _chat_text(self):
        return "\n".join(text for _, text in self.window._message_texts)

    def _send(self, text):
        self.window._input.setText(text)
        QTest.mouseClick(self.window._send_button, Qt.LeftButton)

    def _send_and_wait_for_plan(self, text="Add a button"):
        self._send(text)
        arrived = self._wait_until(
            lambda: self.window._plan_card.isVisible()
        )
        self.assertTrue(arrived, "the plan card never appeared")
        return arrived

    # -- the window itself ----------------------------------------

    def test_window_opens_with_no_project(self):
        window = ChatWindow(client=FakeClient())
        try:
            window.show()
            QTest.qWait(50)
            self.assertIn("No project open", window.windowTitle())
            text = "\n".join(
                body for _, body in window._message_texts
            )
            self.assertIn("No project open yet", text)
        finally:
            window.close()

    def test_send_without_project_says_so_plainly(self):
        window = ChatWindow(client=FakeClient())
        try:
            window.show()
            QTest.qWait(50)
            window._input.setText("Add a button")
            QTest.mouseClick(window._send_button, Qt.LeftButton)
            QTest.qWait(50)
            text = "\n".join(
                body for _, body in window._message_texts
            )
            self.assertIn("Open a project first", text)
            self.assertFalse(window._plan_card.isVisible())
        finally:
            window.close()

    # -- the loop -------------------------------------------------

    def test_send_shows_plan_card(self):
        self._send_and_wait_for_plan()
        self.assertIn(
            "Write the addon file.", self.window._plan_summary.text()
        )
        self.assertIn(
            "Write src/addon.py", self.window._plan_steps.text()
        )
        # Nothing is built before approval.
        self.assertFalse((self.project.root / "src" / "addon.py").exists())

    def test_build_it_applies_plan(self):
        self._send_and_wait_for_plan()
        QTest.mouseClick(self.window._build_button, Qt.LeftButton)
        built = self._wait_until(lambda: "Built it" in self._chat_text())
        self.assertTrue(built, "the build result never appeared")
        addon = self.project.root / "src" / "addon.py"
        self.assertTrue(addon.is_file())
        self.assertEqual(addon.read_text(encoding="utf-8"), "VALUE = 1\n")
        self.assertIn("Wrote src/addon.py", self._chat_text())
        self.assertTrue(self.window._undo_button.isEnabled())

    def test_not_this_changes_nothing(self):
        self._send_and_wait_for_plan()
        QTest.mouseClick(self.window._not_this_button, Qt.LeftButton)
        QTest.qWait(50)
        self.assertFalse(self.window._plan_card.isVisible())
        self.assertFalse((self.project.root / "src" / "addon.py").exists())
        self.assertIn("Nothing changed", self._chat_text())
        self.assertFalse(self.window._undo_button.isEnabled())

    # -- undo -----------------------------------------------------

    def test_undo_removes_created_file(self):
        self._send_and_wait_for_plan()
        QTest.mouseClick(self.window._build_button, Qt.LeftButton)
        self.assertTrue(
            self._wait_until(lambda: "Built it" in self._chat_text())
        )
        addon = self.project.root / "src" / "addon.py"
        self.assertTrue(addon.is_file())
        QTest.mouseClick(self.window._undo_button, Qt.LeftButton)
        QTest.qWait(50)
        self.assertFalse(addon.exists())
        self.assertIn("Undid the last build", self._chat_text())
        self.assertIn("src/addon.py", self._chat_text())

    def test_undo_restores_edited_file(self):
        addon = self.project.root / "src" / "addon.py"
        addon.write_text("VALUE = 1\n", encoding="utf-8")
        self.window._client = FakeClient(reply=json.dumps(edit_plan()))
        self._send_and_wait_for_plan("Change the value")
        QTest.mouseClick(self.window._build_button, Qt.LeftButton)
        self.assertTrue(
            self._wait_until(lambda: "Built it" in self._chat_text())
        )
        self.assertEqual(addon.read_text(encoding="utf-8"), "VALUE = 2\n")
        QTest.mouseClick(self.window._undo_button, Qt.LeftButton)
        QTest.qWait(50)
        self.assertEqual(addon.read_text(encoding="utf-8"), "VALUE = 1\n")
        self.assertIn("Undid the last build", self._chat_text())

    # -- cancel -------------------------------------------------

    def test_cancel_during_build_stops_it(self):
        self.window._client = FakeClient(reply=json.dumps(slow_plan()))
        self._send_and_wait_for_plan("Write it, then check slowly")
        QTest.mouseClick(self.window._build_button, Qt.LeftButton)
        addon = self.project.root / "src" / "addon.py"
        # The first step lands, so the slow check is running.
        landed = self._wait_until(lambda: addon.is_file())
        self.assertTrue(landed, "the first step never ran")
        self.assertTrue(self.window._cancel_button.isVisible())
        QTest.mouseClick(self.window._cancel_button, Qt.LeftButton)
        stopped = self._wait_until(
            lambda: "Cancelled the build" in self._chat_text(),
            timeout_ms=10000,
        )
        self.assertTrue(stopped, "the cancel was never reported")
        self.assertIn("Wrote src/addon.py", self._chat_text())
        self.assertTrue(self.window._undo_button.isEnabled())

    # -- plain-words errors ---------------------------------------

    def test_ollama_down_plain_words_error(self):
        self.window._client = FakeClient(
            error="Ollama is not running on this computer. "
            "Start Ollama and try again."
        )
        self._send("Add a button")
        shown = self._wait_until(
            lambda: "Ollama is not running" in self._chat_text()
        )
        self.assertTrue(shown, "the Ollama error never appeared")
        self.assertFalse(self.window._plan_card.isVisible())

    def test_ollama_down_real_client_dead_port(self):
        """The real client against a port nothing listens on: the
        refusal travels through the loop and the window as the same
        plain-words sentence."""
        self.window._client = OllamaClient(
            base_url="http://127.0.0.1:1", timeout=5
        )
        self._send("Add a button")
        shown = self._wait_until(
            lambda: "Ollama is not running" in self._chat_text(),
            timeout_ms=10000,
        )
        self.assertTrue(shown, "the Ollama error never appeared")
        self.assertFalse(self.window._plan_card.isVisible())


if __name__ == "__main__":
    unittest.main()
