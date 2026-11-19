"""The command palette (DOSSIER.md §6.10, entry 043): Ctrl+K.

Every command in the suite, searchable by name, with its shortcut
shown beside it so the palette teaches as it serves. Menus and
buttons still exist for everything — the palette is a shortcut,
never the only path.

The palette is deliberately dumb: the chat window hands it a list
of commands (label, shortcut, action) each time it opens, and the
palette only filters, selects, and runs. It holds no logic of its
own about what a command does — the action is the window's own
method, so a command can never drift from the button or menu item
that does the same thing.

Selection follows U6: with an empty query nothing is selected,
and Enter with nothing selected does nothing. Once the user has
typed something and matches exist, the first match is selected,
so typing a few letters and pressing Enter runs the command.
"""

from __future__ import annotations

from PySide6.QtCore import QEvent, Qt
from PySide6.QtWidgets import (
    QDialog,
    QHeaderView,
    QLabel,
    QLineEdit,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
)

from devsuite.ui.style import CHAT_STYLESHEET

#: What the palette says when the query matches no command.
_NO_MATCH_TEXT = "No command matches that."


class CommandPalette(QDialog):
    """A popup over the chat window: type, filter, run."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.Popup | Qt.FramelessWindowHint)
        self.setStyleSheet(CHAT_STYLESHEET)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        self._input = QLineEdit(self)
        self._input.setPlaceholderText("Type a command...")
        self._input.textChanged.connect(self._on_text_changed)
        self._input.returnPressed.connect(self._on_enter)
        # Up and Down do nothing in a line edit on their own: the
        # palette moves the selection for them.
        self._input.installEventFilter(self)
        layout.addWidget(self._input)

        self._tree = QTreeWidget(self)
        self._tree.setColumnCount(2)
        self._tree.setHeaderHidden(True)
        self._tree.setRootIsDecorated(False)
        self._tree.setSelectionMode(QTreeWidget.SingleSelection)
        self._tree.header().setSectionResizeMode(0, QHeaderView.Stretch)
        self._tree.setColumnWidth(1, 110)
        self._tree.itemClicked.connect(self._on_item_clicked)
        self._tree.itemActivated.connect(self._on_item_clicked)
        layout.addWidget(self._tree, 1)

        self._no_match_label = QLabel(_NO_MATCH_TEXT)
        self._no_match_label.setObjectName("MutedLabel")
        self._no_match_label.hide()
        layout.addWidget(self._no_match_label)

    # -- the command list -----------------------------------------

    def set_commands(self, commands):
        """Replace the command list with ``commands``: (label,
        shortcut, action) triples. The chat window builds the list
        fresh each time the palette opens, so commands that only
        make sense in the moment (a pending plan) appear and vanish
        honestly."""
        self._tree.clear()
        for label, shortcut, action in commands:
            item = QTreeWidgetItem(self._tree, [label, shortcut])
            item.setData(0, Qt.ItemDataRole.UserRole, action)
        self._filter("")

    def visible_labels(self):
        """The labels currently shown, in order (for tests)."""
        return [
            self._tree.topLevelItem(row).text(0)
            for row in range(self._tree.topLevelItemCount())
            if not self._tree.topLevelItem(row).isHidden()
        ]

    # -- opening --------------------------------------------------

    def open_over(self, parent):
        """Show the palette over ``parent``: fresh input, every
        command listed, nothing selected."""
        self._input.clear()
        self._filter("")
        parent_rect = parent.geometry()
        width, height = 600, 400
        x = parent_rect.x() + (parent_rect.width() - width) // 2
        y = parent_rect.y() + max(40, parent_rect.height() // 6)
        self.setGeometry(x, y, width, height)
        self.show()
        self._input.setFocus()

    # -- filtering and selection ----------------------------------

    def _on_text_changed(self, text):
        self._filter(text)

    def _filter(self, query):
        """Narrow the list by substring match on the label,
        case-insensitive. An empty query shows every command with
        nothing selected (U6); a query with matches selects the
        first match; no match says so plainly."""
        query = query.strip().lower()
        visible = []
        for row in range(self._tree.topLevelItemCount()):
            item = self._tree.topLevelItem(row)
            match = query in item.text(0).lower()
            item.setHidden(not match)
            if match:
                visible.append(item)
        self._no_match_label.setVisible(not visible)
        if query and visible:
            self._tree.setCurrentItem(visible[0])
        else:
            self._tree.setCurrentItem(None)
            self._tree.clearSelection()

    def eventFilter(self, watched, event):
        if watched is self._input and event.type() == QEvent.KeyPress:
            if event.key() == Qt.Key_Down:
                self._move_selection(1)
                return True
            if event.key() == Qt.Key_Up:
                self._move_selection(-1)
                return True
        return super().eventFilter(watched, event)

    def _move_selection(self, step):
        """Move the selection one visible row down (or up)."""
        visible = [
            self._tree.topLevelItem(row)
            for row in range(self._tree.topLevelItemCount())
            if not self._tree.topLevelItem(row).isHidden()
        ]
        if not visible:
            return
        current = self._tree.currentItem()
        if current is None or current not in visible:
            self._tree.setCurrentItem(
                visible[0] if step > 0 else visible[-1]
            )
            return
        index = visible.index(current)
        index = max(0, min(len(visible) - 1, index + step))
        self._tree.setCurrentItem(visible[index])

    # -- running --------------------------------------------------

    def _on_enter(self):
        self._run_item(self._tree.currentItem())

    def _on_item_clicked(self, item, column=0):
        self._run_item(item)

    def _run_item(self, item):
        """Run the command on ``item``: the palette closes first,
        then the action runs — a command that opens a dialog must
        not open it behind the popup. Nothing selected, or an item
        with no action, runs nothing."""
        if item is None:
            return
        action = item.data(0, Qt.ItemDataRole.UserRole)
        if action is None:
            return
        self.close()
        action()
