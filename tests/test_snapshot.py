"""Tests for devsuite.chat.snapshot and the loop's snapshot wiring.

A snapshot is a dated copy of the files a plan touches, taken before
apply (DOSSIER.md §7.4, §9.4). Undo restores from it. These tests
check that snapshots are taken, listed, and restored correctly, and
that the loop never applies a plan without one.
"""

import json
import tempfile
import unittest
from pathlib import Path

from devsuite.chat.loop import apply_plan
from devsuite.chat.snapshot import (
    create_snapshot,
    latest_snapshot,
    list_snapshots,
    restore_snapshot,
)
from devsuite.projects.project import create_project


def make_project(base):
    project, error = create_project(base / "my-addon", name="My Addon")
    assert error is None, error
    return project


def write_plan():
    return {
        "summary": "Write the addon file.",
        "target": "reblend",
        "steps": [
            {
                "action": "write_file",
                "path": "src/addon.py",
                "content": "VALUE = 2\n",
            },
        ],
    }


class SnapshotTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.project = make_project(Path(self.tmp.name))


class TestCreateSnapshot(SnapshotTestCase):
    def test_snapshot_copies_existing_files(self):
        (self.project.root / "src" / "addon.py").write_text("VALUE = 1\n")
        snapshot_id, error = create_snapshot(
            self.project.root, ["src/addon.py"], "Before the change."
        )
        self.assertIsNone(error)
        self.assertTrue(snapshot_id)
        saved = (
            self.project.root / ".snapshots" / snapshot_id / "src" / "addon.py"
        )
        self.assertTrue(saved.is_file())
        self.assertEqual(saved.read_text(), "VALUE = 1\n")

    def test_snapshot_records_files_that_do_not_exist_yet(self):
        snapshot_id, error = create_snapshot(
            self.project.root, ["src/new.py"], "Before the change."
        )
        self.assertIsNone(error)
        manifest = json.loads(
            (
                self.project.root / ".snapshots" / snapshot_id / "snapshot.json"
            ).read_text()
        )
        self.assertEqual(manifest["summary"], "Before the change.")
        self.assertEqual(
            manifest["files"], [{"path": "src/new.py", "existed": False}]
        )

    def test_two_snapshots_get_different_ids(self):
        first, _ = create_snapshot(self.project.root, [], "First.")
        second, _ = create_snapshot(self.project.root, [], "Second.")
        self.assertNotEqual(first, second)


class TestListSnapshots(SnapshotTestCase):
    def test_empty_project_has_no_snapshots(self):
        self.assertEqual(list_snapshots(self.project.root), [])
        self.assertIsNone(latest_snapshot(self.project.root))

    def test_list_is_newest_first(self):
        create_snapshot(self.project.root, [], "First.")
        create_snapshot(self.project.root, [], "Second.")
        snapshots = list_snapshots(self.project.root)
        self.assertEqual(len(snapshots), 2)
        self.assertEqual(snapshots[0]["summary"], "Second.")
        self.assertEqual(snapshots[1]["summary"], "First.")
        self.assertEqual(latest_snapshot(self.project.root), snapshots[0]["id"])


class TestRestoreSnapshot(SnapshotTestCase):
    def test_restore_brings_back_original_content(self):
        target = self.project.root / "src" / "addon.py"
        target.write_text("VALUE = 1\n")
        snapshot_id, _ = create_snapshot(
            self.project.root, ["src/addon.py"], "Before the change."
        )
        target.write_text("VALUE = 2\n")
        ok, error = restore_snapshot(self.project.root, snapshot_id)
        self.assertTrue(ok, error)
        self.assertEqual(target.read_text(), "VALUE = 1\n")

    def test_restore_removes_files_the_plan_created(self):
        snapshot_id, _ = create_snapshot(
            self.project.root, ["src/new.py"], "Before the change."
        )
        target = self.project.root / "src" / "new.py"
        target.write_text("brand new\n")
        ok, error = restore_snapshot(self.project.root, snapshot_id)
        self.assertTrue(ok, error)
        self.assertFalse(target.exists())

    def test_restore_brings_back_a_deleted_file(self):
        target = self.project.root / "src" / "addon.py"
        target.write_text("VALUE = 1\n")
        snapshot_id, _ = create_snapshot(
            self.project.root, ["src/addon.py"], "Before the change."
        )
        target.unlink()
        ok, error = restore_snapshot(self.project.root, snapshot_id)
        self.assertTrue(ok, error)
        self.assertEqual(target.read_text(), "VALUE = 1\n")

    def test_restore_missing_snapshot_fails_plainly(self):
        ok, error = restore_snapshot(self.project.root, "no-such-snapshot")
        self.assertFalse(ok)
        self.assertIn("could not find", error)


class TestLoopSnapshots(SnapshotTestCase):
    def test_apply_takes_a_snapshot(self):
        result = apply_plan(write_plan(), self.project, lambda plan: True)
        self.assertTrue(result.applied)
        self.assertTrue(result.snapshot_id)
        self.assertEqual(len(list_snapshots(self.project.root)), 1)

    def test_undo_after_apply_restores_the_project(self):
        target = self.project.root / "src" / "addon.py"
        target.write_text("VALUE = 1\n")
        plan = write_plan()
        result = apply_plan(plan, self.project, lambda plan: True)
        self.assertTrue(result.applied)
        self.assertEqual(target.read_text(), "VALUE = 2\n")
        ok, error = restore_snapshot(self.project.root, result.snapshot_id)
        self.assertTrue(ok, error)
        self.assertEqual(target.read_text(), "VALUE = 1\n")

    def test_refused_plan_takes_no_snapshot(self):
        result = apply_plan(write_plan(), self.project, lambda plan: False)
        self.assertFalse(result.applied)
        self.assertIsNone(result.snapshot_id)
        self.assertEqual(list_snapshots(self.project.root), [])

    def test_failed_step_still_leaves_a_snapshot(self):
        target = self.project.root / "src" / "addon.py"
        target.write_text("VALUE = 1\n")
        plan = {
            "summary": "Write then fail.",
            "target": "reblend",
            "steps": [
                {
                    "action": "write_file",
                    "path": "src/addon.py",
                    "content": "VALUE = 2\n",
                },
                {
                    "action": "edit_file",
                    "path": "src/addon.py",
                    "old": "text that is not there",
                    "new": "replacement",
                },
            ],
        }
        result = apply_plan(plan, self.project, lambda plan: True)
        self.assertFalse(result.applied)
        self.assertIsNotNone(result.failed_step)
        self.assertTrue(result.snapshot_id)
        ok, error = restore_snapshot(self.project.root, result.snapshot_id)
        self.assertTrue(ok, error)
        self.assertEqual(target.read_text(), "VALUE = 1\n")


if __name__ == "__main__":
    unittest.main()
