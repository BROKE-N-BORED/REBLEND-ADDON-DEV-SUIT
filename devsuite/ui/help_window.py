"""The How to Use window (DOSSIER.md §6.10, U22).

A full index in plain words: every window, every action, with the
three journeys from §3 as the first three entries. The entries
themselves live in ``devsuite.help.entries`` — data, not code —
and this window only lists them, searches them, and shows the one
picked.

The window takes no project: help is the same whatever is open,
so there is no project guard and no project following. Search
filters the titles by substring, case-insensitive, the way the
command palette filters commands. Nothing is selected by default
(U6): the right side says "Pick an entry on the left to read it."
until one is picked.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPlainTextEdit,
    QVBoxLayout,
    QWidget,
)

from devsuite.help.entries import get_entries
from devsuite.ui.style import CHAT_STYLESHEET

#: What the right side shows before any entry is picked (U6:
#: nothing selected by default).
_PICK_LINE = "Pick an entry on the left to read it."

#: What the index says when the search matches no entry.
_NO_MATCH_TEXT = "No entry matches that."


class HelpWindow(QWidget):
    """The How to Use index: search the entries, read the one picked."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._entries = get_entries()
        self.setStyleSheet(CHAT_STYLESHEET)
        self.resize(1000, 680)
        self.setMinimumSize(640, 420)
        self.setWindowTitle("How to use - Reblend Add-on Dev Suite")
        self._build_ui()
        self._fill_list()
        self._show_placeholder()

    # -- layout ---------------------------------------------------

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        main = QHBoxLayout()
        main.setContentsMargins(12, 12, 12, 8)
        main.setSpacing(12)
        self._build_index(main)
        self._build_detail(main)
        root.addLayout(main, 1)

        self._status_label = QLabel("Ready")
        self._status_label.setObjectName("MutedLabel")
        self._status_label.setWordWrap(True)
        self._status_label.setContentsMargins(12, 4, 12, 8)
        root.addWidget(self._status_label)

    def _build_index(self, main):
        left = QVBoxLayout()
        left.setSpacing(8)
        heading = QLabel("HOW TO USE")
        heading.setObjectName("RoleLabel")
        left.addWidget(heading)
        note = QLabel(
            "Every window and every action, in plain words. The "
            "three journeys come first."
        )
        note.setObjectName("MutedLabel")
        note.setWordWrap(True)
        left.addWidget(note)
        self._search_input = QLineEdit()
        self._search_input.setPlaceholderText("Search the index...")
        self._search_input.textChanged.connect(self._on_search_changed)
        left.addWidget(self._search_input)
        self._entry_list = QListWidget()
        self._entry_list.setSelectionMode(
            QListWidget.SelectionMode.SingleSelection
        )
        self._entry_list.currentItemChanged.connect(
            self._on_selection_changed
        )
        left.addWidget(self._entry_list, 1)
        self._no_match_label = QLabel(_NO_MATCH_TEXT)
        self._no_match_label.setObjectName("MutedLabel")
        self._no_match_label.setWordWrap(True)
        self._no_match_label.hide()
        left.addWidget(self._no_match_label)
        main.addLayout(left, 1)

    def _build_detail(self, main):
        right = QVBoxLayout()
        right.setSpacing(8)
        self._detail_title = QLabel()
        title_font = self._detail_title.font()
        title_font.setBold(True)
        self._detail_title.setFont(title_font)
        self._detail_title.setWordWrap(True)
        right.addWidget(self._detail_title)
        self._detail_summary = QLabel()
        self._detail_summary.setObjectName("MutedLabel")
        self._detail_summary.setWordWrap(True)
        right.addWidget(self._detail_summary)
        self._detail_body = QPlainTextEdit()
        self._detail_body.setReadOnly(True)
        right.addWidget(self._detail_body, 1)
        main.addLayout(right, 2)

    # -- the list -------------------------------------------------

    def _fill_list(self):
        """List every entry, in the index's own order. Nothing is
        selected (U6)."""
        for index, entry in enumerate(self._entries):
            item = QListWidgetItem(entry["title"])
            item.setData(Qt.ItemDataRole.UserRole, index)
            self._entry_list.addItem(item)
        self._entry_list.setCurrentRow(-1)

    def visible_titles(self):
        """The titles currently shown, in order (for tests)."""
        return [
            self._entry_list.item(row).text()
            for row in range(self._entry_list.count())
            if not self._entry_list.item(row).isHidden()
        ]

    # -- searching and showing ------------------------------------

    def _on_search_changed(self, text):
        self._filter(text)

    def _filter(self, query):
        """Narrow the list by substring match on the title,
        case-insensitive. An empty query shows every entry; no
        match says so plainly. When the picked entry is filtered
        out, the detail goes back to the pick line — it must never
        show an entry that is not in the list."""
        query = query.strip().lower()
        visible = 0
        for row in range(self._entry_list.count()):
            item = self._entry_list.item(row)
            match = query in item.text().lower()
            item.setHidden(not match)
            if match:
                visible += 1
        self._no_match_label.setVisible(visible == 0)
        current = self._entry_list.currentItem()
        if current is not None and current.isHidden():
            self._entry_list.setCurrentRow(-1)

    def _on_selection_changed(self, current, _previous):
        if current is None:
            self._show_placeholder()
            return
        index = current.data(Qt.ItemDataRole.UserRole)
        self._show_entry(self._entries[index])

    def _show_placeholder(self):
        """Nothing picked yet: the right side says so."""
        self._detail_title.setText("")
        self._detail_summary.setText("")
        self._detail_body.setPlainText(_PICK_LINE)

    def _show_entry(self, entry):
        """Show one entry: title, summary, body."""
        self._detail_title.setText(entry["title"])
        self._detail_summary.setText(entry["summary"])
        self._detail_body.setPlainText(entry["body"])
