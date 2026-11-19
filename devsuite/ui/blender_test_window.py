"""The Blender test window (DOSSIER.md §8.3): driven, not embedded.

Blender cannot be embedded inside another program's window, so
the suite drives it instead: the window writes a test script,
starts Blender in background mode as a subprocess, and shows
what comes back — the renders, the plain-words checklist, and
the log. The same shape as the Reblend results, so the two
targets feel like one workflow.

The window takes a project (``project``). Joshua picks one of the
built Blender add-ons in the project's packs/ folder — nothing is
selected by default (U6) — and taps Run test. The run happens in
a worker thread (the UI never blocks, §9.6) and can be cancelled
(U26: a Blender run can take minutes). The run folder is a dated
folder under the project's renders/ directory (§9.4), holding the
test script, the render, and the run record (``result.json``).

Blender runs in the background for this test. To try the add-on
by hand, install it from the pack window and open Blender — the
suite is honest about that boundary in the window itself.

When Blender is not installed, the window says so plainly and Run
stays disabled; the Reblend side is unaffected. With no project
open, the window says so and disables the actions.
"""

from __future__ import annotations

import threading
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from devsuite.blender_drive.runner import find_blender, run_blender_test
from devsuite.blender_drive.scripts import (
    RENDER_NAME,
    generate_test_script,
    write_test_script,
    zip_is_legacy,
)
from devsuite.measure.measurements import record
from devsuite.projects.project import Project
from devsuite.ui.style import CHAT_STYLESHEET

# Workers in flight, kept alive outside any window: a worker must
# never be destroyed while its thread is still running, and a
# window closed mid-run must not take its worker down with it.
# A finished worker drops out of the set and is deleted by Qt.
_LIVE_WORKERS: set[QThread] = set()


def _track(worker: QThread) -> None:
    _LIVE_WORKERS.add(worker)
    worker.finished.connect(lambda: _LIVE_WORKERS.discard(worker))


class _TestWorker(QThread):
    """Run one Blender test, off the UI thread.

    Emits ``done(token, result)``: ``result`` is the runner's
    result dict. ``token`` lets the window ignore answers from a
    run that started before the window closed or the project
    changed. ``cancel_event`` is how the window stops the run.
    """

    done = Signal(int, object)

    def __init__(self, token, blender_exe, addon_zip, script_path,
                 run_dir, cancel_event, parent=None):
        super().__init__(parent)
        self._token = token
        self._blender_exe = blender_exe
        self._addon_zip = addon_zip
        self._script_path = script_path
        self._run_dir = run_dir
        self._cancel_event = cancel_event

    def run(self):
        result = run_blender_test(
            self._blender_exe,
            self._addon_zip,
            self._script_path,
            self._run_dir,
            cancelled=self._cancel_event.is_set,
        )
        self.done.emit(self._token, result)


class BlenderTestWindow(QWidget):
    """Drive Blender in the background and show what comes back."""

    def __init__(self, project=None, parent=None):
        super().__init__(parent)
        self._project: Project | None = None
        self._blender_exe: str | None = None
        self._worker: QThread | None = None
        self._cancel_event = threading.Event()
        self._test_token = 0
        self._running = False
        self._run_dir: Path | None = None
        self._result_summary = ""
        self._check_lines: list[str] = []
        self._log_text = ""
        self._render_path: Path | None = None

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
            "window's File menu. Then come back here to test it in "
            "Blender."
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
        self._build_picker(inner_layout)
        self._build_run_card(inner_layout)
        self._build_results(inner_layout)
        inner_layout.addStretch(1)
        scroll.setWidget(inner)
        layout.addWidget(scroll, 1)
        root.addWidget(self._content, 1)

    def _build_picker(self, layout):
        card = QFrame(self)
        card.setObjectName("PlanCard")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(12, 10, 12, 10)
        heading = QLabel("THE ADD-ON TO TEST")
        heading.setObjectName("RoleLabel")
        card_layout.addWidget(heading)
        note = QLabel(
            "Blender runs in the background for this test. Open "
            "Blender to try the add-on by hand."
        )
        note.setObjectName("MutedLabel")
        note.setWordWrap(True)
        card_layout.addWidget(note)
        self._blender_label = QLabel()
        self._blender_label.setObjectName("MutedLabel")
        self._blender_label.setWordWrap(True)
        card_layout.addWidget(self._blender_label)
        self._zip_list = QListWidget()
        # Tall enough for a few built add-ons; the results below
        # matter more than empty list space.
        self._zip_list.setMaximumHeight(120)
        self._zip_list.setSelectionMode(
            QListWidget.SelectionMode.SingleSelection
        )
        self._zip_list.currentItemChanged.connect(
            lambda *_: self._refresh_buttons()
        )
        card_layout.addWidget(self._zip_list)
        self._no_zips_label = QLabel(
            "No Blender add-on is built yet. Build the Blender "
            "add-on from the pack window first."
        )
        self._no_zips_label.setObjectName("MutedLabel")
        self._no_zips_label.setWordWrap(True)
        card_layout.addWidget(self._no_zips_label)
        layout.addWidget(card)

    def _build_run_card(self, layout):
        card = QFrame(self)
        card.setObjectName("PlanCard")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(12, 10, 12, 10)
        heading = QLabel("RUN THE TEST")
        heading.setObjectName("RoleLabel")
        card_layout.addWidget(heading)
        row = QHBoxLayout()
        self._run_button = QPushButton("Run test")
        self._run_button.setObjectName("PrimaryButton")
        self._run_button.clicked.connect(self._on_run_clicked)
        row.addWidget(self._run_button)
        self._cancel_button = QPushButton("Cancel")
        self._cancel_button.clicked.connect(self._on_cancel_clicked)
        row.addWidget(self._cancel_button)
        row.addStretch(1)
        card_layout.addLayout(row)
        layout.addWidget(card)

    def _build_results(self, layout):
        card = QFrame(self)
        card.setObjectName("PlanCard")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(12, 10, 12, 10)
        heading = QLabel("RESULTS")
        heading.setObjectName("RoleLabel")
        card_layout.addWidget(heading)
        self._summary_label = QLabel(
            "No test has run yet. Pick an add-on above and run the "
            "test to see its results here."
        )
        self._summary_label.setWordWrap(True)
        card_layout.addWidget(self._summary_label)
        self._elapsed_label = QLabel()
        self._elapsed_label.setObjectName("MutedLabel")
        card_layout.addWidget(self._elapsed_label)
        self._check_rows = QVBoxLayout()
        self._check_rows.setSpacing(6)
        card_layout.addLayout(self._check_rows)
        self._render_label = QLabel()
        self._render_label.setWordWrap(True)
        card_layout.addWidget(self._render_label)
        self._log_button = QPushButton("Show Blender log")
        self._log_button.clicked.connect(self._on_log_button_clicked)
        card_layout.addWidget(self._log_button)
        self._log_text_edit = QPlainTextEdit()
        self._log_text_edit.setReadOnly(True)
        self._log_text_edit.setMaximumBlockCount(200)
        self._log_text_edit.hide()
        card_layout.addWidget(self._log_text_edit)
        layout.addWidget(card)

    def _build_footer(self, root):
        self._status_label = QLabel("Ready")
        self._status_label.setObjectName("MutedLabel")
        self._status_label.setWordWrap(True)
        self._status_label.setContentsMargins(12, 4, 12, 8)
        root.addWidget(self._status_label)

    def showEvent(self, event):
        # Re-list the built add-ons every time the window is shown:
        # a build in the pack window shows up when this window opens
        # again. Results are left alone — a run in flight is not
        # disturbed by showing the window.
        self._refresh_picker()
        super().showEvent(event)

    # -- project --------------------------------------------------

    def set_project(self, project):
        """Open ``project`` in this window: picker, results, and
        buttons all follow it. When the project actually changes,
        an in-flight run's answer is invalidated (the run still
        finishes in the background and its record lands in the old
        project's renders folder — it just cannot report into a
        window showing a different project)."""
        if project is not self._project:
            self._test_token += 1
        self._project = project
        self._clear_results()
        self._refresh()

    def _refresh(self):
        """Recompute everything from the project: title, picker,
        Blender state, and which buttons are on."""
        project = self._project
        if project is None:
            self.setWindowTitle(
                "No project open - Blender test - "
                "Reblend Add-on Dev Suite"
            )
            self._project_label.setText("No project open")
            self._no_project_label.show()
            self._content.hide()
            self._status_label.setText("Ready")
            self._refresh_buttons()
            return
        self.setWindowTitle(
            f"{project.name} - Blender test - Reblend Add-on Dev Suite"
        )
        targets = ", ".join(project.targets)
        self._project_label.setText(
            f"Project: {project.name} ({targets})"
        )
        self._no_project_label.hide()
        self._content.show()
        self._blender_exe = find_blender()
        if self._blender_exe is None:
            self._blender_label.setText(
                "Blender is not installed, so Blender tests cannot "
                "run. The Reblend side still works fully."
            )
        else:
            self._blender_label.setText(
                f"Blender found at {self._blender_exe}."
            )
        self._refresh_picker()
        self._refresh_buttons()

    def _refresh_picker(self):
        """List the built Blender add-ons, newest first. Nothing is
        selected — Joshua picks one (U6)."""
        project = self._project
        self._zip_list.clear()
        if project is None:
            self._no_zips_label.hide()
            return
        zips = sorted(
            (path for path in project.packs_dir.glob("*-blender.zip")
             if path.is_file()),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )
        for path in zips:
            item = QListWidgetItem(path.name)
            item.setData(Qt.ItemDataRole.UserRole, str(path))
            self._zip_list.addItem(item)
        self._zip_list.setCurrentRow(-1)
        self._no_zips_label.setVisible(not zips)
        self._refresh_buttons()

    def _refresh_buttons(self):
        """Which buttons are on: Run needs a project, Blender, a
        picked add-on, and no run in flight; Cancel only runs while
        a run is in flight."""
        project = self._project
        running = self._running
        picked = self._zip_list.currentItem() is not None
        blender = self._blender_exe is not None
        self._run_button.setEnabled(
            project is not None and blender and picked and not running
        )
        if project is None:
            reason = "Open a project first."
        elif not blender:
            reason = (
                "Blender is not installed, so Blender tests cannot "
                "run."
            )
        elif not picked:
            reason = "Pick an add-on to test first."
        elif running:
            reason = "A test is already running."
        else:
            reason = "Run the picked add-on through Blender."
        self._run_button.setToolTip(reason)
        self._cancel_button.setEnabled(running)
        self._cancel_button.setText("Cancel")
        self._zip_list.setEnabled(project is not None and not running)
        self._log_button.setEnabled(bool(self._log_text))

    # -- results --------------------------------------------------

    def _clear_results(self):
        """Forget the last run's results (a new project has none)."""
        self._result_summary = ""
        self._check_lines = []
        self._log_text = ""
        self._render_path = None
        self._run_dir = None
        self._summary_label.setText(
            "No test has run yet. Pick an add-on above and run the "
            "test to see its results here."
        )
        self._elapsed_label.setText("")
        while self._check_rows.count():
            item = self._check_rows.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self._render_label.clear()
        self._render_label.setText("")
        self._log_text_edit.clear()
        self._log_text_edit.hide()
        self._log_button.setText("Show Blender log")
        self._refresh_buttons()

    def _show_results(self, result):
        """Show a finished run: summary, elapsed time, checklist,
        render, and the log behind one click."""
        self._result_summary = result.get("summary", "")
        self._summary_label.setText(self._result_summary)
        elapsed = result.get("elapsed_seconds")
        if elapsed is not None:
            self._elapsed_label.setText(
                f"Finished in {elapsed} seconds."
            )
        else:
            self._elapsed_label.setText("")

        while self._check_rows.count():
            item = self._check_rows.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self._check_lines = []
        for check in result.get("checks", []):
            name = check.get("name", "?")
            detail = check.get("detail", "")
            if check.get("passed"):
                line = f"Passed: {name}"
            else:
                line = f"Failed: {name}"
            self._check_lines.append(line)
            value_label = QLabel(line)
            value_label.setWordWrap(True)
            value_font = value_label.font()
            value_font.setBold(True)
            value_label.setFont(value_font)
            self._check_rows.addWidget(value_label)
            if detail:
                detail_label = QLabel(detail)
                detail_label.setObjectName("MutedLabel")
                detail_label.setWordWrap(True)
                self._check_rows.addWidget(detail_label)

        self._render_path = None
        renders = result.get("renders", [])
        if renders and self._run_dir is not None:
            render_path = self._run_dir / renders[0]
            pixmap = QPixmap(str(render_path))
            if not pixmap.isNull():
                self._render_path = render_path
                # No setText after setPixmap: setting text clears
                # the pixmap on a QLabel.
                self._render_label.setPixmap(
                    pixmap.scaled(
                        512, 384, Qt.KeepAspectRatio,
                        Qt.SmoothTransformation,
                    )
                )
            else:
                self._render_label.setText(
                    f"Render written: {renders[0]} "
                    "(could not show it)."
                )
        else:
            self._render_label.setText("")
            self._render_label.clear()

        self._log_text = "\n".join(result.get("log", []))
        self._log_text_edit.setPlainText(self._log_text)
        self._log_text_edit.hide()
        self._log_button.setText("Show Blender log")
        self._refresh_buttons()

    # -- running --------------------------------------------------

    def _selected_zip(self) -> Path | None:
        item = self._zip_list.currentItem()
        if item is None:
            return None
        return Path(item.data(Qt.ItemDataRole.UserRole))

    def _operator_id(self) -> str | None:
        """The operator to run: the project's first wheel
        contribution action, or None when the project declares
        none — the operator check is left out then."""
        project = self._project
        if project is None:
            return None
        wheel = project.contributions.get("wheel", [])
        if not wheel:
            return None
        action = wheel[0].get("action", "")
        return action or None

    def _make_run_dir(self) -> Path:
        """A dated folder under the project's renders/ directory,
        unique even for two runs in one second."""
        stamp = datetime.now().strftime("%Y-%m-%d-%H%M%S")
        base = self._project.renders_dir / f"blender-test-{stamp}"
        run_dir = base
        suffix = 2
        while run_dir.exists():
            run_dir = self._project.renders_dir / (
                f"blender-test-{stamp}-{suffix}"
            )
            suffix += 1
        return run_dir

    def run_test_for(self, zip_path):
        """Run the test for the add-on at ``zip_path``, as the
        command palette does. Returns ``(started, reason)``:
        ``started`` is True when the run began, and ``reason`` is
        a plain-words sentence when it could not start (a run
        already in flight, no Blender installed, or the add-on no
        longer in the packs folder). The run itself is the Run
        button's own handler — no second copy of the logic."""
        if self._project is None:
            return False, "Open a project first."
        if self._running:
            return False, "A test is already running."
        if find_blender() is None:
            return False, (
                "Blender is not installed, so Blender tests cannot "
                "run. The Reblend side still works fully."
            )
        self._refresh_picker()
        for row in range(self._zip_list.count()):
            item = self._zip_list.item(row)
            if Path(item.data(Qt.ItemDataRole.UserRole)) == Path(zip_path):
                self._zip_list.setCurrentItem(item)
                break
        else:
            return False, (
                "That add-on is not in the packs folder anymore. "
                "Build it again from the pack window."
            )
        self._on_run_clicked()
        return True, None

    def _on_run_clicked(self):
        project = self._project
        if project is None or self._running:
            return
        zip_path = self._selected_zip()
        if zip_path is None:
            self._status_label.setText(
                "Pick an add-on to test first."
            )
            return
        blender_exe = find_blender()
        if blender_exe is None:
            self._blender_exe = None
            self._refresh()
            self._status_label.setText(
                "Blender is not installed, so Blender tests cannot "
                "run. The Reblend side still works fully."
            )
            return
        self._blender_exe = blender_exe

        run_dir = self._make_run_dir()
        try:
            run_dir.mkdir(parents=True, exist_ok=True)
        except OSError:
            self._status_label.setText(
                "I could not make the folder for this test run. "
                "Check the project's renders folder can be written to."
            )
            return
        self._run_dir = run_dir

        blender_id = project.id.replace("-", "_")
        operator_id = self._operator_id()
        legacy = zip_is_legacy(zip_path)
        note = ""
        script, error = generate_test_script(
            blender_id, operator_id, legacy=legacy
        )
        if error is not None and operator_id is not None:
            # The wheel action is not a Blender operator id. The
            # other checks are still worth running, so the test
            # runs without the operator check — and says so.
            script, error = generate_test_script(
                blender_id, None, legacy=legacy
            )
            if error is None:
                note = (
                    f"The wheel action {operator_id!r} is not a "
                    "Blender operator id, so the test runs without "
                    "the operator check."
                )
                operator_id = None
        if error is not None:
            self._status_label.setText(error)
            return
        script_path, error = write_test_script(
            run_dir / "test_script.py",
            blender_id, operator_id, legacy=legacy,
        )
        if error is not None:
            # write_test_script regenerates from the same inputs;
            # a failure here means the folder went away mid-run.
            self._status_label.setText(error)
            return

        self._running = True
        self._test_token += 1
        token = self._test_token
        self._cancel_event.clear()
        self._clear_results_for_run()
        self._status_label.setText(
            f"Running the test in Blender on {zip_path.name}..."
            + (f" {note}" if note else "")
        )
        self._refresh_buttons()
        worker = _TestWorker(
            token, blender_exe, zip_path, script_path, run_dir,
            self._cancel_event,
        )
        worker.done.connect(self._on_test_done)
        _track(worker)
        self._worker = worker
        worker.start()

    def _clear_results_for_run(self):
        """Clear the results area for a new run, without touching
        the picker or the project."""
        self._result_summary = ""
        self._check_lines = []
        self._log_text = ""
        self._render_path = None
        self._summary_label.setText(
            "The test is running in Blender. The checks show up "
            "here when it finishes."
        )
        self._elapsed_label.setText("")
        while self._check_rows.count():
            item = self._check_rows.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self._render_label.clear()
        self._render_label.setText("")
        self._log_text_edit.clear()
        self._log_text_edit.hide()
        self._log_button.setText("Show Blender log")

    def _on_cancel_clicked(self):
        if not self._running:
            return
        self._cancel_event.set()
        self._cancel_button.setEnabled(False)
        self._cancel_button.setText("Cancelling...")
        self._status_label.setText(
            "Cancelling the test. Blender stops shortly."
        )

    def _on_test_done(self, token, result):
        # The flags always reset, even for a stale answer: the
        # window is reused after closing, and a run that finished
        # while it was closed (or after a project switch) must not
        # leave the buttons disabled forever. Only the results are
        # gated on the token.
        self._worker = None
        self._running = False
        if token != self._test_token:
            return  # the window closed, or the project changed
        # A run that finished its checklist — passed or failed — has
        # a real duration and a real check count, so the strip shows
        # them. A run that was cancelled, timed out, or crashed
        # produced no finished checklist, so it records nothing.
        if result.get("status") in ("passed", "failed"):
            elapsed = result.get("elapsed_seconds")
            if isinstance(elapsed, (int, float)) and not isinstance(
                elapsed, bool
            ):
                record("Last Blender test", elapsed, "seconds")
            checks = result.get("checks", [])
            if checks:
                passed = sum(
                    1 for check in checks if check.get("passed")
                )
                record(
                    "Last Blender checks", passed,
                    f"of {len(checks)} checks",
                )
        self._show_results(result)
        self._status_label.setText(self._result_summary)
        self._refresh_buttons()

    def _on_log_button_clicked(self):
        if self._log_text_edit.isVisible():
            self._log_text_edit.hide()
            self._log_button.setText("Show Blender log")
        else:
            self._log_text_edit.show()
            self._log_button.setText("Hide Blender log")

    # -- closing --------------------------------------------------

    def closeEvent(self, event):
        # Invalidate any in-flight answer so a worker finishing
        # after the window closes cannot touch a dead window, and
        # stop the run itself: a Blender run can take minutes, and
        # closing the window should not leave Blender running in
        # the background. The worker is owned by the module set,
        # not the window, so it finishes cleanly.
        self._test_token += 1
        self._cancel_event.set()
        super().closeEvent(event)
