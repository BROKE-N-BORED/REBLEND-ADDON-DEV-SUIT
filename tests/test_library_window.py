"""Tests for devsuite.ui.library_window — the Qt library window (§6.9).

Run offscreen with the Qt venv, from the project root (the EGL env
is a sandbox quirk — his PC has system Qt libs; never override HOME):

    LD_LIBRARY_PATH=$HOME/workspace/qt-libs/root/usr/lib/x86_64-linux-gnu \\
    __EGL_VENDOR_LIBRARY_DIRS=$HOME/workspace/qt-libs/root/usr/share/glvnd/egl_vendor.d \\
    QT_QPA_PLATFORM=offscreen TMPDIR=/tmp \\
    ~/workspace/tmp/qt-venv/bin/python -m unittest tests.test_library_window

The shelf is seeded through a real pack-window build, not by
hand-writing the shelf file, so the tests prove the build hook
works end to end. On a Python without PySide6 the whole module
skips, so the stdlib suite still passes there.

The rules under test (DOSSIER.md §6.9, §5.4, U23/U31):

* The library shows every pack the suite has built, with icon,
  name, version, target, last test result, and a one-line
  description.
* A pack whose file is gone says so plainly and can be removed
  from the shelf — never a crash, never a silent skip.
* Reinstall copies the built file and says where it put it.
* Delete confirms (defaulting to No) and removes the file AND
  its shelf entry; cancelling keeps both.
* Templates are discovered by scanning, and starting a project
  from one lands the files in the §5.4 layout.
"""

import tempfile
import time
import unittest
from pathlib import Path

try:
    from PySide6.QtCore import QSettings, Qt, QTimer
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import (
        QApplication,
        QMessageBox,
    )
except ImportError:
    raise unittest.SkipTest("PySide6 is not installed")

from devsuite.library.shelf import add_entry, load_shelf
from devsuite.projects.project import load_project
from devsuite.templates import create_project_from_template
from devsuite.ui.chat_window import ChatWindow
from devsuite.ui.library_window import LibraryWindow
from devsuite.ui.pack_window import PackWindow


class LibraryWindowTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._app = QApplication.instance() or QApplication([])

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        tmp = Path(self._tmp.name)
        project, error = create_project_from_template(
            "surprise",
            tmp / "surprise",
            name="Surprise",
            targets=["reblend", "blender"],
            version="1.0.0",
        )
        self.assertIsNone(error)
        self.project = project
        # Throwaway settings and shelf: the tests never touch the
        # real remembered install folders or the real library.
        self.settings = QSettings(
            str(tmp / "settings.ini"), QSettings.IniFormat
        )
        self.shelf_path = tmp / "shelf.json"
        self.pack_window = PackWindow(
            project=self.project, settings=self.settings,
            shelf_path=self.shelf_path,
        )
        self.pack_window.show()
        self.opened: list[str] = []
        self.window = LibraryWindow(
            open_project=lambda path: self.opened.append(str(path)),
            settings=self.settings,
            shelf_path=self.shelf_path,
        )
        self.window.show()
        QTest.qWait(50)

    def tearDown(self):
        self.window.close()
        self.pack_window.close()
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

    def _build_pack(self, button, built_name):
        """Build through the pack window and wait for it to land."""
        QTest.mouseClick(button, Qt.LeftButton)
        built = self._wait_until(
            lambda: built_name in self.pack_window._status_label.text()
        )
        self.assertTrue(
            built,
            "the build never finished: "
            f"{self.pack_window._status_label.text()}",
        )
        return self.project.packs_dir / built_name

    def _pack_status(self):
        return self.pack_window._status_label.text()

    def _status(self):
        return self.window._status_label.text()

    def _click_message_box(self, button_role):
        """Click a button on the message box that is showing (used
        with a QTimer single shot scheduled BEFORE the click that
        opens the dialog — a modal dialog blocks the test thread
        otherwise)."""
        for widget in QApplication.topLevelWidgets():
            if isinstance(widget, QMessageBox):
                button = widget.button(button_role)
                self.assertIsNotNone(button)
                QTest.mouseClick(button, Qt.LeftButton)
                return
        self.fail("no message box was showing")

    # -- the shelf ------------------------------------------------

    def test_empty_shelf_shows_plain_message(self):
        self.window.refresh()
        labels = [
            label.text() for label in self.window.findChildren(
                type(self.window._status_label)
            )
        ]
        self.assertTrue(
            any("Nothing built yet" in text for text in labels),
            f"no empty-shelf message in {labels}",
        )
        self.assertEqual(self.window._pack_cards, [])

    def test_library_shows_a_built_pack(self):
        pack = self._build_pack(
            self.pack_window._build_reblend_button,
            "surprise-1.0.0.rblpack",
        )
        self.assertTrue(pack.is_file())
        # The build recorded itself in the shelf — the hook works.
        entries, error = load_shelf(self.shelf_path)
        self.assertIsNone(error)
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["project_name"], "Surprise")
        self.assertEqual(entries[0]["target"], "reblend")
        # And the library shows it when it opens again.
        self.window.refresh()
        self.assertEqual(len(self.window._pack_cards), 1)
        card = self.window._pack_cards[0]
        self.assertFalse(card["gone"])
        self.assertEqual(card["entry"]["project_name"], "Surprise")
        self.assertEqual(card["entry"]["version"], "1.0.0")

    def test_open_project_calls_back_with_the_project(self):
        self._build_pack(
            self.pack_window._build_reblend_button,
            "surprise-1.0.0.rblpack",
        )
        self.window.refresh()
        card = self.window._pack_cards[0]
        QTest.mouseClick(card["open_button"], Qt.LeftButton)
        self.assertEqual(self.opened, [str(self.project.root)])

    def test_missing_file_shows_gone_state_and_removes_cleanly(self):
        pack = self._build_pack(
            self.pack_window._build_reblend_button,
            "surprise-1.0.0.rblpack",
        )
        pack.unlink()  # Moved or deleted outside the suite.
        self.window.refresh()
        QTest.qWait(50)  # Let the rebuilt cards lay out and show.
        self.assertEqual(len(self.window._pack_cards), 1)
        card = self.window._pack_cards[0]
        self.assertTrue(card["gone"])
        self.assertFalse(card["reinstall_button"].isVisible())
        self.assertFalse(card["delete_button"].isVisible())
        self.assertTrue(card["remove_button"].isVisible())
        QTest.mouseClick(card["remove_button"], Qt.LeftButton)
        QTest.qWait(50)
        entries, _ = load_shelf(self.shelf_path)
        self.assertEqual(entries, [])
        self.assertEqual(self.window._pack_cards, [])
        # The project itself is untouched.
        self.assertTrue((self.project.root / "project.json").is_file())

    def test_reinstall_copies_the_file(self):
        self._build_pack(
            self.pack_window._build_reblend_button,
            "surprise-1.0.0.rblpack",
        )
        self.window.refresh()
        install_dir = Path(self._tmp.name) / "packs"
        self.window.set_install_folder("reblend", install_dir)
        card = self.window._pack_cards[0]
        QTest.mouseClick(card["reinstall_button"], Qt.LeftButton)
        installed = install_dir / "surprise-1.0.0.rblpack"
        self.assertTrue(installed.is_file())
        self.assertIn("Installed in Reblend at", self._status())
        self.assertIn(str(installed), self._status())

    def test_reinstall_with_an_unknown_target_fails_plainly(self):
        # A shelf entry whose target is neither program is damaged,
        # not a Blender add-on: reinstall must say so, not guess.
        self._build_pack(
            self.pack_window._build_reblend_button,
            "surprise-1.0.0.rblpack",
        )
        entries, error = load_shelf(self.shelf_path)
        self.assertIsNone(error)
        entry = dict(entries[0])
        entry["target"] = "something-else"
        self.assertIsNone(add_entry(self.shelf_path, entry))
        self.window.refresh()
        card = self.window._pack_cards[0]
        self.assertEqual(card["entry"]["target"], "something-else")
        installs = Path(self._tmp.name) / "installs"
        self.window.set_install_folder("something-else", installs)
        QTest.mouseClick(card["reinstall_button"], Qt.LeftButton)
        QTest.qWait(50)
        self.assertIn("does not say which program", self._status())
        # Nothing was installed anywhere.
        self.assertFalse(installs.exists())

    def test_delete_removes_file_and_entry(self):
        pack = self._build_pack(
            self.pack_window._build_reblend_button,
            "surprise-1.0.0.rblpack",
        )
        self.window.refresh()
        card = self.window._pack_cards[0]
        QTimer.singleShot(
            200, lambda: self._click_message_box(QMessageBox.Yes)
        )
        QTest.mouseClick(card["delete_button"], Qt.LeftButton)
        self.assertFalse(pack.exists())
        entries, _ = load_shelf(self.shelf_path)
        self.assertEqual(entries, [])
        self.assertEqual(self.window._pack_cards, [])
        self.assertIn("Deleted Surprise", self._status())
        # The project itself stays.
        self.assertTrue((self.project.root / "project.json").is_file())

    def test_delete_cancelled_keeps_file_and_entry(self):
        pack = self._build_pack(
            self.pack_window._build_reblend_button,
            "surprise-1.0.0.rblpack",
        )
        self.window.refresh()
        card = self.window._pack_cards[0]
        QTimer.singleShot(
            200, lambda: self._click_message_box(QMessageBox.No)
        )
        QTest.mouseClick(card["delete_button"], Qt.LeftButton)
        self.assertTrue(pack.is_file())
        entries, _ = load_shelf(self.shelf_path)
        self.assertEqual(len(entries), 1)
        self.assertIn("Nothing was deleted", self._status())

    def test_delete_defaults_to_no(self):
        self._build_pack(
            self.pack_window._build_reblend_button,
            "surprise-1.0.0.rblpack",
        )
        self.window.refresh()
        card = self.window._pack_cards[0]
        seen = {}

        def check_default():
            for widget in QApplication.topLevelWidgets():
                if isinstance(widget, QMessageBox):
                    seen["default"] = widget.defaultButton()
                    seen["no"] = widget.button(QMessageBox.No)
                    QTest.mouseClick(seen["no"], Qt.LeftButton)
                    return
            self.fail("no message box was showing")

        QTimer.singleShot(200, check_default)
        QTest.mouseClick(card["delete_button"], Qt.LeftButton)
        self.assertIn("default", seen, "no confirm dialog appeared")
        self.assertIs(seen["default"], seen["no"])

    # -- templates ------------------------------------------------

    def test_surprise_template_card_is_listed(self):
        self.window.refresh()
        names = [
            card["template"]["name"]
            for card in self.window._template_cards
        ]
        self.assertIn("surprise", names)
        card = next(
            c for c in self.window._template_cards
            if c["template"]["name"] == "surprise"
        )
        self.assertTrue(card["template"]["description"])

    def test_template_card_starts_a_project(self):
        started = Path(self._tmp.name) / "started"
        error = self.window.start_project_from_template(
            "surprise", "Started", started, ["reblend"]
        )
        self.assertIsNone(error)
        project, error = load_project(started)
        self.assertIsNone(error)
        self.assertEqual(project.name, "Started")
        self.assertEqual(project.targets, ["reblend"])
        # The template files landed in the §5.4 layout.
        self.assertTrue(
            (started / "src" / "reblend" / "addon.py").is_file()
        )
        self.assertTrue(
            (started / "src" / "shared" / "pick.py").is_file()
        )
        self.assertTrue((started / "README.md").is_file())
        self.assertEqual(self.opened, [str(started)])

    def test_starting_from_a_missing_template_fails_plainly(self):
        error = self.window.start_project_from_template(
            "no-such-template", "Nope",
            Path(self._tmp.name) / "nope", ["reblend"],
        )
        self.assertIsInstance(error, str)
        self.assertIn("no-such-template", error)
        self.assertEqual(self.opened, [])

    # -- wiring ---------------------------------------------------

    def test_chat_window_library_menu_opens_library(self):
        chat = ChatWindow(project=self.project)
        try:
            chat.show()
            QTest.qWait(50)
            chat._library_window_action.trigger()
            QTest.qWait(100)
            library = chat._library_window
            self.assertIsNotNone(library)
            self.assertTrue(library.isVisible())
            self.assertIn("Library", library.windowTitle())
        finally:
            if chat._library_window is not None:
                chat._library_window.close()
            chat.close()

    def test_library_open_project_opens_in_chat_window(self):
        self._build_pack(
            self.pack_window._build_reblend_button,
            "surprise-1.0.0.rblpack",
        )
        chat = ChatWindow()
        try:
            chat.show()
            QTest.qWait(50)
            chat._library_window_action.trigger()
            QTest.qWait(100)
            library = chat._library_window
            # The chat window's library reads the real shelf path,
            # so point it at this test's shelf and refresh.
            library._shelf_path = self.shelf_path
            library.refresh()
            self.assertEqual(len(library._pack_cards), 1)
            card = library._pack_cards[0]
            QTest.mouseClick(card["open_button"], Qt.LeftButton)
            QTest.qWait(50)
            self.assertIsNotNone(chat._project)
            self.assertEqual(chat._project.name, "Surprise")
        finally:
            if chat._library_window is not None:
                chat._library_window.close()
            chat.close()


if __name__ == "__main__":
    unittest.main()
