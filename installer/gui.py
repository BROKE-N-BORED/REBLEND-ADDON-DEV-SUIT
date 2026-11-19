"""The installer's window: tkinter, stdlib only (DOSSIER.md §9.1).

The installer GUI must run on a stock Linux Mint box with no extra
installs — PySide6 is what is being installed, so the installer
itself uses tkinter, which ships with Python. One window, plain
words: what it will install, where, an Install button, a progress
line, and a plain-words result.

The long work (venv, pip) runs in a worker thread, so the window
never freezes; progress comes back through a queue the window
polls. Cancel stops the install between steps (a step already
running finishes first), and a re-run resumes it.

The same window is also the front door for uninstalling: the
Uninstall button opens a second window (``UninstallerWindow``)
that shows what will be removed and asks first — the Uninstall
button stays disabled until the "Yes, uninstall the suite" box is
ticked (U6, U23/U31: destructive choices default to No), and the
saved data stays unless its own box is ticked too.

The uninstall window also runs on its own, as the Uninstall menu
entry: ``main_uninstall`` (the ``devsuite-uninstall`` console
script, shipped inside the installed distribution so it works
after the release tree is deleted) opens the uninstall window
with no installer window behind it. Closing that window ends the
program — the hidden root goes with it, or the process would sit
invisible with nothing on screen.

Run from the release folder:

    python3 installer/gui.py

The ``Install Reblend Add-on Dev Suite.desktop`` launcher starts
it this way, finding the release folder with the ``%k`` pattern.
"""

from __future__ import annotations

import queue
import sys
import threading
from pathlib import Path

# The release root goes on the path first: this file runs as
# `python3 installer/gui.py`, which puts installer/ on the path,
# not the release root, and `installer.install` lives one up.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import tkinter as tk
from tkinter import filedialog

from installer.install import APP_NAME, default_install_dir, install
from installer.uninstall import find_install, uninstall

#: The window title.
_TITLE = f"Install {APP_NAME}"

#: What the window says, in plain words. Visible UI text: no
#: em-dashes, no bare "&" (the word is always "and") — the tests
#: check every string in _VISIBLE_COPY.
_INTRO = (
    "This installs the Reblend Add-on Dev Suite on this computer: "
    "a private copy of the suite, its Python packages, and a menu "
    "entry. Nothing else changes."
)
_NETWORK_NOTE = (
    "Needs the network once, to download its parts. After that "
    "the suite works offline."
)
_FOLDER_LABEL = "Install folder:"
_BROWSE_BUTTON = "Browse..."
_INSTALL_BUTTON = "Install"
_CANCEL_BUTTON = "Cancel"
_CLOSE_BUTTON = "Close"
_READY = "Pick a folder, then tap Install."
_NO_FOLDER = "Pick an install folder first."
_CANCELLING = (
    "Cancelling. The current step finishes first, then the "
    "install stops."
)
_UNINSTALL_BUTTON = "Uninstall..."

#: The uninstall window's words, in plain words. Same house rules
#: as the install window: no em-dashes, no bare "&".
_UNINSTALL_TITLE = f"Uninstall {APP_NAME}"
_UNINSTALL_INTRO = (
    "This removes the suite from this computer: its folder and "
    "its menu entries. Your projects are never touched. They live "
    "where you put them, outside the suite's folder."
)
_UNINSTALL_WILL_REMOVE = "Will be removed:"
_UNINSTALL_CONFIRM = "Yes, uninstall the suite"
_UNINSTALL_APP_DATA = (
    "Also remove the library shelf and remembered settings"
)
_UNINSTALL_READY = "Tick the box, then tap Uninstall."
_UNINSTALL_RUN_BUTTON = "Uninstall"
_UNINSTALL_NOTHING = (
    "The suite is not installed, so there is nothing to "
    "uninstall."
)
_UNINSTALL_RUNNING = "Uninstalling..."

#: Every visible string, for the character-rule test.
_VISIBLE_COPY = (
    _TITLE, _INTRO, _NETWORK_NOTE, _FOLDER_LABEL, _BROWSE_BUTTON,
    _INSTALL_BUTTON, _CANCEL_BUTTON, _CLOSE_BUTTON, _READY,
    _NO_FOLDER, _CANCELLING, _UNINSTALL_BUTTON, _UNINSTALL_TITLE,
    _UNINSTALL_INTRO, _UNINSTALL_WILL_REMOVE, _UNINSTALL_CONFIRM,
    _UNINSTALL_APP_DATA, _UNINSTALL_READY, _UNINSTALL_RUN_BUTTON,
    _UNINSTALL_NOTHING, _UNINSTALL_RUNNING,
)


class InstallerWindow:
    """The installer's one window."""

    def __init__(self, root=None):
        self._root = root if root is not None else tk.Tk()
        self._root.title(_TITLE)
        self._root.geometry("560x400")
        self._root.resizable(False, False)
        self._queue: queue.Queue = queue.Queue()
        self._cancel_event = threading.Event()
        self._worker: threading.Thread | None = None
        self._running = False
        self._build_ui()

    # -- layout ---------------------------------------------------

    def _build_ui(self):
        pad = {"padx": 16, "pady": 6}
        intro = tk.Label(
            self._root, text=_INTRO, wraplength=520,
            justify=tk.LEFT, anchor=tk.W,
        )
        intro.pack(fill=tk.X, **pad)

        folder_row = tk.Frame(self._root)
        folder_row.pack(fill=tk.X, **pad)
        tk.Label(folder_row, text=_FOLDER_LABEL).pack(side=tk.LEFT)
        self._folder_entry = tk.Entry(folder_row)
        self._folder_entry.insert(0, str(default_install_dir()))
        self._folder_entry.pack(
            side=tk.LEFT, fill=tk.X, expand=True, padx=(8, 8),
        )
        browse = tk.Button(
            folder_row, text=_BROWSE_BUTTON,
            command=self._on_browse,
        )
        browse.pack(side=tk.LEFT)

        note = tk.Label(
            self._root, text=_NETWORK_NOTE, wraplength=520,
            justify=tk.LEFT, anchor=tk.W,
        )
        note.pack(fill=tk.X, **pad)

        button_row = tk.Frame(self._root)
        button_row.pack(fill=tk.X, **pad)
        self._install_button = tk.Button(
            button_row, text=_INSTALL_BUTTON,
            command=self._on_install,
        )
        self._install_button.pack(side=tk.LEFT, padx=(0, 8))
        self._cancel_button = tk.Button(
            button_row, text=_CANCEL_BUTTON,
            command=self._on_cancel, state=tk.DISABLED,
        )
        self._cancel_button.pack(side=tk.LEFT, padx=(0, 8))
        self._close_button = tk.Button(
            button_row, text=_CLOSE_BUTTON,
            command=self._root.destroy,
        )
        self._close_button.pack(side=tk.LEFT, padx=(0, 8))
        self._uninstall_button = tk.Button(
            button_row, text=_UNINSTALL_BUTTON,
            command=self._on_uninstall,
        )
        self._uninstall_button.pack(side=tk.LEFT)

        self._progress_label = tk.Label(
            self._root, text=_READY, wraplength=520,
            justify=tk.LEFT, anchor=tk.NW,
        )
        self._progress_label.pack(fill=tk.BOTH, expand=True, **pad)

    # -- actions --------------------------------------------------

    def _on_browse(self):
        folder = filedialog.askdirectory(
            title="Pick the install folder",
            initialdir=str(Path.home()),
        )
        if folder:
            self._folder_entry.delete(0, tk.END)
            self._folder_entry.insert(0, folder)

    def _on_install(self):
        if self._running:
            return
        folder = self._folder_entry.get().strip()
        if not folder:
            self._progress_label.config(text=_NO_FOLDER)
            return
        install_dir = Path(folder).expanduser()
        source_dir = Path(__file__).resolve().parent.parent
        self._running = True
        self._cancel_event.clear()
        self._install_button.config(state=tk.DISABLED)
        self._cancel_button.config(state=tk.NORMAL)
        self._close_button.config(state=tk.DISABLED)
        self._uninstall_button.config(state=tk.DISABLED)
        self._progress_label.config(text="Starting the install...")
        self._worker = threading.Thread(
            target=self._run_install,
            args=(source_dir, install_dir),
            daemon=True,
        )
        self._worker.start()
        self._root.after(100, self._poll_queue)

    def _run_install(self, source_dir, install_dir):
        """The install itself, off the UI thread. Progress and the
        result travel back through the queue — the worker never
        touches a widget."""

        def progress(text):
            self._queue.put(("progress", text))

        ok, message = install(
            source_dir,
            install_dir=install_dir,
            progress=progress,
            cancelled=self._cancel_event.is_set,
        )
        self._queue.put(("done", (ok, message)))

    def _poll_queue(self):
        """Take whatever the worker has posted and show it. Keeps
        polling until the worker reports it is done."""
        done = False
        while True:
            try:
                kind, value = self._queue.get_nowait()
            except queue.Empty:
                break
            if kind == "progress":
                self._progress_label.config(text=value)
            elif kind == "done":
                done = True
                ok, message = value
                self._progress_label.config(text=message)
                self._running = False
                self._cancel_button.config(state=tk.DISABLED)
                self._close_button.config(state=tk.NORMAL)
                self._uninstall_button.config(state=tk.NORMAL)
                # A failed install can be retried from here; a
                # successful one has nothing left to install.
                self._install_button.config(
                    state=tk.NORMAL if not ok else tk.DISABLED,
                )
        if not done:
            self._root.after(100, self._poll_queue)

    def _on_cancel(self):
        if not self._running:
            return
        self._cancel_event.set()
        self._cancel_button.config(state=tk.DISABLED)
        self._progress_label.config(text=_CANCELLING)

    def _on_uninstall(self):
        """Open the uninstall window for the folder in the entry
        (the folder the suite was installed into, when it was
        picked here; the default when the entry is empty)."""
        folder = self._folder_entry.get().strip()
        install_dir = (
            Path(folder).expanduser() if folder
            else default_install_dir()
        )
        UninstallerWindow(self._root, install_dir)

    # -- running --------------------------------------------------

    def run(self):
        self._root.mainloop()


class UninstallerWindow:
    """The uninstaller's window: what goes, asked first.

    Shows what will be removed (the install folder and the menu
    entries, plus the saved data when its box is ticked), and runs
    the uninstall in a worker thread with plain-words progress
    and result. The Uninstall button stays disabled until the
    confirm box is ticked — a destructive action defaults to No
    (U23/U31) — and the saved-data box starts unticked, so the
    shelf and settings stay unless Joshua opts in (U6).
    """

    def __init__(self, parent, install_dir=None, applications_dir=None):
        self._install_dir = (
            Path(install_dir) if install_dir is not None
            else default_install_dir()
        )
        self._applications_dir = applications_dir
        self._found = find_install(
            self._install_dir, self._applications_dir
        )
        self._present = (
            self._found["install_dir"] is not None
            or self._found["record"] is not None
            or self._found["launcher"] is not None
            or self._found["uninstall_launcher"] is not None
        )
        self._root = tk.Toplevel(parent)
        self._root.title(_UNINSTALL_TITLE)
        self._root.geometry("560x400")
        self._root.resizable(False, False)
        self._queue: queue.Queue = queue.Queue()
        self._worker: threading.Thread | None = None
        self._running = False
        self._build_ui()

    # -- layout ---------------------------------------------------

    def _build_ui(self):
        pad = {"padx": 16, "pady": 6}
        intro = tk.Label(
            self._root, text=_UNINSTALL_INTRO, wraplength=520,
            justify=tk.LEFT, anchor=tk.W,
        )
        intro.pack(fill=tk.X, **pad)

        if self._present:
            heading = tk.Label(
                self._root, text=_UNINSTALL_WILL_REMOVE,
                justify=tk.LEFT, anchor=tk.W,
            )
            heading.pack(fill=tk.X, **pad)
            lines = []
            if self._found["install_dir"] is not None:
                lines.append(
                    f"  - the suite's folder "
                    f"({self._found['install_dir']})"
                )
            if self._found["launcher"] is not None:
                lines.append(
                    f"  - the menu entry "
                    f"({self._found['launcher']})"
                )
            if self._found["uninstall_launcher"] is not None:
                lines.append(
                    f"  - the uninstall menu entry "
                    f"({self._found['uninstall_launcher']})"
                )
            self._will_remove_label = tk.Label(
                self._root, text="\n".join(lines),
                wraplength=520, justify=tk.LEFT, anchor=tk.W,
            )
            self._will_remove_label.pack(fill=tk.X, **pad)
        else:
            self._will_remove_label = tk.Label(
                self._root, text=_UNINSTALL_NOTHING,
                wraplength=520, justify=tk.LEFT, anchor=tk.W,
            )
            self._will_remove_label.pack(fill=tk.X, **pad)

        self._confirm_var = tk.IntVar(value=0)
        self._confirm_box = tk.Checkbutton(
            self._root, text=_UNINSTALL_CONFIRM,
            variable=self._confirm_var,
            command=self._on_confirm_toggled,
            state=tk.NORMAL if self._present else tk.DISABLED,
        )
        self._confirm_box.pack(fill=tk.X, **pad)

        self._app_data_var = tk.IntVar(value=0)
        self._app_data_box = tk.Checkbutton(
            self._root, text=_UNINSTALL_APP_DATA,
            variable=self._app_data_var,
            state=tk.NORMAL if self._present else tk.DISABLED,
        )
        self._app_data_box.pack(fill=tk.X, **pad)

        button_row = tk.Frame(self._root)
        button_row.pack(fill=tk.X, **pad)
        self._uninstall_button = tk.Button(
            button_row, text=_UNINSTALL_RUN_BUTTON,
            command=self._on_uninstall, state=tk.DISABLED,
        )
        self._uninstall_button.pack(side=tk.LEFT, padx=(0, 8))
        self._close_button = tk.Button(
            button_row, text=_CLOSE_BUTTON,
            command=self._root.destroy,
        )
        self._close_button.pack(side=tk.LEFT)

        self._progress_label = tk.Label(
            self._root,
            text=_UNINSTALL_READY if self._present
            else _UNINSTALL_NOTHING,
            wraplength=520, justify=tk.LEFT, anchor=tk.NW,
        )
        self._progress_label.pack(fill=tk.BOTH, expand=True, **pad)

    # -- actions --------------------------------------------------

    def _on_confirm_toggled(self):
        """The Uninstall button is on only when the confirm box is
        ticked and an install is present."""
        self._uninstall_button.config(
            state=(
                tk.NORMAL
                if self._present and self._confirm_var.get()
                else tk.DISABLED
            )
        )

    def _on_uninstall(self):
        if self._running or not self._present:
            return
        if not self._confirm_var.get():
            return
        self._running = True
        self._uninstall_button.config(state=tk.DISABLED)
        self._confirm_box.config(state=tk.DISABLED)
        self._app_data_box.config(state=tk.DISABLED)
        self._close_button.config(state=tk.DISABLED)
        self._progress_label.config(text=_UNINSTALL_RUNNING)
        remove_app_data = bool(self._app_data_var.get())
        self._worker = threading.Thread(
            target=self._run_uninstall,
            args=(remove_app_data,),
            daemon=True,
        )
        self._worker.start()
        self._root.after(100, self._poll_queue)

    def _run_uninstall(self, remove_app_data):
        """The uninstall itself, off the UI thread. Progress and
        the result travel back through the queue — the worker
        never touches a widget."""

        def progress(text):
            self._queue.put(("progress", text))

        ok, message = uninstall(
            install_dir=self._install_dir,
            applications_dir=self._applications_dir,
            remove_app_data=remove_app_data,
            progress=progress,
        )
        self._queue.put(("done", (ok, message)))

    def _poll_queue(self):
        """Take whatever the worker has posted and show it. Keeps
        polling until the worker reports it is done."""
        done = False
        while True:
            try:
                kind, value = self._queue.get_nowait()
            except queue.Empty:
                break
            if kind == "progress":
                self._progress_label.config(text=value)
            elif kind == "done":
                done = True
                ok, message = value
                self._progress_label.config(text=message)
                self._running = False
                self._close_button.config(state=tk.NORMAL)
                # A successful uninstall has nothing left to
                # uninstall; a failed one can be retried.
                if ok:
                    self._present = False
                    self._confirm_box.config(state=tk.DISABLED)
                    self._app_data_box.config(state=tk.DISABLED)
                    self._uninstall_button.config(state=tk.DISABLED)
                else:
                    self._confirm_box.config(state=tk.NORMAL)
                    self._app_data_box.config(state=tk.NORMAL)
                    self._on_confirm_toggled()
        if not done:
            self._root.after(100, self._poll_queue)


def main() -> None:
    InstallerWindow().run()


def main_uninstall(install_dir=None, applications_dir=None,
                   _mainloop=True):
    """The standalone uninstall entry point: the uninstall window
    on its own, with no installer window behind it. The
    ``devsuite-uninstall`` console script runs this (the Uninstall
    menu entry). The root window stays hidden; the uninstall
    window is the only window on screen.

    Closing that window ends the program: the Close button and
    the window's close box both destroy the hidden root too, or
    the process would sit invisible with nothing on screen. While
    an uninstall runs, closing does nothing — the Close button is
    disabled then too, and a half-removed install is worse than a
    finished one.

    ``_mainloop`` is the test seam: with it off, the window is
    built and returned without running the loop, so a test can
    drive it in its own thread. Returns the window.
    """
    root = tk.Tk()
    root.withdraw()
    window = UninstallerWindow(root, install_dir, applications_dir)

    def _quit():
        if not window._running:
            root.destroy()

    window._root.protocol("WM_DELETE_WINDOW", _quit)
    window._close_button.config(command=_quit)
    if _mainloop:
        root.mainloop()
    return window


if __name__ == "__main__":
    main()
