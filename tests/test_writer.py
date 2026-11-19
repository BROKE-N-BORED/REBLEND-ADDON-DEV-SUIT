"""Tests for devsuite.packing.writer, the manifest writer (Phase 1 suite side).

The writer turns a project into a manifest dict (DOSSIER.md §5.1).
These tests check that what it produces passes the suite's own
validator — the real one from devsuite.packing.manifest, not a
re-implementation — that the fields come from the project, that the
Reblend range defaults to the Reblend on his PC and can be changed,
and that a project that cannot produce a valid manifest fails with a
plain-words sentence instead of a crash.
"""

import tempfile
import unittest
from pathlib import Path

from devsuite.packing.manifest import (
    KNOWN_CONTRIBUTION_KINDS,
    validate_manifest_data,
)
from devsuite.packing.writer import DEFAULT_REBLEND, build_manifest
from devsuite.projects.project import Project, create_project


def make_project(tmp, **overrides):
    """Create a real project in ``tmp`` and return it."""
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
    return project


def surprise_contributions():
    return {
        "wheel": [
            {"page": "Style", "slot": "bottom-row",
             "label": "Surprise", "action": "surprise.randomize"}
        ],
    }


class TestWriterProducesValidManifests(unittest.TestCase):
    def test_writer_output_validates_clean(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = make_project(tmp)
            manifest, error = build_manifest(
                project, surprise_contributions()
            )
            self.assertIsNone(error)
            ok, errors = validate_manifest_data(manifest)
            self.assertTrue(ok, f"writer output should validate: {errors}")
            self.assertEqual(errors, [])

    def test_fields_come_from_the_project(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = make_project(tmp)
            manifest, error = build_manifest(
                project, surprise_contributions()
            )
            self.assertIsNone(error)
            self.assertEqual(manifest["id"], "surprise")
            self.assertEqual(manifest["name"], "Surprise")
            self.assertEqual(manifest["version"], "1.0.0")
            self.assertEqual(
                manifest["description"],
                "Randomize a material for inspiration.",
            )
            self.assertEqual(manifest["author"], "Joshua Lofland")
            self.assertEqual(manifest["entry"], "addon.py")

    def test_reblend_defaults_to_the_reblend_on_his_pc(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = make_project(tmp)
            manifest, error = build_manifest(
                project, surprise_contributions()
            )
            self.assertIsNone(error)
            self.assertEqual(manifest["reblend"], ">=0.2")
            self.assertEqual(DEFAULT_REBLEND, ">=0.2")

    def test_reblend_range_can_be_changed(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = make_project(tmp)
            manifest, error = build_manifest(
                project, surprise_contributions(), reblend=">=0.3"
            )
            self.assertIsNone(error)
            self.assertEqual(manifest["reblend"], ">=0.3")

    def test_entry_can_be_changed(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = make_project(tmp)
            manifest, error = build_manifest(
                project, surprise_contributions(), entry="main.py"
            )
            self.assertIsNone(error)
            self.assertEqual(manifest["entry"], "main.py")

    def test_every_contribution_kind_is_listed(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = make_project(tmp)
            manifest, error = build_manifest(
                project, surprise_contributions()
            )
            self.assertIsNone(error)
            for kind in KNOWN_CONTRIBUTION_KINDS:
                self.assertIn(kind, manifest["contributions"])
            self.assertEqual(manifest["contributions"]["menu"], [])
            self.assertEqual(len(manifest["contributions"]["wheel"]), 1)

    def test_no_contributions_means_every_kind_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = make_project(tmp)
            manifest, error = build_manifest(project, None)
            self.assertIsNone(error)
            for kind in KNOWN_CONTRIBUTION_KINDS:
                self.assertEqual(manifest["contributions"][kind], [])

    def test_permissions_are_the_v1_values(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = make_project(tmp)
            manifest, error = build_manifest(
                project, surprise_contributions()
            )
            self.assertIsNone(error)
            self.assertEqual(
                manifest["permissions"],
                {"files": "project-only", "network": False},
            )

    def test_icon_included_when_the_project_names_one(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = make_project(tmp, icon="icon.png")
            manifest, error = build_manifest(
                project, surprise_contributions()
            )
            self.assertIsNone(error)
            self.assertEqual(manifest["icon"], "icon.png")

    def test_icon_left_out_when_the_project_names_none(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = make_project(tmp)
            manifest, error = build_manifest(
                project, surprise_contributions()
            )
            self.assertIsNone(error)
            self.assertNotIn("icon", manifest)


class TestWriterRefusesBadProjects(unittest.TestCase):
    def test_bad_version_fails_plainly(self):
        # The project model only asks that the version be text, so a
        # project can hold "1.0" — the writer is the one that catches
        # it, because a manifest version must be three numbers.
        with tempfile.TemporaryDirectory() as tmp:
            project = make_project(tmp, version="1.0")
            manifest, error = build_manifest(
                project, surprise_contributions()
            )
            self.assertIsNone(manifest)
            self.assertIn("1.2.3", error)

    def test_bad_id_fails_plainly(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = make_project(tmp)
            project.id = "Surprise Pack!"
            manifest, error = build_manifest(
                project, surprise_contributions()
            )
            self.assertIsNone(manifest)
            self.assertIn("lowercase", error)

    def test_empty_name_fails_plainly(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = make_project(tmp)
            project.name = "   "
            manifest, error = build_manifest(
                project, surprise_contributions()
            )
            self.assertIsNone(manifest)
            self.assertIn("name", error)

    def test_unknown_contribution_kind_fails_plainly(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = make_project(tmp)
            manifest, error = build_manifest(
                project, {"teleport": [{"label": "Beam"}]}
            )
            self.assertIsNone(manifest)
            self.assertIn("teleport", error)

    def test_wheel_entry_without_an_action_fails_plainly(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = make_project(tmp)
            manifest, error = build_manifest(
                project, {"wheel": [{"label": "Surprise"}]}
            )
            self.assertIsNone(manifest)
            self.assertIn("action", error)

    def test_contributions_that_are_not_a_dict_fail_plainly(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = make_project(tmp)
            manifest, error = build_manifest(project, ["wheel"])
            self.assertIsNone(manifest)
            self.assertIn("contributions", error)

    def test_entry_in_a_subfolder_fails_plainly(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = make_project(tmp)
            manifest, error = build_manifest(
                project, surprise_contributions(), entry="code/addon.py"
            )
            self.assertIsNone(manifest)
            self.assertIn("addon.py", error)

    def test_broken_project_never_crashes_the_writer(self):
        broken = Project(root=Path("/nonexistent"), name="", targets=[],
                         created="", version="x", author="", id="")
        manifest, error = build_manifest(broken, None)
        self.assertIsNone(manifest)
        self.assertIsInstance(error, str)
        self.assertTrue(error)


if __name__ == "__main__":
    unittest.main()
