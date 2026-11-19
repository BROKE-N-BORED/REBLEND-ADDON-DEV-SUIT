"""Tests for devsuite.packing.blender, the Blender emitter (Phase 4).

The emitter turns a project into a standard Blender add-on zip: the
extension package by default (``__init__.py`` +
``blender_manifest.toml`` at the zip root, Blender 4.2 and later),
the legacy ``bl_info`` form when asked. These tests check that the
zip holds the add-on's tree and nothing else, that the generated
manifest matches the project and Blender's rules (parsed back with
tomllib — the real TOML reader), that the build record is correct
and honest about an unproven add-on, that a planted secret refuses
the build naming the file (never the value), and that a missing
entry point, a bad version, or a missing ``bl_info`` fails in plain
words. The round-trip tests build both layouts from the Surprise
template and prove the template's entry point loads under plain
Python.

Blender itself is not in this sandbox, so nothing here runs Blender:
the checks are structural (zip contents, manifest fields, a plain
Python import). A real install test in Blender waits for his PC
(Phase 5).
"""

import importlib.util
import json
import shutil
import sys
import tempfile
import tomllib
import unittest
import zipfile
from datetime import date
from pathlib import Path

from devsuite.packing.blender import (
    build_blender_addon,
    build_blender_manifest,
)
from devsuite.projects.project import create_project
from devsuite.templates import template_dir

INIT_PY = '''"""A small test add-on entry point."""

bl_info = {
    "name": "Surprise",
    "author": "Joshua Lofland",
    "version": (1, 0, 0),
    "blender": (2, 80, 0),
    "location": "View3D > Object > Surprise",
    "description": "Randomize a material for inspiration.",
    "category": "Object",
}


def register():
    pass


def unregister():
    pass
'''

TEMPLATE = template_dir("surprise")


def make_project(tmp, **overrides):
    """Create a real project in ``tmp`` with an entry point, and return it."""
    fields = {
        "name": "Surprise",
        "description": "Randomize a material for inspiration.",
        "targets": ["blender"],
        "version": "1.0.0",
        "author": "Joshua Lofland",
    }
    fields.update(overrides)
    project, error = create_project(Path(tmp) / "surprise", **fields)
    assert error is None, error
    entry = project.root / "src" / "blender" / "__init__.py"
    entry.parent.mkdir(parents=True, exist_ok=True)
    entry.write_text(INIT_PY, encoding="utf-8")
    return project


def zip_names(zip_path):
    with zipfile.ZipFile(zip_path) as zf:
        return sorted(zf.namelist())


def extract_zip(zip_path, dest):
    with zipfile.ZipFile(zip_path) as zf:
        zf.extractall(dest)
    return Path(dest)


def read_manifest(zip_path):
    """The parsed blender_manifest.toml from inside ``zip_path``."""
    with zipfile.ZipFile(zip_path) as zf:
        text = zf.read("blender_manifest.toml").decode("utf-8")
    return tomllib.loads(text)


class TestBlenderManifest(unittest.TestCase):
    def test_manifest_fields_match_the_project(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = make_project(tmp)
            text, error = build_blender_manifest(project)
            self.assertIsNone(error)
            data = tomllib.loads(text)
            self.assertEqual(data["schema_version"], "1.0.0")
            self.assertEqual(data["id"], "surprise")
            self.assertEqual(data["version"], "1.0.0")
            self.assertEqual(data["name"], "Surprise")
            self.assertEqual(
                data["tagline"], "Randomize a material for inspiration"
            )
            self.assertEqual(data["maintainer"], "Joshua Lofland")
            self.assertEqual(data["type"], "add-on")
            self.assertEqual(data["blender_version_min"], "4.2.0")
            self.assertEqual(data["license"], ["SPDX:GPL-3.0-or-later"])
            self.assertNotIn("website", data)

    def test_project_id_dashes_become_underscores(self):
        # A Blender id is a Python package name; a dash is not valid
        # in one. The project id keeps its dashes everywhere else.
        with tempfile.TemporaryDirectory() as tmp:
            project = make_project(tmp, name="Surprise Pack")
            self.assertEqual(project.id, "surprise-pack")
            text, error = build_blender_manifest(project)
            self.assertIsNone(error)
            data = tomllib.loads(text)
            self.assertEqual(data["id"], "surprise_pack")

    def test_long_description_is_cut_to_the_tagline_limit(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = make_project(
                tmp,
                description="Randomize a material for inspiration, "
                            "one button, one undo step, every time.",
            )
            text, error = build_blender_manifest(project)
            self.assertIsNone(error)
            data = tomllib.loads(text)
            self.assertLessEqual(len(data["tagline"]), 64)
            self.assertNotIn(data["tagline"][-1], ".,;:!?")
            # Cut at a word boundary, not mid-word.
            self.assertNotIn(" ", data["tagline"][-1])
            self.assertTrue(data["tagline"][-1].isalpha())

    def test_tagline_never_ends_with_punctuation(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = make_project(tmp, description="A fine add-on!")
            text, error = build_blender_manifest(project)
            self.assertIsNone(error)
            data = tomllib.loads(text)
            self.assertEqual(data["tagline"], "A fine add-on")

    def test_empty_description_falls_back_to_the_name(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = make_project(tmp, description="")
            text, error = build_blender_manifest(project)
            self.assertIsNone(error)
            data = tomllib.loads(text)
            self.assertEqual(data["tagline"], "Surprise")

    def test_website_is_included_when_given(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = make_project(tmp)
            text, error = build_blender_manifest(
                project, website="https://example.org/surprise"
            )
            self.assertIsNone(error)
            data = tomllib.loads(text)
            self.assertEqual(
                data["website"], "https://example.org/surprise"
            )

    def test_license_override_is_used_with_the_spdx_prefix(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = make_project(tmp)
            text, error = build_blender_manifest(
                project, license="MIT"
            )
            self.assertIsNone(error)
            data = tomllib.loads(text)
            self.assertEqual(data["license"], ["SPDX:MIT"])
            text, error = build_blender_manifest(
                project, license="SPDX:Apache-2.0"
            )
            self.assertIsNone(error)
            data = tomllib.loads(text)
            self.assertEqual(data["license"], ["SPDX:Apache-2.0"])

    def test_bad_version_fails_plainly(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = make_project(tmp, version="1.0")
            text, error = build_blender_manifest(project)
            self.assertIsNone(text)
            self.assertIn("1.2.3", error)

    def test_blank_author_fails_plainly(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = make_project(tmp, author="")
            text, error = build_blender_manifest(project)
            self.assertIsNone(text)
            self.assertIn("maintainer", error.lower())


class TestBlenderEmitterProducesAddons(unittest.TestCase):
    def test_build_writes_an_extension_with_the_project_tree(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = make_project(tmp)
            (project.root / "src" / "blender" / "panel.py").write_text(
                "# panel module\n", encoding="utf-8"
            )
            shared = project.root / "src" / "shared"
            shared.mkdir(parents=True, exist_ok=True)
            (shared / "pick.py").write_text(
                "# shared logic\n", encoding="utf-8"
            )
            (project.assets_dir / "preset.json").write_text(
                "{}\n", encoding="utf-8"
            )
            (project.root / "README.md").write_text(
                "# Surprise\n", encoding="utf-8"
            )
            (project.root / "icon.png").write_bytes(b"\x89PNG fake icon")
            out_dir = Path(tmp) / "out"
            zip_path, warnings, error = build_blender_addon(
                project, out_dir
            )
            self.assertIsNone(error)
            self.assertEqual(
                zip_path, out_dir / "surprise-1.0.0-blender.zip"
            )
            self.assertTrue(zip_path.is_file())
            self.assertEqual(
                zip_names(zip_path),
                ["README.md", "__init__.py", "assets/preset.json",
                 "blender_manifest.toml", "icon.png", "panel.py",
                 "pick.py"],
            )
            data = read_manifest(zip_path)
            self.assertEqual(data["id"], "surprise")
            self.assertEqual(data["version"], "1.0.0")
            self.assertEqual(data["name"], "Surprise")

    def test_project_working_files_are_never_packed(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = make_project(tmp)
            (project.root / "idea.md").write_text("an idea\n")
            (project.root / "chat.jsonl").write_text("{}\n")
            (project.tests_dir / "test_x.py").write_text("# check\n")
            (project.renders_dir / "shot.png").write_bytes(b"fake")
            # The Reblend side of the project is not Blender code.
            reblend = project.root / "src" / "reblend"
            reblend.mkdir(parents=True, exist_ok=True)
            (reblend / "addon.py").write_text("# reblend entry\n")
            out_dir = Path(tmp) / "out"
            zip_path, _, error = build_blender_addon(project, out_dir)
            self.assertIsNone(error)
            names = zip_names(zip_path)
            for forbidden in ("project.json", "idea.md", "chat.jsonl",
                              "tests/test_x.py", "renders/shot.png",
                              "addon.py"):
                self.assertNotIn(forbidden, names)

    def test_pycache_is_never_packed(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = make_project(tmp)
            cache = project.root / "src" / "shared" / "__pycache__"
            cache.mkdir(parents=True)
            (cache / "pick.pyc").write_bytes(b"compiled")
            out_dir = Path(tmp) / "out"
            zip_path, _, error = build_blender_addon(project, out_dir)
            self.assertIsNone(error)
            self.assertNotIn("__pycache__/pick.pyc",
                             zip_names(zip_path))

    def test_legacy_build_holds_the_addon_folder_and_no_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = make_project(tmp, name="Surprise Pack")
            shared = project.root / "src" / "shared"
            shared.mkdir(parents=True, exist_ok=True)
            (shared / "pick.py").write_text(
                "# shared logic\n", encoding="utf-8"
            )
            out_dir = Path(tmp) / "out"
            zip_path, _, error = build_blender_addon(
                project, out_dir, legacy=True
            )
            self.assertIsNone(error)
            self.assertEqual(
                zip_path, out_dir / "surprise-pack-1.0.0-blender.zip"
            )
            self.assertEqual(
                zip_names(zip_path),
                ["surprise_pack/__init__.py", "surprise_pack/pick.py"],
            )


class TestBuildRecord(unittest.TestCase):
    def test_build_json_records_the_build(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = make_project(tmp)
            out_dir = Path(tmp) / "out"
            zip_path, _, error = build_blender_addon(
                project, out_dir, test_run_id="run-2026-11-17-001"
            )
            self.assertIsNone(error)
            record = json.loads(
                (out_dir / "build.json").read_text(encoding="utf-8")
            )
            self.assertEqual(record["project_id"], "surprise")
            self.assertEqual(record["project_version"], "1.0.0")
            self.assertEqual(record["target"], "blender")
            self.assertEqual(record["pack"], "surprise-1.0.0-blender.zip")
            self.assertEqual(record["test_run_id"], "run-2026-11-17-001")
            self.assertTrue(record["proven"])
            self.assertEqual(record["built"], date.today().isoformat())

    def test_unproven_addon_is_recorded_plainly_and_warned(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = make_project(tmp)
            out_dir = Path(tmp) / "out"
            zip_path, warnings, error = build_blender_addon(
                project, out_dir
            )
            # It builds anyway: unproven is a warning, not a refusal.
            self.assertIsNone(error)
            self.assertTrue(zip_path.is_file())
            record = json.loads(
                (out_dir / "build.json").read_text(encoding="utf-8")
            )
            self.assertIsNone(record["test_run_id"])
            self.assertFalse(record["proven"])
            self.assertEqual(len(warnings), 1)
            self.assertIn("unproven", warnings[0].lower())

    def test_proven_addon_carries_no_unproven_warning(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = make_project(tmp)
            out_dir = Path(tmp) / "out"
            _, warnings, error = build_blender_addon(
                project, out_dir, test_run_id="run-1"
            )
            self.assertIsNone(error)
            self.assertEqual(warnings, [])


class TestBlenderRefusals(unittest.TestCase):
    def test_planted_secret_refuses_the_build_and_names_the_file(self):
        secret_value = "sk-live-0123456789abcdef0123456789"
        with tempfile.TemporaryDirectory() as tmp:
            project = make_project(tmp)
            shared = project.root / "src" / "shared"
            shared.mkdir(parents=True, exist_ok=True)
            (shared / "keys.py").write_text(
                f'api_key = "{secret_value}"\n', encoding="utf-8"
            )
            out_dir = Path(tmp) / "out"
            zip_path, _, error = build_blender_addon(project, out_dir)
            self.assertIsNone(zip_path)
            self.assertIn("keys.py", error)
            self.assertIn("secret", error.lower())
            # The value itself is never quoted back.
            self.assertNotIn(secret_value, error)
            self.assertFalse((out_dir / "surprise-1.0.0-blender.zip").exists())
            self.assertFalse((out_dir / "build.json").exists())

    def test_secret_in_the_entry_point_refuses_too(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = make_project(tmp)
            (project.root / "src" / "blender" / "__init__.py").write_text(
                INIT_PY + '\npassword = "hunter2-real-password"\n',
                encoding="utf-8",
            )
            out_dir = Path(tmp) / "out"
            zip_path, _, error = build_blender_addon(project, out_dir)
            self.assertIsNone(zip_path)
            self.assertIn("__init__.py", error)
            self.assertNotIn("hunter2", error)

    def test_missing_entry_point_fails_plainly(self):
        with tempfile.TemporaryDirectory() as tmp:
            project, error = create_project(
                Path(tmp) / "empty", name="Empty", targets=["blender"]
            )
            assert error is None, error
            zip_path, _, error = build_blender_addon(
                project, Path(tmp) / "out"
            )
            self.assertIsNone(zip_path)
            self.assertIn("__init__.py", error)

    def test_project_that_does_not_target_blender_fails_plainly(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = make_project(tmp, targets=["reblend"])
            zip_path, _, error = build_blender_addon(
                project, Path(tmp) / "out"
            )
            self.assertIsNone(zip_path)
            self.assertIn("Blender", error)

    def test_project_with_a_bad_version_fails_plainly(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = make_project(tmp, version="1.0")
            zip_path, _, error = build_blender_addon(
                project, Path(tmp) / "out"
            )
            self.assertIsNone(zip_path)
            self.assertIn("1.2.3", error)

    def test_module_name_collision_fails_plainly(self):
        # The same module name in src/blender/ and src/shared/ would
        # land on one name in the add-on — a refusal, not a silent
        # overwrite.
        with tempfile.TemporaryDirectory() as tmp:
            project = make_project(tmp)
            (project.root / "src" / "blender" / "util.py").write_text(
                "# blender side\n", encoding="utf-8"
            )
            shared = project.root / "src" / "shared"
            shared.mkdir(parents=True, exist_ok=True)
            (shared / "util.py").write_text(
                "# shared side\n", encoding="utf-8"
            )
            out_dir = Path(tmp) / "out"
            zip_path, _, error = build_blender_addon(project, out_dir)
            self.assertIsNone(zip_path)
            self.assertIn("util.py", error)
            self.assertFalse((out_dir / "surprise-1.0.0-blender.zip").exists())

    def test_root_file_collision_with_a_module_fails_plainly(self):
        # A README.md in src/shared/ and one at the project root
        # would land on one name — a refusal, not a silent overwrite.
        with tempfile.TemporaryDirectory() as tmp:
            project = make_project(tmp)
            shared = project.root / "src" / "shared"
            shared.mkdir(parents=True, exist_ok=True)
            (shared / "README.md").write_text(
                "# shared readme\n", encoding="utf-8"
            )
            (project.root / "README.md").write_text(
                "# project readme\n", encoding="utf-8"
            )
            out_dir = Path(tmp) / "out"
            zip_path, _, error = build_blender_addon(project, out_dir)
            self.assertIsNone(zip_path)
            self.assertIn("README.md", error)
            self.assertFalse((out_dir / "surprise-1.0.0-blender.zip").exists())

    def test_a_project_manifest_cannot_overwrite_the_generated_one(self):
        # A blender_manifest.toml sitting in src/blender/ must not
        # silently replace the manifest the emitter writes.
        with tempfile.TemporaryDirectory() as tmp:
            project = make_project(tmp)
            (project.root / "src" / "blender"
             / "blender_manifest.toml").write_text(
                'id = "stale"\n', encoding="utf-8"
            )
            out_dir = Path(tmp) / "out"
            zip_path, _, error = build_blender_addon(project, out_dir)
            self.assertIsNone(zip_path)
            self.assertIn("blender_manifest.toml", error)
            self.assertFalse((out_dir / "surprise-1.0.0-blender.zip").exists())

    def test_legacy_without_bl_info_fails_plainly(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = make_project(tmp)
            (project.root / "src" / "blender" / "__init__.py").write_text(
                '"""An entry point with no bl_info."""\n\n\n'
                "def register():\n    pass\n\n\n"
                "def unregister():\n    pass\n",
                encoding="utf-8",
            )
            out_dir = Path(tmp) / "out"
            zip_path, _, error = build_blender_addon(
                project, out_dir, legacy=True
            )
            self.assertIsNone(zip_path)
            self.assertIn("bl_info", error)
            self.assertFalse((out_dir / "surprise-1.0.0-blender.zip").exists())
            # The extension form does not need bl_info: it builds.
            zip_path, _, error = build_blender_addon(
                project, Path(tmp) / "out2"
            )
            self.assertIsNone(error)
            self.assertTrue(zip_path.is_file())

    def test_legacy_with_broken_entry_point_fails_plainly(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = make_project(tmp)
            (project.root / "src" / "blender" / "__init__.py").write_text(
                "def register(:\n", encoding="utf-8"
            )
            zip_path, _, error = build_blender_addon(
                project, Path(tmp) / "out", legacy=True
            )
            self.assertIsNone(zip_path)
            self.assertIn("__init__.py", error)

    def test_broken_project_never_crashes_the_builder(self):
        from devsuite.projects.project import Project

        broken = Project(root=Path("/nonexistent"), name="Broken",
                         targets=["blender"], created="2026-11-17")
        zip_path, _, error = build_blender_addon(broken, "/nonexistent/out")
        self.assertIsNone(zip_path)
        self.assertIsInstance(error, str)
        self.assertTrue(error)


def load_template_entry_as_package(tmp):
    """Load the template's src/blender/__init__.py as a package, the
    way Blender loads it: pick.py beside it, imported relatively.

    Copies the template's blender + shared trees into a temp package
    folder and imports it with importlib, so ``from . import pick``
    resolves. Returns the loaded module.
    """
    pkg_dir = Path(tmp) / "surprise"
    pkg_dir.mkdir()
    shutil.copytree(
        TEMPLATE / "src" / "blender", pkg_dir, dirs_exist_ok=True
    )
    shutil.copytree(
        TEMPLATE / "src" / "shared", pkg_dir, dirs_exist_ok=True
    )
    spec = importlib.util.spec_from_file_location(
        "surprise_blender",
        pkg_dir / "__init__.py",
        submodule_search_locations=[str(pkg_dir)],
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules["surprise_blender"] = module
    try:
        spec.loader.exec_module(module)
    finally:
        del sys.modules["surprise_blender"]
    return module


class TestSurpriseTemplateRoundTrip(unittest.TestCase):
    def _seed_project(self, tmp):
        project, error = create_project(
            Path(tmp) / "surprise",
            name="Surprise",
            description="Randomize a material for inspiration. "
                        "One button, one undo step.",
            targets=["blender"],
            version="1.0.0",
            author="Joshua Lofland",
        )
        assert error is None, error
        # Copy the template into the project, as the suite does when
        # a project starts from a template.
        shutil.copytree(
            TEMPLATE / "src", project.root / "src", dirs_exist_ok=True
        )
        shutil.copy2(TEMPLATE / "README.md", project.root / "README.md")
        return project

    def test_build_an_extension_from_the_surprise_template(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = self._seed_project(tmp)
            out_dir = Path(tmp) / "out"
            zip_path, warnings, error = build_blender_addon(
                project, out_dir
            )
            self.assertIsNone(error, error)
            self.assertTrue(zip_path.is_file())
            self.assertEqual(zip_path.name, "surprise-1.0.0-blender.zip")
            self.assertEqual(
                zip_names(zip_path),
                ["README.md", "__init__.py", "blender_manifest.toml",
                 "pick.py"],
            )
            data = read_manifest(zip_path)
            self.assertEqual(data["id"], "surprise")
            self.assertEqual(data["version"], "1.0.0")
            self.assertEqual(data["name"], "Surprise")
            self.assertEqual(data["type"], "add-on")
            self.assertEqual(data["blender_version_min"], "4.2.0")
            self.assertEqual(data["license"], ["SPDX:GPL-3.0-or-later"])
            # No test run proved it yet, so the record says so.
            record = json.loads(
                (out_dir / "build.json").read_text(encoding="utf-8")
            )
            self.assertFalse(record["proven"])
            self.assertTrue(any("unproven" in w.lower() for w in warnings))

    def test_build_a_legacy_addon_from_the_surprise_template(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = self._seed_project(tmp)
            out_dir = Path(tmp) / "out"
            zip_path, _, error = build_blender_addon(
                project, out_dir, legacy=True
            )
            self.assertIsNone(error, error)
            self.assertEqual(
                zip_names(zip_path),
                ["surprise/README.md", "surprise/__init__.py",
                 "surprise/pick.py"],
            )

    def test_template_entry_point_loads_under_plain_python(self):
        with tempfile.TemporaryDirectory() as tmp:
            module = load_template_entry_as_package(tmp)
            self.assertEqual(module.bl_info["name"], "Surprise")
            self.assertEqual(module.bl_info["version"], (1, 0, 0))
            self.assertTrue(callable(module.register))
            self.assertTrue(callable(module.unregister))
            operator = module.SurpriseOperator
            self.assertEqual(operator.bl_idname, "surprise.randomize")
            self.assertEqual(operator.bl_label, "Surprise")
            self.assertEqual(operator.bl_options, {"REGISTER", "UNDO"})
            # The relative import resolved: the shared pick is there.
            self.assertTrue(callable(module.pick.pick_material))
            # Applying the pick waits on Phase 5 — plainly so.
            with self.assertRaises(NotImplementedError) as caught:
                operator().execute(None)
            self.assertIn("Phase 5", str(caught.exception))
            # Registering needs real Blender, and says so plainly.
            with self.assertRaises(RuntimeError) as caught:
                module.register()
            self.assertIn("Blender", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
