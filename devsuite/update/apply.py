"""Pull an update through the verified path, install it, restart.

The flow, in order — nothing installs before the download is
proven genuine:

1. Download the release's zip and its ``.sha256`` sidecar into a
   temp folder (``download_and_verify``). The zip's SHA-256 must
   match the sidecar's hex, or the pull stops here in plain words
   and nothing is installed. Never install a blind download.
2. Extract the zip into the same temp folder, with a zip-slip
   guard: a member that would land outside the folder refuses
   the whole zip. The release tree is the folder holding
   ``pyproject.toml`` — the zip root, or a single top-level
   folder holding it.
3. Install from the extracted tree by running the tree's own
   installer (``installer.install.install``) in a subprocess.
   The installed suite ships the installer package too (the
   Uninstall menu entry runs it), but the update still runs the
   extracted tree's copy: the new version's installer may
   differ from the installed one, and the tree's copy is part
   of the verified zip, so running it is the verified path, not
   a blind run. The install reuses the existing venv (the
   installer resumes into one that is already there), rewrites
   the menu launchers, and verifies before reporting success —
   the same steps, and the same plain-words failures, as a fresh
   install.
4. The temp folder is cleaned up, whether the install worked or
   not.

The app is running from the venv while it updates it: on Linux,
replacing files under a running process is safe because the
running process keeps the old files open, and the restart prompt
is what makes the new version live. ``restart`` launches the
installed console script and the window then quits; on a "No"
the new files simply wait for the next launch.

Everything returns plain words and never raises on a bad input
or a failed step: ``apply_update`` returns ``(ok, message)``,
``download_and_verify`` returns ``(zip_path, error)``, and
``restart`` returns ``(command, error)`` — the window must check
the error before quitting, or a failed relaunch would leave
Joshua with no suite running at all.
"""

from __future__ import annotations

import hashlib
import os
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

#: The install folder when none is given — mirrors
#: ``installer.install.default_install_dir`` by hand, the way
#: ``installer.uninstall`` mirrors the shelf path: this module
#: is part of the shipped suite and cannot import the installer
#: package (it is not in the installed distribution).
PACKAGE_NAME = "reblend-addon-dev-suite"
CONSOLE_SCRIPT = "devsuite"

#: The download is a small zip, but a slow connection still gets
#: time to finish it.
DOWNLOAD_TIMEOUT_S = 300

#: The install subprocess may run pip, which may download: the
#: installer's own step timeouts bound it from inside, and this
#: is the outer bound.
INSTALL_TIMEOUT_S = 1800

#: Read the download in chunks instead of holding it whole.
_CHUNK = 65536

#: The installer call, run in a subprocess against the extracted
#: tree. argv[1] is the tree, argv[2] the install folder, argv[3]
#: the applications folder. It prints only the installer's final
#: message and exits 0 on success. The empty path (the working
#: directory, which ``python -c`` puts first on sys.path) is
#: dropped before the tree goes on: without that, a tree with no
#: installer would silently pick up whatever ``installer``
#: package the working directory happens to hold.
_INSTALLER_CODE = (
    "import sys\n"
    "sys.path = [p for p in sys.path if p not in ('', '.')]\n"
    "sys.path.insert(0, sys.argv[1])\n"
    "from installer.install import install\n"
    "ok, message = install(\n"
    "    sys.argv[1],\n"
    "    install_dir=sys.argv[2],\n"
    "    applications_dir=sys.argv[3],\n"
    ")\n"
    "print(message)\n"
    "sys.exit(0 if ok else 1)\n"
)


def default_install_dir() -> Path:
    """Where the suite lives when no folder is given: the
    installer's default, computed by hand here."""
    return Path.home() / ".local" / "share" / PACKAGE_NAME


def default_applications_dir() -> Path:
    """Where the menu launcher goes: the installer's default,
    computed by hand here."""
    return Path.home() / ".local" / "share" / "applications"


def find_install(install_dir=None):
    """The install folder, when the suite is installed there: the
    folder holds ``install-info.json``, the record the installer
    leaves behind. Returns None when it does not — a tree run
    with no install has nothing to update. Never raises."""
    target = Path(install_dir) if install_dir is not None \
        else default_install_dir()
    try:
        if (target / "install-info.json").is_file():
            return target
    except OSError:
        return None
    return None


def _sha256_file(path: Path) -> str:
    """The SHA-256 hex of a file, read in chunks."""
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        while True:
            block = handle.read(_CHUNK)
            if not block:
                break
            digest.update(block)
    return digest.hexdigest()


def _download(url, dest: Path, urlopen, timeout):
    """Download ``url`` to ``dest``. Returns an error string, or
    None on success. ``urlopen`` is the test seam. Never raises."""
    opener = urlopen or urllib.request.urlopen
    try:
        with opener(url, timeout=timeout) as response:
            with open(dest, "wb") as handle:
                while True:
                    block = response.read(_CHUNK)
                    if not block:
                        break
                    handle.write(block)
    except urllib.error.URLError as exc:
        return f"could not download the update: {exc.reason}"
    except TimeoutError:
        return "the update download timed out"
    except OSError as exc:
        return f"could not save the update: {exc}"
    return None


def download_and_verify(release, dest_dir, urlopen=None):
    """Download the release's zip and sidecar into ``dest_dir``
    and check the zip against the sidecar's SHA-256.

    Returns ``(zip_path, error)``: ``zip_path`` is the verified
    zip, or None with a plain-words ``error`` when the download
    failed, the sidecar did not look like a checksum, or the
    checksum did not match. A mismatched download is removed —
    nothing unverified is left lying around. Never raises."""
    dest = Path(dest_dir)
    zip_path = dest / release["zip_name"]
    sha_path = dest / (release["zip_name"] + ".sha256")
    try:
        dest.mkdir(parents=True, exist_ok=True)
    except OSError:
        return None, (
            "I could not make a folder to download the update "
            f"into: {dest}."
        )
    error = _download(release["zip_url"], zip_path, urlopen,
                      DOWNLOAD_TIMEOUT_S)
    if error is not None:
        return None, error
    error = _download(release["sha_url"], sha_path, urlopen,
                      DOWNLOAD_TIMEOUT_S)
    if error is not None:
        try:
            zip_path.unlink()
        except OSError:
            pass
        return None, error
    try:
        sidecar = sha_path.read_text(encoding="utf-8")
    except OSError:
        return None, (
            "I could not read the update's checksum file, so the "
            "update cannot be verified."
        )
    parts = sidecar.split()
    expected = parts[0].lower() if parts else ""
    if len(expected) != 64 or any(
        char not in "0123456789abcdef" for char in expected
    ):
        return None, (
            "The update's checksum file did not look like a "
            "checksum, so the update cannot be verified."
        )
    try:
        actual = _sha256_file(zip_path)
    except OSError:
        return None, (
            "I could not read the downloaded update, so it "
            "cannot be verified."
        )
    if actual != expected:
        try:
            zip_path.unlink()
            sha_path.unlink()
        except OSError:
            pass
        return None, (
            "The downloaded update did not match its checksum, "
            "so it was not installed. The download may have "
            "been damaged. Try again, and if it keeps failing, "
            "download the release by hand."
        )
    return zip_path, None


def _safe_extract(zip_path, dest_dir):
    """Extract ``zip_path`` into ``dest_dir`` and return the
    release tree: the folder holding ``pyproject.toml`` — the
    extract root, or a single top-level folder holding it.
    Returns ``(tree, error)``. A member that would land outside
    the folder refuses the whole zip. Never raises."""
    dest = Path(dest_dir)
    try:
        dest.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(zip_path) as archive:
            for member in archive.infolist():
                target = (dest / member.filename).resolve()
                if dest.resolve() not in target.parents \
                        and target != dest.resolve():
                    return None, (
                        "The update's zip held a file outside its "
                        "own folder, so it was not installed."
                    )
            archive.extractall(dest)
    except zipfile.BadZipFile:
        return None, (
            "The downloaded update was not a readable zip file, "
            "so it was not installed."
        )
    except OSError as exc:
        return None, (
            f"I could not unpack the update: {exc}."
        )
    if (dest / "pyproject.toml").is_file():
        return dest, None
    holders = [
        child for child in dest.iterdir()
        if child.is_dir() and (child / "pyproject.toml").is_file()
    ]
    if len(holders) == 1:
        return holders[0], None
    return None, (
        "The update's zip did not hold the suite's project "
        "file, so it was not installed."
    )


def run_extracted_installer(source_dir, install_dir, applications_dir,
                            python_exe=None, timeout=INSTALL_TIMEOUT_S):
    """Run the extracted tree's installer in a subprocess: the
    tree's ``installer.install.install`` against ``source_dir``,
    into ``install_dir``. Returns ``(ok, message)`` — the
    installer's own plain-words result. A timeout or a failure
    to start comes back as a failure, never a crash. Never
    raises."""
    python = str(python_exe) if python_exe is not None \
        else sys.executable
    # The subprocess runs from the extracted tree, with no
    # PYTHONPATH: only the tree's own installer may be imported,
    # never one that happens to sit on the caller's path.
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    try:
        proc = subprocess.run(
            [python, "-c", _INSTALLER_CODE,
             str(source_dir), str(install_dir),
             str(applications_dir)],
            capture_output=True, text=True, timeout=timeout,
            cwd=str(source_dir), env=env,
        )
    except subprocess.TimeoutExpired:
        return False, (
            "Installing the update ran past its time limit. The "
            "suite is still installed as it was. Run the update "
            "again."
        )
    except OSError as exc:
        return False, (
            f"I could not start the update's installer ({exc})."
        )
    message = (proc.stdout or "").strip()
    if proc.returncode == 0:
        return True, message or "The update installed."
    return False, message or (
        "Installing the update failed, and the installer did "
        "not say why."
    )


def apply_update(release, install_dir=None, applications_dir=None,
                 work_dir=None, urlopen=None, progress=None,
                 run_install=None):
    """Pull the update for ``release`` through the verified path
    and install it into the current install folder.

    ``install_dir`` defaults to the installer's default;
    ``applications_dir`` to its default. ``work_dir`` is the
    parent of the temp folder the download and extract use
    (tests pass a temp dir; the system temp otherwise).
    ``progress`` is called with one plain-words string as each
    step starts. ``run_install`` is the install step — the
    extracted tree's installer by default, injectable in tests.

    Returns ``(ok, message)``: ``ok`` is True only when the
    update is downloaded, verified, and installed. The temp
    folder is cleaned up either way. Never raises."""
    def say(text):
        if progress is not None:
            try:
                progress(text)
            except Exception:
                pass

    try:
        return _apply_update(
            release, install_dir, applications_dir, work_dir,
            urlopen, say, run_install,
        )
    except Exception:
        return False, (
            "I could not install the update. The suite is still "
            "installed as it was. Try again, and if it keeps "
            "failing, download the release by hand."
        )


def _apply_update(release, install_dir, applications_dir, work_dir,
                  urlopen, say, run_install):
    target = Path(install_dir) if install_dir is not None \
        else default_install_dir()
    apps = Path(applications_dir) if applications_dir is not None \
        else default_applications_dir()
    install_step = run_install or run_extracted_installer
    with tempfile.TemporaryDirectory(dir=work_dir) as tmp:
        tmp_path = Path(tmp)
        say("Downloading the update...")
        zip_path, error = download_and_verify(
            release, tmp_path, urlopen=urlopen
        )
        if error is not None:
            return False, error
        say("Checking the download...")
        tree, error = _safe_extract(zip_path, tmp_path / "tree")
        if error is not None:
            return False, error
        say("Installing the update...")
        ok, message = install_step(tree, target, apps)
        if not ok:
            return False, message
        return True, message


def relaunch_command(install_dir=None):
    """How to start the suite again after an update: the
    installed console script when it is there, else the tree's
    own entry point. Returns the command as a list. Never
    raises."""
    target = Path(install_dir) if install_dir is not None \
        else default_install_dir()
    script = target / "venv" / "bin" / CONSOLE_SCRIPT
    try:
        if script.is_file():
            return [str(script)]
    except OSError:
        pass
    return [sys.executable, "-m", "devsuite.main"]


def restart(install_dir=None, popen=None):
    """Start the suite again in the background, detached so it
    survives this process quitting. Returns ``(command, error)``:
    the command launched, or None with a plain-words ``error``
    when the relaunch could not start — the caller must check
    before quitting. Never raises."""
    command = relaunch_command(install_dir)
    launcher = popen or subprocess.Popen
    try:
        launcher(command, start_new_session=True)
    except OSError as exc:
        return None, (
            "I could not restart the suite "
            f"({exc}). Start it from the menu."
        )
    return command, None
