"""Read and check a pack's manifest.json.

The manifest is the pack's identity card: what the pack is called, what
it works with, and what it adds. This module only reads and checks it —
it never writes, packs, or installs anything.

Every function here returns a plain result and never raises on a bad
manifest. A missing file, an unreadable file, or a file with a mistake
in it all come back as plain-words errors, never as a crash or a stack
trace.

Rules (DOSSIER.md §5.1 — the pack format v1, the whole contract):

* Required fields: id, name, version, reblend, entry, contributions.
* ``id``: lowercase letters, numbers, dashes and dots only.
* ``version``: three numbers, like 1.2.3.
* ``reblend``: the Reblend versions the pack works with, written as
  text, like ">=0.2". The loader enforces the range; this module
  checks it is there and written as text.
* ``entry``: a Python file name on its own, like addon.py. It must sit
  beside the manifest, at the pack root.
* ``contributions``: an object mapping a kind to a list of entries.
  Known kinds: wheel, menu, inspector, brushes, materials,
  simulations. Every entry is an object; a wheel entry needs a label
  and an action.
* Optional fields: description, author, icon — text when present.
* ``permissions`` (optional): an object. ``network`` must be false —
  packs never touch the network in v1. ``files`` must be
  "project-only" when present — the only value in v1.

Fields the format does not know about are ignored, so an older suite
can still read a pack written by a newer one.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

REQUIRED_FIELDS = (
    "id",
    "name",
    "version",
    "reblend",
    "entry",
    "contributions",
)

OPTIONAL_TEXT_FIELDS = ("description", "author", "icon")

KNOWN_CONTRIBUTION_KINDS = (
    "wheel",
    "menu",
    "inspector",
    "brushes",
    "materials",
    "simulations",
)

_ID_RE = re.compile(r"^[a-z0-9][a-z0-9.-]*$")
_VERSION_RE = re.compile(r"^\d+\.\d+\.\d+$")


def validate_manifest(path) -> tuple[bool, list[str]]:
    """Load and check the manifest at ``path``.

    Returns ``(ok, errors)``. ``ok`` is True only when the file loaded
    and every check passed. ``errors`` is a list of plain-words
    messages; empty when ``ok`` is True. Never raises.

    Also checks that the entry file named in the manifest sits beside
    the manifest — a pack pointing at a missing entry file is broken.
    """
    try:
        text = Path(path).read_text(encoding="utf-8")
    except FileNotFoundError:
        return False, [
            "I could not find the manifest file. "
            "A pack needs a manifest.json file in its folder."
        ]
    except OSError:
        return False, [
            "I could not read the manifest file. "
            "Check the file is there and can be opened."
        ]
    except UnicodeDecodeError:
        return False, [
            "The manifest file is not readable text. "
            "It should be a plain text file in the usual UTF-8 form."
        ]

    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        return False, [
            "The manifest file has a mistake in it, so I could not read it. "
            f"Check near line {exc.lineno} for a missing comma, "
            "quote, or bracket."
        ]

    ok, errors = validate_manifest_data(data)
    if ok:
        # The entry file must exist beside the manifest. Only checked
        # here — validate_manifest_data has no folder to look in.
        entry = data.get("entry")
        if isinstance(entry, str) and entry.endswith(".py"):
            entry_path = Path(path).parent / entry
            if not entry_path.is_file():
                return False, [
                    f"The entry file '{entry}' is missing from the pack. "
                    "It should sit in the pack folder, next to manifest.json."
                ]
    return ok, errors


def validate_manifest_data(data) -> tuple[bool, list[str]]:
    """Check an already-loaded manifest (a dict from JSON).

    Returns ``(ok, errors)`` in the same plain-words form as
    :func:`validate_manifest`. Never raises. Cannot check that the
    entry file exists — use :func:`validate_manifest` for that.
    """
    errors: list[str] = []

    if not isinstance(data, dict):
        return False, [
            "The manifest should hold one pack description, "
            "a set of named fields, not a list or a single value."
        ]

    for field in REQUIRED_FIELDS:
        if field not in data:
            errors.append(
                f"The manifest is missing the '{field}' field. "
                "Every pack needs one."
            )

    if "id" in data:
        errors.extend(_check_id(data["id"]))
    if "name" in data:
        errors.extend(_check_name(data["name"]))
    if "version" in data:
        errors.extend(_check_version(data["version"]))
    if "reblend" in data:
        errors.extend(_check_reblend(data["reblend"]))
    if "entry" in data:
        errors.extend(_check_entry(data["entry"]))
    if "contributions" in data:
        errors.extend(_check_contributions(data["contributions"]))
    for field in OPTIONAL_TEXT_FIELDS:
        if field in data:
            errors.extend(_check_optional_text(field, data[field]))
    if "permissions" in data:
        errors.extend(_check_permissions(data["permissions"]))

    return (not errors), errors


def _check_id(value) -> list[str]:
    if not isinstance(value, str) or not value:
        return ["The pack id should be written as text, like 'surprise'."]
    if not _ID_RE.match(value):
        return [
            f"The pack id '{value}' is not allowed. "
            "Use only lowercase letters, numbers, dashes and dots, "
            "and start with a letter or number."
        ]
    return []


def _check_name(value) -> list[str]:
    if not isinstance(value, str) or not value.strip():
        return ["The pack name should be written as text, like 'Surprise'."]
    return []


def _check_version(value) -> list[str]:
    if not isinstance(value, str) or not _VERSION_RE.match(value):
        return [
            f"The version '{value}' is not in the form 1.2.3. "
            "Use three numbers separated by dots."
        ]
    return []


def _check_reblend(value) -> list[str]:
    if not isinstance(value, str) or not value.strip():
        return [
            "The reblend field should say which Reblend versions "
            "the pack works with, written as text, like '>=0.2'."
        ]
    return []


def _check_entry(value) -> list[str]:
    if not isinstance(value, str) or not value:
        return ["The entry should be a Python file name, like addon.py."]
    if "/" in value or "\\" in value:
        return [
            f"The entry '{value}' should be a file name on its own, "
            "like addon.py, not a path into a folder."
        ]
    if not value.endswith(".py") or value == ".py":
        return [
            f"The entry '{value}' should be a Python file name, "
            "like addon.py."
        ]
    return []


def _check_contributions(value) -> list[str]:
    if not isinstance(value, dict):
        return [
            "The contributions field should list what the pack adds, "
            "grouped by kind."
        ]
    errors = []
    kinds = ", ".join(KNOWN_CONTRIBUTION_KINDS)
    for kind, items in value.items():
        if kind not in KNOWN_CONTRIBUTION_KINDS:
            errors.append(
                f"The contribution kind '{kind}' is not one I know. "
                f"Use one of: {kinds}."
            )
            continue
        if not isinstance(items, list):
            errors.append(
                f"The contributions for '{kind}' should be a list."
            )
            continue
        for item in items:
            if not isinstance(item, dict):
                errors.append(
                    f"Every contribution under '{kind}' "
                    "should be an object with named fields, "
                    "like a wheel button with a label and an action."
                )
                break
        if kind == "wheel":
            for item in items:
                if not isinstance(item, dict):
                    continue
                if (not isinstance(item.get("label"), str)
                        or not item["label"].strip()):
                    errors.append(
                        "Every wheel button needs a label, written as text."
                    )
                if (not isinstance(item.get("action"), str)
                        or not item["action"].strip()):
                    errors.append(
                        "Every wheel button needs an action, written as text, "
                        "saying what it runs."
                    )
    return errors


def _check_optional_text(field, value) -> list[str]:
    if not isinstance(value, str):
        return [
            f"The '{field}' field should be written as text."
        ]
    return []


def _check_permissions(value) -> list[str]:
    if not isinstance(value, dict):
        return [
            "The permissions field should list what the pack is allowed "
            "to do, as named fields."
        ]
    errors = []
    if "network" in value and value["network"] is not False:
        errors.append(
            "Packs cannot use the network. "
            "The network permission must be false."
        )
    if "files" in value and value["files"] != "project-only":
        errors.append(
            "The files permission can only be 'project-only'. "
            "A pack reads and writes inside the project and its own "
            "folder, and nowhere else."
        )
    return errors
