"""The pack window (DOSSIER.md §6.8): where a project becomes a file.

Shows the manifest as the suite will write it — name, version,
targets, contributions, permissions, each field explained in plain
words underneath it (U20) — plus the icon, the wheel-button editor,
the pre-pack report, and the build and install buttons:

* Build Reblend pack / Build Blender add-on — each enabled only for
  the targets the project supports, so the window shows which
  targets a project builds for before it builds (§4). Builds run in
  a worker thread (the UI never blocks, §9.6) and report in plain
  words where the file landed, or why the build failed.
* Install in Reblend / Install in Blender — enabled only when a
  pack built from the project's current version sits in the
  project's packs/ folder, so a stale version can never be
  installed by accident. Install is a file copy, nothing more:
  no code runs at install time. The packs folders are never
  hardcoded — the first install asks where to put the file, and
  the choice is remembered after that (QSettings).
* Bump version — one explicit action, patch number only (1.0.0
  becomes 1.0.1). The suite never bumps silently. Major and minor
  editing is a later item.

The pre-pack report runs first and reports in plain words: secrets
check (over the files that ship, not the whole project), manifest
check, contribution check, last test result. The test harness does
not exist yet, so the last-test line always says plainly "no test
run yet" — never faked — and an unproven build carries the
emitter's warning, not a refusal. A pack is never built on a
failing test run without Joshua saying so explicitly (§6.8); with
no harness there is no failing run to ask about, and the unproven
warning is what stands in for that question today.

Contributions are edited here, wheel entries only in this item (the
only contribution kind with a defined shape in v1 use). Other kinds
come later, when real packs need them. Changes save to the project
at once.

The window takes a project (``project``), an optional ``settings``
(a QSettings the install folders are remembered in), and an
optional ``shelf_path`` (where the library shelf lives — the
default is the standard location). A successful build records the
built file in the shelf, so the library window shows it; a shelf
write that fails is a plain-words warning in the status line, never
a failed build — the pack is built, the shelf is only a record.
Tests pass a throwaway settings file and shelf path so they never
touch the real remembered folders or the real shelf;
``set_install_folder`` sets a folder without a file dialog, which
is how tests install without driving one.
"""

from __future__ import annotations

import re
import time
from datetime import date
from pathlib import Path

from PySide6.QtCore import Qt, QSettings, QThread, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from devsuite.library.shelf import add_entry, default_shelf_path
from devsuite.measure.measurements import record
from devsuite.packing.blender import (
    DEFAULT_BLENDER_VERSION_MIN,
    build_blender_addon,
    build_blender_manifest,
)
from devsuite.packing.builder import build_pack
from devsuite.packing.installer import (
    install_blender_addon,
    install_pack,
)
from devsuite.packing.secrets_scan import scan_pack
from devsuite.packing.writer import build_manifest
from devsuite.projects.project import Project
from devsuite.ui.style import CHAT_STYLESHEET

# Workers in flight, kept alive outside any window: a worker must
# never be destroyed while its thread is still running, and a
# window closed mid-build must not take its worker down with it.
# A finished worker drops out of the set and is deleted by Qt.
_LIVE_WORKERS: set[QThread] = set()


def _track(worker: QThread) -> None:
    _LIVE_WORKERS.add(worker)
    worker.finished.connect(lambda: _LIVE_WORKERS.discard(worker))


#: Files that ship in a pack, by project-relative path prefix (or
#: exact name): the secrets check only covers these, so a secret in
#: the chat history or a test file never blocks a pack that would
#: not carry it anyway.
_SHIPPED_PREFIXES = ("src/reblend/", "src/shared/", "src/blender/",
                     "assets/")
_SHIPPED_FILES = ("README.md", "icon.png")

_VERSION_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")


class _BuildWorker(QThread):
    """Build a pack or an add-on, off the UI thread.

    Emits ``done(token, target, path, warnings, error)``: ``path``
    is the built file, or None with a plain-words ``error`` when
    the build failed. ``token`` lets the window ignore answers from
    a build that started before the window closed.
    """

    done = Signal(int, str, object, object, object)

    def __init__(self, token, target, project, parent=None):
        super().__init__(parent)
        self._token = token
        self._target = target
        self._project = project

    def run(self):
        if self._target == "reblend":
            path, warnings, error = build_pack(
                self._project,
                self._project.packs_dir,
                contributions=self._project.contributions,
            )
        else:
            path, warnings, error = build_blender_addon(
                self._project,
                self._project.packs_dir,
            )
        self.done.emit(self._token, self._target, path, warnings, error)


class PackWindow(QWidget):
    """Where a project becomes a file."""

    def __init__(self, project=None, settings=None, shelf_path=None,
                 parent=None):
        super().__init__(parent)
        self._project: Project | None = None
        self._settings = settings or QSettings(
            "Broke n Bored", "Reblend Add-on Dev Suite"
        )
        self._shelf_path = (
            Path(shelf_path) if shelf_path is not None
            else default_shelf_path()
        )
        self._install_folders: dict[str, str] = {}
        self._worker: QThread | None = None
        self._build_token = 0
        self._building = False
        self._build_started = 0.0
        self._preview_text_lines: list[str] = []
        self._report_text = ""

        self.setStyleSheet(CHAT_STYLESHEET)
        self.resize(1000, 680)
        self.setMinimumSize(640, 420)
        self._build_ui()

        if project is not None:
            self.set_project(project)
        else:
            self._refresh()

    # -- layout ---------------------------------------------------

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self._build_top_bar(root)
        self._build_no_project(root)
        self._build_content(root)
        self._build_footer(root)

    def _build_top_bar(self, root):
        bar = QWidget(self)
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(12, 8, 12, 8)
        self._project_label = QLabel("No project open")
        self._project_label.setObjectName("MutedLabel")
        layout.addWidget(self._project_label)
        root.addWidget(bar)

    def _build_no_project(self, root):
        self._no_project_label = QLabel(
            "Open a project first, or make a new one from the chat "
            "window's File menu. Then come back here to pack it."
        )
        self._no_project_label.setWordWrap(True)
        self._no_project_label.setContentsMargins(12, 24, 12, 24)
        root.addWidget(self._no_project_label)

    def _build_content(self, root):
        self._content = QWidget(self)
        layout = QVBoxLayout(self._content)
        layout.setContentsMargins(12, 4, 12, 8)
        layout.setSpacing(12)

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        inner = QWidget()
        inner_layout = QVBoxLayout(inner)
        inner_layout.setContentsMargins(0, 0, 0, 0)
        inner_layout.setSpacing(12)
        self._build_preview(inner_layout)
        self._build_wheel_editor(inner_layout)
        self._build_report(inner_layout)
        self._build_actions(inner_layout)
        inner_layout.addStretch(1)
        scroll.setWidget(inner)
        layout.addWidget(scroll, 1)
        root.addWidget(self._content, 1)

    def _build_preview(self, layout):
        card = QFrame(self)
        card.setObjectName("PlanCard")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(12, 10, 12, 10)
        heading = QLabel("THE MANIFEST, AS IT WILL BE WRITTEN")
        heading.setObjectName("RoleLabel")
        card_layout.addWidget(heading)
        self._preview_rows = QVBoxLayout()
        self._preview_rows.setSpacing(6)
        card_layout.addLayout(self._preview_rows)
        self._icon_label = QLabel()
        card_layout.addWidget(self._icon_label)
        layout.addWidget(card)

    def _build_wheel_editor(self, layout):
        card = QFrame(self)
        card.setObjectName("PlanCard")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(12, 10, 12, 10)
        heading = QLabel("WHEEL BUTTONS")
        heading.setObjectName("RoleLabel")
        card_layout.addWidget(heading)
        note = QLabel(
            "Buttons this add-on puts on the wheel. Each one needs a "
            "label (what the button says) and an action (what it "
            "runs). Other kinds of contribution come later, when real "
            "packs need them."
        )
        note.setObjectName("MutedLabel")
        note.setWordWrap(True)
        card_layout.addWidget(note)
        self._wheel_rows = QVBoxLayout()
        self._wheel_rows.setSpacing(4)
        card_layout.addLayout(self._wheel_rows)
        add_row = QHBoxLayout()
        self._wheel_label_input = QLineEdit()
        self._wheel_label_input.setPlaceholderText("Label, like Surprise")
        add_row.addWidget(self._wheel_label_input, 1)
        self._wheel_action_input = QLineEdit()
        self._wheel_action_input.setPlaceholderText(
            "Action, like surprise.randomize"
        )
        add_row.addWidget(self._wheel_action_input, 1)
        self._add_wheel_button = QPushButton("Add wheel button")
        self._add_wheel_button.clicked.connect(self._on_add_wheel)
        add_row.addWidget(self._add_wheel_button)
        card_layout.addLayout(add_row)
        layout.addWidget(card)

    def _build_report(self, layout):
        card = QFrame(self)
        card.setObjectName("PlanCard")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(12, 10, 12, 10)
        heading = QLabel("BEFORE PACKING")
        heading.setObjectName("RoleLabel")
        card_layout.addWidget(heading)
        self._report_label = QLabel()
        self._report_label.setWordWrap(True)
        self._report_label.setTextInteractionFlags(
            Qt.TextSelectableByMouse
        )
        card_layout.addWidget(self._report_label)
        layout.addWidget(card)

    def _build_actions(self, layout):
        card = QFrame(self)
        card.setObjectName("PlanCard")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(12, 10, 12, 10)
        heading = QLabel("BUILD AND INSTALL")
        heading.setObjectName("RoleLabel")
        card_layout.addWidget(heading)

        build_row = QHBoxLayout()
        self._build_reblend_button = QPushButton("Build Reblend pack")
        self._build_reblend_button.setObjectName("PrimaryButton")
        self._build_reblend_button.clicked.connect(
            lambda: self._on_build_clicked("reblend")
        )
        build_row.addWidget(self._build_reblend_button)
        self._build_blender_button = QPushButton("Build Blender add-on")
        self._build_blender_button.clicked.connect(
            lambda: self._on_build_clicked("blender")
        )
        build_row.addWidget(self._build_blender_button)
        self._bump_button = QPushButton("Bump version")
        self._bump_button.setToolTip(
            "Raise the patch number: 1.0.0 becomes 1.0.1."
        )
        self._bump_button.clicked.connect(self._on_bump_clicked)
        build_row.addWidget(self._bump_button)
        build_row.addStretch(1)
        card_layout.addLayout(build_row)

        install_row = QHBoxLayout()
        self._install_reblend_button = QPushButton("Install in Reblend")
        self._install_reblend_button.clicked.connect(
            lambda: self._on_install_clicked("reblend")
        )
        install_row.addWidget(self._install_reblend_button)
        self._install_blender_button = QPushButton("Install in Blender")
        self._install_blender_button.clicked.connect(
            lambda: self._on_install_clicked("blender")
        )
        install_row.addWidget(self._install_blender_button)
        install_row.addStretch(1)
        card_layout.addLayout(install_row)
        layout.addWidget(card)

    def _build_footer(self, root):
        self._status_label = QLabel("Ready")
        self._status_label.setObjectName("MutedLabel")
        self._status_label.setWordWrap(True)
        self._status_label.setContentsMargins(12, 4, 12, 8)
        root.addWidget(self._status_label)

    # -- project --------------------------------------------------

    def set_project(self, project):
        """Open ``project`` in this window: preview, editor, report,
        and buttons all follow it. When the project actually changes,
        an in-flight build's answer is invalidated (the build still
        finishes in the background and its file lands in the old
        project's packs folder — it just cannot report into a window
        showing a different project)."""
        if project is not self._project:
            self._build_token += 1
        self._project = project
        self._refresh()

    def _refresh(self):
        """Recompute everything from the project: title, preview,
        wheel list, report, and which buttons are on."""
        project = self._project
        if project is None:
            self.setWindowTitle(
                "No project open - Pack - Reblend Add-on Dev Suite"
            )
            self._project_label.setText("No project open")
            self._no_project_label.show()
            self._content.hide()
            self._status_label.setText("Ready")
            return
        self.setWindowTitle(
            f"{project.name} - Pack - Reblend Add-on Dev Suite"
        )
        targets = ", ".join(project.targets)
        self._project_label.setText(
            f"Project: {project.name} ({targets})"
        )
        self._no_project_label.hide()
        self._content.show()
        self._refresh_preview()
        self._refresh_wheel_list()
        self._refresh_report()
        self._refresh_buttons()

    def _refresh_preview(self):
        """The manifest, as the suite will write it, rebuilt from the
        project. Each field carries a plain-words line underneath
        it (U20). The Reblend manifest is shown when the project
        targets Reblend; a Blender-only project shows the Blender
        manifest instead."""
        project = self._project
        while self._preview_rows.count():
            item = self._preview_rows.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self._preview_text_lines = []

        if "reblend" in project.targets:
            manifest, error = build_manifest(
                project, project.contributions
            )
            if error is not None:
                rows = [(
                    "The manifest cannot be written yet.",
                    error,
                )]
            else:
                wheel = manifest["contributions"].get("wheel", [])
                if wheel:
                    summary = ", ".join(
                        f"{entry.get('label', '?')}"
                        for entry in wheel
                    )
                    contributions = f"{len(wheel)} wheel button(s): {summary}"
                else:
                    contributions = "Nothing declared yet"
                rows = [
                    ("Name: " + manifest["name"],
                     "The name Reblend shows in its pack list."),
                    ("Version: " + manifest["version"],
                     "Three numbers. The Reblend pack and the Blender "
                     "add-on for one project always share it."),
                    ("Targets: " + ", ".join(project.targets),
                     "Which programs this project builds for."),
                    ("Reblend: " + manifest["reblend"],
                     "The Reblend versions this pack works with."),
                    ("Entry: " + manifest["entry"],
                     "The file Reblend calls to run the pack."),
                    ("Contributions: " + contributions,
                     "What the pack adds to the program."),
                    ("Permissions: network false, files project-only",
                     "Packs never touch the network and only read and "
                     "write inside the project. Version 1 allows "
                     "nothing else."),
                ]
        else:
            text, error = build_blender_manifest(project)
            if error is not None:
                rows = [(
                    "The manifest cannot be written yet.",
                    error,
                )]
            else:
                rows = [
                    ("Name: " + project.name,
                     "The name Blender shows in its add-on list."),
                    ("Version: " + project.version,
                     "Three numbers. The Reblend pack and the Blender "
                     "add-on for one project always share it."),
                    ("Targets: " + ", ".join(project.targets),
                     "Which programs this project builds for."),
                    ("Blender: " + DEFAULT_BLENDER_VERSION_MIN
                     + " or later",
                     "The oldest Blender this add-on supports."),
                    ("License: GPL-3.0-or-later",
                     "Blender requires every extension to name a "
                     "license."),
                ]
        for value, explanation in rows:
            self._preview_text_lines.append(value)
            value_label = QLabel(value)
            value_label.setWordWrap(True)
            value_font = value_label.font()
            value_font.setBold(True)
            value_label.setFont(value_font)
            self._preview_rows.addWidget(value_label)
            explain_label = QLabel(explanation)
            explain_label.setObjectName("MutedLabel")
            explain_label.setWordWrap(True)
            self._preview_rows.addWidget(explain_label)
        self._refresh_icon()

    def _refresh_icon(self):
        """Show the project's icon when it names one that loads, or
        a plain line saying there is none yet."""
        project = self._project
        icon = project.icon if project is not None else ""
        pixmap = None
        if icon:
            for candidate in (project.root / icon,
                              project.assets_dir / icon):
                if candidate.is_file():
                    loaded = QPixmap(str(candidate))
                    if not loaded.isNull():
                        pixmap = loaded
                        break
        if pixmap is not None:
            # No setText after setPixmap: setting text clears the
            # pixmap on a QLabel, and the icon never showed.
            self._icon_label.setPixmap(
                pixmap.scaled(
                    48, 48, Qt.KeepAspectRatio, Qt.SmoothTransformation
                )
            )
        elif icon:
            self._icon_label.setText(f"Icon: {icon} (could not load it)")
        else:
            self._icon_label.setText("Icon: none yet")

    def _refresh_wheel_list(self):
        """Rebuild the wheel-button rows from the project."""
        while self._wheel_rows.count():
            item = self._wheel_rows.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        wheel = self._project.contributions.get("wheel", [])
        if not wheel:
            empty = QLabel("No wheel buttons yet.")
            empty.setObjectName("MutedLabel")
            self._wheel_rows.addWidget(empty)
            return
        for index, entry in enumerate(wheel):
            row = QWidget()
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(0, 0, 0, 0)
            label = QLabel(
                f"{entry.get('label', '?')} - {entry.get('action', '?')}"
            )
            row_layout.addWidget(label, 1)
            remove = QPushButton("Remove")
            remove.clicked.connect(
                lambda checked=False, i=index: self._on_remove_wheel(i)
            )
            row_layout.addWidget(remove)
            self._wheel_rows.addWidget(row)

    def _refresh_report(self):
        """The pre-pack report, in plain words: secrets, manifest,
        contributions, last test result."""
        project = self._project
        lines = []

        findings = [
            finding for finding in scan_pack(project.root)
            if _ships(finding["file"])
        ]
        if findings:
            first = findings[0]
            lines.append(
                "Secrets check: found something secret-looking in "
                f"{first['file']} (line {first['line']}). Remove it "
                "before packing. Packs must never carry keys, tokens, "
                "or passwords."
            )
        else:
            lines.append(
                "Secrets check: nothing secret-looking in the files "
                "that ship."
            )

        if "reblend" in project.targets:
            _, error = build_manifest(project, project.contributions)
            if error is None:
                lines.append("Reblend manifest: valid.")
            else:
                lines.append(f"Reblend manifest: {error}")
        if "blender" in project.targets:
            _, error = build_blender_manifest(project)
            if error is None:
                lines.append("Blender manifest: valid.")
            else:
                lines.append(f"Blender manifest: {error}")

        wheel = project.contributions.get("wheel", [])
        if wheel:
            count = len(wheel)
            lines.append(
                f"Contributions: {count} wheel button(s) declared."
            )
        else:
            lines.append(
                "Contributions: nothing declared yet. The pack will "
                "add nothing to the program until you add a wheel "
                "button."
            )

        lines.append(
            "Last test result: no test run yet. The test harness is "
            "a later phase, so nothing has proved this project yet."
        )

        self._report_text = "\n".join(lines)
        self._report_label.setText(self._report_text)

    def _refresh_buttons(self):
        """Which buttons are on: builds follow the project's
        targets, installs follow the packs folder, and nothing runs
        while a build is in flight."""
        project = self._project
        building = self._building
        reblend = project is not None and "reblend" in project.targets
        blender = project is not None and "blender" in project.targets
        self._build_reblend_button.setEnabled(reblend and not building)
        self._build_blender_button.setEnabled(blender and not building)
        self._build_reblend_button.setToolTip(
            "Build the Reblend pack."
            if reblend else
            "This project does not target Reblend, so there is no "
            "Reblend pack to build."
        )
        self._build_blender_button.setToolTip(
            "Build the Blender add-on."
            if blender else
            "This project does not target Blender, so there is no "
            "Blender add-on to build."
        )
        self._bump_button.setEnabled(project is not None and not building)
        self._add_wheel_button.setEnabled(project is not None)
        self._wheel_label_input.setEnabled(project is not None)
        self._wheel_action_input.setEnabled(project is not None)
        self._install_reblend_button.setEnabled(
            self._built_file("reblend") is not None and not building
        )
        self._install_blender_button.setEnabled(
            self._built_file("blender") is not None and not building
        )
        self._install_reblend_button.setToolTip(
            "Copy the built pack into Reblend's packs folder."
            if self._built_file("reblend") is not None else
            "Build the Reblend pack first. The install button turns "
            "on when a pack built from the current version is in the "
            "project's packs folder."
        )
        self._install_blender_button.setToolTip(
            "Copy the built add-on into Blender's add-ons folder."
            if self._built_file("blender") is not None else
            "Build the Blender add-on first. The install button "
            "turns on when an add-on built from the current version "
            "is in the project's packs folder."
        )

    # -- wheel buttons --------------------------------------------

    def _on_add_wheel(self):
        project = self._project
        if project is None:
            return
        label = self._wheel_label_input.text().strip()
        action = self._wheel_action_input.text().strip()
        if not label or not action:
            self._status_label.setText(
                "A wheel button needs both a label and an action. "
                "Fill in both, then add it."
            )
            return
        wheel = list(project.contributions.get("wheel", []))
        wheel.append({"label": label, "action": action})
        project.contributions = dict(project.contributions, wheel=wheel)
        error = project.save()
        if error is not None:
            self._status_label.setText(error)
            return
        self._wheel_label_input.clear()
        self._wheel_action_input.clear()
        self._status_label.setText(f"Added the wheel button {label}.")
        self._refresh()

    def _on_remove_wheel(self, index):
        project = self._project
        if project is None:
            return
        wheel = list(project.contributions.get("wheel", []))
        if index < 0 or index >= len(wheel):
            return
        removed = wheel.pop(index)
        project.contributions = dict(project.contributions, wheel=wheel)
        error = project.save()
        if error is not None:
            self._status_label.setText(error)
            return
        self._status_label.setText(
            f"Removed the wheel button {removed.get('label', '?')}."
        )
        self._refresh()

    # -- version --------------------------------------------------

    def _on_bump_clicked(self):
        project = self._project
        if project is None:
            return
        match = _VERSION_RE.match(project.version or "")
        if match is None:
            self._status_label.setText(
                f"The version '{project.version}' is not three "
                "numbers, so I cannot bump it. A version looks like "
                "1.2.3."
            )
            return
        major, minor, patch = (int(part) for part in match.groups())
        project.version = f"{major}.{minor}.{patch + 1}"
        error = project.save()
        if error is not None:
            self._status_label.setText(error)
            return
        self._status_label.setText(
            f"Version is now {project.version}."
        )
        self._refresh()

    # -- builds ---------------------------------------------------

    def build(self, target):
        """Start a build for ``target`` ("reblend" or "blender"),
        as the command palette does. Returns ``(started, reason)``:
        ``started`` is True when the build began, and ``reason`` is
        a plain-words sentence when it could not start (no project,
        a project that does not target that program, or a build
        already running). The build itself is the button's own
        click — no second copy of the logic."""
        if target not in ("reblend", "blender"):
            return False, (
                f"There is no {target} build. Build the Reblend "
                "pack or the Blender add-on."
            )
        if self._project is None:
            return False, (
                "Open a project first, or make a new one from the "
                "File menu. Then build the pack from here."
            )
        if self._building:
            return False, "A build is already running."
        button = (
            self._build_reblend_button
            if target == "reblend" else
            self._build_blender_button
        )
        if not button.isEnabled():
            # The button's tooltip is the window's own plain-words
            # reason for the target not being buildable.
            return False, button.toolTip()
        button.click()
        return True, None

    def _on_build_clicked(self, target):
        project = self._project
        if project is None or self._building:
            return
        self._building = True
        self._build_token += 1
        token = self._build_token
        self._build_started = time.monotonic()
        self._status_label.setText(
            "Building the Reblend pack..."
            if target == "reblend" else
            "Building the Blender add-on..."
        )
        self._refresh_buttons()
        worker = _BuildWorker(token, target, project)
        worker.done.connect(self._on_build_done)
        _track(worker)
        self._worker = worker
        worker.start()

    def _on_build_done(self, token, target, path, warnings, error):
        # The flags always reset, even for a stale answer: the window
        # is reused after closing, and a build that finished while it
        # was closed (or after a project switch) must not leave the
        # buttons disabled forever. Only the status report is gated
        # on the token.
        self._worker = None
        self._building = False
        if token != self._build_token:
            return  # the window closed, or the project changed
        if error is not None:
            self._status_label.setText(error)
        else:
            # A pack was built: its build time and its size are real
            # measurements, so the strip shows them. A failed build
            # records nothing — there is no pack to measure.
            record(
                "Last pack build",
                time.monotonic() - self._build_started,
                "seconds",
            )
            try:
                size_kb = path.stat().st_size / 1024
            except OSError:
                size_kb = None
            if size_kb is not None:
                record("Last pack size", size_kb, "KB")
            parts = [f"Built {path.name} in the project's packs folder."]
            parts.extend(warnings)
            shelf_error = self._record_in_shelf(target, path)
            if shelf_error is not None:
                parts.append(
                    "The pack is built, but I could not record it in "
                    f"the library: {shelf_error}"
                )
            self._status_label.setText(" ".join(parts))
        self._refresh()

    def _record_in_shelf(self, target, path) -> str | None:
        """Record a built file in the library shelf.

        Returns None on success, or the plain-words shelf error.
        A failed record never fails the build — the caller reports
        it as a warning.
        """
        project = self._project
        entry = {
            "pack_path": str(path),
            "project_id": project.id,
            "project_name": project.name,
            "project_root": str(project.root),
            "version": project.version,
            "target": target,
            "built": date.today().isoformat(),
            "test_run_id": None,
            "description": project.description,
        }
        return add_entry(self._shelf_path, entry)

    # -- installs -------------------------------------------------

    def _built_file(self, target) -> Path | None:
        """The pack or add-on built from the project's current
        version, when one sits in the packs folder. Nothing stale:
        a build from an older version does not count."""
        project = self._project
        if project is None:
            return None
        if target == "reblend":
            name = f"{project.id}-{project.version}.rblpack"
        else:
            name = f"{project.id}-{project.version}-blender.zip"
        candidate = project.packs_dir / name
        return candidate if candidate.is_file() else None

    def set_install_folder(self, target, path):
        """Remember where ``target`` installs go, without a file
        dialog. Tests use this to install into a temporary folder;
        the choice is also saved, so a later install reuses it."""
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

    def _on_install_clicked(self, target):
        project = self._project
        if project is None:
            return
        built = self._built_file(target)
        if built is None:
            self._status_label.setText(
                "Nothing is built from the current version yet. "
                "Build first, then install."
            )
            return
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
            installed, error = install_pack(built, folder)
            where = "Reblend"
        else:
            installed, error = install_blender_addon(built, folder)
            where = "Blender"
        if error is not None:
            self._status_label.setText(error)
            return
        self._status_label.setText(
            f"Installed in {where} at {installed}."
        )
        self._refresh()

    # -- closing --------------------------------------------------

    def closeEvent(self, event):
        # Invalidate any in-flight answer so a worker finishing after
        # the window closes cannot touch a dead window. The worker
        # itself is owned by the module set, not the window, so it
        # finishes cleanly in the background.
        self._build_token += 1
        super().closeEvent(event)


def _ships(relative_path: str) -> bool:
    """Whether a project-relative path is a file that ships in a
    pack: the code folders, assets, README, and icon. Everything
    else (tests, renders, chat history, project.json) stays home."""
    return (
        relative_path in _SHIPPED_FILES
        or any(
            relative_path.startswith(prefix)
            for prefix in _SHIPPED_PREFIXES
        )
    )
