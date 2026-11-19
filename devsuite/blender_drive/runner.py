"""Run a Blender add-on test in background mode (DOSSIER.md §8.3).

The shape is SKULLPT's proven one
(``skullpt/blender_export.py``): find the Blender executable, run
``blender --background --factory-startup --python <script>`` as a
subprocess, and read the results back. A timeout is a result, not
an explosion; a missing Blender is a plain-words report, never a
crash. The suite never downloads or bundles Blender.

The test script reports its checks on stdout, one JSON object per
line (see ``scripts.py`` for the line format). The runner parses
those lines, collects the renders the script wrote, and writes the
test run record (``result.json``, §9.4) into the run folder.

Isolation: the test installs the add-on into Blender, so the run
must not touch Joshua's real Blender setup. The runner points
Blender at a throwaway config inside the run folder
(``BLENDER_USER_CONFIG`` / ``BLENDER_USER_SCRIPTS`` — the Blender
Manual's environment-variable override, documented for exactly
this: "isolating an instance from the default user files to
prevent automated tasks from accessing user configuration"). The
test script also uninstalls the add-on when it finishes, so even
if the isolation ever failed, the test cleans up after itself.

The add-on zip and the output folder reach the script through
environment variables (``DEVSUITE_ADDON_ZIP``,
``DEVSUITE_OUT_DIR``) — the same env-var handoff SKULLPT uses for
its engine choice, and simpler than parsing ``sys.argv`` after
``--`` inside Blender.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
import zipfile
from datetime import date
from pathlib import Path

#: The environment variable that overrides the Blender search, the
#: way SKULLPT's DESIGNSHELL_BLENDER does. A path that does not
#: exist is ignored, and the normal search runs instead.
BLENDER_ENV_VAR = "DEVSUITE_BLENDER"

#: How long a test run may take before it is a timeout. Blender
#: cold-starts slowly on a small PC, and a render takes a while —
#: five minutes is a generous default the caller can raise.
DEFAULT_TIMEOUT = 300

#: How many lines of Blender's output the result keeps. The full
#: log can run to thousands of lines; the tail is where the failure
#: is.
LOG_TAIL_LINES = 40

#: The prefix that marks a check report line on Blender's stdout.
CHECK_PREFIX = "DEVSUITE-CHECK "

#: Statuses a run can end in. "passed" and "failed" come from the
#: script's own checks; "timeout" when Blender ran past the limit;
#: "blender-missing" when there is no Blender to run; "crashed"
#: when Blender died before reporting anything; "cancelled" when
#: the user stopped the run.
STATUSES = ("passed", "failed", "timeout", "blender-missing",
            "crashed", "cancelled")


def find_blender() -> str | None:
    """Locate a Blender executable, or None when there is none.

    Search order (DOSSIER.md §8.3, SKULLPT's pattern):

    1. The ``DEVSUITE_BLENDER`` environment variable, when it names
       a file that exists.
    2. The ``~/.local/bin/blender`` symlink — how Blender 5.3.0 on
       his PC is found.
    3. ``blender`` on PATH.
    4. The usual install spots: ``/opt/blender/blender``,
       ``/usr/bin/blender``, ``/snap/bin/blender``.

    Never raises; a missing Blender is a plain None.
    """
    env = os.environ.get(BLENDER_ENV_VAR)
    if env and Path(env).is_file():
        return env
    symlink = Path.home() / ".local" / "bin" / "blender"
    if symlink.is_file():
        return str(symlink)
    found = shutil.which("blender")
    if found:
        return found
    for candidate in (
        "/opt/blender/blender",
        "/usr/bin/blender",
        "/snap/bin/blender",
    ):
        if Path(candidate).is_file():
            return candidate
    return None


def run_blender_test(blender_exe, addon_zip, test_script_path, out_dir,
                     timeout=DEFAULT_TIMEOUT, cancelled=None) -> dict:
    """Run one Blender add-on test and return the result.

    ``blender_exe`` is the Blender executable (usually
    ``find_blender()``'s answer; None means no Blender was found).
    ``addon_zip`` is the built add-on zip (extension or legacy),
    ``test_script_path`` the generated test script (see
    ``scripts.py``), ``out_dir`` the run folder — the caller names
    it (a dated folder under the project's ``renders/``, §9.4) and
    the runner writes ``result.json`` into it beside the renders.

    ``cancelled`` is an optional callable returning True when the
    run should stop (U26 — a Blender run can take minutes, so the
    test window offers cancel). A cancelled run kills Blender and
    comes back with status "cancelled" and the checks that had
    finished.

    Returns a dict: ``status`` (one of STATUSES), ``summary`` (one
    plain-words sentence), ``checks`` (each ``name`` + ``passed`` +
    ``detail``), ``renders`` (render file names in the run folder),
    ``log`` (the last lines of Blender's output), ``elapsed_seconds``,
    ``record_path`` (the result.json written, or None), and
    ``record_error`` (a plain sentence when the record could not be
    written, else None). Never raises: a bad input, a missing
    Blender, a timeout, or a Blender crash all come back as a
    result with a plain summary.
    """
    started = time.monotonic()
    try:
        return _run_blender_test(
            blender_exe, addon_zip, test_script_path, out_dir,
            timeout, cancelled, started,
        )
    except Exception:
        # A bad input must never crash the suite. Anything
        # unexpected lands here as one sentence.
        return {
            "status": "failed",
            "summary": (
                "I could not run this Blender test. The project may "
                "be damaged. Check its folder opens and its files "
                "can be read."
            ),
            "checks": [],
            "renders": [],
            "log": [],
            "elapsed_seconds": round(time.monotonic() - started, 1),
            "record_path": None,
            "record_error": None,
            "addon_zip": str(addon_zip),
            "blender_exe": str(blender_exe) if blender_exe else None,
        }


def _run_blender_test(blender_exe, addon_zip, test_script_path, out_dir,
                      timeout, cancelled, started):
    result = {
        "status": "failed",
        "summary": "",
        "checks": [],
        "renders": [],
        "log": [],
        "elapsed_seconds": 0.0,
        "record_path": None,
        "record_error": None,
        "addon_zip": str(addon_zip),
        "blender_exe": str(blender_exe) if blender_exe else None,
    }

    if not blender_exe or not Path(blender_exe).is_file():
        result["status"] = "blender-missing"
        result["summary"] = (
            "Blender is not installed, so Blender tests cannot "
            "run. The Reblend side still works fully."
        )
        return _finish(result, out_dir, started)

    zip_path = Path(addon_zip)
    if not zip_path.is_file() or not zipfile.is_zipfile(zip_path):
        # Checked before Blender runs: a broken zip is the suite's
        # problem to report, not Blender's to choke on.
        result["summary"] = (
            "I could not test this add-on because the built file is "
            f"not a zip file: {zip_path.name}. Build the add-on "
            "again from the pack window."
        )
        return _finish(result, out_dir, started)

    script_path = Path(test_script_path)
    if not script_path.is_file():
        result["summary"] = (
            "I could not run this Blender test because the test "
            "script is missing. Generate it again from the test "
            "window."
        )
        return _finish(result, out_dir, started)

    run_dir = Path(out_dir)
    try:
        run_dir.mkdir(parents=True, exist_ok=True)
    except OSError:
        result["summary"] = (
            "I could not write to the folder the test results "
            "should go in. Check the folder exists and can be "
            "written to."
        )
        return _finish(result, run_dir, started)

    env = dict(os.environ)
    env["DEVSUITE_ADDON_ZIP"] = str(zip_path)
    env["DEVSUITE_OUT_DIR"] = str(run_dir)
    # Throwaway Blender config inside the run folder: the test
    # install never touches his real Blender setup.
    env["BLENDER_USER_CONFIG"] = str(run_dir / "blender-config")
    env["BLENDER_USER_SCRIPTS"] = str(run_dir / "blender-scripts")

    # The wait loop polls (the same shape as the loop's _run_check),
    # so a cancel stops Blender promptly instead of waiting for the
    # timeout, and a timeout is still a result, not an explosion.
    timed_out = False
    was_cancelled = False
    try:
        proc = subprocess.Popen(
            [str(blender_exe), "--background", "--factory-startup",
             "--python", str(script_path)],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, env=env,
        )
    except OSError:
        result["status"] = "blender-missing"
        result["summary"] = (
            "Blender was found, but it could not be started. It may "
            "have moved or been removed. Check it still opens."
        )
        return _finish(result, run_dir, started)
    run_started = time.monotonic()
    stdout, stderr = "", ""
    while True:
        try:
            stdout, stderr = proc.communicate(timeout=0.1)
            break
        except subprocess.TimeoutExpired:
            if cancelled is not None and cancelled():
                proc.kill()
                stdout, stderr = proc.communicate()
                was_cancelled = True
                break
            if time.monotonic() - run_started > timeout:
                proc.kill()
                stdout, stderr = proc.communicate()
                timed_out = True
                break
    output = (stdout or "") + "\n" + (stderr or "")
    exit_code = proc.returncode

    checks = parse_checks(output)
    result["checks"] = checks
    result["log"] = _tail_lines(output)
    result["renders"] = sorted(
        path.name for path in run_dir.glob("*.png")
        if path.is_file() and path.stat().st_size > 0
    )

    if was_cancelled:
        result["status"] = "cancelled"
        result["summary"] = "The test was cancelled."
    elif timed_out:
        result["status"] = "timeout"
        done = sum(1 for c in checks if c["passed"])
        result["summary"] = (
            f"Blender ran past the {timeout}-second limit, so the "
            f"test stopped. {done} of {len(checks)} checks had "
            "finished. Try again, or give the test more time."
            if checks else
            f"Blender ran past the {timeout}-second limit before "
            "it reported anything, so the test stopped. Try again, "
            "or give the test more time."
        )
    elif not checks:
        result["status"] = "crashed"
        result["summary"] = (
            "Blender stopped before it reported any checks. The "
            "log below shows where it got to."
            if exit_code not in (0, None) else
            "Blender finished without reporting any checks. The "
            "test script may be damaged. Generate it again."
        )
    elif all(check["passed"] for check in checks):
        result["status"] = "passed"
        result["summary"] = (
            f"All {len(checks)} checks passed in Blender."
        )
    else:
        failed = [c for c in checks if not c["passed"]]
        result["status"] = "failed"
        names = ", ".join(c["name"] for c in failed)
        result["summary"] = (
            f"{len(failed)} of {len(checks)} checks failed in "
            f"Blender: {names}."
        )
    return _finish(result, run_dir, started)


def _finish(result, out_dir, started):
    """Fill in the elapsed time and write the run record."""
    result["elapsed_seconds"] = round(time.monotonic() - started, 1)
    record_path = Path(out_dir) / "result.json"
    record = {
        "status": result["status"],
        "summary": result["summary"],
        "checks": result["checks"],
        "renders": result["renders"],
        "log": result["log"],
        "elapsed_seconds": result["elapsed_seconds"],
        "addon_zip": result["addon_zip"],
        "blender_exe": result["blender_exe"],
        "date": date.today().isoformat(),
    }
    try:
        Path(out_dir).mkdir(parents=True, exist_ok=True)
        record_path.write_text(
            json.dumps(record, indent=2) + "\n", encoding="utf-8"
        )
        result["record_path"] = str(record_path)
    except OSError:
        # The run still counts: the record is a file, not the run.
        result["record_error"] = (
            "The test ran, but I could not write its record "
            "(result.json). Check the run folder can be written to."
        )
    return result


def parse_checks(output: str) -> list[dict]:
    """Pull the check reports out of Blender's output.

    The test script prints one line per check:
    ``DEVSUITE-CHECK {"name": ..., "passed": ..., "detail": ...}``.
    Lines that are not check reports, and reports with a mistake in
    them, are skipped — Blender's own output is noisy, and a broken
    line must never crash the parse.
    """
    checks: list[dict] = []
    for line in output.splitlines():
        if not line.startswith(CHECK_PREFIX):
            continue
        try:
            data = json.loads(line[len(CHECK_PREFIX):])
        except json.JSONDecodeError:
            continue
        if not isinstance(data, dict):
            continue
        name = data.get("name")
        passed = data.get("passed")
        if not isinstance(name, str) or not name:
            continue
        if not isinstance(passed, bool):
            continue
        detail = data.get("detail", "")
        checks.append({
            "name": name,
            "passed": passed,
            "detail": detail if isinstance(detail, str) else "",
        })
    return checks


def _tail_lines(output: str) -> list[str]:
    """The last lines of Blender's output, blank lines dropped."""
    lines = [line for line in output.splitlines() if line.strip()]
    return lines[-LOG_TAIL_LINES:]
