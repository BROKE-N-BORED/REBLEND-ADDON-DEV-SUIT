"""Tests for devsuite.ui.palette — the command palette (Ctrl+K, Phase 6).

Run offscreen with the Qt venv, from the project root (the EGL env
is a sandbox quirk — his PC has system Qt libs; never override HOME):

    LD_LIBRARY_PATH=$HOME/workspace/qt-libs/root/usr/lib/x86_64-linux-gnu \\
    __EGL_VENDOR_LIBRARY_DIRS=$HOME/workspace/qt-libs/root/usr/share/glvnd/egl_vendor.d \\
    QT_QPA_PLATFORM=offscreen TMPDIR=/tmp \\
    ~/workspace/tmp/qt-venv/bin/python -m unittest tests.test_palette

On a Python without PySide6 the whole module skips, so the stdlib
suite still passes there.

The rules under test (DOSSIER.md §6.10, entry 043, U6):

* Ctrl+K opens the palette over the chat window; the Window menu
  offers it too.
* Typing narrows the list by substring match; an empty query shows
  every command; a query with no match says so plainly.
* With nothing typed, nothing is selected, and Enter does nothing.
  Once the user has typed, the first match is selected, and Enter
  runs it; clicking a row runs it too.
* Esc closes the palette without running anything.
* A command that needs a project says so plainly when none is
  open, never a crash, never silence.
"""

import json
import os
import shutil
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

try:
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication
except ImportError:
    raise unittest.SkipTest("PySide6 is not installed")

from devsuite.packing.blender import build_blender_addon
from devsuite.projects.project import create_project
from devsuite.templates import template_dir
from devsuite.ui.chat_window import ChatWindow

TEMPLATE = template_dir("surprise")


class FakeClient:
    """A stand-in for OllamaClient: answers chat() with a canned
    reply (or a canned error), and needs no server."""

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


def seed_template_files(project):
    """Copy the Surprise template into ``project``, as the suite
    does when a project starts from a template."""
    shutil.copytree(
        TEMPLATE / "src", project.root / "src", dirs_exist_ok=True
    )
    shutil.copy2(TEMPLATE / "README.md", project.root / "README.md")


class PaletteTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._app = QApplication.instance() or QApplication([])

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        tmp = Path(self._tmp.name)
        project, error = create_project(
            tmp / "surprise",
            name="Surprise",
            description="Randomize a material for inspiration.",
            targets=["reblend", "blender"],
            version="1.0.0",
            author="Joshua Lofland",
        )
        self.assertIsNone(error)
        self.project = project
        seed_template_files(project)
        self.client = FakeClient(reply=json.dumps(write_plan()))
        self.window = ChatWindow(client=self.client, project=self.project)
        self.window.show()
        QTest.qWait(50)

    def tearDown(self):
        # The palette opens real windows; close them all, or they
        # outlive the chat window and leak into the next test.
        for attr in (
            "_pack_window", "_library_window",
            "_blender_test_window", "_palette",
        ):
            child = getattr(self.window, attr, None)
            if child is not None:
                child.close()
        self.window.close()
        QTest.qWait(50)
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

    def _chat_text(self):
        return "\n".join(text for _, text in self.window._message_texts)

    def _open_palette(self):
        """Open the palette through the chat window's own handler."""
        self.window._on_palette()
        QTest.qWait(50)
        palette = self.window._palette
        self.assertTrue(palette.isVisible())
        return palette

    def _run_command(self, query):
        """Open the palette, type ``query``, press Enter: the
        first match runs."""
        palette = self._open_palette()
        palette._input.setText(query)
        QTest.qWait(50)
        QTest.keyClick(palette._input, Qt.Key_Return)
        QTest.qWait(50)

    # -- opening --------------------------------------------------

    def test_ctrl_k_opens_the_palette(self):
        self.window.activateWindow()
        QTest.qWait(50)
        QTest.keyClick(self.window, Qt.Key_K, Qt.ControlModifier)
        QTest.qWait(50)
        palette = self.window._palette
        self.assertIsNotNone(palette)
        self.assertTrue(palette.isVisible())
        # Every command is listed, and nothing is selected (U6).
        self.assertIn("Open Pack window", palette.visible_labels())
        self.assertIn("Build Reblend pack", palette.visible_labels())
        self.assertIn("Undo last build", palette.visible_labels())
        self.assertIsNone(palette._tree.currentItem())

    def test_window_menu_opens_the_palette(self):
        self.window._palette_action.trigger()
        QTest.qWait(50)
        self.assertIsNotNone(self.window._palette)
        self.assertTrue(self.window._palette.isVisible())

    def test_palette_is_reused_not_rebuilt(self):
        first = self._open_palette()
        QTest.keyClick(first._input, Qt.Key_Escape)
        QTest.qWait(50)
        second = self._open_palette()
        self.assertIs(first, second)

    # -- filtering and selection ----------------------------------

    def test_typing_filters_the_list(self):
        palette = self._open_palette()
        QTest.keyClicks(palette._input, "pack")
        QTest.qWait(50)
        self.assertEqual(
            palette.visible_labels(),
            ["Build Reblend pack", "Open Pack window"],
        )
        # Typing selects the first match.
        self.assertEqual(
            palette._tree.currentItem().text(0), "Build Reblend pack"
        )
        palette._input.setText("build")
        QTest.qWait(50)
        self.assertEqual(
            palette.visible_labels(),
            [
                "Undo last build",
                "Build Reblend pack",
                "Build Blender add-on",
            ],
        )

    def test_nonsense_query_shows_plain_no_match_line(self):
        palette = self._open_palette()
        palette._input.setText("zzzqqq")
        QTest.qWait(50)
        self.assertEqual(palette.visible_labels(), [])
        self.assertTrue(palette._no_match_label.isVisible())
        self.assertEqual(
            palette._no_match_label.text(), "No command matches that."
        )
        # Enter with no match runs nothing, and the palette stays
        # open so the user can fix the query.
        QTest.keyClick(palette._input, Qt.Key_Return)
        QTest.qWait(50)
        self.assertTrue(palette.isVisible())
        self.assertIsNone(self.window._pack_window)

    def test_enter_with_nothing_selected_does_nothing(self):
        palette = self._open_palette()
        self.assertIsNone(palette._tree.currentItem())
        QTest.keyClick(palette._input, Qt.Key_Return)
        QTest.qWait(50)
        self.assertTrue(palette.isVisible())
        self.assertIsNone(self.window._pack_window)

    def test_arrow_keys_move_the_selection(self):
        palette = self._open_palette()
        palette._input.setText("build")
        QTest.qWait(50)
        self.assertEqual(
            palette._tree.currentItem().text(0), "Undo last build"
        )
        QTest.keyClick(palette._input, Qt.Key_Down)
        QTest.qWait(20)
        self.assertEqual(
            palette._tree.currentItem().text(0), "Build Reblend pack"
        )
        QTest.keyClick(palette._input, Qt.Key_Up)
        QTest.qWait(20)
        self.assertEqual(
            palette._tree.currentItem().text(0), "Undo last build"
        )

    # -- running --------------------------------------------------

    def test_enter_runs_the_filtered_command(self):
        palette = self._open_palette()
        palette._input.setText("Pack window")
        QTest.qWait(50)
        self.assertEqual(palette.visible_labels(), ["Open Pack window"])
        QTest.keyClick(palette._input, Qt.Key_Return)
        QTest.qWait(50)
        self.assertFalse(palette.isVisible())
        self.assertIsNotNone(self.window._pack_window)
        self.assertTrue(self.window._pack_window.isVisible())

    def test_esc_closes_without_running_anything(self):
        palette = self._open_palette()
        palette._input.setText("Pack window")
        QTest.qWait(50)
        QTest.keyClick(palette._input, Qt.Key_Escape)
        QTest.qWait(50)
        self.assertFalse(palette.isVisible())
        self.assertIsNone(self.window._pack_window)

    def test_clicking_a_row_runs_it(self):
        palette = self._open_palette()
        tree = palette._tree
        item = None
        for row in range(tree.topLevelItemCount()):
            candidate = tree.topLevelItem(row)
            if candidate.text(0) == "Open Library window":
                item = candidate
                break
        self.assertIsNotNone(item)
        rect = tree.visualItemRect(item)
        QTest.mouseClick(tree.viewport(), Qt.LeftButton, pos=rect.center())
        QTest.qWait(50)
        self.assertFalse(palette.isVisible())
        self.assertIsNotNone(self.window._library_window)
        self.assertTrue(self.window._library_window.isVisible())

    def test_build_command_builds_the_pack(self):
        # The pack window records the build in the shelf: point the
        # shelf at a throwaway file, so the test never writes the
        # real library.
        shelf_path = Path(self._tmp.name) / "shelf.json"
        with mock.patch(
            "devsuite.ui.pack_window.default_shelf_path",
            return_value=shelf_path,
        ):
            self._run_command("Build Reblend pack")
            pack = self.project.packs_dir / "surprise-1.0.0.rblpack"
            built = self._wait_until(lambda: pack.is_file())
            self.assertTrue(built, "the pack never landed")
            self.assertIsNotNone(self.window._pack_window)
            self.assertTrue(self.window._pack_window.isVisible())

    def test_build_command_with_no_project_says_so_plainly(self):
        window = ChatWindow(client=FakeClient())
        try:
            window.show()
            QTest.qWait(50)
            window._on_palette()
            QTest.qWait(50)
            palette = window._palette
            palette._input.setText("Build Reblend pack")
            QTest.qWait(50)
            QTest.keyClick(palette._input, Qt.Key_Return)
            QTest.qWait(50)
            self.assertFalse(palette.isVisible())
            text = "\n".join(body for _, body in window._message_texts)
            self.assertIn("Open a project first", text)
        finally:
            window.close()

    def test_undo_with_nothing_to_undo_says_so_plainly(self):
        self._run_command("Undo last build")
        self.assertIn("Nothing to undo yet", self._chat_text())

    def test_run_blender_test_with_no_blender_says_so_plainly(self):
        # One Blender add-on built, so the command picks it — but
        # Blender is not installed in this sandbox, so the run
        # cannot start, and the chat says so plainly.
        zip_path, warnings, error = build_blender_addon(
            self.project, self.project.packs_dir
        )
        self.assertIsNone(error)
        saved = os.environ.pop("DEVSUITE_BLENDER", None)
        try:
            self._run_command("Run Blender test")
        finally:
            if saved is not None:
                os.environ["DEVSUITE_BLENDER"] = saved
        self.assertIsNotNone(self.window._blender_test_window)
        self.assertTrue(self.window._blender_test_window.isVisible())
        self.assertIn("Blender is not installed", self._chat_text())

    def test_plan_commands_appear_when_a_plan_is_pending(self):
        self.window._input.setText("Add a button")
        QTest.mouseClick(self.window._send_button, Qt.LeftButton)
        arrived = self._wait_until(
            lambda: self.window._plan_card.isVisible()
        )
        self.assertTrue(arrived, "the plan card never appeared")
        palette = self._open_palette()
        palette._input.setText("plan")
        QTest.qWait(50)
        self.assertEqual(
            palette.visible_labels(),
            ["Build the plan", "Dismiss the plan"],
        )
        QTest.keyClick(palette._input, Qt.Key_Down)
        QTest.qWait(20)
        QTest.keyClick(palette._input, Qt.Key_Return)
        QTest.qWait(50)
        self.assertFalse(self.window._plan_card.isVisible())
        self.assertIn("Nothing changed", self._chat_text())


if __name__ == "__main__":
    unittest.main()
