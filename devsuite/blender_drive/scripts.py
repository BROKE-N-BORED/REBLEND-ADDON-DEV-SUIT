"""Generate the test script Blender runs (DOSSIER.md §8.3).

The script is plain text: it is generated without Blender present,
and Blender executes it with ``bpy`` available. It installs the
add-on zip, runs the standard checks against a test scene built in
the script (no external scene file needed), renders one frame, and
unloads the add-on again.

How the script talks back: one line per check on stdout, each a
JSON object after a fixed prefix::

    DEVSUITE-CHECK {"name": "Loads without errors", "passed": true, "detail": "..."}

The runner (``runner.parse_checks``) reads those lines. A check
that fails reports itself as failed with the reason in ``detail``
— never a silent pass, and a broken add-on leaves its traceback
in Blender's log for the one-click view (§12 Phase 5). The script
exits 0 when every check passed, 1 otherwise.

The standard checks (the brief's list, mapped onto §8.4):

1. "Loads without errors" — install the zip and enable the add-on.
2. "Does not crash on the empty scene" — the empty scene with the
   add-on enabled.
3. "Operator runs" — the add-on's operator on a test cube (only
   when an operator id is given; a panel-only add-on skips it).
4. "Render is written" — one small frame rendered to the run
   folder.
5. "Unloads clean" — disable and uninstall, verifying the add-on
   is gone.

Install route (Blender 5.3 Python API, docs.blender.org, checked
2026-11-17): the extension zip goes through
``bpy.ops.extensions.package_install_files(filepath=..., repo=...,
enable_on_install=True)`` into a locally managed repository — the
repo is looked up from the preferences, not hardcoded, and made
when there is none. Uninstall is
``bpy.ops.extensions.package_uninstall(repo_index=..., pkg_id=...)``.
The legacy form uses ``bpy.ops.preferences.addon_install`` /
``addon_enable`` / ``addon_disable``. Enable state is always
verified against ``bpy.context.preferences.addons`` — the operator
returning is not proof enough.

The render tries EEVEE first and falls back to Cycles on CPU when
no render lands (SKULLPT's lesson: EEVEE needs a GPU/GL context
some headless runs cannot give; Cycles always can). Resolution is
256x192 — small on purpose, a test frame, not a beauty shot.

What v1 does not check (later refinements, not silent gaps): the
undo check (§8.4 #5 — the operator runs, but the script does not
yet prove one undo step restores the scene), and project-specific
checks from the project's ``tests/`` folder (the chat writes
those; the drive runs the standard set only).
"""

from __future__ import annotations

import re
import zipfile
from pathlib import Path

#: A Blender extension id: lowercase, starts with a letter, letters,
#: digits, and underscores only (the emitter maps dashes to
#: underscores for exactly this reason).
_ADDON_ID_RE = re.compile(r"^[a-z][a-z0-9_]*$")

#: An operator id: "category.name", each part a Blender identifier.
_OPERATOR_ID_RE = re.compile(r"^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$")

#: The render the test writes into the run folder.
RENDER_NAME = "render-test.png"


def generate_test_script(addon_id, operator_id=None,
                         legacy=False) -> tuple[str | None, str | None]:
    """Build the test script text for an add-on.

    ``addon_id`` is the Blender id (underscores, as the manifest
    writes it). ``operator_id`` is the operator to run
    (``"surprise.randomize"``) or None — with no operator the
    operator check is left out, so a panel-only add-on still gets
    its load/render/unload checks. ``legacy`` builds the script
    for the pre-4.2 ``bl_info`` form instead of the extension
    package.

    Returns ``(script, error)``: ``script`` is the Python source
    Blender runs, or None when the ids cannot make a valid test;
    ``error`` is None on success, or a plain-words sentence.
    """
    if not isinstance(addon_id, str) or not _ADDON_ID_RE.match(addon_id):
        return None, (
            f"The add-on id '{addon_id}' is not a Blender id. A "
            "Blender id starts with a lowercase letter and uses "
            "only lowercase letters, digits, and underscores."
        )
    if operator_id is not None and (
        not isinstance(operator_id, str)
        or not _OPERATOR_ID_RE.match(operator_id)
    ):
        return None, (
            f"The operator id '{operator_id}' is not an operator "
            "id. An operator id looks like category.name, for "
            "example surprise.randomize."
        )
    operator_check = (
        '    check("Operator runs", _operator)'
        if operator_id is not None else ""
    )
    script = (
        _SCRIPT_TEMPLATE
        .replace("__ADDON_ID__", repr(addon_id))
        .replace("__OPERATOR_ID__", repr(operator_id))
        .replace("__LEGACY__", repr(bool(legacy)))
        .replace("__OPERATOR_CHECK__", operator_check)
    )
    return script, None


def zip_is_legacy(zip_path) -> bool:
    """True when the add-on zip is the legacy ``bl_info`` form.

    An extension zip carries ``blender_manifest.toml`` at its
    root; a legacy zip does not. A zip that cannot be read is not
    legacy — the runner rejects it before Blender runs anyway, so
    the answer here never decides anything on its own.
    """
    try:
        with zipfile.ZipFile(zip_path) as zf:
            return "blender_manifest.toml" not in zf.namelist()
    except (OSError, zipfile.BadZipFile):
        return False


def write_test_script(path, addon_id, operator_id=None,
                      legacy=False) -> tuple[str | None, str | None]:
    """Generate the test script and write it to ``path``.

    Returns ``(path, error)`` in the usual plain-words shape.
    """
    script, error = generate_test_script(addon_id, operator_id, legacy)
    if error is not None:
        return None, error
    try:
        Path(path).write_text(script, encoding="utf-8")
    except OSError:
        return None, (
            "I could not write the Blender test script. Check the "
            "folder can be written to."
        )
    return str(path), None


_SCRIPT_TEMPLATE = r'''
"""DevSuite Blender test: install the add-on, run the standard
checks, render one frame, unload it again. Generated by the suite
(devsuite/blender_drive/scripts.py); runs inside Blender with bpy.

The suite hands it two environment variables: DEVSUITE_ADDON_ZIP
(the built add-on zip) and DEVSUITE_OUT_DIR (the run folder, where
the render and the record go). Each check prints one line:
DEVSUITE-CHECK {"name": ..., "passed": ..., "detail": ...}.
"""

import json
import os
import sys
import traceback

ADDON_ID = __ADDON_ID__
OPERATOR_ID = __OPERATOR_ID__
LEGACY = __LEGACY__
ADDON_ZIP = os.environ.get("DEVSUITE_ADDON_ZIP", "")
OUT_DIR = os.environ.get("DEVSUITE_OUT_DIR", "")


def report(name, passed, detail=""):
    """One check result, as a line the runner parses."""
    line = json.dumps({
        "name": name,
        "passed": bool(passed),
        "detail": str(detail),
    })
    print("DEVSUITE-CHECK " + line, flush=True)


_results = []


def check(name, fn):
    """Run one check: pass or fail, it always reports."""
    try:
        detail = fn()
        report(name, True, detail or "")
        _results.append(True)
    except Exception as exc:
        report(name, False, str(exc))
        _results.append(False)


try:
    import bpy
    from mathutils import Vector
except ImportError:
    # Run outside Blender (plain Python): say so plainly instead of
    # dying on the import.
    report(
        "Loads without errors", False,
        "this test script must run inside Blender.",
    )
    sys.exit(1)


_state = {"installed": False, "repo_index": -1}


def _local_repo():
    """A locally managed extension repository: (index, module), or
    (None, None) when Blender has none. Looked up, never hardcoded
    — the default user repo is one, but a fresh config may differ."""
    prefs = bpy.context.preferences.extensions
    for index, repo in enumerate(prefs.repos):
        if repo.type == 'LOCAL':
            return index, repo.module
    return None, None


def _ensure_local_repo():
    index, module = _local_repo()
    if module:
        return index, module
    bpy.ops.preferences.extension_repo_add(
        name="DevSuite Test", type='LOCAL'
    )
    index, module = _local_repo()
    if not module:
        raise RuntimeError(
            "Blender has no local extension repository, and I "
            "could not make one."
        )
    return index, module


def _install():
    if not ADDON_ZIP or not os.path.isfile(ADDON_ZIP):
        raise RuntimeError(
            "the add-on file is missing. The suite did not hand "
            "one to the test."
        )
    if LEGACY:
        bpy.ops.preferences.addon_install(
            filepath=ADDON_ZIP, overwrite=True
        )
        bpy.ops.preferences.addon_enable(module=ADDON_ID)
    else:
        index, module = _ensure_local_repo()
        _state["repo_index"] = index
        result = bpy.ops.extensions.package_install_files(
            filepath=ADDON_ZIP, repo=module,
            enable_on_install=True, overwrite=True,
        )
        if "CANCELLED" in result:
            raise RuntimeError(
                "Blender refused to install the extension."
            )
    if ADDON_ID not in bpy.context.preferences.addons:
        raise RuntimeError(
            "the add-on installed but is not enabled."
        )
    _state["installed"] = True
    return "installed and enabled."


def _require_installed():
    if not _state["installed"]:
        raise RuntimeError(
            "could not run. The add-on did not install."
        )


def _empty_scene():
    _require_installed()
    # An empty scene, made by deleting everything — not by reading
    # factory settings, which would reset the preferences and could
    # disable the add-on just installed.
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete(use_global=False)
    return "the empty scene opens clean with the add-on enabled."


def _operator():
    _require_installed()
    bpy.ops.mesh.primitive_cube_add(location=(0, 0, 0))
    cube = bpy.context.active_object
    cube.select_set(True)
    bpy.context.view_layer.objects.active = cube
    category, name = OPERATOR_ID.split(".", 1)
    group = getattr(bpy.ops, category, None)
    op = getattr(group, name, None) if group is not None else None
    if op is None:
        raise RuntimeError(
            f"the operator {OPERATOR_ID} is not registered."
        )
    result = op()
    if "CANCELLED" in result:
        raise RuntimeError(
            f"the operator {OPERATOR_ID} was cancelled."
        )
    return f"{OPERATOR_ID} ran on the test cube."


def _look_at(obj, point):
    direction = Vector(point) - obj.location
    obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()


def _render():
    _require_installed()
    if not OUT_DIR:
        raise RuntimeError(
            "no output folder was handed to the test."
        )
    os.makedirs(OUT_DIR, exist_ok=True)
    scene = bpy.context.scene
    # The empty-scene step cleared the lights and camera, so the
    # test scene brings its own.
    bpy.ops.object.light_add(type='SUN', location=(2, -2, 4))
    sun = bpy.context.active_object
    sun.data.energy = 2.0
    _look_at(sun, (0, 0, 0))
    cam_data = bpy.data.cameras.new("Test Camera")
    cam = bpy.data.objects.new("Test Camera", cam_data)
    scene.collection.objects.link(cam)
    cam.location = (4, -4, 3)
    _look_at(cam, (0, 0, 0))
    scene.camera = cam
    scene.render.resolution_x = 256
    scene.render.resolution_y = 192
    scene.render.image_settings.file_format = 'PNG'
    path = os.path.join(OUT_DIR, "render-test.png")
    scene.render.filepath = path
    try:
        scene.render.engine = 'BLENDER_EEVEE_NEXT'
        bpy.ops.render.render(write_still=True)
    except Exception:
        # EEVEE needs a GPU context some headless runs cannot give.
        # Cycles on CPU always can (SKULLPT's fallback).
        pass
    if not os.path.isfile(path) or os.path.getsize(path) == 0:
        scene.render.engine = 'CYCLES'
        scene.cycles.samples = 16
        bpy.ops.render.render(write_still=True)
    if not os.path.isfile(path) or os.path.getsize(path) == 0:
        raise RuntimeError(
            "Blender ran but no render file landed."
        )
    return "render-test.png written."


def _unload():
    _require_installed()
    bpy.ops.preferences.addon_disable(module=ADDON_ID)
    if ADDON_ID in bpy.context.preferences.addons:
        raise RuntimeError(
            "the add-on is still enabled after disabling it."
        )
    if LEGACY:
        # The files live in the throwaway scripts folder the
        # runner pointed Blender at, discarded with the run.
        return "disabled; the files go with the throwaway config."
    index = _state["repo_index"]
    result = bpy.ops.extensions.package_uninstall(
        repo_index=index, pkg_id=ADDON_ID
    )
    if "CANCELLED" in result:
        raise RuntimeError(
            "Blender refused to uninstall the extension."
        )
    # The package folder should be gone from the repo. When the
    # folder cannot be checked, the operator's own result stands.
    repos = bpy.context.preferences.extensions.repos
    folder = None
    if 0 <= index < len(repos):
        folder = os.path.join(repos[index].directory, ADDON_ID)
    if folder is not None and os.path.isdir(folder):
        raise RuntimeError(
            "the extension is gone from Blender, but its files "
            "are still on disk."
        )
    return "disabled and uninstalled; nothing left behind."


def main():
    check("Loads without errors", _install)
    check("Does not crash on the empty scene", _empty_scene)
__OPERATOR_CHECK__
    check("Render is written", _render)
    check("Unloads clean", _unload)
    if not all(_results):
        sys.exit(1)


try:
    main()
except SystemExit:
    raise
except Exception:
    # Something failed outside the checks: the traceback goes to
    # the log, and the failure is reported, never silent.
    traceback.print_exc()
    report(
        "Test script", False,
        "the test script failed outside its checks.",
    )
    sys.exit(1)
'''
