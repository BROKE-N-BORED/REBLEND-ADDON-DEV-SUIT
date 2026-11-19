"""Seeded picks for Surprise (PO8) — target-free logic.

``pick_material`` and ``pick_parameters`` are plain Python with no
Reblend or Blender dependency, so they can be tested on their own —
and so the same pick logic serves both twins. They live in
``src/shared/`` (DOSSIER.md §5.4). The Reblend entry point imports
them by flat name (``import pick``); the Blender entry point imports
them relatively (``from . import pick``), because Blender loads the
add-on as a package. Each emitter copies this file beside its own
entry point.
"""

import random


def pick_material(seed, catalog):
    """Pick a material from ``catalog``, deterministically.

    ``catalog`` is a dict of families, each with styles, each with
    layouts:

        {"families": [{"name": "Wood",
                       "styles": [{"name": "White Oak",
                                   "layouts": ["Herringbone", "Plank"]}]}]}

    Returns {"family": ..., "style": ..., "layout": ..., "seed": seed}.
    The same seed always returns the same pick; different seeds
    spread across the catalog. Raises ValueError when the catalog
    has no family, style, or layout to pick from.
    """
    families = catalog.get("families") if isinstance(catalog, dict) else None
    if not families:
        raise ValueError("The material catalog has no families to pick from.")
    rng = random.Random(seed)
    family = rng.choice(families)
    styles = family.get("styles") or []
    if not styles:
        raise ValueError(f"The family '{family['name']}' has no styles to pick from.")
    style = rng.choice(styles)
    layouts = style.get("layouts") or []
    if not layouts:
        raise ValueError(
            f"The style '{style['name']}' has no layouts to pick from."
        )
    layout = rng.choice(layouts)
    return {
        "family": family["name"],
        "style": style["name"],
        "layout": layout,
        "seed": seed,
    }


def pick_parameters(seed, knobs):
    """Pick parameter values within their sane ranges, deterministically.

    ``knobs`` maps a knob name to its (low, high) range, for example
    {"roughness": (0.0, 1.0), "scale": (0.5, 2.0)}. Returns a dict of
    name to value. The same seed always returns the same values.
    """
    rng = random.Random(seed)
    return {name: rng.uniform(low, high) for name, (low, high) in knobs.items()}
