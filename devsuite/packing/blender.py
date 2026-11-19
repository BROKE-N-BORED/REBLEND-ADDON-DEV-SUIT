"""Build a Blender add-on: project -> extension zip (Phase 4).

This is the Blender emitter — the Blender half of dossier §12 Phase 4.
It turns a project into the standard Blender output (DOSSIER.md §5.3,
followed faithfully, not invented): a Blender extension package for
4.2 and later, with the legacy ``bl_info`` add-on as the fallback for
older Blender. The build record beside it follows §9.4.

The add-on tree is gathered from the project's §5.4 layout and mapped
into Blender's layout — the emitter is the mapping step, so the
project and the add-on never have to look the same. Only the add-on's
own files go in; the project's working files (project.json, idea.md,
chat.jsonl, tests/, renders/, packs/) never do. The mapping:

* ``__init__.py`` — the entry point, from ``src/blender/__init__.py``.
  Required: a project without one cannot be packed, and the error
  says so in plain words.
* The other modules — everything under ``src/blender/`` plus
  everything under ``src/shared/`` (the target-free logic), copied
  preserving their relative paths, beside ``__init__.py`` at the
  add-on root. Two files that would land on the same name are a
  plain-words error, not a silent overwrite: module names must be
  unique across the two folders.
* ``blender_manifest.toml`` (extension layout only) — built fresh by
  the manifest writer in this module from the project. A manifest
  sitting in the project folder is never copied: the writer's is the
  only one that goes in, so a stale draft can never ship.
* ``assets/``, ``README.md``, ``icon.png`` — copied from the
  project root when they exist, skipped when they do not (the same
  root files the Reblend emitter packs: a Blender add-on with
  textures or presets needs its assets too). Every file that lands
  in the add-on — from ``src/`` or from the project root — goes
  through the same name check: two files landing on one name is a
  plain-words error, never a silent overwrite.

Two layouts, chosen by ``legacy``:

* **Extension (default).** The zip holds the files at its root —
  ``__init__.py``, the modules beside it, ``blender_manifest.toml`` —
  exactly as the Blender Manual's "How to Create Extensions" shows.
  This is the primary output (D2: Blender 5.3 first, extensions
  format).
* **Legacy.** The zip holds the add-on FOLDER, named after the
  add-on's id, with ``__init__.py`` and the modules inside, and no
  manifest — the pre-4.2 form. The emitter does not write code into
  the user's ``__init__.py``: in legacy mode it checks the entry file
  carries a ``bl_info`` dict and refuses plainly when it does not.

The manifest fields (Blender Manual, "How to Create Extensions",
checked 2026-11-17 — required: ``schema_version``, ``id``,
``version``, ``name``, ``tagline``, ``maintainer``, ``type``,
``blender_version_min``, ``license``; optional: ``website`` and the
rest, omitted when unset, never written blank):

* ``id`` — the project id with dashes turned into underscores.
  Blender ids are Python package names, and a dash is not valid in
  one; the project id keeps its dashes everywhere else, so this is
  a mechanical mapping, documented here, not a second id.
* ``version`` — the project version. Blender requires three numbers
  (``1.0.0``); anything else is a plain-words refusal.
* ``tagline`` — the project description, made one line, cut to 64
  characters (Blender's limit, at a word boundary when one is near),
  with trailing punctuation stripped (Blender forbids it). An empty
  description falls back to the project name: the tagline is
  required and cannot be blank.
* ``maintainer`` — the project author. It must not be blank.
* ``type`` — always ``"add-on"``. ``schema_version`` is always
  ``"1.0.0"``.
* ``blender_version_min`` — ``"4.2.0"``, the extensions format
  floor. D2 targets Blender 5.3, but nothing emitted here needs
  5.3-only features; the add-on's own code may raise this later.
* ``license`` — ``"GPL-3.0-or-later"`` by default, written with the
  ``SPDX:`` prefix Blender requires (``"SPDX:GPL-3.0-or-later"``).
  Blender extensions must carry an SPDX license; GPL-3.0-or-later
  is the standard for Blender add-ons. Pass a different SPDX id to
  override it — the pack window will offer the choice later.
* ``website`` — omitted unless given. The project has no website
  field, so nothing is invented here.

Before anything is zipped, the staged tree is scanned for secrets
(the real scan from secrets_scan.py). A secret found means no
add-on: the build is refused, naming the files (never the values).
No secrets in code, ever.

The zip is written as ``<project-id>-<version>-blender.zip`` and
the ``build.json`` beside it records the project id, the project
version, the target (``blender``), the test run id, and the date —
so an add-on always traces back to the run that proved it (§9.4).
The test harness is a later phase, so a build today usually has no
test run: that is recorded plainly (``test_run_id`` is null,
``proven`` is false) and the result carries a plain-words note that
the add-on is unproven. An unproven add-on still builds — this is a
warning, not a refusal. An add-on is never claimed proven without a
run behind it.

Every function here returns a plain result and never raises on a bad
project: a missing entry point, an unwritable folder, a secret in the
tree, or a manifest the project cannot produce all come back as
plain-words errors, never as a crash. A failed build leaves no partial
add-on behind — the zip is written to a temporary name and moved into
place only when it is complete, and if the build record cannot be
written the zip is removed again.

Blender itself is not needed to build an add-on — this module only
writes files. Whether the add-on installs and runs in real Blender is
proven on his PC (Phase 5), not here.
"""

from __future__ import annotations

import ast
import json
import re
import shutil
import tempfile
import zipfile
from datetime import date
from pathlib import Path

from devsuite.packing.secrets_scan import scan_pack

#: The manifest format version Blender expects. Fixed by Blender.
SCHEMA_VERSION = "1.0.0"

#: The lowest Blender the emitted add-on claims to support: the
#: extensions format floor. See the module docstring for why 4.2.0
#: and not 5.3.0.
DEFAULT_BLENDER_VERSION_MIN = "4.2.0"

#: The default license, as an SPDX id. Blender requires the SPDX:
#: prefix in the manifest; the writer adds it.
DEFAULT_LICENSE = "GPL-3.0-or-later"

#: Pack-tree entries copied from the project root when they exist.
#: The entry point and the code folders are handled separately.
OPTIONAL_PACK_ENTRIES = ("assets", "README.md", "icon.png")

#: Blender's tagline limit: one line, at most 64 characters, and it
#: may not end with punctuation.
TAGLINE_MAX_LENGTH = 64
_TAGLINE_END_PUNCTUATION = ".,;:!?"

_VERSION_RE = re.compile(r"^\d+\.\d+\.\d+$")


def build_blender_manifest(project, license=DEFAULT_LICENSE,
                           website=None) -> tuple[str | None, str | None]:
    """Build the blender_manifest.toml text for ``project``.

    Returns ``(text, error)``: ``text`` is the TOML file, ready to be
    written as blender_manifest.toml, or None when the project cannot
    produce a valid manifest; ``error`` is None on success, or a
    plain-words sentence saying what is wrong. Never raises.
    """
    try:
        return _build_blender_manifest(project, license, website)
    except Exception:
        return None, (
            "I could not write the Blender manifest for this project. "
            "The project may be damaged. Check its folder opens and "
            "its files can be read."
        )


def _build_blender_manifest(project, license, website):
    project_id = getattr(project, "id", "") or ""
    name = _one_line(getattr(project, "name", ""))
    version = getattr(project, "version", "") or ""
    description = _one_line(getattr(project, "description", ""))
    author = _one_line(getattr(project, "author", ""))

    if not project_id:
        return None, (
            "The project has no id, so the Blender add-on would have "
            "no name to install under."
        )
    if not name:
        return None, (
            "The project has no name, so the Blender add-on would "
            "have nothing to show in Blender's add-on list."
        )
    if not _VERSION_RE.match(version):
        return None, (
            f"The project version '{version}' is not three numbers. "
            "Blender needs a version like 1.2.3."
        )
    if not author:
        return None, (
            "The project has no author, so the Blender add-on would "
            "have no maintainer listed."
        )
    license_id = (license or "").strip()
    if not license_id:
        return None, (
            "The Blender add-on needs a license. Blender requires "
            "every extension to name one."
        )
    if not license_id.startswith("SPDX:"):
        license_id = f"SPDX:{license_id}"

    tagline = _tagline(description, name)

    lines = [
        f'schema_version = {_toml_string(SCHEMA_VERSION)}',
        f'id = {_toml_string(_blender_id(project_id))}',
        f'version = {_toml_string(version)}',
        f'name = {_toml_string(name)}',
        f'tagline = {_toml_string(tagline)}',
        f'maintainer = {_toml_string(author)}',
        f'type = {_toml_string("add-on")}',
    ]
    if website is not None and str(website).strip():
        lines.append(f'website = {_toml_string(_one_line(str(website)))}')
    lines.append(
        f'blender_version_min = {_toml_string(DEFAULT_BLENDER_VERSION_MIN)}'
    )
    lines.append(f'license = [{_toml_string(license_id)}]')
    return "\n".join(lines) + "\n", None


def _blender_id(project_id: str) -> str:
    """The project id as a Blender id: dashes become underscores.

    A Blender id is a Python package name, and a dash is not valid in
    one. The project id is unchanged everywhere else.
    """
    return project_id.replace("-", "_")


def _tagline(description: str, name: str) -> str:
    """The manifest tagline: one line, at most 64 characters, never
    ending in punctuation (Blender's rules).

    Cut at a word boundary when one is near, so the tagline does not
    end mid-word. An empty description falls back to the project
    name — the tagline is required and cannot be blank.
    """
    text = description or name
    if len(text) > TAGLINE_MAX_LENGTH:
        cut = text[:TAGLINE_MAX_LENGTH]
        boundary = cut.rfind(" ")
        if boundary >= TAGLINE_MAX_LENGTH // 2:
            cut = cut[:boundary]
        text = cut
    text = text.strip().rstrip(_TAGLINE_END_PUNCTUATION).strip()
    if not text:
        text = name
    return text


def _one_line(value) -> str:
    """Collapse ``value`` to one line: newlines and runs of spaces
    become single spaces. A TOML basic string holds no newlines.
    """
    if not isinstance(value, str):
        return ""
    return " ".join(value.split())


def _toml_string(value: str) -> str:
    """``value`` as a TOML basic string, escaped and quoted."""
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def build_blender_addon(project, out_dir, test_run_id=None,
                        legacy=False, license=DEFAULT_LICENSE,
                        website=None
                        ) -> tuple[Path | None, list[str], str | None]:
    """Build a Blender add-on zip from ``project`` into ``out_dir``.

    ``test_run_id`` is the id of the test run that proved this
    add-on, or None when no run proved it — the usual case until the
    test harness arrives. ``legacy`` builds the pre-4.2 ``bl_info``
    form instead of the extension package. ``license`` is the SPDX
    id for the manifest (default GPL-3.0-or-later); ``website`` is
    the manifest's website, omitted when None.

    Returns ``(zip_path, warnings, error)``. On success ``zip_path``
    is the built zip file, ``warnings`` holds plain-words notes
    (empty when there is nothing to say), and ``error`` is None. On
    failure ``zip_path`` is None and ``error`` is a plain-words
    sentence saying what went wrong. Never raises.
    """
    warnings: list[str] = []
    try:
        return _build_blender_addon(project, out_dir, test_run_id,
                                    legacy, license, website, warnings)
    except Exception:
        # A bad project must never crash the suite. Anything unexpected
        # — a broken path, a strange field — lands here as one sentence.
        return None, [], (
            "I could not build this Blender add-on. The project may "
            "be damaged. Check its folder opens and its files can "
            "be read."
        )


def _build_blender_addon(project, out_dir, test_run_id, legacy,
                         license, website, warnings):
    root = Path(project.root)
    targets = getattr(project, "targets", None) or []
    if "blender" not in targets:
        return None, [], (
            "This project does not target Blender, so there is no "
            "Blender add-on to build. Add blender to the project's "
            "targets first."
        )

    entry_path = root / "src" / "blender" / "__init__.py"
    if not entry_path.is_file():
        return None, [], (
            "I could not build this Blender add-on because the "
            "project has no src/blender/__init__.py file. Every "
            "Blender add-on needs one. It is the entry point "
            "Blender loads."
        )

    if legacy:
        bl_info_error = _check_bl_info(entry_path)
        if bl_info_error is not None:
            return None, [], bl_info_error
        manifest_text = None
    else:
        manifest_text, error = build_blender_manifest(
            project, license=license, website=website
        )
        if error is not None:
            return None, [], (
                "I could not build this Blender add-on because its "
                f"manifest would not be valid. {error}"
            )

    project_id = getattr(project, "id", "") or ""
    version = getattr(project, "version", "") or ""
    blender_id = _blender_id(project_id)

    out_path = Path(out_dir)
    try:
        out_path.mkdir(parents=True, exist_ok=True)
    except OSError:
        return None, [], (
            "I could not write to the folder the add-on should go "
            "in. Check the folder exists and can be written to."
        )

    zip_name = f"{project_id}-{version}-blender.zip"
    zip_path = out_path / zip_name

    with tempfile.TemporaryDirectory(prefix="devsuite-blender-") as staging:
        stage = Path(staging)
        stage_error = _stage_tree(root, stage, legacy, blender_id,
                                  manifest_text)
        if stage_error is not None:
            return None, [], stage_error
        findings = scan_pack(stage)
        if findings:
            return None, [], _secrets_error(findings)
        try:
            _write_zip(stage, zip_path)
        except OSError:
            return None, [], (
                "I could not write the add-on file. "
                "Check there is room on the disk and the folder can be "
                "written to."
            )
        try:
            _write_build_record(out_path, project_id, version, zip_name,
                                test_run_id)
        except OSError:
            try:
                zip_path.unlink()
            except OSError:
                pass
            return None, [], (
                "I could not write the build record next to the "
                "add-on, so I removed the add-on again rather than "
                "leave an add-on with no record of where it came from."
            )

    if test_run_id is None:
        warnings.append(
            "No test run proved this add-on, so it is unproven. The "
            "test harness is a later phase; test this add-on by hand "
            "before trusting it."
        )
    return zip_path, warnings, None


def _check_bl_info(entry_path: Path) -> str | None:
    """Check the entry file carries a ``bl_info`` dict (legacy mode).

    Returns None when it does, or a plain-words sentence when it does
    not — or when the file cannot be read as Python at all. The
    emitter never writes code into the user's entry file, so a
    missing ``bl_info`` is a refusal, not something to fix silently.
    """
    try:
        source = entry_path.read_text(encoding="utf-8")
    except OSError:
        return (
            "I could not read src/blender/__init__.py, so I could not "
            "check it carries a bl_info for the legacy add-on form."
        )
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return (
            "I could not read src/blender/__init__.py as Python, so I "
            "could not check it carries a bl_info for the legacy "
            "add-on form. Check the file for a mistake."
        )
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        if not any(
            isinstance(target, ast.Name) and target.id == "bl_info"
            for target in node.targets
        ):
            continue
        if not isinstance(node.value, ast.Dict):
            return (
                "The bl_info in src/blender/__init__.py is not a set "
                "of details. It should be a bl_info dict, like the "
                "one in the Surprise template."
            )
        return None
    return (
        "I could not build the legacy Blender add-on because "
        "src/blender/__init__.py has no bl_info. The legacy form "
        "needs one. It is how older Blender finds the add-on's name "
        "and version."
    )


def _stage_tree(root: Path, stage: Path, legacy: bool, blender_id: str,
                manifest_text: str | None) -> str | None:
    """Copy the add-on tree into the staging folder.

    Extension layout: the files land at the staging root, with the
    writer's manifest beside them. Legacy layout: everything lands
    inside a folder named after the add-on's id, and there is no
    manifest. A manifest sitting in the project folder is never
    copied — the writer's is the only one in the add-on.

    Returns None on success, or a plain-words error when two files
    would land on the same name.
    """
    seen: dict[str, str] = {}
    if legacy:
        dest = stage / blender_id
        dest.mkdir(parents=True, exist_ok=True)
    else:
        dest = stage
        dest.joinpath("blender_manifest.toml").write_text(
            manifest_text, encoding="utf-8"
        )
        # The generated manifest owns its name: a project file of the
        # same name must not silently overwrite it.
        seen["blender_manifest.toml"] = "the generated manifest"

    def place(path: Path, relative: Path, label: str) -> str | None:
        """Copy one file to its place in the add-on, checking the
        name is not already taken. Returns a plain-words error on a
        collision, else None."""
        name = relative.as_posix()
        if name in seen:
            return (
                "I could not build this Blender add-on because two "
                f"files would land on the same name inside it: "
                f"{name} comes from both {seen[name]} and {label}. "
                "Rename one of them, then try again."
            )
        seen[name] = label
        target = dest / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
        return None

    for source_dir in (root / "src" / "blender", root / "src" / "shared"):
        if not source_dir.is_dir():
            continue
        label = f"src/{source_dir.name}"
        for path in sorted(source_dir.rglob("*")):
            if not path.is_file() or "__pycache__" in path.parts:
                continue
            error = place(path, path.relative_to(source_dir), label)
            if error is not None:
                return error
    for name in OPTIONAL_PACK_ENTRIES:
        source = root / name
        if not source.exists():
            continue
        if source.is_dir():
            for path in sorted(source.rglob("*")):
                if not path.is_file() or "__pycache__" in path.parts:
                    continue
                error = place(
                    path, Path(name) / path.relative_to(source),
                    "the project root",
                )
                if error is not None:
                    return error
        else:
            error = place(source, Path(name), "the project root")
            if error is not None:
                return error
    return None


def _secrets_error(findings: list[dict]) -> str:
    """The plain-words refusal for an add-on that holds a secret.

    Names the files and lines, never the values: the descriptions come
    from the scanner's fixed sentences, and no matched text is ever
    copied into them.
    """
    locations = ", ".join(
        f"{finding['file']} (line {finding['line']})" for finding in findings
    )
    return (
        "I did not build this Blender add-on because it looks like it "
        "holds a secret. Add-ons must never carry keys, tokens, or "
        "passwords. Check these files and remove the secret, then try "
        f"again: {locations}."
    )


def _write_zip(stage: Path, zip_path: Path) -> None:
    """Zip the staged tree into ``zip_path``.

    Entries are sorted, so the same tree always builds the same zip.
    The zip is written to a temporary name beside the add-on and moved
    into place only when complete, so a failed write never leaves a
    half-written add-on behind.
    """
    files = sorted(
        (path for path in stage.rglob("*") if path.is_file()),
        key=lambda path: str(path.relative_to(stage)),
    )
    tmp_path = zip_path.with_name(zip_path.name + ".tmp")
    try:
        with zipfile.ZipFile(tmp_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for path in files:
                zf.write(path, path.relative_to(stage).as_posix())
        tmp_path.replace(zip_path)
    except BaseException:
        try:
            tmp_path.unlink()
        except OSError:
            pass
        raise


def _write_build_record(out_path: Path, project_id: str, version: str,
                        zip_name: str, test_run_id) -> None:
    """Write build.json beside the add-on (§9.4).

    The record is the add-on's trace back to what proved it: the
    project id and version, the target, the test run id, and the
    date. When no test run proved the add-on, ``test_run_id`` is null
    and ``proven`` is false — recorded plainly, not hidden.
    """
    record = {
        "project_id": project_id,
        "project_version": version,
        "target": "blender",
        "pack": zip_name,
        "test_run_id": test_run_id,
        "proven": test_run_id is not None,
        "built": date.today().isoformat(),
    }
    tmp_path = out_path / "build.json.tmp"
    final_path = out_path / "build.json"
    try:
        tmp_path.write_text(
            json.dumps(record, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        tmp_path.replace(final_path)
    except BaseException:
        try:
            tmp_path.unlink()
        except OSError:
            pass
        raise
