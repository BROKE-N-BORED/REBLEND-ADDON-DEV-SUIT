"""Surprise — randomize a material for inspiration (PO8, Blender twin).

The Blender mirror of the Reblend Surprise pack (D3): one operator
that randomizes the selected object's material for inspiration — a
random family, style, and layout, plus parameters within sane ranges.
The pick is seeded, and the seed is stored, so the same seed always
reproduces the same material. One press is one undo step.

This file is the add-on's entry point (DOSSIER.md §5.3). Blender
calls ``register()`` when the add-on is enabled and ``unregister()``
when it is disabled; the classes in the ``classes`` tuple are
registered in order and unregistered in reverse. The ``bl_info``
dict below is the legacy form (pre-4.2 Blender); Blender 4.2 and
later read the manifest instead, and the emitter writes that.

The pick itself lives in ``src/shared/pick.py`` — plain Python with
no Blender dependency — and is imported here RELATIVELY
(``from . import pick``). Blender loads the add-on as a package, so
the flat ``import pick`` that works in Reblend does not work here;
the emitter copies ``pick.py`` beside this file in the add-on, so
the relative import resolves in the installed add-on and in the
project alike.

``bpy`` is imported under a guard, so this file still loads under
plain Python (the suite's tests check it without Blender — Blender
is not in the sandbox). Without ``bpy`` the operator class falls
back to a plain class and ``register()`` says so plainly; inside
Blender it is a real ``bpy.types.Operator``.
"""

try:
    import bpy
except ImportError:
    # Plain Python, no Blender here (the suite's tests, the sandbox).
    bpy = None

from . import pick

bl_info = {
    "name": "Surprise",
    "author": "Joshua Lofland",
    "version": (1, 0, 0),
    "blender": (2, 80, 0),
    "location": "View3D > Object > Surprise",
    "description": "Randomize a material for inspiration. "
                   "One button, one undo step.",
    "category": "Object",
}

# The operator's base class: the real Blender operator inside
# Blender, a plain class anywhere else (see the module docstring).
_OperatorBase = bpy.types.Operator if bpy is not None else object


class SurpriseOperator(_OperatorBase):
    """Randomize the selected object's material (PO8)."""

    bl_idname = "surprise.randomize"
    bl_label = "Surprise"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        """Run one Surprise: pick a fresh material and apply it.

        Called when the Surprise operator runs. Reads the selected
        object and the material catalog through Blender, picks with
        a fresh seed, and applies the result as one undo step. The
        seed is stored on the object, so the same Surprise can be
        reproduced later.

        NOTE: applying the pick through Blender's material API is
        Phase 5 work. Until then this function shows where the
        apply step goes, and the pick itself — pick.pick_material
        and pick.pick_parameters — is finished and tested.
        """
        # TODO (Phase 5): object = context.active_object
        # TODO (Phase 5): catalog = <the material catalog>
        # TODO (Phase 5): seed = <a fresh seed, stored on the object>
        # pick_result = pick.pick_material(seed, catalog)
        # TODO (Phase 5): apply pick_result as one undo step.
        raise NotImplementedError(
            "Surprise needs the Blender material work (Phase 5) "
            "before it can apply a material. The pick itself, "
            "pick.pick_material and pick.pick_parameters, is "
            "finished and tested."
        )


classes = (SurpriseOperator,)


def register():
    """Enable the add-on. Called by Blender (DOSSIER §5.3).

    Registers the operator class. Needs Blender: under plain Python
    there is nothing to register into, and this says so plainly.
    """
    if bpy is None:
        raise RuntimeError(
            "Surprise needs Blender to register. This file loads "
            "without Blender only so it can be checked."
        )
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    """Disable the add-on. Called by Blender (DOSSIER §5.3).

    Unregisters everything register() added, in reverse order.
    """
    if bpy is None:
        raise RuntimeError(
            "Surprise needs Blender to unregister. This file loads "
            "without Blender only so it can be checked."
        )
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
