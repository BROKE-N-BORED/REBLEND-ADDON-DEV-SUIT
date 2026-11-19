"""The Plan, Approve, Build loop (DOSSIER.md §7.2).

Every job follows the same loop, and the loop is visible:

1. ``build_plan`` asks the model for a plan and returns it — nothing
   is built yet.
2. The plan is shown for approval. Approval covers exactly the plan
   shown; if the work needs something the plan did not cover, the
   loop stops and asks instead of expanding the job on its own.
3. ``apply_plan`` runs the steps, but only after the ``approve``
   callback says yes. The headless driver auto-approves in tests;
   the Qt chat window wires a real approval (Build it) later.

The plan JSON schema
--------------------

A plan is one JSON object:

    {
      "summary": "Add the Surprise wheel button and its action.",
      "target": "reblend",
      "steps": [
        {"action": "write_file",
         "path": "src/reblend/addon.py",
         "content": "..."},
        {"action": "edit_file",
         "path": "src/reblend/addon.py",
         "old": "...exact text to find...",
         "new": "...replacement text..."},
        {"action": "run_check",
         "name": "Run the project tests",
         "command": ["python3", "-m", "unittest", "discover", "-s", "tests"]}
      ]
    }

* ``summary`` — required, plain words, what the plan will do.
* ``target`` — optional; "reblend", "blender", or "both". When
  missing it defaults to the project's target.
* ``steps`` — required, at least one step. Steps run in order.

Step actions:

* ``write_file`` — write ``content`` to ``path`` (relative to the
  project folder), creating parent folders. Overwrites the file if
  it already exists.
* ``edit_file`` — replace the first occurrence of ``old`` with
  ``new`` in the file at ``path``. Fails, in plain words, when the
  file is missing or ``old`` is not found in it.
* ``run_check`` — run ``command`` in the project folder and report
  pass or fail. ``command`` is a list of words, never a shell
  string, and the first word must be ``python3`` or ``python``:
  the loop runs checks, it does not install, delete, or fetch
  anything (DOSSIER.md §7.3). The list grows only when a later
  item (the Blender drive) needs a new runner.

Safety rules, enforced here rather than trusted to the model:

* Every file path must stay inside the project folder. Absolute
  paths and paths that escape with ".." are refused.
* A step that fails stops the run: later steps do not run, and the
  result names the step that failed, in plain words.
* Nothing is applied without approval — not even a plan the model
  just produced.

Snapshots and undo (§7.4) are part of the loop: after approval
and before the first step, ``apply_plan`` snapshots the files the
plan touches (see ``devsuite.chat.snapshot``). A failed snapshot
blocks the apply — the loop never builds without a way back. Undo
restores from the snapshot; snapshots are never pruned by the
suite.

Still later items, stated here so the gap is visible: streaming
replies and the chat history file (chat.jsonl).
"""

from __future__ import annotations

import json
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path

from devsuite.chat.ollama import OllamaClient
from devsuite.chat.snapshot import create_snapshot
from devsuite.projects.project import Project

# The driver seat from §7.7 / decision D6: the model that plans and
# talks. One model loaded at a time; the code and vision seats join
# in later items.
DEFAULT_DRIVER_MODEL = "qwen3.5:4b"

# The only programs a run_check step may start. Checks run with
# Python; nothing else is needed yet, and nothing else is allowed.
ALLOWED_CHECK_COMMANDS = {"python3", "python"}

PLAN_ACTIONS = ("write_file", "edit_file", "run_check")


class _Cancelled(Exception):
    """The run was cancelled. Raised inside the step loop and
    caught by ``apply_plan`` — never escapes the module."""


@dataclass
class ApplyResult:
    """What happened when a plan was (or was not) applied.

    * ``approved`` — True only when the approve callback said yes.
    * ``applied`` — True only when every step ran. False when the
      plan was refused, invalid, or a step failed part-way through.
    * ``completed`` — plain-words descriptions of the steps that ran,
      in order. Empty when nothing ran.
    * ``failed_step`` — the step that stopped the run, if any:
      {"index": 1-based step number, "action": ..., "target": the
      file or check name}. None when no step failed.
    * ``error`` — the plain-words reason nothing (or nothing more)
      ran. None when the plan applied cleanly, or when it was
      simply refused.
    * ``snapshot_id`` — the snapshot taken before the plan ran, or
      None when no snapshot was taken (refused or invalid plan).
    * ``cancelled`` — True when the run was stopped by the user
      part-way through. The snapshot still stands, so undo works
      after a cancelled build.
    """

    approved: bool
    applied: bool
    completed: list = field(default_factory=list)
    failed_step: dict | None = None
    error: str | None = None
    snapshot_id: str | None = None
    cancelled: bool = False


def build_plan(
    request: str,
    project: Project,
    client: OllamaClient | None = None,
    model: str | None = None,
) -> tuple[dict | None, str | None]:
    """Ask the model for a plan for ``request`` in ``project``.

    Returns ``(plan, error)``: ``plan`` is the validated plan dict
    (with ``target`` filled in from the project when the model left
    it out), or None when no usable plan came back; ``error`` is
    None on success, or a plain-words sentence — Ollama down, the
    model answering in a form that is not a plan, or a plan with a
    step the loop does not understand. Nothing is built here; the
    plan is for approval.
    """
    client = client or OllamaClient()
    model = model or DEFAULT_DRIVER_MODEL
    messages = [
        {"role": "system", "content": _PLAN_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": _plan_user_message(request, project),
        },
    ]
    reply, error = client.chat(model, messages)
    if error is not None:
        return None, error
    plan, error = _parse_plan_reply(reply)
    if error is not None:
        return None, error
    if "target" not in plan:
        plan["target"] = (
            "both" if len(project.targets) > 1 else project.targets[0]
        )
    ok, errors = validate_plan(plan, project)
    if not ok:
        return None, (
            "The model came back with a plan I could not use. "
            + " ".join(errors)
        )
    return plan, None


def validate_plan(plan, project: Project) -> tuple[bool, list[str]]:
    """Check a plan dict against the schema in this module's docstring.

    Returns ``(ok, errors)`` in the same plain-words form as the
    manifest validator. Never raises.
    """
    errors: list[str] = []

    if not isinstance(plan, dict):
        return False, ["The plan should be one object with a summary and steps."]

    summary = plan.get("summary")
    if not isinstance(summary, str) or not summary.strip():
        errors.append(
            "The plan needs a summary, a plain-words sentence saying "
            "what it will do."
        )

    target = plan.get("target")
    if target is not None and target not in ("reblend", "blender", "both"):
        errors.append(
            f"The plan's target '{target}' is not one I know. "
            "Use 'reblend', 'blender', or 'both'."
        )

    steps = plan.get("steps")
    if not isinstance(steps, list) or not steps:
        errors.append("The plan needs at least one step.")
        return (not errors), errors

    for index, step in enumerate(steps, start=1):
        errors.extend(_validate_step(step, index, project))

    return (not errors), errors


def plan_summary_lines(plan: dict) -> list[str]:
    """The plan as plain-words lines, for the approval screen.

    One line per step: "Write src/reblend/addon.py",
    "Change src/reblend/addon.py", "Run check: Run the project
    tests". Assumes the plan passed ``validate_plan``.
    """
    lines = []
    for step in plan.get("steps", []):
        action = step.get("action")
        if action == "write_file":
            lines.append(f"Write {step.get('path')}")
        elif action == "edit_file":
            lines.append(f"Change {step.get('path')}")
        elif action == "run_check":
            lines.append(f"Run check: {step.get('name')}")
        else:
            lines.append(f"Unknown step: {action}")
    return lines


def apply_plan(
    plan: dict,
    project: Project,
    approve,
    check_timeout: float = 120,
    cancelled=None,
) -> ApplyResult:
    """Run a plan's steps — only after ``approve`` says yes.

    ``approve`` is a callable taking the plan dict and returning
    True to build or False to leave everything alone. The headless
    driver passes a function that always approves (tests); the Qt
    window passes the real Build-it tap.

    ``cancelled`` is an optional callable returning True when the
    run should stop (the window passes a threading.Event's is_set).
    It is checked before every step and while a check runs: a
    cancelled run stops, keeps its snapshot (so undo still works),
    and reports ``cancelled=True`` with the steps that did run.

    Steps run in order. The first step that fails stops the run:
    later steps do not run, and the result names the failed step.
    A refused plan changes nothing.
    """
    ok, errors = validate_plan(plan, project)
    if not ok:
        return ApplyResult(
            approved=False,
            applied=False,
            error="The plan has a problem, so I did not run it. " + " ".join(errors),
        )

    try:
        approved = bool(approve(plan))
    except Exception:
        return ApplyResult(
            approved=False,
            applied=False,
            error="The approval step failed, so I did not run the plan. "
            "Nothing was changed.",
        )
    if not approved:
        return ApplyResult(approved=False, applied=False)

    # Snapshot first: the files this plan touches, copied before
    # anything changes. A snapshot that cannot be taken blocks the
    # apply — the loop never builds without a way back.
    touched = [
        step["path"]
        for step in plan["steps"]
        if step["action"] in ("write_file", "edit_file")
    ]
    snapshot_id, snapshot_error = create_snapshot(
        project.root, touched, plan.get("summary", "")
    )
    if snapshot_error is not None:
        return ApplyResult(
            approved=True,
            applied=False,
            error=snapshot_error,
        )

    result = ApplyResult(
        approved=True, applied=False, snapshot_id=snapshot_id
    )
    try:
        for index, step in enumerate(plan["steps"], start=1):
            if cancelled is not None and cancelled():
                raise _Cancelled()
            description, error = _run_step(
                step, project, check_timeout, cancelled
            )
            if error is not None:
                result.failed_step = {
                    "index": index,
                    "action": step["action"],
                    "target": step.get("path") or step.get("name", ""),
                }
                result.error = error
                return result
            result.completed.append(description)
    except _Cancelled:
        result.cancelled = True
        result.error = "You cancelled the build."
        return result
    result.applied = True
    return result


def _validate_step(step, index: int, project: Project) -> list[str]:
    if not isinstance(step, dict):
        return [f"Step {index} should be an object with an action in it."]
    action = step.get("action")
    if action not in PLAN_ACTIONS:
        return [
            f"Step {index} asks for '{action}', which is not an action "
            "I know. The actions are: write_file, edit_file, run_check."
        ]
    if action in ("write_file", "edit_file"):
        return _validate_file_step(step, index, project)
    return _validate_check_step(step, index)


def _validate_file_step(step, index: int, project: Project) -> list[str]:
    errors = []
    path = step.get("path")
    if not isinstance(path, str) or not path.strip():
        errors.append(f"Step {index} needs a file path to work on.")
    else:
        _, error = _safe_path(project, path)
        if error is not None:
            errors.append(f"Step {index}: {error}")
    if step["action"] == "write_file":
        if not isinstance(step.get("content"), str):
            errors.append(
                f"Step {index} needs the file's content as text."
            )
    else:
        old = step.get("old")
        new = step.get("new")
        if not isinstance(old, str) or not old:
            errors.append(
                f"Step {index} needs the exact text to find, as 'old'."
            )
        if not isinstance(new, str):
            errors.append(
                f"Step {index} needs the replacement text, as 'new'."
            )
    return errors


def _validate_check_step(step, index: int) -> list[str]:
    errors = []
    name = step.get("name")
    if not isinstance(name, str) or not name.strip():
        errors.append(
            f"Step {index} needs a name, a plain-words sentence saying "
            "what the check does."
        )
    command = step.get("command")
    if (not isinstance(command, list) or not command
            or not all(isinstance(word, str) and word for word in command)):
        errors.append(
            f"Step {index} needs a command as a list of words, "
            "like ['python3', '-m', 'unittest']."
        )
    elif Path(command[0]).name not in ALLOWED_CHECK_COMMANDS:
        errors.append(
            f"Step {index} wants to run '{command[0]}', which I do not "
            "run. Checks run with python3. The loop does not install, "
            "delete, or fetch anything."
        )
    return errors


def _safe_path(project: Project, path: str) -> tuple[Path | None, str | None]:
    """Resolve ``path`` inside the project folder, or refuse it.

    Returns ``(resolved, error)``: ``resolved`` is the absolute path
    when ``path`` stays inside the project, or None with a
    plain-words reason when it is absolute or escapes the folder.
    """
    candidate = Path(path)
    if candidate.is_absolute():
        return None, (
            f"The path '{path}' is an absolute path. "
            "Plans only touch files inside the project, named "
            "relative to it, like src/reblend/addon.py."
        )
    root = project.root.resolve()
    resolved = (root / candidate).resolve()
    if not resolved.is_relative_to(root):
        return None, (
            f"The path '{path}' leaves the project folder. "
            "Plans only touch files inside the project."
        )
    return resolved, None


def _run_step(step: dict, project: Project, check_timeout: float,
              cancelled=None):
    """Run one validated step. Returns ``(description, error)``:
    the plain-words description when it ran, or None plus the
    plain-words reason when it failed. Raises ``_Cancelled`` when
    the run is cancelled mid-step.
    """
    action = step["action"]
    if action == "write_file":
        return _run_write_file(step, project)
    if action == "edit_file":
        return _run_edit_file(step, project)
    return _run_check(step, project, check_timeout, cancelled)


def _run_write_file(step: dict, project: Project):
    path, _ = _safe_path(project, step["path"])
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(step["content"], encoding="utf-8")
    except OSError:
        return None, (
            f"I could not write {step['path']}. "
            "Check the project folder can be written to."
        )
    return f"Wrote {step['path']}", None


def _run_edit_file(step: dict, project: Project):
    path, _ = _safe_path(project, step["path"])
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None, (
            f"I could not change {step['path']} because the file is not "
            "there. The plan may be out of date. Ask the chat to look "
            "again."
        )
    except (OSError, UnicodeDecodeError):
        return None, (
            f"I could not read {step['path']}, so I could not change it."
        )
    if step["old"] not in text:
        return None, (
            f"I could not change {step['path']}: the text the plan asked "
            "me to find is not in the file any more. The file may have "
            "changed since the plan was made. Ask the chat to look again."
        )
    try:
        path.write_text(text.replace(step["old"], step["new"], 1), encoding="utf-8")
    except OSError:
        return None, (
            f"I could not write the change back to {step['path']}."
        )
    return f"Changed {step['path']}", None


def _run_check(step: dict, project: Project, check_timeout: float,
               cancelled=None):
    """Run a check, watching for cancel and for the timeout.

    The command runs with its output piped; the wait loop polls so
    a cancel stops the check promptly instead of waiting for the
    timeout. A cancelled check raises ``_Cancelled``; a timed-out
    check is stopped and reported as a failure.
    """
    try:
        proc = subprocess.Popen(
            step["command"],
            cwd=project.root,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
    except OSError:
        return None, (
            f"The check '{step['name']}' could not start. "
            f"'{step['command'][0]}' may not be installed."
        )
    started = time.monotonic()
    output = ""
    while True:
        try:
            output, _ = proc.communicate(timeout=0.1)
            break
        except subprocess.TimeoutExpired:
            if cancelled is not None and cancelled():
                proc.kill()
                proc.communicate()
                raise _Cancelled()
            if time.monotonic() - started > check_timeout:
                proc.kill()
                proc.communicate()
                return None, (
                    f"The check '{step['name']}' took too long. It ran "
                    f"past {int(check_timeout)} seconds, so I stopped it."
                )
    if proc.returncode != 0:
        tail = _output_tail(output)
        detail = f" The last lines it printed were:\n{tail}" if tail else ""
        return None, (
            f"The check '{step['name']}' failed "
            f"(it finished with code {proc.returncode}).{detail}"
        )
    return f"Ran check: {step['name']}", None


def _output_tail(output: str, lines: int = 10) -> str:
    """The last few non-blank lines of a command's output, for a
    failure message. Empty when the command printed nothing.
    """
    kept = [line for line in output.splitlines() if line.strip()]
    return "\n".join(kept[-lines:])


def _parse_plan_reply(reply: str) -> tuple[dict | None, str | None]:
    """Pull the plan JSON out of a model reply.

    Small local models often wrap their JSON in a fenced code block,
    or add a sentence around it. Fences are stripped, and a reply
    with prose around the JSON is read by finding the outermost
    braces. Anything that still is not JSON comes back as a
    plain-words error, never a crash.
    """
    text = reply.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else ""
        if text.rstrip().endswith("```"):
            text = text.rstrip()[:-3]
        text = text.strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end <= start:
            return None, (
                "The model answered, but its answer was not a plan I could "
                "read. Ask it to try again, in plain words."
            )
        try:
            data = json.loads(text[start:end + 1])
        except json.JSONDecodeError:
            return None, (
                "The model answered, but its answer was not a plan I could "
                "read. Ask it to try again, in plain words."
            )
    if not isinstance(data, dict):
        return None, (
            "The model answered, but its answer was not a plan I could "
            "read. Ask it to try again, in plain words."
        )
    return data, None


def _plan_user_message(request: str, project: Project) -> str:
    files = _project_file_list(project)
    file_list = "\n".join(f"- {name}" for name in files) or "- (no files yet)"
    return (
        f"Project: {project.name} (targets: {', '.join(project.targets)}).\n"
        f"Files in the project:\n{file_list}\n\n"
        f"Request: {request}"
    )


def _project_file_list(project: Project) -> list[str]:
    """The project's files, relative to the project folder, sorted —
    so the model plans against what is really there. Skips compiled
    Python output and hidden folders.
    """
    names = []
    for path in sorted(project.root.rglob("*")):
        if path.is_dir():
            continue
        if "__pycache__" in path.parts:
            continue
        if any(part.startswith(".") for part in path.relative_to(project.root).parts):
            continue
        names.append(str(path.relative_to(project.root)))
    return names


_PLAN_SYSTEM_PROMPT = """You are the planner for the Reblend Add-on Dev Suite, a program that authors add-on packs for Reblend and Blender. Answer with ONE JSON object and nothing else — no explanation outside the JSON. The object has this shape:

{
  "summary": "One plain-words sentence saying what the plan will do.",
  "target": "reblend",
  "steps": [
    {"action": "write_file", "path": "src/reblend/addon.py", "content": "the full file text"},
    {"action": "edit_file", "path": "src/reblend/addon.py", "old": "exact text to find", "new": "replacement text"},
    {"action": "run_check", "name": "Run the project tests", "command": ["python3", "-m", "unittest", "discover", "-s", "tests"]}
  ]
}

Rules: keep the plan small — a few steps, the smallest change that does the job. File paths are relative to the project folder and must stay inside it. Only write or edit files inside the project. A run_check command is a list of words starting with python3; never propose installing, deleting, or fetching anything. "target" is "reblend", "blender", or "both"."""
