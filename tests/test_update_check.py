"""Tests for devsuite.update — the silent update check + ask-first
auto-update (standing order, 2026-11-17).

A fake GitHub server (http.server in a thread) serves the release
JSON, the update zip, and the checksum sidecar, so no test touches
the real network. The window tests drive the real chat window with
a fake updater — and one drives the real updater against the fake
server end to end, through the verified pull and the stub
installer in the fake release zip.

The rules under test:

* Launch check is silent: up to date, unreachable, no repo yet,
  or a broken answer is no news — never a popup, never a crash.
* A newer release asks before anything is pulled; only a Yes
  starts the download.
* The pull is verified by checksum before anything installs; a
  mismatch refuses and installs nothing.
* A successful install asks whether to restart now or on the
  next launch; No waits.
* The Help-menu manual check reports its result in plain words.
* A tree run with no install has nothing to update: no launch
  check, and the manual check says so plainly.

Run the window tests offscreen with the Qt venv, from the project
root (the EGL env is a sandbox quirk — his PC has system Qt libs;
never override HOME):

    LD_LIBRARY_PATH=$HOME/workspace/qt-libs/root/usr/lib/x86_64-linux-gnu \\
    __EGL_VENDOR_LIBRARY_DIRS=$HOME/workspace/qt-libs/root/usr/share/glvnd/egl_vendor.d \\
    QT_QPA_PLATFORM=offscreen TMPDIR=/tmp \\
    ~/workspace/tmp/qt-venv/bin/python -m unittest tests.test_update_check

On a Python without PySide6 the window tests skip and the core
tests still run.
"""

import hashlib
import http.server
import io
import json
import socketserver
import tempfile
import threading
import time
import unittest
import zipfile
from pathlib import Path

from devsuite.update import Updater
from devsuite.update.apply import (
    apply_update,
    download_and_verify,
    find_install,
    relaunch_command,
    restart,
    run_extracted_installer,
)
from devsuite.update.check import (
    check_for_update,
    current_version,
    fetch_latest_release,
    is_newer,
    parse_version,
)

try:
    from PySide6.QtCore import Qt, QTimer
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication, QMessageBox

    from devsuite.ui.chat_window import ChatWindow

    HAS_QT = True
except ImportError:
    HAS_QT = False

RELEASE_PATH = (
    "/repos/BROKE-N-BORED/REBLEND-ADDON-DEV-SUIT/releases/latest"
)
ZIP_NAME = "reblend-addon-dev-suite-0.2.0.zip"

#: A stub installer for the fake release zip: it writes a marker
#: into the install folder instead of running pip, so the real
#: apply path runs end to end in under a second.
_STUB_INSTALLER = (
    "from pathlib import Path\n"
    "\n"
    "def install(source, install_dir=None, applications_dir=None,"
    " **kwargs):\n"
    "    Path(install_dir, 'updated.txt').write_text(\n"
    "        'new version', encoding='utf-8'\n"
    "    )\n"
    "    return True, 'Stub installed.'\n"
)


def make_release_zip(files=None):
    """A release zip as bytes: a minimal tree with the project
    file at its root, plus whatever ``files`` names."""
    entries = {
        "pyproject.toml": (
            '[project]\nname = "reblend-addon-dev-suite"\n'
            'version = "0.2.0"\n'
        ),
        "marker.txt": "new version",
    }
    entries.update(files or {})
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, text in entries.items():
            archive.writestr(name, text)
    return buffer.getvalue()


class _FakeGitHubHandler(http.server.BaseHTTPRequestHandler):
    """Serves the release JSON, the zip, and the sidecar, shaped
    by ``server.config`` (see FakeGitHubServer). Quiet: no
    request logging."""

    def log_message(self, *args):
        pass

    def do_GET(self):
        config = self.server.config
        if self.path == RELEASE_PATH:
            mode = config.get("release_mode", "ok")
            if mode == "not_found":
                self._send(404, b"")
                return
            if mode == "bad_json":
                self._send(200, b"not json{{{")
                return
            if mode == "slow":
                time.sleep(1)
            payload = {"html_url": self._base() + "/releases/tag/v0.2.0"}
            if mode != "no_tag":
                payload["tag_name"] = config.get("tag", "v0.2.0")
            if mode not in ("no_assets", "no_tag"):
                assets = [
                    {
                        "name": ZIP_NAME,
                        "browser_download_url": (
                            self._base() + "/download/" + ZIP_NAME
                        ),
                    }
                ]
                if mode != "no_sidecar":
                    assets.append(
                        {
                            "name": ZIP_NAME + ".sha256",
                            "browser_download_url": (
                                self._base() + "/download/" + ZIP_NAME
                                + ".sha256"
                            ),
                        }
                    )
                payload["assets"] = assets
            self._send(200, json.dumps(payload).encode("utf-8"))
            return
        if self.path.startswith("/download/"):
            name = self.path[len("/download/"):]
            files = config.get("files", {})
            if name in files:
                self._send(200, files[name])
                return
            self._send(404, b"")
            return
        self._send(404, b"")

    def _base(self):
        port = self.server.server_address[1]
        return f"http://127.0.0.1:{port}"

    def _send(self, code, body):
        self.send_response(code)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class FakeGitHubServer(socketserver.ThreadingTCPServer):
    """A GitHub stand-in on a thread: ``config`` shapes the next
    answer (release_mode, tag, files). Reusable across tests in
    one class; the config is reset in each setUp."""

    daemon_threads = True
    allow_reuse_address = True

    def __init__(self):
        super().__init__(("127.0.0.1", 0), _FakeGitHubHandler)
        self.config = {}
        self._thread = threading.Thread(
            target=self.serve_forever, daemon=True
        )
        self._thread.start()

    @property
    def base_url(self):
        return f"http://127.0.0.1:{self.server_address[1]}"

    @property
    def api_url(self):
        return self.base_url + RELEASE_PATH

    def stop(self):
        self.shutdown()
        self.server_close()


class _ServerCase(unittest.TestCase):
    """A fake GitHub server per test class, with a good release
    (tag v0.2.0, zip + matching sidecar) as the default config."""

    @classmethod
    def setUpClass(cls):
        cls.server = FakeGitHubServer()

    @classmethod
    def tearDownClass(cls):
        cls.server.stop()

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.zip_bytes = make_release_zip()
        digest = hashlib.sha256(self.zip_bytes).hexdigest()
        self.server.config = {
            "release_mode": "ok",
            "tag": "v0.2.0",
            "files": {
                ZIP_NAME: self.zip_bytes,
                ZIP_NAME + ".sha256": (
                    f"{digest}  {ZIP_NAME}\n".encode("utf-8")
                ),
            },
        }

    def _release(self):
        """The release dict the fake server describes (via the
        real fetch)."""
        return fetch_latest_release(api_url=self.server.api_url)


class VersionTests(unittest.TestCase):
    def test_parse_version(self):
        self.assertEqual(parse_version("0.1.0"), (0, 1, 0))
        self.assertEqual(parse_version("v0.2"), (0, 2))
        self.assertEqual(parse_version("  1.0  "), (1, 0))
        self.assertIsNone(parse_version("v0.2-beta"))
        self.assertIsNone(parse_version(""))
        self.assertIsNone(parse_version(None))
        self.assertIsNone(parse_version("latest"))

    def test_is_newer(self):
        self.assertTrue(is_newer("0.2.0", "0.1.0"))
        self.assertTrue(is_newer("v0.2.0", "0.1.0"))
        self.assertTrue(is_newer("0.1.1", "0.1.0"))
        self.assertFalse(is_newer("0.1.0", "0.1.0"))
        self.assertFalse(is_newer("0.1", "0.1.0"))
        self.assertFalse(is_newer("0.1.0", "0.2.0"))
        self.assertFalse(is_newer("banana", "0.1.0"))
        self.assertFalse(is_newer("0.2.0", "banana"))

    def test_current_version_is_the_tree_version(self):
        self.assertEqual(current_version(), "0.1.0")


class CheckTests(_ServerCase):
    def test_up_to_date_is_current(self):
        result = check_for_update("0.2.0", api_url=self.server.api_url)
        self.assertEqual(result["state"], "current")
        self.assertEqual(result["latest"], "0.2.0")
        self.assertIsNone(result["release"])

    def test_newer_release_is_newer_with_the_package(self):
        result = check_for_update("0.1.0", api_url=self.server.api_url)
        self.assertEqual(result["state"], "newer")
        self.assertEqual(result["latest"], "0.2.0")
        release = result["release"]
        self.assertEqual(release["zip_name"], ZIP_NAME)
        self.assertIn("/download/" + ZIP_NAME, release["zip_url"])
        self.assertIn(".sha256", release["sha_url"])

    def test_dev_tree_newer_than_release_is_current(self):
        result = check_for_update("0.3.0", api_url=self.server.api_url)
        self.assertEqual(result["state"], "current")

    def test_no_repo_yet_is_unknown_not_an_error(self):
        self.server.config["release_mode"] = "not_found"
        result = check_for_update("0.1.0", api_url=self.server.api_url)
        self.assertEqual(result["state"], "unknown")
        self.assertIn("no releases yet", result["reason"])

    def test_unreachable_server_is_unknown(self):
        result = check_for_update(
            "0.1.0", api_url="http://127.0.0.1:1/releases/latest"
        )
        self.assertEqual(result["state"], "unknown")
        self.assertIsNotNone(result["reason"])

    def test_malformed_answer_is_unknown(self):
        self.server.config["release_mode"] = "bad_json"
        result = check_for_update("0.1.0", api_url=self.server.api_url)
        self.assertEqual(result["state"], "unknown")

    def test_release_without_a_tag_is_unknown(self):
        self.server.config["release_mode"] = "no_tag"
        result = check_for_update("0.1.0", api_url=self.server.api_url)
        self.assertEqual(result["state"], "unknown")

    def test_release_without_a_package_is_unknown(self):
        self.server.config["release_mode"] = "no_assets"
        result = check_for_update("0.1.0", api_url=self.server.api_url)
        self.assertEqual(result["state"], "unknown")
        self.assertIn("no update package", result["reason"])

    def test_release_without_a_checksum_is_unknown(self):
        self.server.config["release_mode"] = "no_sidecar"
        result = check_for_update("0.1.0", api_url=self.server.api_url)
        self.assertEqual(result["state"], "unknown")
        self.assertIn("checksum", result["reason"])

    def test_default_current_version_is_the_running_one(self):
        result = check_for_update(api_url=self.server.api_url)
        self.assertEqual(result["state"], "newer")
        self.assertEqual(result["latest"], "0.2.0")


class DownloadTests(_ServerCase):
    def test_matching_checksum_verifies(self):
        dest = Path(self._tmp.name)
        path, error = download_and_verify(self._release(), dest)
        self.assertIsNone(error)
        self.assertEqual(path.read_bytes(), self.zip_bytes)

    def test_mismatched_checksum_refuses_and_removes(self):
        digest = "0" * 64
        self.server.config["files"][ZIP_NAME + ".sha256"] = (
            f"{digest}  {ZIP_NAME}\n".encode("utf-8")
        )
        dest = Path(self._tmp.name)
        path, error = download_and_verify(self._release(), dest)
        self.assertIsNone(path)
        self.assertIn("did not match its checksum", error)
        self.assertFalse((dest / ZIP_NAME).exists())

    def test_sidecar_that_is_not_a_checksum_refuses(self):
        self.server.config["files"][ZIP_NAME + ".sha256"] = (
            b"not a checksum\n"
        )
        dest = Path(self._tmp.name)
        path, error = download_and_verify(self._release(), dest)
        self.assertIsNone(path)
        self.assertIn("did not look like a checksum", error)

    def test_bare_hex_sidecar_is_accepted(self):
        digest = hashlib.sha256(self.zip_bytes).hexdigest()
        self.server.config["files"][ZIP_NAME + ".sha256"] = (
            f"{digest}\n".encode("utf-8")
        )
        dest = Path(self._tmp.name)
        path, error = download_and_verify(self._release(), dest)
        self.assertIsNone(error)
        self.assertIsNotNone(path)


class ApplyTests(_ServerCase):
    def _install_dir(self):
        target = Path(self._tmp.name) / "install"
        target.mkdir()
        (target / "install-info.json").write_text(
            '{"app": "Reblend Add-on Dev Suite"}', encoding="utf-8"
        )
        return target

    def test_apply_lands_the_new_tree_in_the_install_dir(self):
        install_dir = self._install_dir()
        apps_dir = Path(self._tmp.name) / "apps"
        calls = []

        def fake_install(source, target, apps):
            calls.append((Path(source), Path(target), Path(apps)))
            content = (Path(source) / "marker.txt").read_text(
                encoding="utf-8"
            )
            (Path(target) / "marker.txt").write_text(
                content, encoding="utf-8"
            )
            return True, "Fake installed."

        ok, message = apply_update(
            self._release(),
            install_dir=install_dir,
            applications_dir=apps_dir,
            work_dir=self._tmp.name,
            run_install=fake_install,
        )
        self.assertTrue(ok)
        self.assertEqual(message, "Fake installed.")
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][1], install_dir)
        self.assertEqual(calls[0][2], apps_dir)
        self.assertEqual(
            (install_dir / "marker.txt").read_text(encoding="utf-8"),
            "new version",
        )

    def test_apply_with_a_failing_install_reports_it(self):
        install_dir = self._install_dir()
        ok, message = apply_update(
            self._release(),
            install_dir=install_dir,
            work_dir=self._tmp.name,
            run_install=lambda s, t, a: (
                False, "The fake installer broke."
            ),
        )
        self.assertFalse(ok)
        self.assertEqual(message, "The fake installer broke.")

    def test_apply_never_installs_a_bad_checksum(self):
        self.server.config["files"][ZIP_NAME + ".sha256"] = (
            ("0" * 64 + f"  {ZIP_NAME}\n").encode("utf-8")
        )
        called = []

        def must_not_run(source, target, apps):
            called.append(True)
            return True, "should not run"

        ok, message = apply_update(
            self._release(),
            install_dir=self._install_dir(),
            work_dir=self._tmp.name,
            run_install=must_not_run,
        )
        self.assertFalse(ok)
        self.assertIn("did not match its checksum", message)
        self.assertEqual(called, [])

    def test_apply_refuses_a_zip_outside_its_folder(self):
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr("../escape.txt", "outside")
            archive.writestr("pyproject.toml", "[project]\n")
        self.server.config["files"][ZIP_NAME] = buffer.getvalue()
        digest = hashlib.sha256(buffer.getvalue()).hexdigest()
        self.server.config["files"][ZIP_NAME + ".sha256"] = (
            f"{digest}  {ZIP_NAME}\n".encode("utf-8")
        )
        ok, message = apply_update(
            self._release(),
            install_dir=self._install_dir(),
            work_dir=self._tmp.name,
            run_install=lambda s, t, a: (True, "should not run"),
        )
        self.assertFalse(ok)
        self.assertIn("outside its own folder", message)

    def test_apply_refuses_a_zip_without_the_project_file(self):
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr("nothing-here.txt", "nope")
        self.server.config["files"][ZIP_NAME] = buffer.getvalue()
        digest = hashlib.sha256(buffer.getvalue()).hexdigest()
        self.server.config["files"][ZIP_NAME + ".sha256"] = (
            f"{digest}  {ZIP_NAME}\n".encode("utf-8")
        )
        ok, message = apply_update(
            self._release(),
            install_dir=self._install_dir(),
            work_dir=self._tmp.name,
            run_install=lambda s, t, a: (True, "should not run"),
        )
        self.assertFalse(ok)
        self.assertIn("did not hold the suite's project file", message)

    def test_apply_accepts_a_single_top_level_folder(self):
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr("suite-0.2.0/pyproject.toml", "[project]\n")
            archive.writestr("suite-0.2.0/marker.txt", "wrapped")
        self.server.config["files"][ZIP_NAME] = buffer.getvalue()
        digest = hashlib.sha256(buffer.getvalue()).hexdigest()
        self.server.config["files"][ZIP_NAME + ".sha256"] = (
            f"{digest}  {ZIP_NAME}\n".encode("utf-8")
        )
        seen = []

        def fake_install(source, target, apps):
            seen.append(Path(source))
            return True, "Fake installed."

        ok, message = apply_update(
            self._release(),
            install_dir=self._install_dir(),
            work_dir=self._tmp.name,
            run_install=fake_install,
        )
        self.assertTrue(ok)
        self.assertEqual(seen[0].name, "suite-0.2.0")


class ExtractedInstallerTests(unittest.TestCase):
    def test_stub_installer_runs_and_reports(self):
        with tempfile.TemporaryDirectory() as tmp:
            tree = Path(tmp) / "tree"
            (tree / "installer").mkdir(parents=True)
            (tree / "installer" / "__init__.py").write_text("")
            (tree / "installer" / "install.py").write_text(
                _STUB_INSTALLER, encoding="utf-8"
            )
            install_dir = Path(tmp) / "install"
            install_dir.mkdir()
            apps_dir = Path(tmp) / "apps"
            ok, message = run_extracted_installer(
                tree, install_dir, apps_dir
            )
            self.assertTrue(ok)
            self.assertEqual(message, "Stub installed.")
            self.assertEqual(
                (install_dir / "updated.txt").read_text(
                    encoding="utf-8"
                ),
                "new version",
            )

    def test_missing_installer_is_a_plain_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            tree = Path(tmp) / "tree"
            tree.mkdir()
            install_dir = Path(tmp) / "install"
            install_dir.mkdir()
            ok, message = run_extracted_installer(
                tree, install_dir, Path(tmp) / "apps"
            )
            self.assertFalse(ok)
            self.assertIn("did not say why", message)


class InstallDetectionTests(unittest.TestCase):
    def test_find_install(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "install"
            target.mkdir()
            self.assertIsNone(find_install(target))
            (target / "install-info.json").write_text(
                "{}", encoding="utf-8"
            )
            self.assertEqual(find_install(target), target)

    def test_relaunch_command_prefers_the_console_script(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "install"
            script = target / "venv" / "bin" / "devsuite"
            self.assertEqual(
                relaunch_command(target)[-2:],
                ["-m", "devsuite.main"],
            )
            script.parent.mkdir(parents=True)
            script.write_text("#!/bin/sh\n", encoding="utf-8")
            self.assertEqual(relaunch_command(target), [str(script)])

    def test_restart_launches_and_reports(self):
        launched = []

        def fake_popen(command, start_new_session=False):
            launched.append((command, start_new_session))

        command, error = restart(popen=fake_popen)
        self.assertIsNone(error)
        self.assertEqual(len(launched), 1)
        self.assertEqual(launched[0][0], command)
        self.assertTrue(launched[0][1])

    def test_restart_failure_is_plain_words(self):
        def broken_popen(command, start_new_session=False):
            raise OSError("no such file")

        command, error = restart(popen=broken_popen)
        self.assertIsNone(command)
        self.assertIn("could not restart", error.lower())


class FakeUpdater:
    """A stand-in for Updater: canned check result, recorded
    apply and relaunch calls, no network, no install."""

    def __init__(self, installed=True, result=None, apply_result=None,
                 check_delay=0.0):
        self.installed = installed
        self.result = result or {
            "state": "current", "latest": "0.1.0", "url": None,
            "reason": None, "release": None,
        }
        self.apply_result = apply_result or (True, "Fake installed.")
        self.check_delay = check_delay
        self.check_started = False
        self.check_done = False
        self.check_calls = 0
        self.apply_calls = []
        self.relaunch_calls = 0

    def is_installed(self):
        return self.installed

    def current_version(self):
        return "0.1.0"

    def check(self):
        self.check_calls += 1
        self.check_started = True
        if self.check_delay:
            time.sleep(self.check_delay)
        self.check_done = True
        return self.result

    def apply(self, release, progress=None):
        self.apply_calls.append(release)
        if progress is not None:
            progress("Fake installing...")
        return self.apply_result

    def relaunch(self):
        self.relaunch_calls += 1
        return ["fake-devsuite"], None


def _newer_result():
    return {
        "state": "newer",
        "latest": "0.2.0",
        "url": "http://example.invalid/releases",
        "reason": None,
        "release": {
            "version": "0.2.0",
            "url": "http://example.invalid/releases",
            "zip_name": ZIP_NAME,
            "zip_url": "http://example.invalid/download",
            "sha_url": "http://example.invalid/download.sha256",
        },
    }


@unittest.skipUnless(HAS_QT, "PySide6 is not installed")
class UpdateWindowTests(_ServerCase):
    @classmethod
    def setUpClass(cls):
        cls._app = QApplication.instance() or QApplication([])
        super().setUpClass()

    def setUp(self):
        super().setUp()
        self.window = None
        self._dialog_timer = None

    def tearDown(self):
        if self._dialog_timer is not None:
            self._dialog_timer.stop()
            self._dialog_timer = None
        if self.window is not None:
            self.window.close()
            self.window = None
        super().tearDown()

    def _make_window(self, updater):
        self.window = ChatWindow(updater=updater)
        return self.window

    def _arm_dialog_clicks(self, roles, seen):
        """Arm a repeating timer that clicks each message box as
        it appears, taking the next role from ``roles`` and
        recording each box's text in ``seen``. Arm BEFORE the
        action that opens the first dialog: a modal dialog blocks
        the test thread, so nothing scheduled after it can run —
        and the update dialogs open from worker threads, so the
        first one can appear at any moment after the check
        starts. The timer keeps running until the plan is
        exhausted, so a second dialog (the restart prompt) is
        clicked even when it appears at once. The timer is kept
        on the test so it stays alive; tearDown stops it."""
        plan = list(roles)
        timer = QTimer()
        timer.setInterval(50)

        def _try_click():
            if not plan:
                return
            for widget in QApplication.topLevelWidgets():
                if isinstance(widget, QMessageBox) \
                        and widget.isVisible():
                    seen.append(widget.text())
                    role = plan.pop(0)
                    button = widget.button(role)
                    if button is not None:
                        QTest.mouseClick(button, Qt.LeftButton)
                    if not plan:
                        timer.stop()
                    return

        timer.timeout.connect(_try_click)
        timer.start()
        self._dialog_timer = timer
        return timer

    def _wait_until(self, condition, timeout_ms=10000):
        deadline = time.monotonic() + timeout_ms / 1000
        while time.monotonic() < deadline:
            if condition():
                return True
            QTest.qWait(50)
        return False

    # -- the silent launch check ----------------------------------

    def test_launch_check_never_blocks_the_window(self):
        updater = FakeUpdater(check_delay=1.0)
        window = self._make_window(updater)
        window.show()
        window.start_update_check()
        self.assertTrue(
            self._wait_until(lambda: updater.check_started, 5000)
        )
        self.assertTrue(window.isVisible())
        self.assertFalse(updater.check_done)
        self.assertTrue(
            self._wait_until(lambda: updater.check_done, 5000)
        )

    def test_launch_check_is_silent_when_current(self):
        updater = FakeUpdater()
        window = self._make_window(updater)
        window.show()
        window.start_update_check()
        self.assertTrue(
            self._wait_until(lambda: updater.check_done, 5000)
        )
        QTest.qWait(200)
        boxes = [
            widget for widget in QApplication.topLevelWidgets()
            if isinstance(widget, QMessageBox) and widget.isVisible()
        ]
        self.assertEqual(boxes, [])

    def test_launch_check_skipped_with_no_install(self):
        updater = FakeUpdater(installed=False)
        window = self._make_window(updater)
        window.show()
        window.start_update_check()
        QTest.qWait(300)
        self.assertEqual(updater.check_calls, 0)

    def test_launch_check_runs_only_once(self):
        updater = FakeUpdater()
        window = self._make_window(updater)
        window.show()
        window.start_update_check()
        window.start_update_check()
        self.assertTrue(
            self._wait_until(lambda: updater.check_done, 5000)
        )
        QTest.qWait(200)
        self.assertEqual(updater.check_calls, 1)

    # -- the offer, the pull, the restart -------------------------

    def test_offer_yes_pulls_and_restart_yes_relaunches(self):
        updater = FakeUpdater(result=_newer_result())
        window = self._make_window(updater)
        window.show()
        seen = []
        self._arm_dialog_clicks(
            [QMessageBox.Yes, QMessageBox.Yes], seen
        )
        window.start_update_check()
        self.assertTrue(
            self._wait_until(lambda: updater.relaunch_calls == 1, 10000)
        )
        self.assertEqual(len(updater.apply_calls), 1)
        self.assertEqual(len(seen), 2)
        self.assertIn("0.2.0", seen[0])
        self.assertIn("Restart now", seen[1])

    def test_offer_no_pulls_nothing(self):
        updater = FakeUpdater(result=_newer_result())
        window = self._make_window(updater)
        window.show()
        seen = []
        self._arm_dialog_clicks([QMessageBox.No], seen)
        window.start_update_check()
        self.assertTrue(
            self._wait_until(lambda: len(seen) == 1, 10000)
        )
        QTest.qWait(300)
        self.assertEqual(updater.apply_calls, [])

    def test_restart_no_waits_for_next_launch(self):
        updater = FakeUpdater(result=_newer_result())
        window = self._make_window(updater)
        window.show()
        seen = []
        self._arm_dialog_clicks(
            [QMessageBox.Yes, QMessageBox.No], seen
        )
        window.start_update_check()
        self.assertTrue(
            self._wait_until(
                lambda: any(
                    "next time the suite starts" in text
                    for _role, text in window._message_texts
                ),
                10000,
            )
        )
        self.assertEqual(updater.relaunch_calls, 0)
        self.assertEqual(len(seen), 2)

    def test_failed_apply_reports_and_asks_nothing(self):
        updater = FakeUpdater(
            result=_newer_result(),
            apply_result=(False, "The fake installer broke."),
        )
        window = self._make_window(updater)
        window.show()
        seen = []
        self._arm_dialog_clicks(
            [QMessageBox.Yes, QMessageBox.Ok], seen
        )
        window.start_update_check()
        self.assertTrue(
            self._wait_until(lambda: len(seen) == 2, 10000)
        )
        self.assertIn("The fake installer broke.", seen[1])
        self.assertEqual(updater.relaunch_calls, 0)

    # -- the manual check -----------------------------------------

    def test_manual_check_reports_up_to_date(self):
        updater = FakeUpdater()
        window = self._make_window(updater)
        window.show()
        seen = []
        self._arm_dialog_clicks([QMessageBox.Ok], seen)
        window._check_updates_action.trigger()
        self.assertTrue(
            self._wait_until(lambda: len(seen) == 1, 10000)
        )
        self.assertIn("newest version", seen[0])

    def test_manual_check_reports_unreachable(self):
        updater = FakeUpdater(result={
            "state": "unknown", "latest": None, "url": None,
            "reason": "could not reach GitHub: refused",
            "release": None,
        })
        window = self._make_window(updater)
        window.show()
        seen = []
        self._arm_dialog_clicks([QMessageBox.Ok], seen)
        window._check_updates_action.trigger()
        self.assertTrue(
            self._wait_until(lambda: len(seen) == 1, 10000)
        )
        self.assertIn("Could not reach GitHub", seen[0])

    def test_manual_check_with_no_install_says_so(self):
        updater = FakeUpdater(installed=False)
        window = self._make_window(updater)
        window.show()
        seen = []
        self._arm_dialog_clicks([QMessageBox.Ok], seen)
        window._check_updates_action.trigger()
        self.assertTrue(
            self._wait_until(lambda: len(seen) == 1, 10000)
        )
        self.assertIn("not installed yet", seen[0])
        self.assertEqual(updater.check_calls, 0)

    # -- the real updater, end to end against the fake server -----

    def test_real_updater_end_to_end(self):
        install_dir = Path(self._tmp.name) / "install"
        install_dir.mkdir()
        (install_dir / "install-info.json").write_text(
            '{"app": "Reblend Add-on Dev Suite"}', encoding="utf-8"
        )
        apps_dir = Path(self._tmp.name) / "apps"
        zip_bytes = make_release_zip({
            "installer/__init__.py": "",
            "installer/install.py": _STUB_INSTALLER,
        })
        digest = hashlib.sha256(zip_bytes).hexdigest()
        self.server.config["files"] = {
            ZIP_NAME: zip_bytes,
            ZIP_NAME + ".sha256": (
                f"{digest}  {ZIP_NAME}\n".encode("utf-8")
            ),
        }
        updater = Updater(
            install_dir=install_dir,
            applications_dir=apps_dir,
            api_url=self.server.api_url,
        )
        window = self._make_window(updater)
        window.show()
        seen = []
        self._arm_dialog_clicks(
            [QMessageBox.Yes, QMessageBox.No], seen
        )
        window._check_updates_action.trigger()
        self.assertTrue(
            self._wait_until(
                lambda: (install_dir / "updated.txt").is_file(),
                30000,
            )
        )
        self.assertTrue(
            self._wait_until(lambda: len(seen) == 2, 10000)
        )
        self.assertIn("0.2.0", seen[0])
        self.assertIn("Restart now", seen[1])
        self.assertEqual(
            (install_dir / "updated.txt").read_text(encoding="utf-8"),
            "new version",
        )


if __name__ == "__main__":
    unittest.main()
