"""The library window (DOSSIER.md §6.9): a shelf, not a store.

Every pack the suite has built, plus the templates and starters —
cards with icon, name, version, target, last test result, and a
one-line description. From a card Joshua can open the pack's
project, reinstall the pack, or delete it (delete confirms, and
the confirmation defaults to No, U23/U31). No ratings, no
downloads, no network: the library is a shelf of his own work.

The shelf section reads the shelf record (``devsuite.library.shelf``)
every time the window is shown, so a build in the pack window shows
up when the library opens again. A card whose file is gone — moved
or deleted outside the suite — says so plainly and offers to remove
the record from the shelf; it never crashes and never silently
skips the missing pack.

The window takes an ``open_project`` callback (the chat window
supplies it: load the project by path, make it the current project,
show the chat window), an optional ``settings`` (a QSettings the
install folders are remembered in — the same keys the pack window
uses, so a folder remembered in one window is remembered in the
other), and an optional ``shelf_path`` (tests pass a temp one).

Reinstall is a file copy, nothing more: no code runs at install
time, and the window says exactly where it put the file. Delete
removes the built file AND its shelf entry.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QSettings
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from devsuite.library.shelf import (
    default_shelf_path,
    load_shelf,
    remove_entry,
)
from devsuite.packing.installer import (
    install_blender_addon,
    install_pack,
)
from devsuite.projects.project import load_project
from devsuite.templates import (
    create_project_from_template,
    list_templates,
)
from devsuite.ui.style import CHAT_STYLESHEET

#: The words the library uses for each target, in card text.
TARGET_WORDS = {
    "reblend": "Reblend pack",
    "blender": "Blender add-on",
}


class LibraryWindow(QWidget):
    """The shelf of built packs, plus the templates."""

    def __init__(self, open_project=None, settings=None,
                 shelf_path=None, parent=None):
        super().__init__(parent)
        self._open_project = open_project
        self._settings = settings or QSettings(
            "Broke n Bored", "Reblend Add-on Dev Suite"
        )
        self._shelf_path = (
            Path(shelf_path) if shelf_path is not None
            else default_shelf_path()
        )
        self._install_folders: dict[str, str] = {}
        # Card widgets, kept for the tests (and for the status line):
        # each pack card is a dict with its entry and its buttons.
        self._pack_cards: list[dict] = []
        self._template_cards: list[dict] = []

        self.setStyleSheet(CHAT_STYLESHEET)
        self.resize(1000, 680)
        self.setMinimumSize(640, 420)
        self.setWindowTitle("Library - Reblend Add-on Dev Suite")
        self._build_ui()
        self.refresh()

    # -- layout ---------------------------------------------------

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        bar = QWidget(self)
        bar_layout = QHBoxLayout(bar)
        bar_layout.setContentsMargins(12, 8, 12, 8)
        heading = QLabel("Built packs, and the templates to start from")
        heading.setObjectName("MutedLabel")
        bar_layout.addWidget(heading)
        root.addWidget(bar)

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        inner = QWidget()
        layout = QVBoxLayout(inner)
        layout.setContentsMargins(12, 4, 12, 8)
        layout.setSpacing(12)

        shelf_heading = QLabel("BUILT PACKS")
        shelf_heading.setObjectName("RoleLabel")
        layout.addWidget(shelf_heading)
        self._shelf_layout = QVBoxLayout()
        self._shelf_layout.setSpacing(8)
        layout.addLayout(self._shelf_layout)

        templates_heading = QLabel("TEMPLATES")
        templates_heading.setObjectName("RoleLabel")
        layout.addWidget(templates_heading)
        self._templates_layout = QVBoxLayout()
        self._templates_layout.setSpacing(8)
        layout.addLayout(self._templates_layout)

        layout.addStretch(1)
        scroll.setWidget(inner)
        root.addWidget(scroll, 1)

        self._status_label = QLabel("Ready")
        self._status_label.setObjectName("MutedLabel")
        self._status_label.setWordWrap(True)
        self._status_label.setContentsMargins(12, 4, 12, 8)
        root.addWidget(self._status_label)

    def showEvent(self, event):
        # Re-read the shelf every time the window is shown: a build
        # in the pack window shows up when the library opens again.
        self.refresh()
        super().showEvent(event)

    # -- refresh --------------------------------------------------

    def refresh(self):
        """Rebuild both sections from the shelf and the templates."""
        entries, error = load_shelf(self._shelf_path)
        self._rebuild_shelf(entries)
        self._rebuild_templates()
        if error is not None:
            self._status_label.setText(error)
        else:
            self._status_label.setText("Ready")

    def _clear_layout(self, layout):
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def _rebuild_shelf(self, entries):
        self._clear_layout(self._shelf_layout)
        self._pack_cards = []
        if not entries:
            empty = QLabel(
                "Nothing built yet. Build your first pack from the "
                "pack window, and it shows up here."
            )
            empty.setObjectName("MutedLabel")
            empty.setWordWrap(True)
            self._shelf_layout.addWidget(empty)
            return
        for entry in entries:
            self._pack_cards.append(self._build_pack_card(entry))

    def _rebuild_templates(self):
        self._clear_layout(self._templates_layout)
        self._template_cards = []
        templates = list_templates()
        if not templates:
            empty = QLabel("No templates found.")
            empty.setObjectName("MutedLabel")
            empty.setWordWrap(True)
            self._templates_layout.addWidget(empty)
            return
        for template in templates:
            self._template_cards.append(
                self._build_template_card(template)
            )

    # -- cards ----------------------------------------------------

    def _build_pack_card(self, entry):
        card = QFrame(self)
        card.setObjectName("PlanCard")
        layout = QHBoxLayout(card)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(12)

        pixmap = _load_icon(entry.get("project_root", ""))
        icon_label = QLabel()
        if pixmap is not None:
            icon_label.setPixmap(
                pixmap.scaled(
                    48, 48, Qt.KeepAspectRatio, Qt.SmoothTransformation
                )
            )
        icon_label.setFixedWidth(48)
        layout.addWidget(icon_label)

        text = QVBoxLayout()
        text.setSpacing(2)
        name = QLabel(entry.get("project_name", "?"))
        name_font = name.font()
        name_font.setBold(True)
        name.setFont(name_font)
        name.setWordWrap(True)
        text.addWidget(name)
        target = TARGET_WORDS.get(
            entry.get("target", ""), entry.get("target", "?")
        )
        detail = QLabel(
            f"Version {entry.get('version', '?')} - {target}"
        )
        detail.setWordWrap(True)
        text.addWidget(detail)
        test_run = entry.get("test_run_id")
        if test_run:
            test_line = f"Last test result: tested in run {test_run}."
        else:
            test_line = "Last test result: not tested yet."
        test_label = QLabel(test_line)
        test_label.setObjectName("MutedLabel")
        test_label.setWordWrap(True)
        text.addWidget(test_label)
        description = entry.get("description", "")
        if description:
            description_label = QLabel(description)
            description_label.setObjectName("MutedLabel")
            description_label.setWordWrap(True)
            text.addWidget(description_label)
        built = entry.get("built", "")
        if built:
            built_label = QLabel(f"Built {built}.")
            built_label.setObjectName("MutedLabel")
            text.addWidget(built_label)
        layout.addLayout(text, 1)

        pack_path = Path(entry.get("pack_path", ""))
        gone = not pack_path.is_file()
        buttons = QVBoxLayout()
        buttons.setSpacing(4)
        open_button = QPushButton("Open project")
        open_button.clicked.connect(
            lambda checked=False, e=entry: self._on_open_project(e)
        )
        buttons.addWidget(open_button)
        reinstall_button = QPushButton("Reinstall")
        reinstall_button.clicked.connect(
            lambda checked=False, e=entry: self._on_reinstall(e)
        )
        buttons.addWidget(reinstall_button)
        delete_button = QPushButton("Delete")
        delete_button.clicked.connect(
            lambda checked=False, e=entry: self._on_delete(e)
        )
        buttons.addWidget(delete_button)
        remove_button = QPushButton("Remove from the shelf")
        remove_button.clicked.connect(
            lambda checked=False, e=entry: self._on_remove_from_shelf(e)
        )
        buttons.addWidget(remove_button)
        if gone:
            gone_label = QLabel(
                "This file is gone. It was moved or deleted outside "
                "the suite."
            )
            gone_label.setObjectName("MutedLabel")
            gone_label.setWordWrap(True)
            text.addWidget(gone_label)
            reinstall_button.hide()
            delete_button.hide()
        else:
            remove_button.hide()
        layout.addLayout(buttons)

        self._shelf_layout.addWidget(card)
        return {
            "entry": entry,
            "frame": card,
            "gone": gone,
            "open_button": open_button,
            "reinstall_button": reinstall_button,
            "delete_button": delete_button,
            "remove_button": remove_button,
        }

    def _build_template_card(self, template):
        card = QFrame(self)
        card.setObjectName("PlanCard")
        layout = QHBoxLayout(card)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(12)

        text = QVBoxLayout()
        text.setSpacing(2)
        name = QLabel(template["name"].replace("-", " ").title())
        name_font = name.font()
        name_font.setBold(True)
        name.setFont(name_font)
        name.setWordWrap(True)
        text.addWidget(name)
        if template["description"]:
            description = QLabel(template["description"])
            description.setObjectName("MutedLabel")
            description.setWordWrap(True)
            text.addWidget(description)
        layout.addLayout(text, 1)

        start_button = QPushButton("Start a project")
        start_button.clicked.connect(
            lambda checked=False, t=template: self._on_start_project(t)
        )
        layout.addWidget(start_button)

        self._templates_layout.addWidget(card)
        return {
            "template": template,
            "frame": card,
            "start_button": start_button,
        }

    # -- pack actions ---------------------------------------------

    def _on_open_project(self, entry):
        if self._open_project is None:
            self._status_label.setText(
                "The chat window did not say how to open projects, "
                "so I cannot open this one."
            )
            return
        self._open_project(entry.get("project_root", ""))

    def _on_reinstall(self, entry):
        pack_path = Path(entry.get("pack_path", ""))
        target = entry.get("target", "")
        folder = self._install_folder(target)
        if folder is None:
            folder = QFileDialog.getExistingDirectory(
                self,
                "Where should the pack go?" if target == "reblend"
                else "Where should the add-on go?",
            )
            if not folder:
                self._status_label.setText(
                    "No folder chosen, so nothing was installed."
                )
                return
            self.set_install_folder(target, folder)
        if target == "reblend":
            installed, error = install_pack(pack_path, folder)
            where = "Reblend"
        elif target == "blender":
            installed, error = install_blender_addon(pack_path, folder)
            where = "Blender"
        else:
            # A shelf entry with no known target is damaged, not a
            # Blender add-on: say so instead of guessing.
            self._status_label.setText(
                "This shelf entry does not say which program the "
                f"pack is for (target: {target or 'none'}), so I "
                "cannot reinstall it. Remove it from the shelf and "
                "build the pack again."
            )
            return
        if error is not None:
            self._status_label.setText(error)
            return
        self._status_label.setText(
            f"Installed in {where} at {installed}."
        )

    def _on_delete(self, entry):
        pack_path = Path(entry.get("pack_path", ""))
        name = entry.get("project_name", "?")
        answer = QMessageBox.question(
            self,
            "Delete this pack?",
            f"Delete {name} ({pack_path.name}) from the shelf and "
            "from the disk? The project itself stays. Only the "
            "built file goes.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            self._status_label.setText("Nothing was deleted.")
            return
        try:
            pack_path.unlink()
        except FileNotFoundError:
            pass  # Already gone; the shelf entry still goes.
        except OSError:
            self._status_label.setText(
                "I could not delete the built file. Check the "
                "project's packs folder can be written to."
            )
            return
        removed, error = remove_entry(self._shelf_path, str(pack_path))
        if error is not None:
            self._status_label.setText(
                "The file is deleted, but I could not remove its "
                f"record from the library: {error}"
            )
            return
        self.refresh()
        self._status_label.setText(f"Deleted {name}.")

    def _on_remove_from_shelf(self, entry):
        pack_path = str(entry.get("pack_path", ""))
        removed, error = remove_entry(self._shelf_path, pack_path)
        if error is not None:
            self._status_label.setText(error)
            return
        self.refresh()
        if removed:
            self._status_label.setText(
                "Removed it from the shelf. The project itself is "
                "untouched."
            )

    # -- install folders ------------------------------------------

    def set_install_folder(self, target, path):
        """Remember where ``target`` installs go, without a file
        dialog. Tests use this to install into a temporary folder;
        the choice is also saved, so a later install reuses it. The
        keys are the pack window's keys, so a folder remembered in
        one window is remembered in the other."""
        folder = str(path)
        self._install_folders[target] = folder
        self._settings.setValue(f"install_folder/{target}", folder)

    def _install_folder(self, target) -> str | None:
        """Where ``target`` installs go: the remembered folder, or
        None when nothing has been chosen yet."""
        if target in self._install_folders:
            return self._install_folders[target]
        value = self._settings.value(f"install_folder/{target}", "")
        return str(value) if value else None

    # -- starting a project ---------------------------------------

    def _on_start_project(self, template):
        name, ok = QInputDialog.getText(
            self, "New project", "What should the project be called?"
        )
        if not ok or not name.strip():
            return
        name = name.strip()
        target, ok = QInputDialog.getItem(
            self,
            "New project",
            "Which program is the add-on for?",
            ["reblend", "blender", "both"],
            0,
            False,
        )
        if not ok:
            return
        folder = QFileDialog.getExistingDirectory(
            self, "Where should the project live?"
        )
        if not folder:
            return
        targets = (
            ["reblend", "blender"] if target == "both" else [target]
        )
        safe_name = name.replace("/", "-").replace("\\", "-")
        self.start_project_from_template(
            template["name"],
            name,
            Path(folder) / safe_name,
            targets,
        )

    def start_project_from_template(self, template_name, name, path,
                                    targets):
        """Create a project from ``template_name`` at ``path`` and
        open it in the chat window. The dialog-free half of
        starting a project: the dialogs live in
        ``_on_start_project``, and the tests call this directly.
        Returns None on success, or the plain-words error (also
        shown in the status line)."""
        project, error = create_project_from_template(
            template_name, path, name=name, targets=targets
        )
        if error is not None:
            self._status_label.setText(error)
            return error
        if self._open_project is None:
            self._status_label.setText(
                f"Made {name}, but the chat window did not say how "
                "to open projects, so it is not open yet."
            )
            return None
        self._open_project(str(project.root))
        return None


def _load_icon(project_root: str) -> QPixmap | None:
    """The project's icon as a pixmap, or None when there is none.

    Reads the icon name from the project's project.json when the
    project still opens, and falls back to the conventional
    ``icon.png`` spots. A missing project or a file that does not
    load is not an error — the card simply shows no icon."""
    root = Path(project_root) if project_root else None
    if root is None or not root.is_dir():
        return None
    candidates: list[Path] = []
    project, error = load_project(root)
    if error is None and project.icon:
        candidates.append(root / project.icon)
        candidates.append(project.assets_dir / project.icon)
    candidates.append(root / "icon.png")
    candidates.append(root / "assets" / "icon.png")
    for candidate in candidates:
        if candidate.is_file():
            pixmap = QPixmap(str(candidate))
            if not pixmap.isNull():
                return pixmap
    return None
