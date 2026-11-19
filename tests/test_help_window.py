"""Tests for devsuite.ui.help_window — the How to Use window (§6.10).

Run offscreen with the Qt venv, from the project root (the EGL env
is a sandbox quirk — his PC has system Qt libs; never override HOME):

    LD_LIBRARY_PATH=$HOME/workspace/qt-libs/root/usr/lib/x86_64-linux-gnu \\
    __EGL_VENDOR_LIBRARY_DIRS=$HOME/workspace/qt-libs/root/usr/share/glvnd/egl_vendor.d \\
    QT_QPA_PLATFORM=offscreen TMPDIR=/tmp \\
    ~/workspace/tmp/qt-venv/bin/python -m unittest tests.test_help_window

On a Python without PySide6 the whole module skips, so the stdlib
suite still passes there. The entry content itself is checked by
tests/test_help_entries.py, which needs no Qt.

The rules under test (DOSSIER.md §6.10, U22, U6):

* The window opens from the Help menu and from the command
  palette; one window is kept and reused.
* Every entry the help module declares appears in the list, in
  the index's own order.
* Picking an entry shows its title, summary, and body.
* Searching filters the list by substring; a query with no match
  says so plainly.
* Nothing is selected on open: the right side shows the pick line.
* The visible text carries no em-dash and no bare "&".
"""

import unittest

try:
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication
except ImportError:
    raise unittest.SkipTest("PySide6 is not installed")

from devsuite.help.entries import ENTRIES
from devsuite.ui.chat_window import ChatWindow
from devsuite.ui.help_window import HelpWindow


class HelpWindowTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._app = QApplication.instance() or QApplication([])

    def setUp(self):
        # Help takes no project, so the chat window opens without
        # one; the help window itself needs no project either.
        self.chat = ChatWindow()
        self.chat.show()
        QTest.qWait(50)
        self.window = HelpWindow()
        self.window.show()
        QTest.qWait(50)

    def tearDown(self):
        self.window.close()
        if self.chat._help_window is not None:
            self.chat._help_window.close()
        self.chat.close()
        QTest.qWait(50)

    # -- opening --------------------------------------------------

    def test_opens_from_the_help_menu(self):
        self.chat._help_action.trigger()
        QTest.qWait(50)
        self.assertIsNotNone(self.chat._help_window)
        self.assertTrue(self.chat._help_window.isVisible())

    def test_help_window_is_reused(self):
        self.chat._help_action.trigger()
        first = self.chat._help_window
        self.chat._help_action.trigger()
        self.assertIs(self.chat._help_window, first)

    def test_opens_from_the_palette(self):
        self.chat._on_palette()
        palette = self.chat._palette
        QTest.keyClicks(palette._input, "how to use")
        QTest.qWait(50)
        self.assertEqual(palette.visible_labels(), ["How to use"])
        QTest.keyClick(palette._input, Qt.Key_Return)
        QTest.qWait(50)
        self.assertIsNotNone(self.chat._help_window)
        self.assertTrue(self.chat._help_window.isVisible())

    # -- the list and the detail ----------------------------------

    def test_every_entry_appears_in_order(self):
        self.assertEqual(
            self.window.visible_titles(),
            [entry["title"] for entry in ENTRIES],
        )

    def test_nothing_selected_on_open(self):
        self.assertEqual(self.window._entry_list.currentRow(), -1)
        self.assertEqual(
            self.window._detail_body.toPlainText(),
            "Pick an entry on the left to read it.",
        )
        self.assertEqual(self.window._detail_title.text(), "")

    def test_picking_an_entry_shows_its_body(self):
        self.window._entry_list.setCurrentRow(0)
        QTest.qWait(50)
        first = ENTRIES[0]
        self.assertEqual(
            self.window._detail_title.text(), first["title"]
        )
        self.assertEqual(
            self.window._detail_summary.text(), first["summary"]
        )
        self.assertEqual(
            self.window._detail_body.toPlainText(), first["body"]
        )

    def test_search_filters_the_list(self):
        QTest.keyClicks(self.window._search_input, "palette")
        QTest.qWait(50)
        self.assertEqual(
            self.window.visible_titles(), ["The command palette"]
        )
        self.assertFalse(self.window._no_match_label.isVisible())

    def test_search_with_no_match_says_so_plainly(self):
        QTest.keyClicks(self.window._search_input, "zzzqqq")
        QTest.qWait(50)
        self.assertEqual(self.window.visible_titles(), [])
        self.assertTrue(self.window._no_match_label.isVisible())
        self.assertEqual(
            self.window._no_match_label.text(), "No entry matches that."
        )

    def test_filtering_out_the_picked_entry_clears_the_detail(self):
        self.window._entry_list.setCurrentRow(0)
        QTest.qWait(50)
        self.assertNotEqual(
            self.window._detail_body.toPlainText(),
            "Pick an entry on the left to read it.",
        )
        QTest.keyClicks(self.window._search_input, "palette")
        QTest.qWait(50)
        self.assertEqual(self.window._entry_list.currentRow(), -1)
        self.assertEqual(
            self.window._detail_body.toPlainText(),
            "Pick an entry on the left to read it.",
        )

    def test_visible_text_has_no_em_dash_or_bare_ampersand(self):
        for entry in ENTRIES:
            for field in ("title", "summary", "body"):
                text = entry[field]
                self.assertNotIn("—", text)
                self.assertNotIn("&", text)


if __name__ == "__main__":
    unittest.main()
