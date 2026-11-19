"""Surprise — randomize a material for inspiration (PO8).

One button morphs the selected object into a fresh material: a random
family, style, and layout, plus parameters within sane ranges. The
pick is seeded, and the seed is stored, so the same seed always
reproduces the same material — deterministic, so tests can prove it.
One press is one undo step.

This file is the pack's entry point (DOSSIER.md §5.1). The Reblend
loader calls ``register(api)`` when the pack is enabled and
``unregister(api)`` when it is disabled; everything registered here
is removed there, in reverse. The loader renders the wheel button
from the manifest's declared contribution and wires the declared
action "surprise.randomize" to the ``randomize`` function below.

The pick itself lives in ``src/shared/pick.py`` — plain Python with
no Reblend dependency — and is imported here by flat name
(``import pick``). The emitter copies it into the pack's ``code/``
folder, and the loader puts ``code/`` on the import path, so the
same import works in the project and in the pack.
"""

import pick

# The Reblend API object handed to register(), kept while the pack is
# enabled and cleared by unregister(). None when the pack is off.
_api = None


def register(api):
    """Enable the pack. Called by the Reblend loader (DOSSIER §5.1).

    ``api`` is the plugin API object (§5.2) — the pack's only way into
    Reblend. The loader wires the declared "surprise.randomize"
    action to the ``randomize`` function below; this function keeps
    the API object so ``randomize`` can reach the selected object.
    """
    global _api
    _api = api


def unregister(api):
    """Disable the pack. Called by the Reblend loader (DOSSIER §5.1).

    Removes everything register() added — in this pack's case, the
    kept API object. The loader removes the wheel button itself.
    """
    global _api
    _api = None


def randomize(api):
    """Run one Surprise: pick a fresh material and apply it.

    Called by the loader when the Surprise wheel button is pressed.
    Reads the selected object and the material catalog through the
    API, picks with a fresh seed, and applies the result as one undo
    step. The seed is stored on the object, so the same Surprise can
    be reproduced later.

    NOTE: the API calls below are the shape the loader's §5.2 spec
    describes (read the selected object, apply a material by
    family/style/layout, set knob values, one undo step). They are
    filled in when the loader's exact calls are frozen in Phase 1;
    until then this function shows the flow and the pick, and the
    apply step is marked where it goes.
    """
    # TODO (Phase 1): object = api.scene.selected_object()
    # TODO (Phase 1): catalog = api.materials.catalog()
    # TODO (Phase 1): seed = <a fresh seed, stored on the object>
    # pick_result = pick.pick_material(seed, catalog)
    # TODO (Phase 1): apply pick_result as one undo step via the API.
    raise NotImplementedError(
        "Surprise needs the Reblend loader's plugin API (Phase 1) "
        "before it can apply a material. The pick itself, "
        "pick.pick_material and pick.pick_parameters, is finished "
        "and tested."
    )
