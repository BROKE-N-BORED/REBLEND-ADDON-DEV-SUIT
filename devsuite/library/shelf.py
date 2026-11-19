"""The shelf record: every pack the suite has built (DOSSIER.md §6.9).

A plain JSON file, one entry per built file:

* ``pack_path`` — where the built file sits (a ``.rblpack`` or a
  ``-blender.zip`` in the project's packs/ folder).
* ``project_id``, ``project_name``, ``project_root`` — which project
  it came from, and where that project lives.
* ``version``, ``target`` (``"reblend"`` or ``"blender"``),
  ``built`` (the date, ``2026-11-17``), ``test_run_id`` (the run
  that proved it, or null — unproven until the test harness
  exists), ``description`` (one line, for the card).

The shelf is a record, not the packs themselves: rebuilding a pack
updates its entry (dedupe by pack path), deleting a pack removes
its entry, and a shelf that cannot be read is treated as empty
rather than crashing anything. The packs on disk are untouched by
every function here — this module only reads and writes the JSON
file.

Default location: the Linux location QStandardPaths AppDataLocation
resolves to for this app (``~/.local/share/Broke n Bored/Reblend
Add-on Dev Suite/shelf.json``) — computed by hand because this
module is stdlib only and cannot call Qt. The windows and the tests
pass an explicit path; the default is only used when none is given.

Every function returns plain-words errors and never raises on a bad
file: a missing shelf reads as empty, a damaged one reads as empty
with a sentence saying so, and a file that cannot be written says
so instead of crashing.
"""

from __future__ import annotations

import json
from pathlib import Path

#: The entry fields the shelf keeps. ``pack_path`` is the key:
#: two entries for the same file are the same entry.
ENTRY_FIELDS = (
    "pack_path",
    "project_id",
    "project_name",
    "project_root",
    "version",
    "target",
    "built",
    "test_run_id",
    "description",
)


def default_shelf_path() -> Path:
    """Where the shelf lives when no path is given.

    The Linux resolution of QStandardPaths AppDataLocation for this
    app (organization "Broke n Bored", application "Reblend Add-on
    Dev Suite"). Computed by hand: this module is stdlib only and
    cannot ask Qt.
    """
    return (
        Path.home()
        / ".local"
        / "share"
        / "Broke n Bored"
        / "Reblend Add-on Dev Suite"
        / "shelf.json"
    )


def load_shelf(path) -> tuple[list[dict], str | None]:
    """Read the shelf at ``path``.

    Returns ``(entries, error)``: ``entries`` is the list of shelf
    entries (newest first), or an empty list when the shelf does
    not exist yet or cannot be read; ``error`` is None on success,
    or a plain-words sentence when the file is damaged. Never
    raises.
    """
    shelf = Path(path)
    try:
        text = shelf.read_text(encoding="utf-8")
    except FileNotFoundError:
        return [], None
    except OSError:
        return [], (
            "I could not read the library shelf, so the library is "
            "showing empty. Check the shelf file can be opened."
        )
    except UnicodeDecodeError:
        return [], (
            "The library shelf is not readable text, so the library "
            "is showing empty. The shelf file may be damaged."
        )

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return [], (
            "The library shelf has a mistake in it, so the library "
            "is showing empty. The shelf file may be damaged. "
            "Rebuilding a pack records it again."
        )
    if not isinstance(data, list):
        return [], (
            "The library shelf should hold a list of packs, so the "
            "library is showing empty. The shelf file may be damaged."
        )
    for entry in data:
        if not isinstance(entry, dict) or not entry.get("pack_path"):
            return [], (
                "The library shelf holds a pack record I cannot "
                "read, so the library is showing empty. The shelf "
                "file may be damaged. Rebuilding a pack records it "
                "again."
            )
    return data, None


def save_shelf(path, entries) -> str | None:
    """Write ``entries`` to the shelf at ``path``.

    Returns None on success, or a plain-words sentence when the
    file could not be written. The write is atomic (a temporary
    file moved into place), so a failed write never leaves a
    half-written shelf behind. Never raises.
    """
    shelf = Path(path)
    try:
        shelf.parent.mkdir(parents=True, exist_ok=True)
    except OSError:
        return (
            "I could not make the folder for the library shelf. "
            "Check the location can be written to."
        )
    tmp_path = shelf.with_name(shelf.name + ".tmp")
    try:
        tmp_path.write_text(
            json.dumps(entries, indent=2) + "\n", encoding="utf-8"
        )
        tmp_path.replace(shelf)
    except OSError:
        try:
            tmp_path.unlink()
        except OSError:
            pass
        return (
            "I could not write the library shelf. "
            "Check the location can be written to."
        )
    return None


def add_entry(path, entry) -> str | None:
    """Record ``entry`` in the shelf at ``path``.

    Rebuilding the same file updates its entry instead of adding a
    second one: entries are deduped by ``pack_path``, and the
    newest entry sorts first. Returns None on success, or a
    plain-words sentence when the shelf could not be written. A
    shelf that cannot be read is started fresh with just this
    entry — the old record is unreadable anyway, and the packs on
    disk are untouched. Never raises.
    """
    entries, _ = load_shelf(path)
    pack_path = str(entry.get("pack_path", ""))
    entries = [
        old for old in entries if str(old.get("pack_path", "")) != pack_path
    ]
    entries.insert(0, dict(entry))
    return save_shelf(path, entries)


def remove_entry(path, pack_path) -> tuple[bool, str | None]:
    """Remove the entry for ``pack_path`` from the shelf at ``path``.

    Returns ``(removed, error)``: ``removed`` is True when an entry
    was taken out, False when the shelf held no entry for that
    file; ``error`` is None on success, or a plain-words sentence
    when the shelf could not be written. Never raises. Only the
    record is removed — the pack file itself is untouched.
    """
    entries, error = load_shelf(path)
    if error is not None:
        return False, error
    kept = [
        entry for entry in entries
        if str(entry.get("pack_path", "")) != str(pack_path)
    ]
    if len(kept) == len(entries):
        return False, None
    error = save_shelf(path, kept)
    if error is not None:
        return False, error
    return True, None
