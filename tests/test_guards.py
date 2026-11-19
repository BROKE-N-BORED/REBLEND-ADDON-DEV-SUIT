"""Guard tests (§13): the rules that hold the whole tree.

Three guards, all stdlib-only so they run on both interpreters
(system python3, where PySide6 is absent, and the Qt venv):

* No secrets in the shipped source — the suite's own scanner run
  over devsuite/, installer/, the shell scripts, the .desktop
  launcher, pyproject.toml, and DOSSIER.md.
* No blue in the workbench identity — every color literal in
  devsuite/ui/ is warm or bench-green, never blue.
* No em-dash and no bare & in visible text — every string literal
  in the shipped Python, except docstrings and two named non-visible
  constants, carries neither character. The windows show backend
  error strings verbatim, so backend modules are in scope too:
  a dash in an error message is a dash on screen.

What is NOT in scope, and why:

* tests/ is not shipped, and test_secrets_scan.py plants fake
  secrets on purpose — the secrets guard covers shipped source
  only.
* devsuite/help/entries.py has its own character test
  (test_help_entries.py) — the character guard skips the file
  rather than duplicating that test.
* The two exempt constants below are named in _NOT_VISIBLE with
  the reason each never reaches a window.
"""

import ast
import re
import shutil
import tempfile
import unittest
from pathlib import Path

from devsuite.packing.secrets_scan import scan_pack

TREE = Path(__file__).resolve().parent.parent

# Loose shipped files at the tree root (the scanner takes a folder,
# so the test copies these into a temp folder and scans that).
LOOSE_SHIPPED_FILES = [
    "install.sh",
    "uninstall.sh",
    "run.sh",
    "Install Reblend Add-on Dev Suite.desktop",
    "pyproject.toml",
    "DOSSIER.md",
]

# (relative path, enclosing assignment name) -> why it never shows.
# These are the only literals allowed to carry an em-dash or a bare &.
_NOT_VISIBLE = {
    ("devsuite/chat/loop.py", "_PLAN_SYSTEM_PROMPT"):
        "the planner's system prompt — sent to the model, never shown.",
    ("devsuite/blender_drive/scripts.py", "_SCRIPT_TEMPLATE"):
        "the generated Blender test script — runs inside Blender; "
        "only its check details reach the windows.",
}

# Whole files the character guard skips, with the reason.
_COVERED_ELSEWHERE = {
    "devsuite/help/entries.py":
        "covered by test_help_entries.py's own character test",
}

_HEX_COLOR = re.compile(r"#([0-9a-fA-F]{6}|[0-9a-fA-F]{3})\b")

# Qt named colors that are blue (a named color is another way blue
# could get into the identity). Checked as whole words in literals.
_BLUE_NAMES = {
    "blue", "navy", "darkblue", "mediumblue", "lightblue", "steelblue",
    "dodgerblue", "royalblue", "skyblue", "powderblue",
    "cornflowerblue", "midnightblue", "slateblue", "deepskyblue",
    "cadetblue",
}


def _docstring_ranges(tree):
    """Line ranges of module/class/function docstrings.

    Docstrings are developer notes, not visible text, so the
    character guard skips them.
    """
    ranges = []
    for node in ast.walk(tree):
        if (isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef,
                              ast.AsyncFunctionDef))
                and node.body and isinstance(node.body[0], ast.Expr)
                and isinstance(node.body[0].value, ast.Constant)
                and isinstance(node.body[0].value.value, str)):
            first = node.body[0].value
            ranges.append((first.lineno, first.end_lineno))
    return ranges


def _literals_with_names(path):
    """(line, value, enclosing assignment name) for every string
    literal in a module, docstrings excluded."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    docs = _docstring_ranges(tree)
    parents = {}
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            parents[child] = node
    found = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Constant)
                and isinstance(node.value, str)):
            continue
        if any(a <= node.lineno <= b for a, b in docs):
            continue
        name = None
        parent = parents.get(node)
        while parent is not None:
            if isinstance(parent, ast.Assign) \
                    and isinstance(parent.targets[0], ast.Name):
                name = parent.targets[0].id
                break
            parent = parents.get(parent)
        found.append((node.lineno, node.value, name))
    return found


def _is_blue(hex_color):
    """True when a hex color reads as blue: its blue channel is the
    largest. Bench green (#5aa75e) has green largest, so it passes;
    a blue-grey (blue largest, even slightly) does not — the
    identity is warm, and a blue tint breaks it."""
    digits = hex_color.lstrip("#")
    if len(digits) == 3:
        digits = "".join(char * 2 for char in digits)
    red = int(digits[0:2], 16)
    green = int(digits[2:4], 16)
    blue = int(digits[4:6], 16)
    return blue > red and blue > green


class SecretsGuardTests(unittest.TestCase):
    def test_shipped_source_has_no_secrets(self):
        findings = []
        for root in ("devsuite", "installer"):
            findings.extend(scan_pack(TREE / root))
        with tempfile.TemporaryDirectory() as tmp:
            for name in LOOSE_SHIPPED_FILES:
                shutil.copy(TREE / name, Path(tmp) / name)
            findings.extend(scan_pack(Path(tmp)))
        # A finding names file + line + description, never a value,
        # so it is safe to show the whole list in the failure.
        self.assertEqual(findings, [])

    def test_guard_covers_the_whole_shipped_tree(self):
        # The guard is only as good as its scope: every shipped
        # Python file must sit under one of the scanned roots.
        # Build output (build/, dist/, *.egg-info/) is not shipped
        # source — the install sims regenerate it in the tree on
        # every run, and .gitignore covers it — so it is skipped
        # here rather than scanned.
        scanned = {TREE / "devsuite", TREE / "installer"}
        skipped_top = {"tests", "render-venv", "build", "dist"}
        for path in TREE.rglob("*.py"):
            if "__pycache__" in path.parts:
                continue
            rel = path.relative_to(TREE)
            if rel.parts[0] in skipped_top:
                continue
            if rel.parts[0].endswith(".egg-info"):
                continue
            if path.name == "render_pdf.py":
                continue  # the dossier renderer, not shipped
            self.assertTrue(
                any(str(path).startswith(str(root) + "/")
                    for root in scanned),
                f"{rel} is shipped Python outside the scanned roots",
            )


class NoBlueTests(unittest.TestCase):
    def test_no_blue_hex_color_in_ui(self):
        ui_dir = TREE / "devsuite" / "ui"
        checked = 0
        for path in sorted(ui_dir.glob("*.py")):
            for match in _HEX_COLOR.finditer(
                    path.read_text(encoding="utf-8")):
                checked += 1
                self.assertFalse(
                    _is_blue(match.group(0)),
                    f"{path.name}: {match.group(0)} is blue — "
                    "the identity is warm neutrals and bench green",
                )
        # The stylesheet defines the palette; if this is zero the
        # test scanned nothing and proves nothing.
        self.assertGreater(checked, 0)

    def test_no_blue_named_color_in_ui_literals(self):
        ui_dir = TREE / "devsuite" / "ui"
        for path in sorted(ui_dir.glob("*.py")):
            for lineno, value, _name in _literals_with_names(path):
                words = set(re.findall(r"[A-Za-z]+", value.lower()))
                found = words & _BLUE_NAMES
                self.assertEqual(
                    found, set(),
                    f"{path.name}:{lineno} names a blue color: {found}",
                )

    def test_blue_check_knows_bench_green_from_blue(self):
        self.assertFalse(_is_blue("#5aa75e"))  # bench green
        self.assertFalse(_is_blue("#232019"))  # warm charcoal
        self.assertFalse(_is_blue("#f2ede3"))  # warm paper-white
        self.assertTrue(_is_blue("#4a90d9"))   # plain blue
        self.assertTrue(_is_blue("#5a6a7a"))   # blue-grey


class VisibleTextCharacterTests(unittest.TestCase):
    def test_no_em_dash_or_bare_ampersand_in_visible_text(self):
        bad = []
        for root in ("devsuite", "installer"):
            for path in sorted((TREE / root).rglob("*.py")):
                if "__pycache__" in path.parts:
                    continue
                rel = str(path.relative_to(TREE))
                if rel in _COVERED_ELSEWHERE:
                    continue
                for lineno, value, name in _literals_with_names(path):
                    if (rel, name) in _NOT_VISIBLE:
                        continue
                    if "—" in value:
                        bad.append(f"{rel}:{lineno} has an em-dash")
                    if "&" in value:
                        bad.append(f"{rel}:{lineno} has a bare &")
        self.assertEqual(bad, [])

    def test_exemptions_are_real_and_named(self):
        # An exemption must point at a literal that exists and still
        # carries the character — otherwise it is dead weight hiding
        # nothing, and a future edit could silently rely on it.
        for (rel, name), reason in _NOT_VISIBLE.items():
            self.assertTrue(reason)
            literals = _literals_with_names(TREE / rel)
            matches = [
                value for _line, value, found in literals
                if found == name
            ]
            self.assertEqual(
                len(matches), 1,
                f"{rel} should hold exactly one {name} literal",
            )
            self.assertTrue(
                "—" in matches[0] or "&" in matches[0],
                f"{rel} {name} no longer carries the character — "
                "remove the exemption",
            )
        for rel, reason in _COVERED_ELSEWHERE.items():
            self.assertTrue(reason)
            self.assertTrue((TREE / rel).is_file())


if __name__ == "__main__":
    unittest.main()
