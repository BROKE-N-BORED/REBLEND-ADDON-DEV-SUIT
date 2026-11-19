"""Tests for devsuite.packing.manifest.

A manifest is the pack's identity card. These tests check that a good
one passes, and that every kind of bad one fails with a plain-words
message instead of a crash.

The shape tested here is DOSSIER.md §5.1, the pack format v1: id,
name, version, reblend, entry, contributions (lists of objects), with
optional description, author, icon, and permissions.
"""

import json
import tempfile
import unittest
from pathlib import Path

from devsuite.packing.manifest import (
    REQUIRED_FIELDS,
    validate_manifest,
    validate_manifest_data,
)


def good_manifest():
    # The §5.1 example, word for word.
    return {
        "id": "surprise",
        "name": "Surprise",
        "version": "1.0.0",
        "description": "Randomize a material for inspiration. One button, one undo step.",
        "author": "Joshua Lofland",
        "reblend": ">=0.2",
        "entry": "addon.py",
        "icon": "icon.png",
        "contributions": {
            "wheel": [
                {"page": "Style", "slot": "bottom-row",
                 "label": "Surprise", "action": "surprise.randomize"}
            ],
            "menu": [],
            "inspector": [],
            "brushes": [],
            "materials": [],
            "simulations": [],
        },
        "permissions": {
            "files": "project-only",
            "network": False,
        },
    }


class TestValidManifest(unittest.TestCase):
    def test_valid_manifest_passes(self):
        ok, errors = validate_manifest_data(good_manifest())
        self.assertTrue(ok)
        self.assertEqual(errors, [])

    def test_valid_manifest_from_file_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "manifest.json"
            path.write_text(json.dumps(good_manifest()), encoding="utf-8")
            (Path(tmp) / "addon.py").write_text(
                "def register(api): pass\ndef unregister(api): pass\n",
                encoding="utf-8",
            )
            ok, errors = validate_manifest(path)
            self.assertTrue(ok)
            self.assertEqual(errors, [])

    def test_missing_entry_file_fails_plainly(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "manifest.json"
            path.write_text(json.dumps(good_manifest()), encoding="utf-8")
            ok, errors = validate_manifest(path)
            self.assertFalse(ok)
            self.assertIn("addon.py", errors[0])
            self.assertIn("missing", errors[0])

    def test_unknown_fields_are_ignored(self):
        # Forward compatibility: a newer pack may carry fields this
        # version does not know about. They must not break validation.
        data = good_manifest()
        data["future_field"] = {"something": True}
        ok, _ = validate_manifest_data(data)
        self.assertTrue(ok)

    def test_empty_contributions_object_passes(self):
        data = good_manifest()
        data["contributions"] = {}
        ok, _ = validate_manifest_data(data)
        self.assertTrue(ok)

    def test_permissions_absent_passes(self):
        data = good_manifest()
        del data["permissions"]
        ok, _ = validate_manifest_data(data)
        self.assertTrue(ok)

    def test_optional_text_absent_passes(self):
        data = good_manifest()
        for field in ("description", "author", "icon"):
            del data[field]
        ok, _ = validate_manifest_data(data)
        self.assertTrue(ok)


class TestMissingFields(unittest.TestCase):
    def test_each_missing_field_fails_with_plain_message(self):
        for field in REQUIRED_FIELDS:
            with self.subTest(field=field):
                data = good_manifest()
                del data[field]
                ok, errors = validate_manifest_data(data)
                self.assertFalse(ok)
                self.assertTrue(
                    any(field in message for message in errors),
                    f"no error mentioned the missing '{field}' field: {errors}",
                )

    def test_missing_everything_reports_every_field(self):
        ok, errors = validate_manifest_data({})
        self.assertFalse(ok)
        self.assertEqual(len(errors), len(REQUIRED_FIELDS))


class TestInvalidFields(unittest.TestCase):
    def test_uppercase_id_fails(self):
        data = good_manifest()
        data["id"] = "Surprise"
        ok, errors = validate_manifest_data(data)
        self.assertFalse(ok)
        self.assertIn("surprise", errors[0].lower().replace("'", ""))

    def test_id_with_space_fails(self):
        data = good_manifest()
        data["id"] = "my pack"
        ok, _ = validate_manifest_data(data)
        self.assertFalse(ok)

    def test_id_with_underscore_fails(self):
        data = good_manifest()
        data["id"] = "my_pack"
        ok, _ = validate_manifest_data(data)
        self.assertFalse(ok)

    def test_id_with_dots_and_dashes_passes(self):
        data = good_manifest()
        data["id"] = "my-pack.v2"
        ok, _ = validate_manifest_data(data)
        self.assertTrue(ok)

    def test_version_missing_patch_fails(self):
        data = good_manifest()
        data["version"] = "1.0"
        ok, errors = validate_manifest_data(data)
        self.assertFalse(ok)
        self.assertIn("1.2.3", errors[0])

    def test_version_with_words_fails(self):
        data = good_manifest()
        data["version"] = "one.two.three"
        ok, _ = validate_manifest_data(data)
        self.assertFalse(ok)

    def test_blank_name_fails(self):
        data = good_manifest()
        data["name"] = "   "
        ok, _ = validate_manifest_data(data)
        self.assertFalse(ok)

    def test_reblend_not_text_fails(self):
        data = good_manifest()
        data["reblend"] = 0.2
        ok, errors = validate_manifest_data(data)
        self.assertFalse(ok)
        self.assertIn("reblend", errors[0])

    def test_reblend_empty_fails(self):
        data = good_manifest()
        data["reblend"] = "   "
        ok, _ = validate_manifest_data(data)
        self.assertFalse(ok)

    def test_entry_without_py_fails(self):
        data = good_manifest()
        data["entry"] = "addon"
        ok, errors = validate_manifest_data(data)
        self.assertFalse(ok)
        self.assertIn("addon.py", errors[0])

    def test_entry_with_folder_fails(self):
        data = good_manifest()
        data["entry"] = "code/addon.py"
        ok, _ = validate_manifest_data(data)
        self.assertFalse(ok)

    def test_contributions_not_an_object_fails(self):
        data = good_manifest()
        data["contributions"] = ["wheel"]
        ok, _ = validate_manifest_data(data)
        self.assertFalse(ok)

    def test_contributions_value_not_a_list_fails(self):
        data = good_manifest()
        data["contributions"] = {"wheel": "Surprise"}
        ok, errors = validate_manifest_data(data)
        self.assertFalse(ok)
        self.assertIn("wheel", errors[0])

    def test_contributions_item_not_an_object_fails(self):
        data = good_manifest()
        data["contributions"] = {"wheel": ["Surprise"]}
        ok, errors = validate_manifest_data(data)
        self.assertFalse(ok)
        self.assertIn("wheel", errors[0])

    def test_unknown_contribution_kind_fails(self):
        data = good_manifest()
        data["contributions"] = {"teleport": []}
        ok, errors = validate_manifest_data(data)
        self.assertFalse(ok)
        self.assertIn("teleport", errors[0])

    def test_wheel_entry_without_label_fails(self):
        data = good_manifest()
        data["contributions"] = {"wheel": [{"action": "surprise.randomize"}]}
        ok, errors = validate_manifest_data(data)
        self.assertFalse(ok)
        self.assertIn("label", errors[0])

    def test_wheel_entry_without_action_fails(self):
        data = good_manifest()
        data["contributions"] = {"wheel": [{"label": "Surprise"}]}
        ok, errors = validate_manifest_data(data)
        self.assertFalse(ok)
        self.assertIn("action", errors[0])

    def test_non_wheel_entry_without_label_passes(self):
        # Only wheel entries need a label and an action in v1.
        data = good_manifest()
        data["contributions"] = {"brushes": [{"name": "Soft"}]}
        ok, _ = validate_manifest_data(data)
        self.assertTrue(ok)

    def test_description_not_text_fails(self):
        data = good_manifest()
        data["description"] = 7
        ok, errors = validate_manifest_data(data)
        self.assertFalse(ok)
        self.assertIn("description", errors[0])

    def test_permissions_not_an_object_fails(self):
        data = good_manifest()
        data["permissions"] = "project-only"
        ok, _ = validate_manifest_data(data)
        self.assertFalse(ok)

    def test_permissions_network_true_fails(self):
        data = good_manifest()
        data["permissions"]["network"] = True
        ok, errors = validate_manifest_data(data)
        self.assertFalse(ok)
        self.assertIn("network", errors[0])

    def test_permissions_files_other_value_fails(self):
        data = good_manifest()
        data["permissions"]["files"] = "anywhere"
        ok, errors = validate_manifest_data(data)
        self.assertFalse(ok)
        self.assertIn("project-only", errors[0])


class TestUnreadableManifests(unittest.TestCase):
    def test_missing_file_fails_plainly(self):
        ok, errors = validate_manifest("/no/such/folder/manifest.json")
        self.assertFalse(ok)
        self.assertTrue(errors)
        self.assertIn("could not find", errors[0])

    def test_malformed_json_fails_plainly(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "manifest.json"
            path.write_text('{"id": "surprise", "name": }', encoding="utf-8")
            ok, errors = validate_manifest(path)
            self.assertFalse(ok)
            self.assertTrue(errors)
            self.assertIn("mistake", errors[0])

    def test_top_level_list_fails_plainly(self):
        ok, errors = validate_manifest_data(["surprise"])
        self.assertFalse(ok)
        self.assertTrue(errors)

    def test_no_error_message_mentions_a_traceback(self):
        # Plain words only: no jargon, no stack traces, no exception
        # type names leak into what the user sees.
        bad_inputs = [
            "/no/such/folder/manifest.json",
            ["not", "a", "dict"],
            {"id": 42},
        ]
        for bad in bad_inputs:
            with self.subTest(bad=bad):
                if isinstance(bad, str):
                    _, errors = validate_manifest(bad)
                else:
                    _, errors = validate_manifest_data(bad)
                blob = " ".join(errors).lower()
                for word in ("traceback", "exception", "keyerror",
                             "typeerror", "jsondecodeerror"):
                    self.assertNotIn(word, blob)


if __name__ == "__main__":
    unittest.main()
