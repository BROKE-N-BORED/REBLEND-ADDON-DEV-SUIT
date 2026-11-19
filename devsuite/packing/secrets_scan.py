"""Scan a pack folder for secret-like content before it is packed.

The rule is absolute: no secrets in code, ever. A pack must never carry
a key, a token, a password, or anything that looks like a credential.
This module is the check that enforces it — the pack builder refuses to
pack a folder this scan flags.

A finding names the file and the line, and says in plain words what the
line looks like. It NEVER includes the secret value itself: descriptions
are fixed sentences, and no matched text is ever copied into a finding.
A value is only ever read to compare it against a short list of obvious
placeholders (like "change-me"); it is never stored, returned, or
printed.

Binary files are skipped, and so is ``__pycache__`` (compiled copies
that should never be packed anyway).

Two precision rules keep the scan from refusing clean packs (§13
verification, 2026-11-17 — both were proven by running the scan over
the suite's own tree):

* An assignment whose value is code, not a written-down secret, is
  not flagged: a token taken from another variable
  (``self._build_token``), from a call (``get_token()``), or set
  to a number (``0``). The
  secret is not in the file. A quoted value always flags, and a bare
  word still flags (in a config file a bare word is a literal value).
* Bare "pass" only counts with "=" after it. Prose says "the test
  it must pass:" — that colon is not a credential. The full words
  (password, passwd, pwd) count with either separator.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

# Folders never scanned: compiled Python output.
SKIPPED_DIRS = {"__pycache__"}

# File endings treated as binary without trying to read them.
BINARY_EXTENSIONS = {
    ".blend", ".bz2", ".dll", ".exe", ".gif", ".gz", ".ico", ".jpeg",
    ".jpg", ".mp3", ".ogg", ".otf", ".pdf", ".png", ".pyc", ".rblpack",
    ".so", ".ttf", ".wav", ".woff", ".woff2", ".xz", ".zip",
}

# Values that are clearly stand-ins, not real secrets. Compared only;
# never returned or printed.
PLACEHOLDER_VALUES = {
    "", "changeme", "change-me", "change_me", "example", "none", "null",
    "placeholder", "todo", "xxx", "your-api-key", "your-api-key-here",
    "your-password", "your-password-here", "your-secret-here",
    "your-token-here",
}

# (pattern, plain-words description, is_assignment). Descriptions are
# fixed sentences: nothing matched is ever copied into them.
# Assignment patterns (name = value) get one extra step: the value after
# the = or : is checked against the placeholder list, so a stand-in like
# "change-me" is not flagged. The value is compared and dropped; it never
# leaves this module.
_PATTERNS = [
    (
        re.compile(r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----"),
        "This file holds a private key. Private keys must never be packed.",
        False,
    ),
    (
        re.compile(r"(?i)\b(api[_-]?key|apikey)\s*[:=]\s*[\"']?\S"),
        "This line sets an API key. Keys must never be packed.",
        True,
    ),
    (
        re.compile(
            r"(?i)\b(access[_-]?token|auth[_-]?token|token)\s*[:=]\s*[\"']?\S"
        ),
        "This line sets a token. Tokens must never be packed.",
        True,
    ),
    (
        re.compile(r"(?i)\b(password|passwd|pwd)\s*[:=]\s*[\"']?\S"),
        "This line sets a password. Passwords must never be packed.",
        True,
    ),
    (
        # Bare "pass" only with "=" after it: prose says "the test
        # it must pass:" and that colon is not a credential. A real
        # assignment still flags.
        re.compile(r"(?i)\bpass\s*=\s*[\"']?\S"),
        "This line sets a password. Passwords must never be packed.",
        True,
    ),
    (
        re.compile(
            r"(?i)\b(client[_-]?secret|secret[_-]?key|secret)\s*[:=]\s*[\"']?\S"
        ),
        "This line sets a secret value. Secrets must never be packed.",
        True,
    ),
    (
        re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
        "This line looks like a cloud access key. Keys must never be packed.",
        False,
    ),
    (
        re.compile(r"\b(ghp_|github_pat_)[A-Za-z0-9_]+"),
        "This line looks like a GitHub token. Tokens must never be packed.",
        False,
    ),
    (
        re.compile(r"\bsk-[A-Za-z0-9]{20,}\b"),
        "This line looks like a service key. Keys must never be packed.",
        False,
    ),
    (
        re.compile(r"\bxox[baprs]-[A-Za-z0-9-]+\b"),
        "This line looks like a Slack token. Tokens must never be packed.",
        False,
    ),
]


def scan_pack(root) -> list[dict]:
    """Scan every readable text file under ``root`` for secret-like lines.

    Returns a list of findings. Each finding is a dict with:

    * ``file`` — the file's path, relative to ``root``.
    * ``line`` — the line number, starting at 1.
    * ``description`` — a plain-words sentence saying what the line
      looks like. Never contains the secret value.

    An empty list means nothing secret-like was found. Files that cannot
    be read as text are skipped quietly.
    """
    root = Path(root)
    findings: list[dict] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIPPED_DIRS]
        for filename in sorted(filenames):
            path = Path(dirpath) / filename
            findings.extend(_scan_file(path, root))
    return findings


def _scan_file(path: Path, root: Path) -> list[dict]:
    if path.suffix.lower() in BINARY_EXTENSIONS:
        return []
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        # Unreadable, or not text: nothing we can check here.
        return []
    try:
        display = str(path.relative_to(root))
    except ValueError:
        display = str(path)
    findings: list[dict] = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        description = _describe_line(line)
        if description is not None:
            findings.append(
                {"file": display, "line": lineno, "description": description}
            )
    return findings


def _describe_line(line: str) -> str | None:
    """Return the plain-words description if the line looks secret-like.

    One finding per line: the first matching pattern wins. Returns None
    for a clean line, or for an assignment holding only a placeholder.
    """
    for pattern, description, is_assignment in _PATTERNS:
        match = pattern.search(line)
        if match is None:
            continue
        if is_assignment:
            value = _assigned_value(line, match)
            if value is not None:
                cleaned = value.strip("\"' ").lower()
                if cleaned in PLACEHOLDER_VALUES:
                    return None
                # Reading a secret from the environment at run time does
                # not put the secret in the pack, so it is not flagged.
                if cleaned.startswith(("os.environ", "os.getenv", "getenv(")):
                    return None
                # A value that is code, not a written-down secret, is
                # not flagged: an attribute (a token taken from
                # self._build_token), a call (a token from
                # get_token()), or a number (a token set to 0). The
                # secret is not in the file; the code produces the
                # value at run time. This only applies to unquoted
                # values — a quoted value is always a literal, so it
                # always flags.
                if not value.lstrip().startswith(("\"", "'")):
                    first = cleaned.split(None, 1)[0] if cleaned else ""
                    if re.match(r"^[A-Za-z_][A-Za-z0-9_]*\s*[\.(]", cleaned):
                        return None
                    if re.match(r"^-?\d+(\.\d+)?$", first):
                        return None
        return description
    return None


def _assigned_value(line: str, match: re.Match) -> str | None:
    """The value after the = or : in an assignment match, if there is one.

    Used only to compare against the placeholder list. The caller never
    stores or returns this value.
    """
    matched = line[match.start():match.end()]
    for i, char in enumerate(matched):
        if char in "=:":
            return line[match.start() + i + 1:].strip()
    return None
