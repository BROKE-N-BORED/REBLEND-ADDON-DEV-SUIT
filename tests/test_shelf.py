"""Tests for devsuite.library.shelf — the shelf record (DOSSIER.md §6.9).

The shelf is a plain JSON file listing every pack the suite has
built. These tests check the round-trip, the dedupe on rebuild, the
damaged-shelf behavior (empty, with a plain-words sentence — never
a crash), and removal. Stdlib only; no Qt needed.
"""

import json
import tempfile
import unittest
from pathlib import Path

from devsuite.library.shelf import (
    add_entry,
    default_shelf_path,
    load_shelf,
    remove_entry,
    save_shelf,
)


def sample_entry(pack_path="/tmp/surprise-1.0.0.rblpack", **overrides):
    entry = {
        "pack_path": pack_path,
        "project_id": "surprise",
        "project_name": "Surprise",
        "project_root": "/tmp/surprise",
        "version": "1.0.0",
        "target": "reblend",
        "built": "2026-11-17",
        "test_run_id": None,
        "description": "Randomize a material for inspiration.",
    }
    entry.update(overrides)
    return entry


class TestShelfRoundTrip(unittest.TestCase):
    def test_save_and_load_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "shelf.json"
            entries = [sample_entry(), sample_entry(
                "/tmp/other-2.0.0-blender.zip",
                project_id="other", project_name="Other",
                version="2.0.0", target="blender",
            )]
            error = save_shelf(path, entries)
            self.assertIsNone(error)
            loaded, error = load_shelf(path)
            self.assertIsNone(error)
            self.assertEqual(loaded, entries)

    def test_missing_shelf_reads_as_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            loaded, error = load_shelf(Path(tmp) / "shelf.json")
            self.assertIsNone(error)
            self.assertEqual(loaded, [])

    def test_damaged_shelf_reads_as_empty_with_a_sentence(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "shelf.json"
            path.write_text("this is not json at all", encoding="utf-8")
            loaded, error = load_shelf(path)
            self.assertEqual(loaded, [])
            self.assertIsInstance(error, str)
            self.assertIn("shelf", error.lower())

    def test_shelf_with_a_bad_entry_reads_as_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "shelf.json"
            path.write_text(
                json.dumps([sample_entry(), {"no_pack_path": True}]),
                encoding="utf-8",
            )
            loaded, error = load_shelf(path)
            self.assertEqual(loaded, [])
            self.assertIsInstance(error, str)

    def test_shelf_that_is_not_a_list_reads_as_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "shelf.json"
            path.write_text(json.dumps({"pack_path": "x"}), encoding="utf-8")
            loaded, error = load_shelf(path)
            self.assertEqual(loaded, [])
            self.assertIsInstance(error, str)


class TestShelfEntries(unittest.TestCase):
    def test_add_entry_dedupes_by_pack_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "shelf.json"
            self.assertIsNone(add_entry(path, sample_entry()))
            # Rebuilding the same file updates the entry; it never
            # adds a second one.
            self.assertIsNone(add_entry(
                path, sample_entry(version="1.0.1", built="2026-11-18")
            ))
            loaded, error = load_shelf(path)
            self.assertIsNone(error)
            self.assertEqual(len(loaded), 1)
            self.assertEqual(loaded[0]["version"], "1.0.1")
            self.assertEqual(loaded[0]["built"], "2026-11-18")

    def test_add_entry_puts_the_newest_first(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "shelf.json"
            self.assertIsNone(add_entry(path, sample_entry()))
            self.assertIsNone(add_entry(path, sample_entry(
                "/tmp/other-2.0.0-blender.zip",
                project_id="other", project_name="Other",
            )))
            loaded, _ = load_shelf(path)
            self.assertEqual(loaded[0]["project_id"], "other")
            self.assertEqual(loaded[1]["project_id"], "surprise")

    def test_remove_entry_removes_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "shelf.json"
            self.assertIsNone(add_entry(path, sample_entry()))
            removed, error = remove_entry(
                path, "/tmp/surprise-1.0.0.rblpack"
            )
            self.assertIsNone(error)
            self.assertTrue(removed)
            loaded, _ = load_shelf(path)
            self.assertEqual(loaded, [])

    def test_remove_missing_entry_reports_not_removed(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "shelf.json"
            self.assertIsNone(add_entry(path, sample_entry()))
            removed, error = remove_entry(path, "/tmp/nope.rblpack")
            self.assertIsNone(error)
            self.assertFalse(removed)
            loaded, _ = load_shelf(path)
            self.assertEqual(len(loaded), 1)

    def test_default_path_is_under_local_share(self):
        path = default_shelf_path()
        self.assertEqual(path.name, "shelf.json")
        self.assertIn(".local", path.parts)
        self.assertIn("share", path.parts)


if __name__ == "__main__":
    unittest.main()
