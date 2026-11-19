"""The silent update check (standing order, 2026-11-17): ask GitHub
whether a newer Release of the suite is out, and say nothing when
there is not one.

On launch the app asks GitHub's public releases endpoint for the
latest release and compares its tag against the running version.
The request is a plain GET to a public endpoint — it sends no
identifying information and needs no token — and it never
downloads or installs anything: that half lives in
``devsuite.update.apply`` and only runs after Joshua taps Update.

``check_for_update`` is the one-call API the chat window's worker
uses: it never raises for a network or parsing problem — a failed
check comes back as state "unknown" with a plain reason, so the
window can stay silent on launch (a failed silent check is no
news) and say so plainly on a manual check. A 404 (the repo does
not exist yet, or has no releases) is "unknown" too, never an
error: the repo is Joshua's to create (dossier D8), and until
then there is simply nothing to check against.

The release convention (what the release process must carry —
``apply`` depends on it):

- One asset holding the release tree: a zip whose name ends in
  ``.zip`` and whose root holds ``pyproject.toml`` (a single
  top-level folder holding it is accepted too). The asset is
  named ``reblend-addon-dev-suite-<version>.zip``.
- Its checksum sidecar, named the zip name plus ``.sha256``,
  holding the SHA-256 of the zip in ``sha256sum`` form
  (``<hex>  <filename>`` — a bare hex line is accepted too).

A release carrying no zip, or a zip with no sidecar, cannot be
pulled through the verified path, so the check reports it as
"unknown" with a plain reason instead of offering an update it
cannot install safely. GitHub's own source zipball is never used:
it has no checksum sidecar, so it cannot go through the verified
path.

Version tags that do not look like versions (anything but an
optional "v" followed by numbers and dots) are treated the same
way, and a local version newer than the latest release (a dev
tree) is simply "current" — neither is an error.
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from pathlib import Path

#: The suite's repo, as one slug (dossier D8 — Joshua's spelling,
#: SUIT; he created the repo 2026-11-18). The check treats a 404
#: as "nothing to check against", so the suite runs quietly until
#: a release exists.
REPO = "BROKE-N-BORED/REBLEND-ADDON-DEV-SUIT"

#: The installed distribution name (pyproject.toml), for asking
#: importlib.metadata which version is running.
PACKAGE_NAME = "reblend-addon-dev-suite"

LATEST_RELEASE_URL = (
    f"https://api.github.com/repos/{REPO}/releases/latest"
)
RELEASES_PAGE_URL = f"https://github.com/{REPO}/releases"

#: The check is a quick question, not a download: a slow answer is
#: a failed check, and a failed silent check is no news.
CHECK_TIMEOUT_S = 8

#: The update package's file names inside a release.
ZIP_SUFFIX = ".zip"
SIDECAR_SUFFIX = ".zip.sha256"

_VERSION_RE = re.compile(r"^v?(\d+(?:\.\d+)*)$")


class UpdateError(Exception):
    """A plain-words reason the update check (or pull) could not
    run. Raised by the fetching functions; ``check_for_update``
    and the apply functions turn it into data, never a crash."""


def parse_version(text):
    """A version string as a tuple of ints — "0.1.0" becomes
    (0, 1, 0), "v0.2" the same shape — or None when it is not a
    version at all. Anything but an optional "v" followed by
    numbers and dots is refused, so a tag like "v0.2-beta"
    reads as no usable version rather than a wrong one."""
    if not isinstance(text, str):
        return None
    match = _VERSION_RE.match(text.strip())
    if match is None:
        return None
    return tuple(int(part) for part in match.group(1).split("."))


def is_newer(latest, current):
    """True when the latest version is newer than the running
    one. Either side unparsable means no — an unknown version
    is never reported as an update. Shorter tuples are padded
    with zeros, so 0.1 and 0.1.0 compare equal."""
    latest_parsed = parse_version(latest)
    current_parsed = parse_version(current)
    if latest_parsed is None or current_parsed is None:
        return False
    width = max(len(latest_parsed), len(current_parsed))
    latest_padded = latest_parsed + (0,) * (width - len(latest_parsed))
    current_padded = current_parsed + (0,) * (width - len(current_parsed))
    return latest_padded > current_padded


def current_version():
    """The running suite's version as a string, or None when it
    cannot be told. The installed distribution metadata is asked
    first; when the suite runs from the tree (no installed
    distribution), the version line of the tree's pyproject.toml
    is read instead. Never raises."""
    try:
        import importlib.metadata

        return importlib.metadata.version(PACKAGE_NAME)
    except Exception:
        pass
    try:
        root = Path(__file__).resolve().parent.parent.parent
        text = (root / "pyproject.toml").read_text(encoding="utf-8")
    except OSError:
        return None
    match = re.search(r'^version\s*=\s*"([^"]+)"', text, re.M)
    if match is None:
        return None
    return match.group(1)


def _read_json(url, urlopen, timeout):
    """The JSON at ``url`` as a dict, or an UpdateError with a
    plain reason. ``urlopen`` is the test seam — pass a stub and
    no network is touched."""
    opener = urlopen or urllib.request.urlopen
    try:
        with opener(url, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            raise UpdateError(
                "the suite has no releases yet"
            ) from exc
        raise UpdateError(
            f"GitHub answered with an error ({exc.code})"
        ) from exc
    except urllib.error.URLError as exc:
        reason = exc.reason
        if isinstance(reason, TimeoutError):
            raise UpdateError("the update check timed out") from exc
        raise UpdateError(
            f"could not reach GitHub: {reason}"
        ) from exc
    except TimeoutError as exc:
        raise UpdateError("the update check timed out") from exc
    except (ValueError, UnicodeDecodeError) as exc:
        raise UpdateError(
            "the releases page did not answer in a form the suite "
            "understands"
        ) from exc
    if not isinstance(payload, dict):
        raise UpdateError(
            "the releases page did not answer in a form the suite "
            "understands"
        )
    return payload


def fetch_latest_release(urlopen=None, api_url=None):
    """The latest release from GitHub's public endpoint, as
    {"version", "url", "zip_name", "zip_url", "sha_url"} — the
    version from the tag, the release page, and the update
    package + its checksum sidecar from the release's assets.
    Raises UpdateError with a plain reason when the network
    fails, the answer is not JSON, it carries no tag, or the
    release carries no usable update package. ``urlopen`` and
    ``api_url`` are test seams — pass a stub and a fake server
    and no real network is touched."""
    payload = _read_json(
        api_url or LATEST_RELEASE_URL, urlopen, CHECK_TIMEOUT_S
    )
    tag = payload.get("tag_name")
    if not isinstance(tag, str) or not tag:
        raise UpdateError("the releases page did not name a version")
    version = parse_version(tag)
    if version is None:
        raise UpdateError(
            "the latest release tag did not look like a version: "
            f"{tag}"
        )
    assets = payload.get("assets")
    if not isinstance(assets, list):
        raise UpdateError(
            "the latest release carries no update package"
        )
    zip_asset = None
    sha_asset = None
    for asset in assets:
        if not isinstance(asset, dict):
            continue
        name = asset.get("name")
        url = asset.get("browser_download_url")
        if not isinstance(name, str) or not isinstance(url, str):
            continue
        if name.endswith(SIDECAR_SUFFIX):
            sha_asset = url
        elif name.endswith(ZIP_SUFFIX):
            zip_asset = (name, url)
    if zip_asset is None:
        raise UpdateError(
            "the latest release carries no update package"
        )
    if sha_asset is None:
        raise UpdateError(
            "the latest release carries no checksum for its "
            "update package, so the update cannot be verified"
        )
    return {
        "version": ".".join(str(part) for part in version),
        "url": payload.get("html_url") or RELEASES_PAGE_URL,
        "zip_name": zip_asset[0],
        "zip_url": zip_asset[1],
        "sha_url": sha_asset,
    }


def check_for_update(current=None, urlopen=None, api_url=None):
    """One call, three outcomes, never an exception for a
    network or parsing problem:

    {"state": "newer", "latest": "0.2.0",
     "url": "<release page>", "release": {...}} — a newer
     release is out, carrying a verifiable update package.
    {"state": "current", "latest": "0.1.0",
     "url": "<release page>", "release": None} — the running
     version is the newest (or newer than the latest release,
     a dev tree).
    {"state": "unknown", "latest": None, "url": None,
     "reason": "<plain words>", "release": None} — the check
     could not run, or the release cannot be pulled safely.

    ``current`` defaults to the running version; pass one
    explicitly in tests.
    """
    if current is None:
        current = current_version()
    if current is None:
        return {
            "state": "unknown",
            "latest": None,
            "url": None,
            "reason": (
                "the suite could not tell which version is "
                "running"
            ),
            "release": None,
        }
    try:
        release = fetch_latest_release(
            urlopen=urlopen, api_url=api_url
        )
    except UpdateError as exc:
        return {
            "state": "unknown",
            "latest": None,
            "url": None,
            "reason": str(exc),
            "release": None,
        }
    if is_newer(release["version"], current):
        return {
            "state": "newer",
            "latest": release["version"],
            "url": release["url"],
            "reason": None,
            "release": release,
        }
    return {
        "state": "current",
        "latest": release["version"],
        "url": release["url"],
        "reason": None,
        "release": None,
    }
