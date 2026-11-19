"""Tests for devsuite.projects.project.

A project is a folder of plain files (DOSSIER.md §9.4): project.json
plus src/, tests/, assets/, renders/ and packs/. These tests check
that a project is created, loaded, and saved correctly, and that every
kind of bad project file fails with a plain-words sentence instead of
a crash.

The shape tested here is §9.4: id, name, description, targets (a
list), version, author, icon, created. Required in the file: name,
targets, created.
"""

import json
import tempfile
import unittest
from pathlib import Path

from devsuite.projects.project import (
    create_project,
    load_project,
    validate_project_data,
)


class ProjectTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)


class TestCreateProject(ProjectTestCase):
    def test_create_builds_the_folder_layout(self):
        project, error = create_project(
            self.base / "surprise", name="Surprise",
            description="Randomize a material.",
        )
        self.assertIsNone(error)
        self.assertEqual(project.name, "Surprise")
        self.assertEqual(project.targets, ["reblend"])
        self.assertEqual(project.version, "0.1.0")
        self.assertEqual(project.id, "surprise")
        for dirname in ("src", "tests", "assets", "renders", "packs"):
            self.assertTrue((self.base / "surprise" / dirname).is_dir())
        self.assertTrue((self.base / "surprise" / "project.json").is_file())

    def test_create_writes_readable_project_json(self):
        project, error = create_project(
            self.base / "surprise", name="Surprise",
            targets=["reblend", "blender"], created="2026-11-17",
        )
        self.assertIsNone(error)
        data = json.loads((self.base / "surprise" / "project.json").read_text())
        self.assertEqual(data["name"], "Surprise")
        self.assertEqual(data["targets"], ["reblend", "blender"])
        self.assertEqual(data["created"], "2026-11-17")

    def test_create_id_comes_from_the_name(self):
        project, error = create_project(self.base / "p", name="Water Splash!")
        self.assertIsNone(error)
        self.assertEqual(project.id, "water-splash")

    def test_create_into_non_empty_folder_fails_plainly(self):
        folder = self.base / "busy"
        folder.mkdir()
        (folder / "something.txt").write_text("already here")
        project, error = create_project(folder, name="Surprise")
        self.assertIsNone(project)
        self.assertIn("already holds files", error)

    def test_create_into_existing_empty_folder_works(self):
        folder = self.base / "empty"
        folder.mkdir()
        project, error = create_project(folder, name="Surprise")
        self.assertIsNone(error)
        self.assertTrue((folder / "project.json").is_file())

    def test_create_where_a_file_sits_fails_plainly(self):
        path = self.base / "afile"
        path.write_text("a file, not a folder")
        project, error = create_project(path, name="Surprise")
        self.assertIsNone(project)
        self.assertIn("already a file", error)

    def test_create_with_bad_target_fails_plainly(self):
        project, error = create_project(
            self.base / "p", name="Surprise", targets=["maya"]
        )
        self.assertIsNone(project)
        self.assertIn("maya", error)
        self.assertFalse((self.base / "p").exists())

    def test_create_with_empty_targets_fails_plainly(self):
        project, error = create_project(
            self.base / "p", name="Surprise", targets=[]
        )
        self.assertIsNone(project)
        self.assertIn("at least one", error)

    def test_create_with_empty_name_fails_plainly(self):
        project, error = create_project(self.base / "p", name="   ")
        self.assertIsNone(project)
        self.assertIn("name", error)


class TestLoadAndSave(ProjectTestCase):
    def test_load_round_trip(self):
        created, error = create_project(
            self.base / "surprise", name="Surprise",
            targets=["reblend", "blender"],
            description="Randomize a material.", created="2026-11-17",
        )
        self.assertIsNone(error)
        loaded, error = load_project(self.base / "surprise")
        self.assertIsNone(error)
        self.assertEqual(loaded.name, created.name)
        self.assertEqual(loaded.targets, created.targets)
        self.assertEqual(loaded.description, created.description)
        self.assertEqual(loaded.created, created.created)
        self.assertEqual(loaded.root, created.root)

    def test_save_updates_the_file(self):
        project, error = create_project(self.base / "p", name="First")
        self.assertIsNone(error)
        project.name = "Second"
        project.description = "Renamed."
        self.assertIsNone(project.save())
        loaded, error = load_project(self.base / "p")
        self.assertIsNone(error)
        self.assertEqual(loaded.name, "Second")
        self.assertEqual(loaded.description, "Renamed.")

    def test_contributions_round_trip(self):
        contributions = {"wheel": [
            {"label": "Surprise", "action": "surprise.randomize"}
        ]}
        project, error = create_project(
            self.base / "c", name="Contrib",
            contributions=contributions,
        )
        self.assertIsNone(error)
        loaded, error = load_project(self.base / "c")
        self.assertIsNone(error)
        self.assertEqual(loaded.contributions, contributions)

    def test_contributions_save_after_edit(self):
        project, error = create_project(self.base / "e", name="Edit")
        self.assertIsNone(error)
        self.assertEqual(project.contributions, {})
        project.contributions = {"wheel": [
            {"label": "Surprise", "action": "surprise.randomize"}
        ]}
        self.assertIsNone(project.save())
        loaded, error = load_project(self.base / "e")
        self.assertIsNone(error)
        self.assertEqual(
            loaded.contributions["wheel"][0]["label"], "Surprise"
        )

    def test_project_without_contributions_loads_empty(self):
        # An older project.json, written before the field existed.
        folder = self.base / "old"
        folder.mkdir()
        (folder / "project.json").write_text(json.dumps({
            "name": "Old", "targets": ["reblend"],
            "created": "2026-11-17",
        }))
        project, error = load_project(folder)
        self.assertIsNone(error)
        self.assertEqual(project.contributions, {})

    def test_contributions_not_a_dict_fails_plainly(self):
        folder = self.base / "bad"
        folder.mkdir()
        (folder / "project.json").write_text(json.dumps({
            "name": "Bad", "targets": ["reblend"],
            "created": "2026-11-17", "contributions": ["wheel"],
        }))
        project, error = load_project(folder)
        self.assertIsNone(project)
        self.assertIn("contributions", error)

    def test_load_missing_folder_fails_plainly(self):
        project, error = load_project(self.base / "no-such-project")
        self.assertIsNone(project)
        self.assertIn("no project.json", error)

    def test_load_folder_without_project_json_fails_plainly(self):
        folder = self.base / "empty"
        folder.mkdir()
        project, error = load_project(folder)
        self.assertIsNone(project)
        self.assertIn("no project.json", error)

    def test_load_bad_json_fails_plainly(self):
        folder = self.base / "broken"
        folder.mkdir()
        (folder / "project.json").write_text('{"name": "Surprise",}')
        project, error = load_project(folder)
        self.assertIsNone(project)
        self.assertIn("mistake", error)
        self.assertIn("line 1", error)

    def test_load_missing_fields_fails_plainly(self):
        folder = self.base / "thin"
        folder.mkdir()
        (folder / "project.json").write_text(json.dumps({"name": "Surprise"}))
        project, error = load_project(folder)
        self.assertIsNone(project)
        self.assertIn("'targets'", error)
        self.assertIn("'created'", error)

    def test_load_unknown_fields_are_ignored(self):
        folder = self.base / "future"
        folder.mkdir()
        (folder / "project.json").write_text(json.dumps({
            "name": "Surprise",
            "targets": ["reblend"],
            "created": "2026-11-17",
            "some_future_field": {"nested": True},
        }))
        project, error = load_project(folder)
        self.assertIsNone(error)
        self.assertEqual(project.name, "Surprise")


class TestValidateProjectData(unittest.TestCase):
    def good_data(self):
        return {
            "name": "Surprise",
            "targets": ["reblend"],
            "created": "2026-11-17",
        }

    def test_good_data_validates(self):
        ok, errors = validate_project_data(self.good_data())
        self.assertTrue(ok)
        self.assertEqual(errors, [])

    def test_all_target_combinations_validate(self):
        for targets in (["reblend"], ["blender"], ["reblend", "blender"]):
            data = self.good_data()
            data["targets"] = targets
            ok, errors = validate_project_data(data)
            self.assertTrue(ok, f"{targets} should validate: {errors}")

    def test_bad_target_fails(self):
        data = self.good_data()
        data["targets"] = ["maya"]
        ok, errors = validate_project_data(data)
        self.assertFalse(ok)
        self.assertTrue(any("maya" in e for e in errors))

    def test_targets_not_a_list_fails(self):
        data = self.good_data()
        data["targets"] = "reblend"
        ok, errors = validate_project_data(data)
        self.assertFalse(ok)
        self.assertTrue(any("list" in e for e in errors))

    def test_bad_date_form_fails(self):
        data = self.good_data()
        data["created"] = "17/11/2026"
        ok, errors = validate_project_data(data)
        self.assertFalse(ok)
        self.assertTrue(any("date" in e for e in errors))

    def test_impossible_date_fails(self):
        data = self.good_data()
        data["created"] = "2026-02-30"
        ok, errors = validate_project_data(data)
        self.assertFalse(ok)
        self.assertTrue(any("not a real date" in e for e in errors))

    def test_non_dict_fails(self):
        ok, errors = validate_project_data(["not", "a", "dict"])
        self.assertFalse(ok)
        self.assertTrue(any("named fields" in e for e in errors))


if __name__ == "__main__":
    unittest.main()
