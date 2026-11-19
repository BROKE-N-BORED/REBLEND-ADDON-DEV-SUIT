"""Tests for the Surprise project template (devsuite/templates/surprise).

The template is the suite's first target, PO8 (DOSSIER.md §11): one
button that randomizes a material, seeded so the same seed always
reproduces the same material. The template follows the §5.4 project
layout: the entry point at ``src/reblend/addon.py``, the target-free
pick logic at ``src/shared/pick.py``. It carries no manifest.json —
the manifest writer builds the manifest from the project (§5.1), and
the §5.1 example manifest is covered by the validator's own tests.

The template's ``randomize`` function itself waits on the Reblend
loader's plugin API (Phase 1), so it is not tested here beyond
existing; the pure pick logic is tested in full.
"""

import importlib.util
import sys
import unittest
from pathlib import Path

from devsuite.templates import template_dir

TEMPLATE = template_dir("surprise")


def load_module(name, path):
    """Import a module from ``path`` under ``name``."""
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_addon():
    """Import the template's addon.py as a module, by path.

    The entry point imports ``pick`` by flat name, the way the pack
    will (DOSSIER.md §5.1): the loader puts the pack's ``code/`` on
    the import path, and the test harness puts ``src/shared/`` on it
    in the project. This test mirrors the project side of that.
    """
    shared = str(TEMPLATE / "src" / "shared")
    sys.path.insert(0, shared)
    try:
        return load_module(
            "surprise_template_addon",
            TEMPLATE / "src" / "reblend" / "addon.py",
        )
    finally:
        sys.path.remove(shared)


def sample_catalog():
    return {
        "families": [
            {"name": "Wood", "styles": [
                {"name": "White Oak", "layouts": ["Herringbone", "Plank"]},
                {"name": "Walnut", "layouts": ["Plank", "Parquet"]},
            ]},
            {"name": "Stone", "styles": [
                {"name": "Marble", "layouts": ["Slab", "Tile"]},
                {"name": "Granite", "layouts": ["Slab", "Block"]},
            ]},
            {"name": "Metal", "styles": [
                {"name": "Brushed Steel", "layouts": ["Sheet", "Mesh"]},
            ]},
        ]
    }


class TestTemplateFiles(unittest.TestCase):
    def test_template_folder_has_its_files(self):
        for filename in ("src/reblend/addon.py", "src/shared/pick.py",
                         "README.md"):
            self.assertTrue((TEMPLATE / filename).is_file(), filename)

    def test_template_carries_no_manifest(self):
        # The manifest writer builds the manifest from the project;
        # a template manifest would be a stale draft waiting to ship.
        self.assertFalse((TEMPLATE / "manifest.json").exists())


class TestTemplateAddon(unittest.TestCase):
    def setUp(self):
        self.addon = load_addon()

    def test_register_and_unregister_exist(self):
        self.assertTrue(callable(self.addon.register))
        self.assertTrue(callable(self.addon.unregister))

    def test_register_and_unregister_round_trip(self):
        api = object()  # The real API object arrives with the loader.
        self.addon.register(api)
        self.assertIs(self.addon._api, api)
        self.addon.unregister(api)
        self.assertIsNone(self.addon._api)

    def test_entry_point_imports_the_shared_pick(self):
        self.assertTrue(callable(self.addon.pick.pick_material))
        self.assertTrue(callable(self.addon.pick.pick_parameters))


class TestTemplatePick(unittest.TestCase):
    def setUp(self):
        self.pick = load_module(
            "surprise_template_pick",
            TEMPLATE / "src" / "shared" / "pick.py",
        )

    def test_same_seed_reproduces_the_same_material(self):
        catalog = sample_catalog()
        first = self.pick.pick_material(42, catalog)
        second = self.pick.pick_material(42, catalog)
        self.assertEqual(first, second)
        self.assertEqual(first["seed"], 42)

    def test_pick_comes_from_the_catalog(self):
        catalog = sample_catalog()
        pick = self.pick.pick_material(7, catalog)
        families = {f["name"] for f in catalog["families"]}
        self.assertIn(pick["family"], families)
        family = next(f for f in catalog["families"] if f["name"] == pick["family"])
        styles = {s["name"] for s in family["styles"]}
        self.assertIn(pick["style"], styles)
        style = next(s for s in family["styles"] if s["name"] == pick["style"])
        self.assertIn(pick["layout"], style["layouts"])

    def test_different_seeds_spread_across_the_catalog(self):
        catalog = sample_catalog()
        picks = {
            (p["family"], p["style"], p["layout"])
            for p in (self.pick.pick_material(seed, catalog) for seed in range(10))
        }
        # Ten seeds over a 12-combination catalog: at least two
        # distinct materials, or the pick is not randomizing at all.
        self.assertGreaterEqual(len(picks), 2)

    def test_same_seed_reproduces_the_same_parameters(self):
        knobs = {"roughness": (0.0, 1.0), "scale": (0.5, 2.0)}
        first = self.pick.pick_parameters(42, knobs)
        second = self.pick.pick_parameters(42, knobs)
        self.assertEqual(first, second)
        self.assertTrue(0.0 <= first["roughness"] <= 1.0)
        self.assertTrue(0.5 <= first["scale"] <= 2.0)

    def test_empty_catalog_fails_plainly(self):
        with self.assertRaises(ValueError) as caught:
            self.pick.pick_material(1, {"families": []})
        self.assertIn("no families", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
