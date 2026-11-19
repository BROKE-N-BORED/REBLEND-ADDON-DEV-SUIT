"""Snapshots and undo (DOSSIER.md §7.4, §9.4).

Before a plan is applied, the loop takes a snapshot: a dated copy of
the files the plan touches. Undo restores from the snapshot. A
snapshot is plain file copies in the project folder, under
``.snapshots/<id>/``, plus a small ``snapshot.json`` that records
when it was taken, what the plan was for, and which files it holds.

Each snapshotted file records whether it existed before the plan.
On restore, a file that existed is copied back; a file the plan
created (one that did not exist before) is removed — so undo truly
returns the project to how it was before the plan ran.

Snapshots are never pruned by the suite. They are only removed when
Joshua says so — no silent cleanup (§9.4).

Every function here returns plain-words errors and never raises on a
bad snapshot: a missing snapshot, a snapshot with a mistake in it, or
a file that cannot be read all come back as sentences.
"""

from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path

SNAPSHOT_DIR_NAME = ".snapshots"
MANIFEST_NAME = "snapshot.json"


def snapshots_root(project_root) -> Path:
    """The folder that holds a project's snapshots."""
    return Path(project_root) / SNAPSHOT_DIR_NAME


def create_snapshot(project_root, files, summary: str):
    """Snapshot ``files`` (paths relative to ``project_root``).

    Only files that exist are copied; a file that does not exist yet
    is recorded as not existing, so undo removes it if the plan
    created it. Returns ``(snapshot_id, error)``: ``snapshot_id`` is
    the new snapshot's id, or None with a plain-words sentence when
    the snapshot could not be taken.
    """
    root = Path(project_root)
    now = datetime.now()
    stamp = now.strftime("%Y-%m-%d-%H%M%S")
    snapshot_id = stamp
    target = snapshots_root(root) / snapshot_id
    suffix = 2
    while target.exists():
        snapshot_id = f"{stamp}-{suffix}"
        target = snapshots_root(root) / snapshot_id
        suffix += 1

    entries = []
    try:
        target.mkdir(parents=True)
        seen = set()
        for rel in files:
            if rel in seen:
                continue
            seen.add(rel)
            source = root / rel
            if source.is_file():
                dest = target / rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, dest)
                entries.append({"path": rel, "existed": True})
            else:
                entries.append({"path": rel, "existed": False})
        manifest = {
            "id": snapshot_id,
            "created": now.isoformat(timespec="seconds"),
            "summary": summary,
            "files": entries,
        }
        (target / MANIFEST_NAME).write_text(
            json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
        )
    except OSError:
        return None, (
            "I could not take a snapshot of the project before applying "
            "the plan, so I did not run it. Check the project folder can "
            "be written to."
        )
    return snapshot_id, None


def list_snapshots(project_root) -> list[dict]:
    """The project's snapshots, newest first.

    Each entry is the snapshot's manifest: id, created, summary,
    files. A snapshot whose manifest cannot be read is skipped —
    listing never fails on one broken snapshot.
    """
    root = snapshots_root(project_root)
    found = []
    if not root.is_dir():
        return found
    for folder in root.iterdir():
        if not folder.is_dir():
            continue
        manifest_path = folder / MANIFEST_NAME
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, ValueError, UnicodeDecodeError):
            continue
        if isinstance(manifest, dict) and "id" in manifest:
            found.append(manifest)
    found.sort(key=lambda item: item.get("created", ""), reverse=True)
    return found


def latest_snapshot(project_root) -> str | None:
    """The id of the newest snapshot, or None when there is none."""
    snapshots = list_snapshots(project_root)
    return snapshots[0]["id"] if snapshots else None


def restore_snapshot(project_root, snapshot_id: str):
    """Undo to the snapshot ``snapshot_id``.

    Files the snapshot holds are copied back; files the plan created
    (recorded as not existing) are removed. Returns ``(ok, error)``:
    ``ok`` is True when everything was restored, or False with a
    plain-words sentence saying what went wrong. Never raises.
    """
    root = Path(project_root)
    folder = snapshots_root(root) / snapshot_id
    manifest_path = folder / MANIFEST_NAME
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return False, (
            f"I could not find a snapshot called '{snapshot_id}', "
            "so there was nothing to undo to."
        )
    except (OSError, ValueError, UnicodeDecodeError):
        return False, (
            f"The snapshot '{snapshot_id}' has a mistake in it, so I "
            "could not undo to it."
        )
    if not isinstance(manifest, dict) or "files" not in manifest:
        return False, (
            f"The snapshot '{snapshot_id}' has a mistake in it, so I "
            "could not undo to it."
        )

    for entry in manifest["files"]:
        rel = entry.get("path", "")
        if not rel:
            continue
        target = root / rel
        saved = folder / rel
        try:
            if entry.get("existed"):
                if not saved.is_file():
                    return False, (
                        f"The snapshot is missing the saved copy of "
                        f"'{rel}', so I could not undo to it."
                    )
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(saved, target)
            else:
                if target.is_file():
                    target.unlink()
        except OSError:
            return False, (
                f"I could not undo the change to '{rel}'. "
                "Check the project folder can be written to."
            )
    return True, None
