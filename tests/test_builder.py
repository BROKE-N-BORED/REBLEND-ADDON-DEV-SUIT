"""Tests for devsuite.packing.builder, the Reblend emitter (Phase 4, pulled forward).

The builder turns a project into a .rblpack zip and the build.json
beside it (DOSSIER.md §5.1 and §9.4). These tests check that the zip
holds the project's pack tree and nothing else, that the manifest
inside the zip passes the suite's own validator, that the build record
is correct and honest about an unproven pack, that a planted secret
refuses the build naming the file (never the value), and that a
missing entry point fails in plain words. The round-trip test builds a
pack from the Surprise template and proves the manifest inside the zip.
"""

import json
import shutil
import tempfile
import unittest
import zipfile
from datetime import date
from pathlib import Path

from devsuite.packing.builder import build_pack
from devsuite.packing.manifest import validate_manifest
from devsuite.projects.project import create_project
from devsuite.templates import template_dir

ADDON_PY = '''"""A small test pack entry point."""


def register(api):
    pass


def unregister(api):
    pass
'''

TEMPLATE = template_dir("surprise")


def make_project(tmp, **overrides):
    """Create a real project in ``tmp`` with an entry point, and return it."""
    fields = {
        "name": "Surprise",
        "description": "Randomize a material for inspiration.",
        "targets": ["reblend"],
        "version": "1.0.0",
        "author": "Joshua Lofland",
    }
    fields.update(overrides)
    project, error = create_project(Path(tmp) / "surprise", **fields)
    assert error is None, error
    entry = project.root / "src" / "reblend" / "addon.py"
    entry.parent.mkdir(parents=True, exist_ok=True)
    entry.write_text(ADDON_PY, encoding="utf-8")
    return project


def zip_names(pack_path):
    with zipfile.ZipFile(pack_path) as zf:
        return sorted(zf.namelist())


def extract_pack(pack_path, dest):
    with zipfile.ZipFile(pack_path) as zf:
        zf.extractall(dest)
    return Path(dest)


class TestBuilderProducesPacks(unittest.TestCase):
    def test_build_writes_a_pack_with_the_project_tree(self):
        # §5.4 project layout maps to the §5.1 pack layout: the entry
        # point from src/reblend/, the modules from src/reblend/ and
        # src/shared/ into code/.
        with tempfile.TemporaryDirectory() as tmp:
            project = make_project(tmp)
            (project.root / "src" / "reblend" / "helpers.py").write_text(
                "# helper module\n", encoding="utf-8"
            )
            shared = project.root / "src" / "shared"
            shared.mkdir(parents=True, exist_ok=True)
            (shared / "util.py").write_text(
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
            pack_path, warnings, error = build_pack(project, out_dir)
            self.assertIsNone(error)
            self.assertEqual(pack_path, out_dir / "surprise-1.0.0.rblpack")
            self.assertTrue(pack_path.is_file())
            self.assertEqual(
                zip_names(pack_path),
                ["README.md", "addon.py", "assets/preset.json",
                 "code/helpers.py", "code/util.py", "icon.png",
                 "manifest.json"],
            )

    def test_project_working_files_are_never_packed(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = make_project(tmp)
            (project.root / "idea.md").write_text("an idea\n")
            (project.root / "chat.jsonl").write_text("{}\n")
            (project.tests_dir / "test_x.py").write_text("# check\n")
            (project.renders_dir / "shot.png").write_bytes(b"fake")
            out_dir = Path(tmp) / "out"
            pack_path, _, error = build_pack(project, out_dir)
            self.assertIsNone(error)
            names = zip_names(pack_path)
            for forbidden in ("project.json", "idea.md", "chat.jsonl",
                              "tests/test_x.py", "renders/shot.png"):
                self.assertNotIn(forbidden, names)

    def test_manifest_inside_the_zip_validates(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = make_project(tmp)
            out_dir = Path(tmp) / "out"
            pack_path, _, error = build_pack(
                project, out_dir,
                contributions={"wheel": [
                    {"label": "Surprise", "action": "surprise.randomize"}
                ]},
            )
            self.assertIsNone(error)
            extracted = extract_pack(pack_path, Path(tmp) / "unzipped")
            ok, errors = validate_manifest(extracted / "manifest.json")
            self.assertTrue(ok, f"manifest in pack should validate: {errors}")
            data = json.loads(
                (extracted / "manifest.json").read_text(encoding="utf-8")
            )
            self.assertEqual(data["id"], "surprise")
            self.assertEqual(data["version"], "1.0.0")
            self.assertEqual(data["reblend"], ">=0.2")
            self.assertEqual(data["entry"], "addon.py")
            self.assertEqual(
                data["contributions"]["wheel"][0]["action"],
                "surprise.randomize",
            )

    def test_a_stale_manifest_in_the_project_never_ships(self):
        # A project may carry a draft manifest.json (the template does).
        # The writer's manifest is the only one that goes in the pack.
        with tempfile.TemporaryDirectory() as tmp:
            project = make_project(tmp)
            (project.root / "manifest.json").write_text(
                json.dumps({"id": "stale", "version": "9.9.9"}),
                encoding="utf-8",
            )
            out_dir = Path(tmp) / "out"
            pack_path, _, error = build_pack(project, out_dir)
            self.assertIsNone(error)
            extracted = extract_pack(pack_path, Path(tmp) / "unzipped")
            data = json.loads(
                (extracted / "manifest.json").read_text(encoding="utf-8")
            )
            self.assertEqual(data["id"], "surprise")
            self.assertEqual(data["version"], "1.0.0")

    def test_pycache_is_never_packed(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = make_project(tmp)
            cache = project.root / "src" / "shared" / "__pycache__"
            cache.mkdir(parents=True)
            (cache / "helpers.pyc").write_bytes(b"compiled")
            out_dir = Path(tmp) / "out"
            pack_path, _, error = build_pack(project, out_dir)
            self.assertIsNone(error)
            self.assertNotIn("code/__pycache__/helpers.pyc",
                             zip_names(pack_path))


class TestBuildRecord(unittest.TestCase):
    def test_build_json_records_the_build(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = make_project(tmp)
            out_dir = Path(tmp) / "out"
            pack_path, _, error = build_pack(
                project, out_dir, test_run_id="run-2026-11-17-001"
            )
            self.assertIsNone(error)
            record = json.loads(
                (out_dir / "build.json").read_text(encoding="utf-8")
            )
            self.assertEqual(record["project_id"], "surprise")
            self.assertEqual(record["project_version"], "1.0.0")
            self.assertEqual(record["target"], "reblend")
            self.assertEqual(record["pack"], "surprise-1.0.0.rblpack")
            self.assertEqual(record["test_run_id"], "run-2026-11-17-001")
            self.assertTrue(record["proven"])
            self.assertEqual(record["built"], date.today().isoformat())

    def test_unproven_pack_is_recorded_plainly_and_warned(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = make_project(tmp)
            out_dir = Path(tmp) / "out"
            pack_path, warnings, error = build_pack(project, out_dir)
            # It builds anyway: unproven is a warning, not a refusal.
            self.assertIsNone(error)
            self.assertTrue(pack_path.is_file())
            record = json.loads(
                (out_dir / "build.json").read_text(encoding="utf-8")
            )
            self.assertIsNone(record["test_run_id"])
            self.assertFalse(record["proven"])
            self.assertEqual(len(warnings), 1)
            self.assertIn("unproven", warnings[0].lower())

    def test_proven_pack_carries_no_unproven_warning(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = make_project(tmp)
            out_dir = Path(tmp) / "out"
            _, warnings, error = build_pack(
                project, out_dir, test_run_id="run-1"
            )
            self.assertIsNone(error)
            self.assertEqual(warnings, [])


class TestBuilderRefusals(unittest.TestCase):
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
            pack_path, _, error = build_pack(project, out_dir)
            self.assertIsNone(pack_path)
            self.assertIn("keys.py", error)
            self.assertIn("secret", error.lower())
            # The value itself is never quoted back.
            self.assertNotIn(secret_value, error)
            self.assertFalse((out_dir / "surprise-1.0.0.rblpack").exists())
            self.assertFalse((out_dir / "build.json").exists())

    def test_secret_in_the_entry_point_refuses_too(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = make_project(tmp)
            (project.root / "src" / "reblend" / "addon.py").write_text(
                ADDON_PY + '\npassword = "hunter2-real-password"\n',
                encoding="utf-8",
            )
            out_dir = Path(tmp) / "out"
            pack_path, _, error = build_pack(project, out_dir)
            self.assertIsNone(pack_path)
            self.assertIn("addon.py", error)
            self.assertNotIn("hunter2", error)

    def test_module_name_collision_fails_plainly(self):
        # The same module name in src/reblend/ and src/shared/ would
        # land on one name in code/ — a refusal, not a silent
        # overwrite.
        with tempfile.TemporaryDirectory() as tmp:
            project = make_project(tmp)
            (project.root / "src" / "reblend" / "util.py").write_text(
                "# reblend side\n", encoding="utf-8"
            )
            shared = project.root / "src" / "shared"
            shared.mkdir(parents=True, exist_ok=True)
            (shared / "util.py").write_text(
                "# shared side\n", encoding="utf-8"
            )
            out_dir = Path(tmp) / "out"
            pack_path, _, error = build_pack(project, out_dir)
            self.assertIsNone(pack_path)
            self.assertIn("code/util.py", error)
            self.assertFalse((out_dir / "surprise-1.0.0.rblpack").exists())

    def test_missing_entry_point_fails_plainly(self):
        with tempfile.TemporaryDirectory() as tmp:
            project, error = create_project(
                Path(tmp) / "empty", name="Empty", targets=["reblend"]
            )
            assert error is None, error
            pack_path, _, error = build_pack(project, Path(tmp) / "out")
            self.assertIsNone(pack_path)
            self.assertIn("addon.py", error)

    def test_project_that_does_not_target_reblend_fails_plainly(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = make_project(tmp, targets=["blender"])
            pack_path, _, error = build_pack(project, Path(tmp) / "out")
            self.assertIsNone(pack_path)
            self.assertIn("Reblend", error)

    def test_project_with_a_bad_version_fails_plainly(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = make_project(tmp, version="1.0")
            pack_path, _, error = build_pack(project, Path(tmp) / "out")
            self.assertIsNone(pack_path)
            self.assertIn("1.2.3", error)

    def test_broken_project_never_crashes_the_builder(self):
        from devsuite.projects.project import Project

        broken = Project(root=Path("/nonexistent"), name="Broken",
                         targets=["reblend"], created="2026-11-17")
        pack_path, _, error = build_pack(broken, "/nonexistent/out")
        self.assertIsNone(pack_path)
        self.assertIsInstance(error, str)
        self.assertTrue(error)


class TestSurpriseTemplateRoundTrip(unittest.TestCase):
    def test_build_a_pack_from_the_surprise_template(self):
        with tempfile.TemporaryDirectory() as tmp:
            project, error = create_project(
                Path(tmp) / "surprise",
                name="Surprise",
                description="Randomize a material for inspiration. "
                            "One button, one undo step.",
                targets=["reblend"],
                version="1.0.0",
                author="Joshua Lofland",
            )
            assert error is None, error
            # Copy the template into the project, as the suite does
            # when a project starts from a template.
            shutil.copytree(TEMPLATE / "src", project.root / "src", dirs_exist_ok=True)
            shutil.copy2(TEMPLATE / "README.md", project.root / "README.md")
            out_dir = Path(tmp) / "out"
            pack_path, warnings, error = build_pack(
                project, out_dir,
                contributions={"wheel": [
                    {"label": "Surprise", "action": "surprise.randomize"}
                ]},
            )
            self.assertIsNone(error, error)
            self.assertTrue(pack_path.is_file())
            self.assertEqual(pack_path.name, "surprise-1.0.0.rblpack")
            self.assertEqual(
                zip_names(pack_path),
                ["README.md", "addon.py", "code/pick.py", "manifest.json"],
            )
            extracted = extract_pack(pack_path, Path(tmp) / "unzipped")
            ok, errors = validate_manifest(extracted / "manifest.json")
            self.assertTrue(ok, f"round-trip manifest should validate: {errors}")
            data = json.loads(
                (extracted / "manifest.json").read_text(encoding="utf-8")
            )
            self.assertEqual(data["id"], "surprise")
            wheel = data["contributions"]["wheel"]
            self.assertEqual(len(wheel), 1)
            self.assertEqual(wheel[0]["label"], "Surprise")
            self.assertEqual(wheel[0]["action"], "surprise.randomize")
            # No test run proved it yet, so the record says so.
            record = json.loads(
                (out_dir / "build.json").read_text(encoding="utf-8")
            )
            self.assertFalse(record["proven"])
            self.assertTrue(any("unproven" in w.lower() for w in warnings))


if __name__ == "__main__":
    unittest.main()
