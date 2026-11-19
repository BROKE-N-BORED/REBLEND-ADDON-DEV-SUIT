"""Write a pack's manifest.json (Phase 1 suite side).

The manifest writer is the suite side of dossier §12 Phase 1: it turns
a project into the manifest dict the Reblend emitter packs (DOSSIER.md
§5.1, the pack format v1). The validator in manifest.py is the other
half — this module builds the manifest, the validator checks it, and
the writer runs the real validator over its own output before handing
it back. A manifest that leaves here has already passed the same
checks Reblend's loader will run.

What comes from where:

* ``id``, ``name``, ``version``, ``description``, ``author`` — from
  the project (``project.json``). The project's version flows into the
  pack, so the Reblend pack and the Blender add-on for one project
  always share a version number (§5.4).
* ``contributions`` — passed in by the caller. The pack window owns
  them later; the writer only shapes them. Every known kind is listed,
  even when empty, so the manifest matches the §5.1 example shape.
* ``entry`` — the entry file name, ``addon.py`` by default. It must
  sit beside the manifest at the pack root (§5.1).
* ``reblend`` — the Reblend versions the pack works with, written as
  text. This lives in the manifest, NOT in the project: one source of
  truth, and the pack window lets Joshua change it per pack later.
  The default is ">=0.2" because 0.2 is the Reblend on his PC today
  (the latest inspected build is 0.2.0), so a pack built now works
  with the Reblend it will actually run in. A pack that needs a newer
  Reblend says so by passing a different range — the writer never
  guesses a range from anything else.
* ``icon`` — included only when the project names one (``project.icon``).
  An empty icon field is left out rather than written blank.
* ``permissions`` — always the v1 values, ``files: project-only`` and
  ``network: false``. They are the only values v1 allows, so there is
  nothing for the caller to choose (§5.1).

Every function here returns a plain result and never raises on a bad
project. When the project cannot produce a valid manifest — a bad id,
a version that is not three numbers, a contribution kind the format
does not know — the error comes back as a plain-words sentence, never
as a crash or a stack trace.
"""

from __future__ import annotations

from devsuite.packing.manifest import (
    KNOWN_CONTRIBUTION_KINDS,
    validate_manifest_data,
)

#: The default Reblend range for a new pack. See the module docstring
#: for why ">=0.2" is the default — it is the Reblend on his PC today.
DEFAULT_REBLEND = ">=0.2"


def build_manifest(project, contributions, entry="addon.py",
                   reblend=DEFAULT_REBLEND) -> tuple[dict | None, str | None]:
    """Build the manifest dict for ``project``.

    ``contributions`` maps a contribution kind (wheel, menu, inspector,
    brushes, materials, simulations) to a list of entries, as in §5.1.
    Missing kinds are filled in as empty lists. Pass ``None`` for a
    pack that declares nothing yet.

    Returns ``(manifest, error)``: ``manifest`` is the dict, ready to
    be written as manifest.json, or None when the project cannot
    produce a valid manifest; ``error`` is None on success, or a
    plain-words sentence saying what is wrong. The manifest is checked
    with the real validator before it is returned, so a manifest that
    comes back here has already passed every §5.1 check.
    """
    manifest = {
        "id": getattr(project, "id", ""),
        "name": getattr(project, "name", ""),
        "version": getattr(project, "version", ""),
        "description": getattr(project, "description", ""),
        "author": getattr(project, "author", ""),
        "reblend": reblend,
        "entry": entry,
        "contributions": _normalize_contributions(contributions),
        "permissions": {
            "files": "project-only",
            "network": False,
        },
    }
    icon = getattr(project, "icon", "")
    if isinstance(icon, str) and icon:
        manifest["icon"] = icon

    ok, errors = validate_manifest_data(manifest)
    if not ok:
        return None, " ".join(errors)
    return manifest, None


def _normalize_contributions(contributions):
    """Shape contributions into the §5.1 form: every known kind listed.

    ``None`` becomes every kind empty. A dict passes through with
    missing kinds filled in as empty lists. Anything else is returned
    unchanged, so the validator — not this function — reports it in
    plain words.
    """
    if contributions is None:
        return {kind: [] for kind in KNOWN_CONTRIBUTION_KINDS}
    if not isinstance(contributions, dict):
        return contributions
    normalized = {kind: [] for kind in KNOWN_CONTRIBUTION_KINDS}
    normalized.update(contributions)
    return normalized
