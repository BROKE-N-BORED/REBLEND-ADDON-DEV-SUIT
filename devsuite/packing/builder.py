"""Build a Reblend pack: project -> .rblpack zip (Phase 4, pulled forward).

This is the Reblend emitter — the Reblend half of dossier §12 Phase 4,
built early because it is independently verifiable while Phase 3 waits
on the Reblend loader. It turns a project into a pack (DOSSIER.md §5.1)
and the build record beside it (§9.4).

The pack tree is gathered from the project's §5.4 layout and mapped
into the pack's §5.1 layout — the emitter is the mapping step, so the
project and the pack never have to look the same. Only the pack's own
files go in; the project's working files (project.json, idea.md,
chat.jsonl, tests/, renders/, packs/) never do. The mapping:

* ``manifest.json`` — built fresh by the manifest writer from the
  project. A manifest.json sitting in the project folder is never
  copied: the writer's manifest is the only one that goes in, so a
  stale draft can never ship inside a pack.
* ``addon.py`` — the entry point, from ``src/reblend/addon.py``.
  Required: a project without one cannot be packed, and the error
  says so in plain words.
* ``code/`` — the modules from ``src/reblend/`` (everything but
  addon.py) plus ``src/shared/`` (the target-free logic), copied
  preserving their relative paths. Two files that would land on the
  same name in ``code/`` are a plain-words error, not a silent
  overwrite: module names must be unique across the two folders.
  Pack modules are imported by flat name (``import pick``, not
  ``import code.pick``) — the loader puts the pack's ``code/`` on
  the import path, and the test harness puts ``src/reblend/`` and
  ``src/shared/`` on the path in the project, so the same import
  works on both sides (§5.1).
* ``assets/``, ``README.md``, ``icon.png`` — copied from the
  project root when they exist, skipped when they do not. A pack
  with just an entry point is a valid pack.

Before anything is zipped, the staged tree is scanned for secrets
(the real scan from secrets_scan.py). A secret found means no pack:
the build is refused, naming the files (never the values). No secrets
in code, ever.

The zip is written as ``<project-id>-<version>.rblpack`` and the
``build.json`` beside it records the project id, the project version,
the target (``reblend``), the test run id, and the date — so a pack
always traces back to the run that proved it (§9.4). The test harness
is a later phase, so a build today usually has no test run: that is
recorded plainly (``test_run_id`` is null, ``proven`` is false) and
the result carries a plain-words note that the pack is unproven. An
unproven pack still builds — this is a warning, not a refusal. A pack
is never claimed proven without a run behind it.

Every function here returns a plain result and never raises on a bad
project: a missing entry point, an unwritable folder, a secret in the
tree, or a manifest the project cannot produce all come back as
plain-words errors, never as a crash. A failed build leaves no partial
pack behind — the zip is written to a temporary name and moved into
place only when it is complete, and if the build record cannot be
written the zip is removed again.
"""

from __future__ import annotations

import json
import shutil
import tempfile
import zipfile
from datetime import date
from pathlib import Path

from devsuite.packing.secrets_scan import scan_pack
from devsuite.packing.writer import build_manifest

#: Pack-tree entries copied from the project root when they exist.
#: The entry point and the code folders are handled separately.
OPTIONAL_PACK_ENTRIES = ("assets", "README.md", "icon.png")


def build_pack(project, out_dir, test_run_id=None,
               contributions=None) -> tuple[Path | None, list[str], str | None]:
    """Build a .rblpack zip from ``project`` into ``out_dir``.

    ``test_run_id`` is the id of the test run that proved this pack, or
    None when no run proved it — the usual case until the test harness
    arrives. ``contributions`` is what the pack declares (wheel, menu,
    and the rest, as in §5.1); the caller supplies them — the pack
    window will own them later — and None means the pack declares
    nothing yet.

    Returns ``(pack_path, warnings, error)``. On success ``pack_path``
    is the built ``.rblpack`` file, ``warnings`` holds plain-words
    notes (empty when there is nothing to say), and ``error`` is None.
    On failure ``pack_path`` is None and ``error`` is a plain-words
    sentence saying what went wrong. Never raises.
    """
    warnings: list[str] = []
    try:
        return _build_pack(project, out_dir, test_run_id, contributions,
                           warnings)
    except Exception:
        # A bad project must never crash the suite. Anything unexpected
        # — a broken path, a strange field — lands here as one sentence.
        return None, [], (
            "I could not build this pack. The project may be damaged. "
            "Check its folder opens and its files can be read."
        )


def _build_pack(project, out_dir, test_run_id, contributions, warnings):
    root = Path(project.root)
    targets = getattr(project, "targets", None) or []
    if "reblend" not in targets:
        return None, [], (
            "This project does not target Reblend, so there is no Reblend "
            "pack to build. Add reblend to the project's targets first."
        )

    entry_path = root / "src" / "reblend" / "addon.py"
    if not entry_path.is_file():
        return None, [], (
            "I could not build this pack because the project has no "
            "src/reblend/addon.py file. Every Reblend pack needs one "
            ". It is the entry point Reblend calls to run the pack."
        )

    manifest, error = build_manifest(project, contributions)
    if error is not None:
        return None, [], (
            "I could not build this pack because its manifest would not "
            f"be valid. {error}"
        )

    out_path = Path(out_dir)
    try:
        out_path.mkdir(parents=True, exist_ok=True)
    except OSError:
        return None, [], (
            "I could not write to the folder the pack should go in. "
            "Check the folder exists and can be written to."
        )

    pack_name = f"{manifest['id']}-{manifest['version']}.rblpack"
    pack_path = out_path / pack_name

    with tempfile.TemporaryDirectory(prefix="devsuite-pack-") as staging:
        stage = Path(staging)
        stage_error = _stage_tree(root, stage, manifest)
        if stage_error is not None:
            return None, [], stage_error
        findings = scan_pack(stage)
        if findings:
            return None, [], _secrets_error(findings)
        try:
            _write_zip(stage, pack_path)
        except OSError:
            return None, [], (
                "I could not write the pack file. "
                "Check there is room on the disk and the folder can be "
                "written to."
            )
        try:
            _write_build_record(out_path, manifest, pack_name, test_run_id)
        except OSError:
            try:
                pack_path.unlink()
            except OSError:
                pass
            return None, [], (
                "I could not write the build record next to the pack, "
                "so I removed the pack again rather than leave a pack "
                "with no record of where it came from."
            )

    if test_run_id is None:
        warnings.append(
            "No test run proved this pack, so it is unproven. The test "
            "harness is a later phase; test this pack by hand before "
            "trusting it."
        )
    return pack_path, warnings, None


def _stage_tree(root: Path, stage: Path, manifest: dict) -> str | None:
    """Copy the pack tree into the staging folder.

    The writer's manifest goes in as manifest.json; the entry point
    and the code folders follow (§5.4 to §5.1 mapping, see the module
    docstring). A manifest.json in the project folder is never
    copied — the writer's is the only manifest in the pack.

    Returns None on success, or a plain-words error when two module
    files would land on the same name inside ``code/``.
    """
    (stage / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    shutil.copy2(root / "src" / "reblend" / "addon.py", stage / "addon.py")
    code_dir = stage / "code"
    seen: dict[str, str] = {}
    for source_dir in (root / "src" / "reblend", root / "src" / "shared"):
        if not source_dir.is_dir():
            continue
        for path in sorted(source_dir.rglob("*")):
            if not path.is_file() or "__pycache__" in path.parts:
                continue
            relative = path.relative_to(source_dir)
            if source_dir.name == "reblend" and relative == Path("addon.py"):
                continue  # The entry point already went to the pack root.
            name = relative.as_posix()
            if name in seen:
                return (
                    "I could not build this pack because two files "
                    f"would land on the same name inside it: code/{name} "
                    f"comes from both {seen[name]} and {source_dir.name}. "
                    "Rename one of them, then try again."
                )
            seen[name] = source_dir.name
            target = code_dir / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)
    for name in OPTIONAL_PACK_ENTRIES:
        source = root / name
        if not source.exists():
            continue
        if source.is_dir():
            shutil.copytree(
                source, stage / name,
                ignore=shutil.ignore_patterns("__pycache__"),
            )
        else:
            shutil.copy2(source, stage / name)
    return None


def _secrets_error(findings: list[dict]) -> str:
    """The plain-words refusal for a pack that holds a secret.

    Names the files and lines, never the values: the descriptions come
    from the scanner's fixed sentences, and no matched text is ever
    copied into them.
    """
    locations = ", ".join(
        f"{finding['file']} (line {finding['line']})" for finding in findings
    )
    return (
        "I did not build this pack because it looks like it holds a "
        "secret. Packs must never carry keys, tokens, or passwords. "
        f"Check these files and remove the secret, then try again: "
        f"{locations}."
    )


def _write_zip(stage: Path, pack_path: Path) -> None:
    """Zip the staged tree into ``pack_path``.

    Entries are sorted, so the same tree always builds the same zip.
    The zip is written to a temporary name beside the pack and moved
    into place only when complete, so a failed write never leaves a
    half-written pack behind.
    """
    files = sorted(
        (path for path in stage.rglob("*") if path.is_file()),
        key=lambda path: str(path.relative_to(stage)),
    )
    tmp_path = pack_path.with_name(pack_path.name + ".tmp")
    try:
        with zipfile.ZipFile(tmp_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for path in files:
                zf.write(path, path.relative_to(stage).as_posix())
        tmp_path.replace(pack_path)
    except BaseException:
        try:
            tmp_path.unlink()
        except OSError:
            pass
        raise


def _write_build_record(out_path: Path, manifest: dict, pack_name: str,
                        test_run_id) -> None:
    """Write build.json beside the pack (§9.4).

    The record is the pack's trace back to what proved it: the project
    id and version, the target, the test run id, and the date. When no
    test run proved the pack, ``test_run_id`` is null and ``proven``
    is false — recorded plainly, not hidden.
    """
    record = {
        "project_id": manifest["id"],
        "project_version": manifest["version"],
        "target": "reblend",
        "pack": pack_name,
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
