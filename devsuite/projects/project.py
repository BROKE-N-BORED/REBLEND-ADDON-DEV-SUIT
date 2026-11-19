"""The project model (DOSSIER.md §9.4, layout from §5.4).

A suite project is a folder of plain files:

    my-addon/
      project.json     Name, targets, version, author, created date.
      src/             The add-on's code.
      tests/           The project's checks.
      assets/          Icons, test scenes, textures, presets.
      renders/         Captured renders from test runs, newest first.
      packs/           Built packs (.rblpack zips, Blender zips).

``project.json`` is one human-readable file. Its fields are the ones
§9.4 lists: id, name, description, targets, version, author, icon,
created — plus ``contributions``, the §5.1 shape of what the add-on
declares (wheel buttons, menu items, and the rest), owned by the
pack window. Required in the file: ``name``, ``targets``,
``created``. ``targets`` is a list — "reblend", "blender", or both —
because one project can aim at both programs; the emitters each read
the one file. ``id`` is derived from the name at creation and
stored. The Reblend version a pack needs lives in the pack manifest
(§5.1 ``reblend`` field), not here — one source of truth, not two.

Every function here returns plain-words errors and never raises on a
bad project: a missing file, a file with a mistake in it, or a field
with the wrong value all come back as sentences, never as a crash or
a stack trace. Fields the model does not know about are ignored, so a
project written by a newer suite still opens in an older one.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

REQUIRED_FIELDS = ("name", "targets", "created")

KNOWN_TARGETS = ("reblend", "blender")

DEFAULT_VERSION = "0.1.0"
DEFAULT_AUTHOR = "Joshua Lofland"

PROJECT_DIRS = ("src", "tests", "assets", "renders", "packs")

_ID_RE = re.compile(r"[^a-z0-9]+")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


@dataclass
class Project:
    """One suite project, backed by a folder on disk."""

    root: Path
    name: str
    targets: list = field(default_factory=lambda: ["reblend"])
    created: str = ""
    description: str = ""
    version: str = DEFAULT_VERSION
    author: str = DEFAULT_AUTHOR
    icon: str = ""
    id: str = ""
    contributions: dict = field(default_factory=dict)

    @property
    def src_dir(self) -> Path:
        return self.root / "src"

    @property
    def tests_dir(self) -> Path:
        return self.root / "tests"

    @property
    def assets_dir(self) -> Path:
        return self.root / "assets"

    @property
    def renders_dir(self) -> Path:
        return self.root / "renders"

    @property
    def packs_dir(self) -> Path:
        return self.root / "packs"

    def project_file(self) -> Path:
        """The path of this project's project.json."""
        return self.root / "project.json"

    def to_dict(self) -> dict:
        """The project as the dict stored in project.json."""
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "targets": list(self.targets),
            "version": self.version,
            "author": self.author,
            "icon": self.icon,
            "created": self.created,
            "contributions": dict(self.contributions),
        }

    def save(self) -> str | None:
        """Write this project's project.json. Returns None on success,
        or a plain-words sentence when the file could not be written.
        """
        try:
            self.project_file().write_text(
                json.dumps(self.to_dict(), indent=2) + "\n", encoding="utf-8"
            )
        except OSError:
            return (
                "I could not write the project file. "
                "Check the project folder can be written to."
            )
        return None


def create_project(
    path,
    *,
    name: str,
    targets: list | None = None,
    description: str = "",
    version: str = DEFAULT_VERSION,
    author: str = DEFAULT_AUTHOR,
    icon: str = "",
    created: str | None = None,
    contributions: dict | None = None,
) -> tuple[Project | None, str | None]:
    """Create a new project folder at ``path``.

    Creates project.json and the src/, tests/, assets/, renders/ and
    packs/ folders. Returns ``(project, error)``: ``project`` is the
    new Project, or None when creation failed; ``error`` is None on
    success, or a plain-words sentence — the folder already holds
    something, a field is wrong, or the folder could not be made.
    """
    root = Path(path)
    targets = list(targets) if targets is not None else ["reblend"]
    created = created or date.today().isoformat()
    data = {
        "name": name,
        "targets": targets,
        "created": created,
        "description": description,
        "version": version,
        "author": author,
        "icon": icon,
        "contributions": dict(contributions) if contributions else {},
    }
    ok, errors = validate_project_data(data)
    if not ok:
        return None, " ".join(errors)

    if root.is_file():
        return None, (
            "There is already a file where the project folder should go. "
            "Pick another name or move the file out of the way."
        )
    if root.is_dir() and any(root.iterdir()):
        return None, (
            "That folder already holds files, so I did not make a project "
            "there. Pick an empty folder or a new name."
        )
    try:
        root.mkdir(parents=True, exist_ok=True)
        for dirname in PROJECT_DIRS:
            (root / dirname).mkdir(parents=True, exist_ok=True)
    except OSError:
        return None, (
            "I could not make the project folder. "
            "Check the location can be written to."
        )

    project = Project(
        root=root,
        name=name,
        targets=targets,
        created=created,
        description=description,
        version=version,
        author=author,
        icon=icon,
        id=_slug(name),
        contributions=dict(contributions) if contributions else {},
    )
    error = project.save()
    if error is not None:
        return None, error
    return project, None


def load_project(path) -> tuple[Project | None, str | None]:
    """Open the project in the folder at ``path``.

    Returns ``(project, error)``: ``project`` is the loaded Project,
    or None when the folder has no readable, valid project.json;
    ``error`` is None on success, or a plain-words sentence saying
    what is wrong with the project file.
    """
    root = Path(path)
    project_file = root / "project.json"
    try:
        text = project_file.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None, (
            "I could not find a project here. There is no project.json "
            "file in this folder."
        )
    except OSError:
        return None, (
            "I could not read the project file. "
            "Check the file is there and can be opened."
        )
    except UnicodeDecodeError:
        return None, (
            "The project file is not readable text. "
            "It should be a plain text file in the usual UTF-8 form."
        )

    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        return None, (
            "The project file has a mistake in it, so I could not read it. "
            f"Check near line {exc.lineno} for a missing comma, "
            "quote, or bracket."
        )

    ok, errors = validate_project_data(data)
    if not ok:
        return None, " ".join(errors)

    return Project(
        root=root,
        name=data["name"],
        targets=list(data["targets"]),
        created=data["created"],
        description=data.get("description", ""),
        version=data.get("version", DEFAULT_VERSION),
        author=data.get("author", DEFAULT_AUTHOR),
        icon=data.get("icon", ""),
        id=data.get("id", _slug(data["name"])),
        contributions=data.get("contributions", {}),
    ), None


def validate_project_data(data) -> tuple[bool, list[str]]:
    """Check an already-loaded project.json (a dict from JSON).

    Returns ``(ok, errors)`` in the same plain-words form as the
    manifest validator. Never raises. Unknown fields are ignored.
    """
    errors: list[str] = []

    if not isinstance(data, dict):
        return False, [
            "The project file should hold one project description, "
            "a set of named fields, not a list or a single value."
        ]

    for field in REQUIRED_FIELDS:
        if field not in data:
            errors.append(
                f"The project file is missing the '{field}' field. "
                "Every project needs one."
            )

    if "name" in data:
        errors.extend(_check_name(data["name"]))
    if "targets" in data:
        errors.extend(_check_targets(data["targets"]))
    if "created" in data:
        errors.extend(_check_created(data["created"]))
    for field in ("description", "version", "author", "icon", "id"):
        if field in data and not isinstance(data[field], str):
            errors.append(
                f"The '{field}' field should be written as text."
            )
    if "contributions" in data and not isinstance(
        data["contributions"], dict
    ):
        # Shallow check only: contributions must be a set of named
        # kinds. Whether the kinds and entries are valid is the
        # manifest validator's job, when the pack is built.
        errors.append(
            "The 'contributions' field should hold a set of named "
            "kinds, like {\"wheel\": [...]}."
        )

    return (not errors), errors


def _check_name(value) -> list[str]:
    if not isinstance(value, str) or not value.strip():
        return ["The project name should be written as text, like 'Surprise'."]
    return []


def _check_targets(value) -> list[str]:
    if not isinstance(value, list):
        return [
            "The targets field should be a list, like [\"reblend\"]."
        ]
    if not value:
        return [
            "The project must target at least one program: "
            "reblend or blender."
        ]
    errors = []
    for item in value:
        if item not in KNOWN_TARGETS:
            errors.append(
                f"The target '{item}' is not one I know. "
                "Use reblend or blender."
            )
    return errors


def _check_created(value) -> list[str]:
    if not isinstance(value, str) or not _DATE_RE.match(value):
        return [
            "The created date should be written as a date, like 2026-11-17."
        ]
    try:
        date.fromisoformat(value)
    except ValueError:
        return [
            f"The created date '{value}' is not a real date. "
            "Use the form 2026-11-17."
        ]
    return []


def _slug(name: str) -> str:
    """A folder-friendly id from a project name: lowercase, words
    joined with dashes. "Surprise Pack" becomes "surprise-pack".
    """
    slug = _ID_RE.sub("-", name.lower()).strip("-")
    return slug or "project"
