"""The How to Use index entries (DOSSIER.md §6.10, U22).

Every entry is a dict with a title, a one-line summary, and a body
written in short plain sentences. The three journeys from §3 are
the first three entries, in the dossier's order, and the rest
cover the windows that exist today and the loop that drives them.

The text says what exists. Windows that are not built yet (the
Reblend render window, the Reblend test window) are named only
where the dossier's build sequence says they are coming, in one
line each: they wait on the Reblend pack loader. Nothing here
describes a feature Joshua cannot use today.

Two house rules, enforced by the tests: no em-dash in any title,
summary, or body (visible UI text carries none), and no bare "&"
(the word is always "and").
"""

from __future__ import annotations

#: The index, in the order the help window shows it. The three
#: journeys from §3 come first (DOSSIER.md §6.10), then the
#: windows and the loop.
ENTRIES = [
    {
        "title": "Journey A: A new Reblend add-on from an idea",
        "summary": (
            "Describe the idea in chat, approve the plan, build it, "
            "pack it, install it in Reblend."
        ),
        "body": "\n\n".join([
            "Start in the chat window. Tell the suite what the "
            "add-on should do, in plain words. One idea at a time "
            "works best.",
            "The chat answers with a short plan: what it will "
            "build, which files it will touch, and what it is for. "
            "Nothing is built until you tap Build it.",
            "When the build is done, open the pack window. It "
            "shows the manifest as it will be written, and the "
            "pre-pack report. Tap Build Reblend pack, then Install "
            "in Reblend.",
            "Seeing the add-on run inside the suite, and running "
            "its Reblend checks here, waits on the Reblend pack "
            "loader, which is still being built.",
        ]),
    },
    {
        "title": "Journey B: A new Blender add-on from an idea",
        "summary": (
            "The same front door, with a Blender add-on at the end "
            "and a test run to prove it."
        ),
        "body": "\n\n".join([
            "Start in the chat window, the same as a Reblend "
            "add-on. Say what the add-on should do. When you make "
            "the project, pick Blender as the target.",
            "Approve the plan, then build it. The Blender emitter "
            "turns the project into a standard Blender extension "
            "package: a zip with an entry file and a manifest.",
            "Open the Blender test window, pick the built add-on, "
            "and tap Run test. Blender runs in the background and "
            "the checklist and render come back here.",
            "When the checks pass, install it from the pack "
            "window, or take the zip and install it in Blender by "
            "hand. It is a normal Blender add-on either way.",
        ]),
    },
    {
        "title": "Journey C: Fix or improve a pack that already exists",
        "summary": (
            "Open the project, say what should change, approve the "
            "fix, and build it again."
        ),
        "body": "\n\n".join([
            "Open the project from the File menu, or from the "
            "library window. The chat works on the project's "
            "files and code. The pack window shows the project's "
            "last pack and its last test result.",
            "Say what should change, in plain words. The chat "
            "finds the right place and changes only that. It never "
            "rebuilds the whole add-on unless you ask it to.",
            "Every change is a plan you approve first, and every "
            "build takes a snapshot before it starts. If the "
            "change is wrong, Undo last build puts the project "
            "back.",
            "When the fix is in, build the pack again from the "
            "pack window. Bump the version first, so the new pack "
            "is a new file.",
        ]),
    },
    {
        "title": "The chat window",
        "summary": (
            "The front door and the heart of the suite. The "
            "conversation is the work."
        ),
        "body": "\n\n".join([
            "Everything starts here. You describe what you want in "
            "plain words, and the suite plans it, builds it, and "
            "shows you the result.",
            "The text box is the center of the window. Above it is "
            "the conversation: what you asked, what the suite "
            "planned, and what it built.",
            "The status line at the bottom says what is happening "
            "right now, and how long it has taken. Long work can "
            "be cancelled.",
            "The Window menu opens the other windows: Pack, "
            "Library, Blender test, and the command palette. The "
            "File menu opens and makes projects.",
        ]),
    },
    {
        "title": "The Plan, Approve, Build loop",
        "summary": "Every job follows the same loop, and the loop is visible.",
        "body": "\n\n".join([
            "Ask. Describe what you want in plain words. The chat "
            "asks one question at a time, only when the answer "
            "changes the work.",
            "Plan. The chat answers with a short plan: what it "
            "will build, which files it will touch, and which "
            "target it is for. The plan is shown before anything "
            "is built.",
            "Approve. Tap Build it, or edit the plan in chat "
            "first. Approval covers exactly the plan shown. If "
            "the work needs something the plan did not cover, the "
            "chat stops and asks.",
            "Build. The work happens in the open: each step named "
            "as it runs, files listed as they change. Cancel is "
            "always available.",
            "Show. The result appears where it belongs: the test "
            "window for checks, the pack window for the built "
            "file. The chat summarizes what changed, with the "
            "proof attached.",
        ]),
    },
    {
        "title": "Undo",
        "summary": (
            "Every build takes a snapshot first. Undo last build "
            "puts the project back."
        ),
        "body": "\n\n".join([
            "Before a build touches any file, the suite snapshots "
            "the files the plan will change. The snapshot stays "
            "until you undo it.",
            "Undo last build restores those files exactly, and "
            "removes files the build created. The chat says what "
            "it undid.",
            "Undo is in the chat window, at the top right, and in "
            "the command palette. A cancelled build keeps its "
            "snapshot too, so it can still be undone.",
        ]),
    },
    {
        "title": "The pack window",
        "summary": "Where a project becomes a file you can install.",
        "body": "\n\n".join([
            "The pack window shows the manifest as the suite will "
            "write it: name, version, targets, contributions, and "
            "permissions. Every field has a plain-words line "
            "underneath it.",
            "The wheel button editor adds buttons to the Reblend "
            "wheel. Each button needs a label and an action. "
            "Buttons save to the project at once.",
            "The pre-pack report runs first: a secrets check, a "
            "manifest check, and the last test result. A secret in "
            "the files that would ship stops the build, and the "
            "report names the file and line.",
            "Build Reblend pack makes a .rblpack file. Build "
            "Blender add-on makes a Blender extension zip. Both "
            "land in the project's packs folder.",
            "Bump version raises the patch number by one, for "
            "example 1.0.0 to 1.0.1. Install buttons work only "
            "when a pack built from the current version is sitting "
            "in the packs folder.",
            "Install copies the built file into Reblend or "
            "Blender, and says exactly where it put it. The first "
            "install asks which folder; the suite remembers it "
            "after that.",
        ]),
    },
    {
        "title": "What unproven means",
        "summary": (
            "A pack built without a test run proving it. Test it by "
            "hand before trusting it."
        ),
        "body": "\n\n".join([
            "A pack is proven when a test run has checked it and "
            "the checks passed. A pack built with no test run "
            "behind it is unproven.",
            "Unproven is a warning, not a refusal. The suite "
            "builds the pack and says so plainly, so you know to "
            "test it by hand before trusting it.",
            "Blender add-ons are proven in the Blender test "
            "window. Reblend packs are proven when the Reblend "
            "test window exists, which waits on the pack loader.",
            "The pack window and the library both show the last "
            "test result for a pack, or say plainly that it has "
            "not been tested yet.",
        ]),
    },
    {
        "title": "The library window",
        "summary": (
            "Every pack the suite has built, and the templates to "
            "start from."
        ),
        "body": "\n\n".join([
            "Each built pack is a card: its icon, name, version, "
            "target, last test result, and a one-line description. "
            "The newest builds sit first.",
            "Open project opens the pack's project in the chat "
            "window. Reinstall copies the built file into Reblend "
            "or Blender again.",
            "Delete removes the built file and its shelf entry. It "
            "asks first, and the answer defaults to No.",
            "A pack whose file was moved or deleted outside the "
            "suite says so plainly. Remove from the shelf takes "
            "only the record, and leaves the project alone.",
            "Templates sit below the built packs. Start a project "
            "makes a new project from a template, with real "
            "working code.",
        ]),
    },
    {
        "title": "The Blender test window",
        "summary": (
            "Run a built Blender add-on through Blender and see the "
            "checklist and render come back."
        ),
        "body": "\n\n".join([
            "Pick one of the built Blender add-ons in the "
            "project's packs folder, then tap Run test. Nothing is "
            "picked for you.",
            "Blender runs in the background for this test. The "
            "suite installs the add-on into a throwaway Blender "
            "setup, runs five checks, renders one frame, and "
            "uninstalls it again. Your real Blender setup is never "
            "touched.",
            "The five checks: it loads without errors, it does not "
            "crash on the empty scene, its operator runs on a test "
            "cube, a render is written, and it unloads clean.",
            "When the run finishes, the checklist shows each check "
            "with its result, the render shows below, and the "
            "Blender log is one click away. A failed run says "
            "which checks failed and why.",
            "A test can take minutes. Cancel stops it. Closing the "
            "window stops the run too.",
            "To try the add-on by hand, install it from the pack "
            "window and open Blender.",
        ]),
    },
    {
        "title": "The command palette",
        "summary": (
            "Press Ctrl+K, type a command, run it. Every command in "
            "the suite, searchable by name."
        ),
        "body": "\n\n".join([
            "Ctrl+K opens the palette over the chat window. Type a "
            "few letters to narrow the list, then press Enter to "
            "run the command, or click it.",
            "Every command shows its shortcut beside it, so the "
            "palette teaches as it serves. Menus and buttons still "
            "exist for everything. The palette is a shortcut, "
            "never the only path.",
            "With nothing typed, nothing is selected, and Enter "
            "does nothing. Once you have typed, the first match is "
            "selected.",
            "A command that cannot run right now says so plainly "
            "in the chat: no project open, a project that does not "
            "target that program, or nothing to undo.",
        ]),
    },
    {
        "title": "What the chat cannot do",
        "summary": (
            "The chat builds add-ons. It cannot install, delete, or "
            "change anything outside the project."
        ),
        "body": "\n\n".join([
            "The chat cannot install anything, delete anything, "
            "change Reblend itself, change the suite's own code, "
            "or touch the network.",
            "It reads only the project and its reference folders. "
            "It never reads files outside them.",
            "Deleting a pack is your tap in the library window, "
            "and it asks first, defaulting to No. The chat never "
            "deletes for you.",
            "If a step cannot run, the chat says so with the "
            "reason, and never silently skips it.",
        ]),
    },
    {
        "title": "Where a project lives",
        "summary": (
            "One folder per project: the plan, the code, the "
            "assets, the tests, the renders, and the packs."
        ),
        "body": "\n\n".join([
            "project.json holds the project's name, description, "
            "targets, version, and wheel buttons. The suite reads "
            "and writes it; you never have to open it.",
            "src holds the code: shared code in src/shared, "
            "Reblend code in src/reblend, Blender code in "
            "src/blender. The emitters gather from these folders "
            "when they build.",
            "assets holds icons and other files that ship in the "
            "pack. tests holds the project's checks. renders holds "
            "test renders and run records, newest first.",
            "packs holds the built files: .rblpack files and "
            "Blender zips. The library window shows them as cards.",
        ]),
    },
]


def get_entries() -> list[dict]:
    """The index entries, in display order: a fresh copy each time,
    so a caller cannot rewrite the shared list by accident."""
    return [dict(entry) for entry in ENTRIES]
