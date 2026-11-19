"""Tests for devsuite.blender_drive — the Blender drive backend.

Blender is not installed in this sandbox, so nothing here runs
real Blender. The runner is proven against the fake Blender
(``tests/fake_blender.py``), which mimics Blender's command-line
contract, and the generated test script is verified by parsing
it. A real Blender run waits for his PC (Phase 5's done-when).

The rules under test (DOSSIER.md §8.3, §8.4, §9.4):

* Blender is found the SKULLPT way: env override, the
  ``~/.local/bin/blender`` symlink, PATH, then the usual spots.
* A timeout is a result, not a crash; a missing Blender is a
  plain-words report.
* A broken add-on zip fails before Blender runs.
* Checks come back parsed, renders collected, and the run record
  (``result.json``) written beside them.
* The generated script is valid Python and carries the
  install/enable/check/render/unload steps.
"""

import ast
import json
import os
import shutil
import stat
import tempfile
import threading
import time
import unittest
import zipfile
from pathlib import Path

from devsuite.blender_drive.runner import (
    DEFAULT_TIMEOUT,
    find_blender,
    parse_checks,
    run_blender_test,
)
from devsuite.blender_drive.scripts import (
    RENDER_NAME,
    generate_test_script,
    write_test_script,
    zip_is_legacy,
)
from devsuite.packing.blender import build_blender_addon
from devsuite.templates import create_project_from_template

FAKE_BLENDER = Path(__file__).resolve().parent / "fake_blender.py"


def make_fake_exe(tmp):
    """A runnable copy of the fake Blender in ``tmp``."""
    Path(tmp).mkdir(parents=True, exist_ok=True)
    exe = Path(tmp) / "blender"
    shutil.copy2(FAKE_BLENDER, exe)
    exe.chmod(exe.stat().st_mode | stat.S_IXUSR)
    return exe


def make_zip(path, name="addon.zip"):
    """A small valid zip file at ``path / name``."""
    zip_path = Path(path) / name
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("__init__.py", "# test add-on\n")
    return zip_path


def make_script(path):
    """A generated test script written to ``path``."""
    script, error = generate_test_script("surprise", "surprise.randomize")
    assert error is None, error
    script_path = Path(path) / "test_script.py"
    script_path.write_text(script, encoding="utf-8")
    return script_path


class FindBlenderTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self._saved = dict(os.environ)

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self._saved)
        self._tmp.cleanup()

    def _isolate(self):
        """A HOME with no Blender in it, and a PATH with none."""
        home = self.tmp / "home"
        home.mkdir()
        os.environ["HOME"] = str(home)
        bindir = self.tmp / "bin"
        bindir.mkdir()
        os.environ["PATH"] = str(bindir)
        os.environ.pop("DEVSUITE_BLENDER", None)
        return home, bindir

    def test_finds_a_blender_on_path(self):
        _, bindir = self._isolate()
        exe = make_fake_exe(bindir)
        self.assertEqual(find_blender(), str(exe))

    def test_returns_none_when_there_is_no_blender(self):
        self._isolate()
        self.assertIsNone(find_blender())

    def test_symlink_beats_path(self):
        home, bindir = self._isolate()
        make_fake_exe(bindir)
        link_dir = home / ".local" / "bin"
        link_dir.mkdir(parents=True)
        symlink = link_dir / "blender"
        shutil.copy2(FAKE_BLENDER, symlink)
        self.assertEqual(find_blender(), str(symlink))

    def test_env_override_wins(self):
        home, bindir = self._isolate()
        make_fake_exe(bindir)
        custom = make_fake_exe(self.tmp / "custom")
        os.environ["DEVSUITE_BLENDER"] = str(custom)
        self.assertEqual(find_blender(), str(custom))

    def test_env_override_to_a_missing_file_is_ignored(self):
        _, bindir = self._isolate()
        exe = make_fake_exe(bindir)
        os.environ["DEVSUITE_BLENDER"] = str(self.tmp / "nope" / "blender")
        self.assertEqual(find_blender(), str(exe))


class ParseChecksTest(unittest.TestCase):
    def test_parses_check_lines_and_ignores_noise(self):
        output = (
            "Blender 5.3.0 (hash 000000000000)\n"
            "Read blend: <startup>\n"
            'DEVSUITE-CHECK {"name": "Loads without errors", '
            '"passed": true, "detail": "installed and enabled."}\n'
            "Some Blender noise here.\n"
            'DEVSUITE-CHECK {"name": "Render is written", '
            '"passed": false, "detail": "no render landed."}\n'
            "DEVSUITE-CHECK {not json}\n"
            'DEVSUITE-CHECK {"name": "", "passed": true}\n'
            "Blender quit\n"
        )
        checks = parse_checks(output)
        self.assertEqual(len(checks), 2)
        self.assertEqual(checks[0]["name"], "Loads without errors")
        self.assertTrue(checks[0]["passed"])
        self.assertEqual(checks[0]["detail"], "installed and enabled.")
        self.assertEqual(checks[1]["name"], "Render is written")
        self.assertFalse(checks[1]["passed"])


class RunnerTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.exe = make_fake_exe(self.tmp)
        self.zip_path = make_zip(self.tmp)
        self.script_path = make_script(self.tmp)
        self.out_dir = self.tmp / "run"
        self._saved_env = dict(os.environ)

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self._saved_env)
        self._tmp.cleanup()

    def _run(self, mode, **kwargs):
        os.environ["FAKE_BLENDER_MODE"] = mode
        return run_blender_test(
            str(self.exe), str(self.zip_path), str(self.script_path),
            str(self.out_dir), **kwargs,
        )

    def test_success_path_parses_checks_and_collects_the_render(self):
        result = self._run("pass")
        self.assertEqual(result["status"], "passed")
        self.assertEqual(len(result["checks"]), 5)
        self.assertTrue(all(c["passed"] for c in result["checks"]))
        self.assertEqual(
            [c["name"] for c in result["checks"]],
            ["Loads without errors",
             "Does not crash on the empty scene",
             "Operator runs",
             "Render is written",
             "Unloads clean"],
        )
        self.assertEqual(result["renders"], [RENDER_NAME])
        self.assertIn("All 5 checks passed", result["summary"])
        self.assertIsNotNone(result["record_path"])
        record = json.loads(
            Path(result["record_path"]).read_text(encoding="utf-8")
        )
        self.assertEqual(record["status"], "passed")
        self.assertEqual(len(record["checks"]), 5)
        self.assertEqual(record["renders"], [RENDER_NAME])
        self.assertIn("log", record)

    def test_success_path_against_a_real_emitter_zip(self):
        # The drive accepts the Blender emitter's real output: build
        # the Surprise add-on, then run the drive against it.
        project, error = create_project_from_template(
            "surprise",
            self.tmp / "surprise",
            name="Surprise",
            targets=["blender"],
            version="1.0.0",
        )
        self.assertIsNone(error)
        zip_path, _, error = build_blender_addon(
            project, project.packs_dir
        )
        self.assertIsNone(error)
        os.environ["FAKE_BLENDER_MODE"] = "pass"
        result = run_blender_test(
            str(self.exe), str(zip_path), str(self.script_path),
            str(self.out_dir),
        )
        self.assertEqual(result["status"], "passed")
        self.assertEqual(result["addon_zip"], str(zip_path))

    def test_failure_path_reports_the_failed_check_and_the_log(self):
        result = self._run("fail")
        self.assertEqual(result["status"], "failed")
        self.assertEqual(len(result["checks"]), 2)
        self.assertFalse(result["checks"][0]["passed"])
        self.assertIn("Loads without errors", result["summary"])
        self.assertIn("not enabled", result["checks"][0]["detail"])
        log = "\n".join(result["log"])
        self.assertIn("Traceback", log)
        self.assertEqual(result["renders"], [])

    def test_crash_path_reports_no_checks(self):
        result = self._run("crash")
        self.assertEqual(result["status"], "crashed")
        self.assertEqual(result["checks"], [])
        self.assertIn("before it reported", result["summary"])
        log = "\n".join(result["log"])
        self.assertIn("EXCEPTION_ACCESS_VIOLATION", log)

    def test_timeout_is_a_result_and_stops_promptly(self):
        started = time.monotonic()
        result = self._run("sleep", timeout=2)
        elapsed = time.monotonic() - started
        self.assertLess(
            elapsed, 10,
            f"the timeout took {elapsed:.1f}s — the run was not killed",
        )
        self.assertEqual(result["status"], "timeout")
        self.assertIn("2-second limit", result["summary"])
        self.assertEqual(result["checks"], [])

    def test_cancel_stops_a_sleeping_blender_promptly(self):
        event = threading.Event()
        timer = threading.Timer(0.3, event.set)
        timer.start()
        started = time.monotonic()
        try:
            result = self._run("sleep", cancelled=event.is_set)
        finally:
            timer.cancel()
        elapsed = time.monotonic() - started
        self.assertLess(
            elapsed, 10,
            f"the cancel took {elapsed:.1f}s — Blender kept running",
        )
        self.assertEqual(result["status"], "cancelled")
        self.assertEqual(result["summary"], "The test was cancelled.")
        self.assertEqual(result["checks"], [])

    def test_cancel_hook_left_out_runs_normally(self):
        result = self._run("pass")
        self.assertEqual(result["status"], "passed")

    def test_missing_blender_is_reported_plainly(self):
        result = run_blender_test(
            None, str(self.zip_path), str(self.script_path),
            str(self.out_dir),
        )
        self.assertEqual(result["status"], "blender-missing")
        self.assertIn("Blender is not installed", result["summary"])
        result = run_blender_test(
            str(self.tmp / "no-blender-here"),
            str(self.zip_path), str(self.script_path),
            str(self.out_dir),
        )
        self.assertEqual(result["status"], "blender-missing")

    def test_broken_zip_fails_before_blender_runs(self):
        broken = self.tmp / "broken.zip"
        broken.write_text("this is not a zip file\n", encoding="utf-8")
        os.environ["FAKE_BLENDER_MODE"] = "pass"
        result = run_blender_test(
            str(self.exe), str(broken), str(self.script_path),
            str(self.out_dir),
        )
        self.assertEqual(result["status"], "failed")
        self.assertIn("not a zip file", result["summary"])
        # Blender never ran: no checks, no render, no fake output.
        self.assertEqual(result["checks"], [])
        self.assertEqual(result["renders"], [])
        self.assertEqual(result["log"], [])

    def test_missing_script_fails_plainly(self):
        os.environ["FAKE_BLENDER_MODE"] = "pass"
        result = run_blender_test(
            str(self.exe), str(self.zip_path),
            str(self.tmp / "no-script.py"), str(self.out_dir),
        )
        self.assertEqual(result["status"], "failed")
        self.assertIn("test script is missing", result["summary"])

    def test_default_timeout_is_sane(self):
        self.assertGreaterEqual(DEFAULT_TIMEOUT, 60)


class GenerateScriptTest(unittest.TestCase):
    def test_generated_script_is_valid_python(self):
        script, error = generate_test_script(
            "surprise", "surprise.randomize"
        )
        self.assertIsNone(error)
        ast.parse(script)

    def test_script_carries_the_install_enable_check_render_unload_steps(
        self,
    ):
        script, error = generate_test_script(
            "surprise", "surprise.randomize"
        )
        self.assertIsNone(error)
        for needle in (
            "package_install_files",
            "enable_on_install",
            "preferences.addons",
            "Does not crash on the empty scene",
            "Operator runs",
            "surprise.randomize",
            "render-test.png",
            "BLENDER_EEVEE_NEXT",
            "CYCLES",
            "addon_disable",
            "package_uninstall",
            "DEVSUITE-CHECK",
        ):
            self.assertIn(needle, script, needle)

    def test_legacy_script_selects_the_legacy_branch(self):
        # The template carries both install routes; the LEGACY flag
        # selects at runtime. The legacy script must set the flag
        # and carry the addon_install path.
        script, error = generate_test_script(
            "surprise", "surprise.randomize", legacy=True
        )
        self.assertIsNone(error)
        ast.parse(script)
        self.assertIn("LEGACY = True", script)
        self.assertIn("addon_install", script)
        self.assertIn("addon_enable", script)
        extension, error = generate_test_script(
            "surprise", "surprise.randomize", legacy=False
        )
        self.assertIsNone(error)
        self.assertIn("LEGACY = False", extension)
        self.assertIn("package_install_files", extension)

    def test_no_operator_means_no_operator_check(self):
        script, error = generate_test_script("surprise")
        self.assertIsNone(error)
        ast.parse(script)
        self.assertNotIn('"Operator runs"', script)
        self.assertIn('"Loads without errors"', script)
        self.assertIn('"Render is written"', script)

    def test_bad_ids_fail_plainly(self):
        script, error = generate_test_script("Surprise Pack")
        self.assertIsNone(script)
        self.assertIn("Blender id", error)
        script, error = generate_test_script(
            "surprise", "not an operator"
        )
        self.assertIsNone(script)
        self.assertIn("operator id", error)

    def test_zip_is_legacy_tells_the_two_forms_apart(self):
        with tempfile.TemporaryDirectory() as tmp:
            project, error = create_project_from_template(
                "surprise",
                Path(tmp) / "surprise",
                name="Surprise",
                targets=["blender"],
                version="1.0.0",
            )
            self.assertIsNone(error)
            extension, _, error = build_blender_addon(
                project, Path(tmp) / "out-ext"
            )
            self.assertIsNone(error)
            self.assertFalse(zip_is_legacy(extension))
            legacy, _, error = build_blender_addon(
                project, Path(tmp) / "out-legacy", legacy=True
            )
            self.assertIsNone(error)
            self.assertTrue(zip_is_legacy(legacy))
            self.assertFalse(zip_is_legacy(Path(tmp) / "no-such.zip"))

    def test_write_test_script_writes_a_real_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path, error = write_test_script(
                Path(tmp) / "test.py", "surprise", "surprise.randomize"
            )
            self.assertIsNone(error)
            self.assertTrue(Path(path).is_file())
            ast.parse(Path(path).read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
