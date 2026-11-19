"""The chat window (DOSSIER.md §6.3, §7): the AI workstation.

The front door and the heart of the suite, wired to the real loop
(``devsuite.chat.loop``). The loop is visible, exactly as §7.2
writes it:

1. Ask — Joshua describes what he wants in plain words.
2. Plan — the driver model answers with a plan, in a worker thread
   (the UI never blocks, §9.6). A status line shows what is
   happening and for how long, with Cancel.
3. Approve — the plan is shown as a card: summary, one plain-words
   line per step, Build it or Not this. Approval covers exactly
   the plan shown.
4. Build — Build it runs ``apply_plan`` in a worker thread, with
   progress and Cancel. The result is reported in plain words:
   what ran, which step failed and why, or that the build was
   cancelled (the snapshot still stands, so undo works).
5. Undo — Undo last build restores the latest snapshot (§7.4) and
   says plainly what it undid.

No project, no plan: with no project open, sending a message says
plainly to open a project first instead of failing. Ollama down or
a missing model shows the loop's plain-words error in the chat,
never a crash or a traceback.

The window also owns the update check (``devsuite.update``):
main() starts the silent launch check after the window shows —
up to date, unreachable, or no repo yet is silence — and the Help
menu holds a manual "Check for updates" that reports its result.
A newer release asks before anything is pulled, the pull is
verified by checksum before it installs, and a successful install
asks whether to restart now or on the next launch.

Above the footer sits the measurements strip (DOSSIER.md §6.10,
U37): the newest real numbers from the suite's own work — the last
model reply, the last build, the last pack, the last Blender test —
live, display-only. The numbers come from the measurements store
(``devsuite.measure.measurements``); this window records the model
reply and the build, the pack and Blender test windows record
theirs, and the strip refreshes the moment any number lands.

The window takes an injectable Ollama client (``client``) so tests
never need a real server, and a project (``project``) so tests can
open one without dialogs. It is a plain QWidget with a menu bar
in the layout (File: New Project, Open Project), sized for a
1366x768 screen: 1000x680 by default, resizable.
"""

from __future__ import annotations

import threading
import time
from pathlib import Path

from PySide6.QtCore import Qt, QThread, QTimer, Signal
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMenuBar,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from devsuite.chat.loop import (
    DEFAULT_DRIVER_MODEL,
    apply_plan,
    build_plan,
    plan_summary_lines,
)
from devsuite.chat.ollama import OllamaClient
from devsuite.chat.snapshot import (
    latest_snapshot,
    list_snapshots,
    restore_snapshot,
)
from devsuite.measure.measurements import (
    all_latest,
    record,
    subscribe,
    unsubscribe,
)
from devsuite.projects.project import Project, create_project, load_project
from devsuite.ui.blender_test_window import BlenderTestWindow
from devsuite.ui.help_window import HelpWindow
from devsuite.ui.library_window import LibraryWindow
from devsuite.ui.pack_window import PackWindow
from devsuite.ui.palette import CommandPalette
from devsuite.ui.style import CHAT_STYLESHEET
from devsuite.update import Updater

# Workers in flight, kept alive outside any window: a worker must
# never be destroyed while its thread is still running, and a
# window closed mid-plan must not take its worker down with it.
# A finished worker drops out of the set and is deleted by Qt.
_LIVE_WORKERS: set[QThread] = set()


def _track(worker: QThread) -> None:
    _LIVE_WORKERS.add(worker)
    worker.finished.connect(lambda: _LIVE_WORKERS.discard(worker))


def _format_measurement(entry: dict) -> str:
    """One measurement as a short strip item: "Last build: 2.3
    seconds", "Last Blender checks: 5 of 5 checks". Whole numbers
    stay whole; fractions show one decimal."""
    value = entry["value"]
    if isinstance(value, float):
        shown = f"{value:.1f}"
    else:
        shown = str(value)
    return f"{entry['name']}: {shown} {entry['unit']}"


class _PlanWorker(QThread):
    """Ask the driver model for a plan, off the UI thread.

    Emits ``done(token, plan, error)``: ``plan`` is the validated
    plan dict, or None with a plain-words ``error`` when no usable
    plan came back. ``token`` lets the window ignore answers from
    a request that was cancelled or superseded.
    """

    done = Signal(int, object, object)

    def __init__(self, token, request, project, client, parent=None):
        super().__init__(parent)
        self._token = token
        self._request = request
        self._project = project
        self._client = client

    def run(self):
        plan, error = build_plan(
            self._request, self._project, client=self._client
        )
        self.done.emit(self._token, plan, error)


class _BuildWorker(QThread):
    """Apply an approved plan, off the UI thread.

    Emits ``done(token, result)`` with the loop's ApplyResult.
    The approve callback always says yes: the Build it tap was the
    approval, and this worker runs only after that tap.
    """

    done = Signal(int, object)

    def __init__(self, token, plan, project, cancel_event, parent=None):
        super().__init__(parent)
        self._token = token
        self._plan = plan
        self._project = project
        self._cancel_event = cancel_event

    def run(self):
        result = apply_plan(
            self._plan,
            self._project,
            approve=lambda plan: True,
            cancelled=self._cancel_event.is_set,
        )
        self.done.emit(self._token, result)


class _UpdateCheckWorker(QThread):
    """Ask GitHub for the latest release, off the UI thread.

    Emits ``done(token, manual, result)`` with the check result
    dict. ``manual`` says whether Joshua asked for this check
    (Help menu) or it is the silent launch check — only a manual
    check reports "up to date" or "could not reach".
    """

    done = Signal(int, bool, object)

    def __init__(self, token, manual, updater, parent=None):
        super().__init__(parent)
        self._token = token
        self._manual = manual
        self._updater = updater

    def run(self):
        self.done.emit(self._token, self._manual, self._updater.check())


class _UpdateApplyWorker(QThread):
    """Pull a release through the verified path and install it,
    off the UI thread. Emits ``progress(text)`` as each step
    starts and ``done(token, ok, message)`` with the plain-words
    result. No cancel: a half-installed update is worse than a
    finished one, like the uninstaller.
    """

    progress = Signal(str)
    done = Signal(int, bool, object)

    def __init__(self, token, release, updater, parent=None):
        super().__init__(parent)
        self._token = token
        self._release = release
        self._updater = updater

    def run(self):
        ok, message = self._updater.apply(
            self._release, progress=self.progress.emit
        )
        self.done.emit(self._token, ok, message)


def _as_sentence(text):
    """A plain-words fragment as a sentence: capitalized, with a
    period when it has none. The update check's reasons arrive
    as lowercase fragments ("could not reach GitHub"), and a
    dialog should show a sentence, not a fragment."""
    text = (text or "").strip()
    if not text:
        return text
    if text[0].islower():
        text = text[0].upper() + text[1:]
    if text[-1] not in ".!?":
        text += "."
    return text


class ChatWindow(QWidget):
    """The AI chat interface workstation."""

    def __init__(self, client=None, project=None, updater=None,
                 parent=None):
        super().__init__(parent)
        self._client = client or OllamaClient()
        self._updater = updater or Updater()
        self._project: Project | None = None
        self._pending_plan: dict | None = None
        self._worker: QThread | None = None
        self._update_worker: QThread | None = None
        self._cancel_event: threading.Event | None = None
        self._plan_token = 0
        self._update_check_token = 0
        self._update_apply_token = 0
        self._update_check_started = False
        self._pack_window: PackWindow | None = None
        self._library_window: LibraryWindow | None = None
        self._blender_test_window: BlenderTestWindow | None = None
        self._help_window: HelpWindow | None = None
        self._palette: CommandPalette | None = None
        self._last_undone_id: str | None = None
        self._work_kind: str | None = None
        self._work_base = ""
        self._work_started = 0.0
        self._message_texts: list[tuple[str, str]] = []

        self.setStyleSheet(CHAT_STYLESHEET)
        self.resize(1000, 680)
        self.setMinimumSize(640, 420)
        self._build_ui()
        subscribe(self.refresh_measurements)
        self.refresh_measurements()
        self._elapsed_timer = QTimer(self)
        self._elapsed_timer.setInterval(1000)
        self._elapsed_timer.timeout.connect(self._on_elapsed_tick)

        if project is not None:
            self.set_project(project)
        else:
            self._update_title()
            self._update_project_label()
            self._refresh_undo()
            self._add_message(
                "suite",
                "No project open yet. Open a project or make a new one "
                "from the File menu, then tell me what to build.",
            )

    # -- layout ---------------------------------------------------

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self._build_menu(root)
        self._build_top_bar(root)
        self._build_messages(root)
        self._build_plan_card(root)
        self._build_status_row(root)
        self._build_input_row(root)
        self._build_measurements_strip(root)
        self._build_footer(root)

    def _build_menu(self, root):
        menu_bar = QMenuBar(self)
        file_menu = menu_bar.addMenu("File")
        self._new_action = file_menu.addAction("New Project...")
        self._new_action.setShortcut("Ctrl+N")
        self._new_action.triggered.connect(self._on_new_project)
        self._open_action = file_menu.addAction("Open Project...")
        self._open_action.setShortcut("Ctrl+O")
        self._open_action.triggered.connect(self._on_open_project)
        file_menu.addSeparator()
        quit_action = file_menu.addAction("Quit")
        quit_action.setShortcut("Ctrl+Q")
        quit_action.triggered.connect(self.close)
        window_menu = menu_bar.addMenu("Window")
        self._pack_window_action = window_menu.addAction("Pack window")
        self._pack_window_action.triggered.connect(self._on_pack_window)
        self._library_window_action = window_menu.addAction(
            "Library window"
        )
        self._library_window_action.triggered.connect(
            self._on_library_window
        )
        self._blender_test_window_action = window_menu.addAction(
            "Blender test window"
        )
        self._blender_test_window_action.triggered.connect(
            self._on_blender_test_window
        )
        window_menu.addSeparator()
        # The shortcut on the action is what opens the palette:
        # it shows Ctrl+K in the menu, so the menu teaches it, and
        # it fires whenever the chat window is active.
        self._palette_action = window_menu.addAction("Command palette")
        self._palette_action.setShortcut("Ctrl+K")
        self._palette_action.triggered.connect(self._on_palette)
        help_menu = menu_bar.addMenu("Help")
        self._help_action = help_menu.addAction("How to use")
        self._help_action.triggered.connect(self._on_help_window)
        self._check_updates_action = help_menu.addAction(
            "Check for updates"
        )
        self._check_updates_action.triggered.connect(
            self._on_check_for_updates
        )
        root.addWidget(menu_bar)

    def _build_top_bar(self, root):
        bar = QWidget(self)
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(12, 8, 12, 8)
        self._project_label = QLabel("No project open")
        self._project_label.setObjectName("MutedLabel")
        layout.addWidget(self._project_label)
        layout.addStretch(1)
        self._undo_button = QPushButton("Undo last build")
        self._undo_button.setToolTip(
            "Put the project back how it was before the last build."
        )
        self._undo_button.clicked.connect(self._on_undo_clicked)
        layout.addWidget(self._undo_button)
        root.addWidget(bar)

    def _build_messages(self, root):
        self._scroll = QScrollArea(self)
        self._scroll.setWidgetResizable(True)
        inner = QWidget()
        self._messages_layout = QVBoxLayout(inner)
        self._messages_layout.setContentsMargins(12, 4, 12, 4)
        self._messages_layout.addStretch(1)
        self._scroll.setWidget(inner)
        root.addWidget(self._scroll, 1)

    def _build_plan_card(self, root):
        self._plan_card = QFrame(self)
        self._plan_card.setObjectName("PlanCard")
        layout = QVBoxLayout(self._plan_card)
        layout.setContentsMargins(12, 10, 12, 10)
        heading = QLabel("THE PLAN")
        heading.setObjectName("RoleLabel")
        layout.addWidget(heading)
        self._plan_summary = QLabel()
        self._plan_summary.setWordWrap(True)
        summary_font = self._plan_summary.font()
        summary_font.setBold(True)
        self._plan_summary.setFont(summary_font)
        layout.addWidget(self._plan_summary)
        self._plan_steps = QLabel()
        self._plan_steps.setWordWrap(True)
        layout.addWidget(self._plan_steps)
        buttons = QHBoxLayout()
        self._build_button = QPushButton("Build it")
        self._build_button.setObjectName("PrimaryButton")
        self._build_button.clicked.connect(self._on_build_clicked)
        buttons.addWidget(self._build_button)
        self._not_this_button = QPushButton("Not this")
        self._not_this_button.clicked.connect(self._on_not_this_clicked)
        buttons.addWidget(self._not_this_button)
        buttons.addStretch(1)
        layout.addLayout(buttons)
        self._plan_card.hide()
        root.addWidget(self._plan_card)

    def _build_status_row(self, root):
        self._status_row = QWidget(self)
        layout = QHBoxLayout(self._status_row)
        layout.setContentsMargins(12, 6, 12, 6)
        self._progress_bar = QProgressBar(self)
        self._progress_bar.setFixedWidth(120)
        self._progress_bar.setFixedHeight(10)
        self._progress_bar.setTextVisible(False)
        layout.addWidget(self._progress_bar)
        self._status_label = QLabel()
        layout.addWidget(self._status_label, 1)
        self._cancel_button = QPushButton("Cancel")
        self._cancel_button.clicked.connect(self._on_cancel_clicked)
        layout.addWidget(self._cancel_button)
        self._status_row.hide()
        root.addWidget(self._status_row)

    def _build_input_row(self, root):
        row = QWidget(self)
        layout = QHBoxLayout(row)
        layout.setContentsMargins(12, 8, 12, 8)
        self._input = QLineEdit()
        self._input.setPlaceholderText("Tell me what to build...")
        self._input.returnPressed.connect(self._on_send)
        layout.addWidget(self._input, 1)
        self._send_button = QPushButton("Send")
        self._send_button.setObjectName("PrimaryButton")
        self._send_button.clicked.connect(self._on_send)
        layout.addWidget(self._send_button)
        root.addWidget(row)

    def _build_measurements_strip(self, root):
        self._measurements_label = QLabel()
        self._measurements_label.setObjectName("MutedLabel")
        self._measurements_label.setWordWrap(True)
        self._measurements_label.setContentsMargins(12, 2, 12, 2)
        root.addWidget(self._measurements_label)

    def _build_footer(self, root):
        self._footer_label = QLabel(
            f"Model {DEFAULT_DRIVER_MODEL} - ready"
        )
        self._footer_label.setObjectName("MutedLabel")
        self._footer_label.setContentsMargins(12, 4, 12, 8)
        root.addWidget(self._footer_label)

    # -- measurements -------------------------------------------------

    def refresh_measurements(self):
        """Show the newest measurements in the strip: one short
        "label: value unit" item per name, newest number each. With
        nothing measured yet this session, the strip says so plainly
        instead of showing a zero that was never measured."""
        entries = all_latest()
        if not entries:
            self._measurements_label.setText(
                "Nothing measured yet. Build or test something and "
                "the numbers show up here."
            )
            return
        self._measurements_label.setText(
            "  ·  ".join(
                _format_measurement(entry) for entry in entries
            )
        )

    def showEvent(self, event):
        # The strip subscribes to the measurements store, so a
        # number recorded anywhere in the suite shows up here the
        # moment it lands. Subscribing is idempotent, and the
        # refresh catches anything recorded while the window was
        # closed (close unsubscribes).
        subscribe(self.refresh_measurements)
        self.refresh_measurements()
        super().showEvent(event)

    # -- messages -------------------------------------------------

    def _add_message(self, role, text):
        """Add a chat row: a small mono role label over plain text."""
        self._message_texts.append((role, text))
        row = QWidget()
        layout = QVBoxLayout(row)
        layout.setContentsMargins(0, 6, 0, 6)
        role_label = QLabel("YOU" if role == "you" else "SUITE")
        role_label.setObjectName("RoleLabel")
        layout.addWidget(role_label)
        body = QLabel(text)
        body.setWordWrap(True)
        body.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(body)
        # The stretch is the last item; new rows go just before it.
        self._messages_layout.insertWidget(
            self._messages_layout.count() - 1, row
        )
        QTimer.singleShot(0, self._scroll_to_bottom)

    def _clear_messages(self):
        while self._messages_layout.count() > 1:
            item = self._messages_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self._message_texts.clear()

    def _scroll_to_bottom(self):
        bar = self._scroll.verticalScrollBar()
        bar.setValue(bar.maximum())

    # -- working state --------------------------------------------

    def _show_working(self, kind, base):
        """Show the status row: busy bar, what is happening, elapsed
        time, and Cancel — while a plan is being asked for, and
        while a build runs (U26: every long operation offers
        cancel). An update in flight shows the same row with no
        Cancel: a half-installed update is worse than a finished
        one, like the uninstaller."""
        self._work_kind = kind
        self._work_base = base
        self._work_started = time.monotonic()
        self._status_label.setText(base + "...")
        self._progress_bar.setRange(0, 0)
        self._cancel_button.setVisible(kind in ("plan", "build"))
        self._cancel_button.setEnabled(True)
        self._status_row.show()
        self._footer_label.setText(
            f"Model {DEFAULT_DRIVER_MODEL} - {base.lower()}"
        )
        self._elapsed_timer.start()
        self._refresh_undo()
        self._new_action.setEnabled(False)
        self._open_action.setEnabled(False)

    def _hide_working(self):
        self._work_kind = None
        self._elapsed_timer.stop()
        self._status_row.hide()
        self._footer_label.setText(f"Model {DEFAULT_DRIVER_MODEL} - ready")
        self._refresh_undo()
        self._new_action.setEnabled(True)
        self._open_action.setEnabled(True)

    def _on_elapsed_tick(self):
        seconds = int(time.monotonic() - self._work_started)
        self._status_label.setText(f"{self._work_base}... {seconds}s")

    def _set_input_enabled(self, enabled):
        self._input.setEnabled(enabled)
        self._send_button.setEnabled(enabled)

    # -- the loop: ask, plan, approve, build ----------------------

    def _on_send(self):
        text = self._input.text().strip()
        if not text:
            return
        self._add_message("you", text)
        self._input.clear()
        if self._project is None:
            self._add_message(
                "suite",
                "Open a project first, or make a new one from the File "
                "menu. Then tell me what to build, and I will make a "
                "plan for it.",
            )
            return
        if self._pending_plan is not None:
            # A new request sets the old plan aside; it can no longer
            # be approved, so Build it can never run a stale plan.
            self._pending_plan = None
            self._hide_plan_card()
            self._add_message(
                "suite", "Set that plan aside. Nothing was built from it."
            )
        self._start_plan(text)

    def _start_plan(self, request):
        self._plan_token += 1
        token = self._plan_token
        self._set_input_enabled(False)
        self._show_working("plan", f"Asking {DEFAULT_DRIVER_MODEL} for a plan")
        worker = _PlanWorker(
            token, request, self._project, self._client
        )
        worker.done.connect(self._on_plan_done)
        _track(worker)
        self._worker = worker
        worker.start()

    def _on_plan_done(self, token, plan, error):
        if token != self._plan_token:
            return  # cancelled or superseded; ignore the stale answer
        self._worker = None
        self._hide_working()
        self._set_input_enabled(True)
        if error is not None:
            # The loop's error is already plain words (Ollama down,
            # model missing, answer not a plan). Show it as it is.
            # No reply came back, so no reply time is recorded.
            self._add_message("suite", error)
            return
        # A plan came back: the wait was a real model reply, and
        # its length is a real measurement.
        record(
            "Last model reply",
            time.monotonic() - self._work_started,
            "seconds",
        )
        self._pending_plan = plan
        self._show_plan_card(plan)
        self._add_message(
            "suite",
            "Here is the plan. Tap Build it to run it, or Not this "
            "to leave it alone.",
        )

    def _show_plan_card(self, plan):
        self._plan_summary.setText(plan.get("summary", ""))
        steps = plan_summary_lines(plan)
        self._plan_steps.setText("\n".join("\u2022  " + line for line in steps))
        self._plan_card.show()
        QTimer.singleShot(0, self._scroll_to_bottom)

    def _hide_plan_card(self):
        self._plan_card.hide()

    def _on_build_clicked(self):
        plan = self._pending_plan
        if plan is None or self._project is None:
            return
        # The tap is the approval, and it covers exactly this plan:
        # the card is gone before the build starts, so the plan
        # cannot be approved twice or swapped mid-build.
        self._pending_plan = None
        self._hide_plan_card()
        self._plan_token += 1
        token = self._plan_token
        self._set_input_enabled(False)
        self._show_working("build", "Building the plan")
        self._cancel_event = threading.Event()
        worker = _BuildWorker(token, plan, self._project, self._cancel_event)
        worker.done.connect(self._on_build_done)
        _track(worker)
        self._worker = worker
        worker.start()

    def _on_build_done(self, token, result):
        if token != self._plan_token:
            return
        self._worker = None
        self._hide_working()
        self._set_input_enabled(True)
        self._refresh_undo()
        # A build that ran to an answer — applied, or stopped at a
        # failed step — has a real duration. A cancelled build was
        # stopped, not finished, so it records nothing.
        if result.applied or result.failed_step is not None:
            record(
                "Last build",
                time.monotonic() - self._work_started,
                "seconds",
            )
        if result.cancelled:
            done = ". ".join(result.completed)
            detail = f" {done}." if done else " Nothing had run yet."
            self._add_message(
                "suite",
                f"Cancelled the build.{detail} Undo last build puts "
                "the project back how it was.",
            )
        elif result.applied:
            done = ". ".join(result.completed)
            self._add_message("suite", f"Built it. {done}.")
        elif result.failed_step is not None:
            self._add_message(
                "suite",
                f"Stopped at step {result.failed_step['index']}. "
                f"{result.error}",
            )
        elif result.error is not None:
            self._add_message("suite", result.error)
        else:
            self._add_message("suite", "Nothing was built.")

    def _on_not_this_clicked(self):
        self._pending_plan = None
        self._hide_plan_card()
        self._add_message("suite", "Left it alone. Nothing changed.")

    def _on_cancel_clicked(self):
        if self._work_kind == "build":
            # The build worker sees the event and stops: between
            # steps, or by killing a running check. The worker's
            # done signal reports the cancel; the token is left
            # alone so the result is processed.
            if self._cancel_event is not None:
                self._cancel_event.set()
            self._cancel_button.setEnabled(False)
            self._status_label.setText("Cancelling...")
            return
        # Cancelling a plan wait: the in-flight model call finishes
        # on its own in the background; bumping the token means its
        # answer is ignored when it arrives, and nothing is built
        # from it.
        self._plan_token += 1
        self._worker = None
        self._hide_working()
        self._set_input_enabled(True)
        self._add_message(
            "suite", "Stopped waiting for the plan. Nothing changed."
        )

    # -- undo -----------------------------------------------------

    def _on_undo_clicked(self):
        # The button is disabled when there is nothing to undo, so
        # these messages only ever fire from the palette — where a
        # command that cannot run must say so, never stay silent.
        if self._project is None:
            self._add_message(
                "suite",
                "Open a project first, or make a new one from the "
                "File menu. Then build something, and undo will "
                "put it back.",
            )
            return
        snapshots = list_snapshots(self._project.root)
        if not snapshots:
            self._add_message(
                "suite", "Nothing to undo yet. Undo works after a build."
            )
            return
        latest = snapshots[0]
        ok, error = restore_snapshot(self._project.root, latest["id"])
        if not ok:
            self._add_message("suite", error)
            return
        self._last_undone_id = latest["id"]
        self._refresh_undo()
        parts = ["Undid the last build."]
        if latest.get("summary"):
            parts.append(f"It was: {latest['summary']}")
        restored = [
            entry["path"]
            for entry in latest.get("files", [])
            if entry.get("existed")
        ]
        removed = [
            entry["path"]
            for entry in latest.get("files", [])
            if not entry.get("existed")
        ]
        if restored:
            parts.append("Put back: " + ", ".join(restored) + ".")
        if removed:
            parts.append(
                "Removed: " + ", ".join(removed)
                + " (those files did not exist before)."
            )
        self._add_message("suite", " ".join(parts))

    def _refresh_undo(self):
        """Undo is on only when there is a snapshot newer than the
        last undo, and no work is running (undo must not race a
        build)."""
        enabled = False
        if self._project is not None and self._work_kind is None:
            latest = latest_snapshot(self._project.root)
            enabled = latest is not None and latest != self._last_undone_id
        self._undo_button.setEnabled(enabled)

    # -- projects -------------------------------------------------

    def set_project(self, project):
        """Open ``project`` in this window: title, label, undo state,
        and a fresh conversation for the project. The pack window,
        when it is open, follows the same project — it must never
        keep showing (and building) the project that was open
        before."""
        self._project = project
        self._pending_plan = None
        self._hide_plan_card()
        self._last_undone_id = None
        self._clear_messages()
        self._update_title()
        self._update_project_label()
        self._refresh_undo()
        if self._pack_window is not None:
            self._pack_window.set_project(project)
        if self._blender_test_window is not None:
            self._blender_test_window.set_project(project)
        self._add_message(
            "suite",
            f"Opened {project.name}. Tell me what to build, and I "
            "will make a plan for it.",
        )

    def open_project(self, path):
        """Open the project in the folder at ``path``.

        Returns None on success, or the plain-words error (also
        shown in the chat) when the folder holds no readable
        project. Used by the File menu and by tests.
        """
        project, error = load_project(path)
        if error is not None:
            self._add_message("suite", error)
            return error
        self.set_project(project)
        return None

    def _on_new_project(self):
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
        project, error = create_project(
            Path(folder) / safe_name, name=name, targets=targets
        )
        if error is not None:
            self._add_message("suite", error)
            return
        self.set_project(project)

    def _on_open_project(self):
        folder = QFileDialog.getExistingDirectory(
            self, "Open a project folder"
        )
        if not folder:
            return
        self.open_project(folder)

    def _update_title(self):
        if self._project is None:
            self.setWindowTitle(
                "No project open - Chat - Reblend Add-on Dev Suite"
            )
        else:
            self.setWindowTitle(
                f"{self._project.name} - Chat - Reblend Add-on Dev Suite"
            )

    def _update_project_label(self):
        if self._project is None:
            self._project_label.setText("No project open")
        else:
            targets = ", ".join(self._project.targets)
            self._project_label.setText(
                f"Project: {self._project.name} ({targets})"
            )

    # -- windows --------------------------------------------------

    def _on_pack_window(self):
        """Open the pack window for the current project. One pack
        window is kept and reused; opening it again follows the
        project that is open now. With no project open, the pack
        window says so itself."""
        if self._pack_window is None:
            self._pack_window = PackWindow()
        self._pack_window.set_project(self._project)
        self._pack_window.show()
        self._pack_window.raise_()
        self._pack_window.activateWindow()

    def _on_library_window(self):
        """Open the library window: the shelf of built packs, plus
        the templates. One library window is kept and reused; it
        re-reads the shelf every time it is shown, so a build in
        the pack window shows up when the library opens again."""
        if self._library_window is None:
            self._library_window = LibraryWindow(
                open_project=self._open_project_from_library
            )
        self._library_window.show()
        self._library_window.raise_()
        self._library_window.activateWindow()

    def _on_blender_test_window(self):
        """Open the Blender test window for the current project.
        One window is kept and reused; opening it again follows
        the project that is open now. With no project open, the
        test window says so itself."""
        if self._blender_test_window is None:
            self._blender_test_window = BlenderTestWindow()
        self._blender_test_window.set_project(self._project)
        self._blender_test_window.show()
        self._blender_test_window.raise_()
        self._blender_test_window.activateWindow()

    def _on_help_window(self):
        """Open the How to Use index. One window is kept and
        reused; help takes no project, so there is nothing to
        follow when the project changes."""
        if self._help_window is None:
            self._help_window = HelpWindow()
        self._help_window.show()
        self._help_window.raise_()
        self._help_window.activateWindow()

    def _open_project_from_library(self, path):
        """Open the project at ``path`` (from the library window)
        and bring the chat window forward. A project that cannot be
        opened says so in the chat, in plain words."""
        error = self.open_project(path)
        if error is None:
            self.show()
            self.raise_()
            self.activateWindow()

    # -- the command palette --------------------------------------

    def _on_palette(self):
        """Open the command palette (Ctrl+K): every command,
        searchable. One palette is kept and reused; the command
        list is built fresh each time it opens."""
        if self._palette is None:
            self._palette = CommandPalette(self)
        self._palette.set_commands(self._palette_commands())
        self._palette.open_over(self)

    def _palette_commands(self):
        """The commands the palette offers: (label, shortcut,
        action). Plan commands only appear while a plan is
        pending; everything else is always there, and a command
        that cannot run in the moment says so when it is run."""
        commands = [
            ("New project", "Ctrl+N", self._on_new_project),
            ("Open project", "Ctrl+O", self._on_open_project),
            ("Undo last build", "", self._on_undo_clicked),
        ]
        if self._pending_plan is not None:
            commands.append(("Build the plan", "", self._on_build_clicked))
            commands.append(
                ("Dismiss the plan", "", self._on_not_this_clicked)
            )
        commands.extend([
            ("Build Reblend pack", "", self._palette_build_reblend),
            ("Build Blender add-on", "", self._palette_build_blender),
            ("Run Blender test", "", self._palette_run_blender_test),
            ("Open Pack window", "", self._on_pack_window),
            ("Open Library window", "", self._on_library_window),
            ("Open Blender test window", "", self._on_blender_test_window),
            ("How to use", "", self._on_help_window),
            ("Quit", "Ctrl+Q", self.close),
        ])
        return commands

    def _palette_build(self, target):
        """Build the pack for ``target`` from the palette: the pack
        window opens and its own build runs. With no project open,
        or a project that does not target that program, the chat
        says so plainly instead."""
        if self._project is None:
            self._add_message(
                "suite",
                "Open a project first, or make a new one from the "
                "File menu. Then build the pack from the pack window.",
            )
            return
        self._on_pack_window()
        started, reason = self._pack_window.build(target)
        if not started:
            self._add_message("suite", reason)

    def _palette_build_reblend(self):
        self._palette_build("reblend")

    def _palette_build_blender(self):
        self._palette_build("blender")

    def _palette_run_blender_test(self):
        """Run the Blender test from the palette. With exactly one
        Blender add-on built, it runs on that one — the command
        names the test, and there is only one add-on it could
        mean. With none, or more than one, the test window opens
        and the chat says what to do there."""
        if self._project is None:
            self._add_message(
                "suite",
                "Open a project first, or make a new one from the "
                "File menu. Then test the add-on in the Blender "
                "test window.",
            )
            return
        zips = sorted(
            path
            for path in self._project.packs_dir.glob("*-blender.zip")
            if path.is_file()
        )
        if len(zips) == 1:
            self._on_blender_test_window()
            started, reason = self._blender_test_window.run_test_for(
                zips[0]
            )
            if not started:
                self._add_message("suite", reason)
            return
        self._on_blender_test_window()
        if not zips:
            self._add_message(
                "suite",
                "No Blender add-on is built yet. Build the Blender "
                "add-on from the pack window first.",
            )
        else:
            self._add_message(
                "suite",
                "More than one Blender add-on is built. Pick one in "
                "the Blender test window, then tap Run test.",
            )

    # -- updates --------------------------------------------------

    def start_update_check(self):
        """Start the silent launch check, once. Only an installed
        suite checks: a tree run with no install has nothing to
        update. Called by main() after the window shows, so the
        check never blocks the window opening — and so windows
        built without main() (tests, the installer's smoke check)
        never touch the network. Up to date, unreachable, or no
        repo yet: all silence, by design."""
        if self._update_check_started:
            return
        if not self._updater.is_installed():
            return
        self._update_check_started = True
        self._start_update_check(manual=False)

    def _start_update_check(self, manual):
        self._update_check_token += 1
        token = self._update_check_token
        worker = _UpdateCheckWorker(token, manual, self._updater)
        worker.done.connect(self._on_update_check_done)
        _track(worker)
        self._update_worker = worker
        worker.start()

    def _on_check_for_updates(self):
        """The manual check (Help menu): Joshua asked, so the
        result is reported, whatever it is. A tree run with no
        install says so plainly instead of checking."""
        if not self._updater.is_installed():
            QMessageBox.information(
                self,
                "Check for updates",
                "The suite is not installed yet, so there is "
                "nothing to update.",
            )
            return
        self._start_update_check(manual=True)

    def _on_update_check_done(self, token, manual, result):
        if token != self._update_check_token:
            return  # superseded or the window closed; ignore it
        self._update_worker = None
        if result["state"] == "newer":
            answer = QMessageBox.question(
                self,
                "Update available",
                f"Version {result['latest']} of Reblend Add-on "
                "Dev Suite is out. Update now?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if answer == QMessageBox.Yes:
                self._start_update_apply(result["release"])
            return
        if not manual:
            return  # silent check: up to date or unreachable is no news
        if result["state"] == "current":
            QMessageBox.information(
                self,
                "Check for updates",
                "You have the newest version.",
            )
        else:
            QMessageBox.information(
                self,
                "Check for updates",
                _as_sentence(result["reason"]),
            )

    def _start_update_apply(self, release):
        self._update_apply_token += 1
        token = self._update_apply_token
        self._show_working("update", "Updating the suite")
        worker = _UpdateApplyWorker(token, release, self._updater)
        worker.progress.connect(self._on_update_progress)
        worker.done.connect(self._on_update_apply_done)
        _track(worker)
        self._update_worker = worker
        worker.start()

    def _on_update_progress(self, text):
        # The elapsed timer rewrites the status label every second
        # from the base text, so the progress step becomes the
        # base: the label shows the step and the seconds together.
        self._work_base = text.rstrip(".")
        self._status_label.setText(f"{self._work_base}...")

    def _on_update_apply_done(self, token, ok, message):
        if token != self._update_apply_token:
            return  # superseded or the window closed; ignore it
        self._update_worker = None
        self._hide_working()
        if not ok:
            QMessageBox.information(self, "Update", message)
            return
        answer = QMessageBox.question(
            self,
            "Update installed",
            "The update is installed. Restart now to complete "
            "the update?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            self._add_message(
                "suite",
                "The update will finish the next time the suite "
                "starts.",
            )
            return
        _command, error = self._updater.relaunch()
        if error is not None:
            # The relaunch failed: stay running and say so, or
            # quitting would leave Joshua with no suite at all.
            QMessageBox.information(self, "Update", error)
            return
        QApplication.instance().quit()

    # -- closing --------------------------------------------------

    def closeEvent(self, event):
        # Invalidate any in-flight answer so a worker finishing after
        # the window closes cannot touch a dead window. The worker
        # itself is owned by the module set, not the window, so it
        # finishes cleanly in the background.
        self._plan_token += 1
        self._update_check_token += 1
        self._update_apply_token += 1
        # Stop hearing about measurements: a closed window must not
        # be refreshed, and the subscription must not keep it alive.
        # showEvent subscribes again if the window opens again.
        unsubscribe(self.refresh_measurements)
        if self._cancel_event is not None:
            # A build in flight stops promptly instead of running
            # on blind after the window closes.
            self._cancel_event.set()
        super().closeEvent(event)
