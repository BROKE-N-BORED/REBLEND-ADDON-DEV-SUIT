"""Install and uninstall packs (Phase 4, pulled forward).

Install and uninstall are file operations — nothing more (DOSSIER.md
§5.1). Install copies a ``.rblpack`` file, or an unzipped pack folder,
into the packs folder. Uninstall deletes it. No registry, no installer
inside the pack, no code that runs at install time: doing it by hand
works identically, and this module only does the copying.

The packs folder is always a parameter, never a guess. Where Reblend
looks for packs is the loader thread's decision (Phase 1, REBLEND DEV
thread); this module copies where it is told and says where it put
things. The pack window will pass Reblend's real packs folder; tests
pass a temporary one.

This module does not check whether a pack is good — it copies what it
is given. Checking a pack is the loader's job: a bad pack is reported
in Reblend's pack list in plain words, and Reblend keeps running
(§5.1). The one exception is the file ending: a file that is not a
``.rblpack`` is refused, because copying a random file into the packs
folder can only be a mistake.

The Blender side is the same idea for a different file: a Blender
add-on ships as a zip, and installing it means copying that zip where
Blender looks (``install_blender_addon``). Same rule — a file that
is not a zip is refused. Only the zip is installed, never an
unzipped folder: Blender installs add-ons from the zip (drag it into
Extensions preferences, or place it in the add-ons folder), and the
emitter's zip is the deliverable.

Every function here returns a plain result and never raises on a bad
pack or folder: a missing file, a folder that cannot be written, or a
pack that is not installed all come back as plain-words errors, never
as a crash.
"""

from __future__ import annotations

import glob
import shutil
from pathlib import Path


def install_pack(pack_path, packs_dir) -> tuple[Path | None, str | None]:
    """Copy a pack into the packs folder.

    ``pack_path`` is a ``.rblpack`` file or an unzipped pack folder;
    ``packs_dir`` is the folder to copy it into, created when it does
    not exist yet. Reinstalling a pack replaces the copy already
    there — rebuilding and reinstalling is the normal flow.

    Returns ``(installed_path, error)``: ``installed_path`` is where
    the pack now sits, or None when the install failed; ``error`` is
    None on success, or a plain-words sentence saying what went wrong.
    Never raises, and never runs anything in the pack.
    """
    source = Path(pack_path)
    dest_dir = Path(packs_dir)
    try:
        if not source.exists():
            return None, (
                "I could not find that pack. "
                "Check the file or folder is there and try again."
            )
        try:
            dest_dir.mkdir(parents=True, exist_ok=True)
        except OSError:
            return None, (
                "I could not write to the packs folder. "
                "Check the folder can be written to."
            )
        if source.is_file():
            if source.suffix.lower() != ".rblpack":
                return None, (
                    "That file is not a pack. Packs end in .rblpack. "
                    "Check the file and try again."
                )
            dest = dest_dir / source.name
            shutil.copy2(source, dest)
            return dest, None
        if source.is_dir():
            dest = dest_dir / source.name
            if dest.is_dir() and not dest.is_symlink():
                shutil.rmtree(dest)
            elif dest.exists() or dest.is_symlink():
                dest.unlink()
            shutil.copytree(
                source, dest,
                ignore=shutil.ignore_patterns("__pycache__"),
            )
            return dest, None
        return None, (
            "That pack is neither a file nor a folder, so I could not "
            "install it. Check the pack and try again."
        )
    except OSError:
        return None, (
            "I could not copy the pack into the packs folder. "
            "Check there is room on the disk and the folder can be "
            "written to."
        )


def install_blender_addon(zip_path, addons_dir) -> tuple[Path | None, str | None]:
    """Copy a Blender add-on zip into the add-ons folder.

    ``zip_path`` is the ``-blender.zip`` file the Blender emitter
    built; ``addons_dir`` is the folder to copy it into, created
    when it does not exist yet. Reinstalling replaces the copy
    already there — rebuilding and reinstalling is the normal flow.

    Returns ``(installed_path, error)``: ``installed_path`` is where
    the zip now sits, or None when the install failed; ``error`` is
    None on success, or a plain-words sentence saying what went
    wrong. Never raises, and never runs anything in the add-on.
    """
    source = Path(zip_path)
    dest_dir = Path(addons_dir)
    try:
        if not source.is_file():
            return None, (
                "I could not find that Blender add-on. "
                "Check the zip file is there and try again."
            )
        if source.suffix.lower() != ".zip":
            return None, (
                "That file is not a Blender add-on. Add-ons are zip "
                "files. Check the file and try again."
            )
        try:
            dest_dir.mkdir(parents=True, exist_ok=True)
        except OSError:
            return None, (
                "I could not write to the add-ons folder. "
                "Check the folder can be written to."
            )
        dest = dest_dir / source.name
        shutil.copy2(source, dest)
        return dest, None
    except OSError:
        return None, (
            "I could not copy the add-on into the add-ons folder. "
            "Check there is room on the disk and the folder can be "
            "written to."
        )


def uninstall_pack(packs_dir, pack_id) -> tuple[list[Path], str | None]:
    """Remove an installed pack from the packs folder.

    ``pack_id`` is the pack's id, as in its manifest — ``surprise``,
    not a file name. Every installed copy of that pack is removed:
    the ``.rblpack`` file (whatever version it carries) and an
    unzipped folder of the same name, when either is there.

    Returns ``(removed, error)``: ``removed`` is the list of paths
    taken out, empty when nothing was removed; ``error`` is None on
    success, or a plain-words sentence — the pack is not installed,
    or a file could not be removed. Never raises.
    """
    if not isinstance(pack_id, str) or not pack_id:
        return [], "I need a pack id to uninstall, like 'surprise'."
    if "/" in pack_id or "\\" in pack_id or pack_id in (".", ".."):
        return [], (
            f"The pack id '{pack_id}' is not a pack id. "
            "Use the id from the pack's manifest, like 'surprise'."
        )

    dest_dir = Path(packs_dir)
    candidates = []
    folder = dest_dir / pack_id
    if folder.is_dir() and not folder.is_symlink():
        candidates.append(folder)
    elif folder.is_symlink():
        candidates.append(folder)
    bare_file = dest_dir / f"{pack_id}.rblpack"
    if bare_file.is_file():
        candidates.append(bare_file)
    pattern = f"{glob.escape(pack_id)}-*.rblpack"
    candidates.extend(
        path for path in sorted(dest_dir.glob(pattern)) if path.is_file()
    )

    if not candidates:
        return [], (
            f"The pack '{pack_id}' is not installed, "
            "so there is nothing to remove."
        )

    removed: list[Path] = []
    try:
        for path in candidates:
            if path.is_dir() and not path.is_symlink():
                shutil.rmtree(path)
            else:
                path.unlink()
            removed.append(path)
    except OSError:
        return removed, (
            f"I could not remove the pack '{pack_id}' completely. "
            "Check the packs folder can be written to and try again."
        )
    return removed, None
