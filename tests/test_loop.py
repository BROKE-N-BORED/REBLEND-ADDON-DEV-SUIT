"""Tests for devsuite.chat.loop — the Plan, Approve, Build loop.

The model side is tested with a fake client returning canned replies,
so no Ollama is needed. The apply side runs against real projects in
temporary folders, so the tests prove files really land (or really do
not, when the plan is refused).

The rules under test (DOSSIER.md §7.2, §7.3):

* Nothing is built before approval; a refused plan changes nothing.
* A step that fails stops the run and names the step.
* Paths stay inside the project folder.
* Checks run with Python only — the loop installs, deletes, and
  fetches nothing.
"""

import json
import tempfile
import threading
import time
import unittest
from pathlib import Path

from devsuite.chat.loop import (
    apply_plan,
    build_plan,
    plan_summary_lines,
    validate_plan,
)
from devsuite.chat.snapshot import restore_snapshot
from devsuite.projects.project import create_project


class FakeClient:
    """A stand-in for OllamaClient: answers chat() with a canned reply
    (or a canned error), and needs no server."""

    def __init__(self, reply=None, error=None):
        self.reply = reply
        self.error = error
        self.last_model = None
        self.last_messages = None

    def chat(self, model, messages, timeout=None):
        self.last_model = model
        self.last_messages = messages
        return self.reply, self.error


def good_plan():
    return {
        "summary": "Write the addon and run the tests.",
        "target": "reblend",
        "steps": [
            {
                "action": "write_file",
                "path": "src/addon.py",
                "content": "VALUE = 1\n",
            },
            {
                "action": "edit_file",
                "path": "src/addon.py",
                "old": "VALUE = 1",
                "new": "VALUE = 2",
            },
            {
                "action": "run_check",
                "name": "Check the file parses",
                "command": ["python3", "-c", "import ast; ast.parse(open('src/addon.py').read())"],
            },
        ],
    }


class LoopTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        project, error = create_project(
            Path(self.tmp.name) / "my-addon", name="My Addon"
        )
        self.assertIsNone(error)
        self.project = project

    def approve(self, plan):
        return True

    def refuse(self, plan):
        return False


class TestBuildPlan(LoopTestCase):
    def test_build_plan_returns_validated_plan(self):
        client = FakeClient(reply=json.dumps(good_plan()))
        plan, error = build_plan("Build it.", self.project, client=client)
        self.assertIsNone(error)
        self.assertEqual(plan["summary"], "Write the addon and run the tests.")
        self.assertEqual(len(plan["steps"]), 3)
        self.assertEqual(client.last_model, "qwen3.5:4b")

    def test_build_plan_strips_fenced_reply(self):
        client = FakeClient(reply="```json\n" + json.dumps(good_plan()) + "\n```")
        plan, error = build_plan("Build it.", self.project, client=client)
        self.assertIsNone(error)
        self.assertEqual(len(plan["steps"]), 3)

    def test_build_plan_reads_json_with_prose_around_it(self):
        client = FakeClient(
            reply="Here is the plan:\n" + json.dumps(good_plan()) + "\nHope that helps."
        )
        plan, error = build_plan("Build it.", self.project, client=client)
        self.assertIsNone(error)
        self.assertEqual(len(plan["steps"]), 3)

    def test_build_plan_fills_target_from_project(self):
        plan_dict = good_plan()
        del plan_dict["target"]
        client = FakeClient(reply=json.dumps(plan_dict))
        plan, error = build_plan("Build it.", self.project, client=client)
        self.assertIsNone(error)
        self.assertEqual(plan["target"], "reblend")

    def test_build_plan_with_unreadable_reply_is_plain_words(self):
        client = FakeClient(reply="I have no plan, only vibes.")
        plan, error = build_plan("Build it.", self.project, client=client)
        self.assertIsNone(plan)
        self.assertIn("not a plan", error)

    def test_build_plan_with_invalid_plan_is_plain_words(self):
        bad = good_plan()
        bad["steps"][0]["action"] = "delete_everything"
        client = FakeClient(reply=json.dumps(bad))
        plan, error = build_plan("Build it.", self.project, client=client)
        self.assertIsNone(plan)
        self.assertIn("could not use", error)
        self.assertIn("delete_everything", error)

    def test_build_plan_passes_client_error_through(self):
        client = FakeClient(error="Ollama is not running on this computer.")
        plan, error = build_plan("Build it.", self.project, client=client)
        self.assertIsNone(plan)
        self.assertIn("not running", error)

    def test_build_plan_asks_about_the_project(self):
        client = FakeClient(reply=json.dumps(good_plan()))
        build_plan("Add a wheel button.", self.project, client=client)
        user_text = client.last_messages[1]["content"]
        self.assertIn("My Addon", user_text)
        self.assertIn("Add a wheel button.", user_text)


class TestValidatePlan(LoopTestCase):
    def test_good_plan_validates(self):
        ok, errors = validate_plan(good_plan(), self.project)
        self.assertTrue(ok)
        self.assertEqual(errors, [])

    def test_missing_summary_fails(self):
        plan = good_plan()
        del plan["summary"]
        ok, errors = validate_plan(plan, self.project)
        self.assertFalse(ok)
        self.assertTrue(any("summary" in e for e in errors))

    def test_no_steps_fails(self):
        plan = good_plan()
        plan["steps"] = []
        ok, errors = validate_plan(plan, self.project)
        self.assertFalse(ok)
        self.assertTrue(any("at least one step" in e for e in errors))

    def test_unknown_target_fails(self):
        plan = good_plan()
        plan["target"] = "maya"
        ok, errors = validate_plan(plan, self.project)
        self.assertFalse(ok)
        self.assertTrue(any("maya" in e for e in errors))

    def test_unknown_action_fails(self):
        plan = good_plan()
        plan["steps"][0]["action"] = "teleport"
        ok, errors = validate_plan(plan, self.project)
        self.assertFalse(ok)
        self.assertTrue(any("teleport" in e for e in errors))

    def test_escaping_path_fails(self):
        plan = good_plan()
        plan["steps"][0]["path"] = "../outside.py"
        ok, errors = validate_plan(plan, self.project)
        self.assertFalse(ok)
        self.assertTrue(any("leaves the project" in e for e in errors))

    def test_absolute_path_fails(self):
        plan = good_plan()
        plan["steps"][0]["path"] = "/tmp/outside.py"
        ok, errors = validate_plan(plan, self.project)
        self.assertFalse(ok)
        self.assertTrue(any("absolute path" in e for e in errors))

    def test_edit_without_old_fails(self):
        plan = good_plan()
        del plan["steps"][1]["old"]
        ok, errors = validate_plan(plan, self.project)
        self.assertFalse(ok)
        self.assertTrue(any("old" in e for e in errors))

    def test_check_with_disallowed_command_fails(self):
        plan = good_plan()
        plan["steps"][2]["command"] = ["rm", "-rf", "."]
        ok, errors = validate_plan(plan, self.project)
        self.assertFalse(ok)
        self.assertTrue(any("rm" in e for e in errors))

    def test_check_with_string_command_fails(self):
        plan = good_plan()
        plan["steps"][2]["command"] = "python3 -m unittest"
        ok, errors = validate_plan(plan, self.project)
        self.assertFalse(ok)
        self.assertTrue(any("list of words" in e for e in errors))

    def test_plan_summary_lines(self):
        lines = plan_summary_lines(good_plan())
        self.assertEqual(lines, [
            "Write src/addon.py",
            "Change src/addon.py",
            "Run check: Check the file parses",
        ])


class TestApplyPlan(LoopTestCase):
    def test_approved_plan_writes_and_edits_files(self):
        result = apply_plan(good_plan(), self.project, self.approve)
        self.assertTrue(result.approved)
        self.assertTrue(result.applied)
        self.assertIsNone(result.failed_step)
        self.assertIsNone(result.error)
        self.assertEqual(len(result.completed), 3)
        content = (self.project.root / "src" / "addon.py").read_text()
        self.assertEqual(content, "VALUE = 2\n")

    def test_refused_plan_changes_nothing(self):
        result = apply_plan(good_plan(), self.project, self.refuse)
        self.assertFalse(result.approved)
        self.assertFalse(result.applied)
        self.assertEqual(result.completed, [])
        self.assertFalse((self.project.root / "src" / "addon.py").exists())

    def test_invalid_plan_is_not_applied(self):
        plan = good_plan()
        plan["steps"][0]["action"] = "teleport"
        result = apply_plan(plan, self.project, self.approve)
        self.assertFalse(result.applied)
        self.assertIn("problem", result.error)
        self.assertFalse((self.project.root / "src" / "addon.py").exists())

    def test_failing_step_stops_the_run_and_names_the_step(self):
        plan = good_plan()
        # The edit looks for text the write did not put there.
        plan["steps"][1]["old"] = "VALUE = 99"
        result = apply_plan(plan, self.project, self.approve)
        self.assertTrue(result.approved)
        self.assertFalse(result.applied)
        self.assertEqual(result.failed_step["index"], 2)
        self.assertEqual(result.failed_step["action"], "edit_file")
        self.assertEqual(result.failed_step["target"], "src/addon.py")
        self.assertIn("src/addon.py", result.error)
        # The first step ran; the third (the check) never did.
        self.assertEqual(len(result.completed), 1)
        self.assertEqual(
            (self.project.root / "src" / "addon.py").read_text(), "VALUE = 1\n"
        )

    def test_failing_check_stops_the_run_and_names_the_check(self):
        plan = {
            "summary": "Write a file, then run a check that fails.",
            "steps": [
                {"action": "write_file", "path": "src/a.py", "content": "x = 1\n"},
                {
                    "action": "run_check",
                    "name": "The failing check",
                    "command": ["python3", "-c", "raise SystemExit(1)"],
                },
                {"action": "write_file", "path": "src/b.py", "content": "y = 2\n"},
            ],
        }
        result = apply_plan(plan, self.project, self.approve)
        self.assertFalse(result.applied)
        self.assertEqual(result.failed_step["index"], 2)
        self.assertEqual(result.failed_step["action"], "run_check")
        self.assertEqual(result.failed_step["target"], "The failing check")
        self.assertIn("The failing check", result.error)
        self.assertIn("code 1", result.error)
        self.assertEqual(len(result.completed), 1)
        self.assertFalse((self.project.root / "src" / "b.py").exists())

    def test_edit_of_missing_file_fails_plainly(self):
        plan = {
            "summary": "Edit a file that is not there.",
            "steps": [
                {"action": "edit_file", "path": "src/missing.py",
                 "old": "a", "new": "b"},
            ],
        }
        result = apply_plan(plan, self.project, self.approve)
        self.assertFalse(result.applied)
        self.assertIn("src/missing.py", result.error)
        self.assertIn("not there", result.error)

    def test_check_timeout_fails_plainly(self):
        plan = {
            "summary": "Run a check that hangs.",
            "steps": [
                {
                    "action": "run_check",
                    "name": "The hanging check",
                    "command": ["python3", "-c", "import time; time.sleep(30)"],
                },
            ],
        }
        result = apply_plan(plan, self.project, self.approve, check_timeout=0.2)
        self.assertFalse(result.applied)
        self.assertIn("The hanging check", result.error)
        self.assertIn("too long", result.error)

    def test_approve_callback_failing_changes_nothing(self):
        def broken_approve(plan):
            raise RuntimeError("the window crashed")

        result = apply_plan(good_plan(), self.project, broken_approve)
        self.assertFalse(result.approved)
        self.assertFalse(result.applied)
        self.assertIn("approval", result.error)
        self.assertFalse((self.project.root / "src" / "addon.py").exists())



class TestCancel(LoopTestCase):
    """Cancel (U26): every long operation offers cancel. A cancelled
    build stops, keeps its snapshot, and undo still works."""

    def slow_plan(self):
        return {
            "summary": "Write the file, then run a slow check.",
            "target": "reblend",
            "steps": [
                {
                    "action": "write_file",
                    "path": "src/addon.py",
                    "content": "VALUE = 1\n",
                },
                {
                    "action": "run_check",
                    "name": "A slow check",
                    "command": [
                        "python3", "-c",
                        "import time; time.sleep(30)",
                    ],
                },
            ],
        }

    def test_precancelled_event_stops_before_first_step(self):
        event = threading.Event()
        event.set()
        result = apply_plan(
            self.slow_plan(), self.project, self.approve,
            cancelled=event.is_set,
        )
        self.assertFalse(result.applied)
        self.assertTrue(result.cancelled)
        self.assertEqual(result.completed, [])
        self.assertFalse(
            (self.project.root / "src" / "addon.py").exists()
        )
        self.assertTrue(result.snapshot_id)

    def test_cancel_during_long_check_stops_promptly(self):
        event = threading.Event()
        timer = threading.Timer(0.3, event.set)
        timer.start()
        started = time.monotonic()
        try:
            result = apply_plan(
                self.slow_plan(), self.project, self.approve,
                cancelled=event.is_set,
            )
        finally:
            timer.cancel()
        elapsed = time.monotonic() - started
        self.assertLess(
            elapsed, 10, f"cancel took {elapsed:.1f}s — the check kept running"
        )
        self.assertFalse(result.applied)
        self.assertTrue(result.cancelled)
        # The first step ran before the cancel landed.
        self.assertEqual(result.completed, ["Wrote src/addon.py"])
        addon = self.project.root / "src" / "addon.py"
        self.assertTrue(addon.is_file())
        # Undo still works after a cancelled build.
        ok, error = restore_snapshot(
            self.project.root, result.snapshot_id
        )
        self.assertTrue(ok, error)
        self.assertFalse(addon.exists())

    def test_no_cancel_hook_runs_normally(self):
        result = apply_plan(
            good_plan(), self.project, self.approve
        )
        self.assertTrue(result.applied)
        self.assertFalse(result.cancelled)


if __name__ == "__main__":
    unittest.main()
