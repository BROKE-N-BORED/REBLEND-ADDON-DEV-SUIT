"""Tests for devsuite.ui.pack_window — the Qt pack window (Phase 4).

Run offscreen with the Qt venv, from the project root (the EGL env
is a sandbox quirk — his PC has system Qt libs; never override HOME):

    LD_LIBRARY_PATH=$HOME/workspace/qt-libs/root/usr/lib/x86_64-linux-gnu \\
    __EGL_VENDOR_LIBRARY_DIRS=$HOME/workspace/qt-libs/root/usr/share/glvnd/egl_vendor.d \\
    QT_QPA_PLATFORM=offscreen TMPDIR=/tmp \\
    ~/workspace/tmp/qt-venv/bin/python -m unittest tests.test_pack_window

The window uses the real emitters against temporary projects seeded
from the Surprise template, so no fake stands in for a build. On a
Python without PySide6 the whole module skips, so the stdlib suite
still passes there.

The rules under test (DOSSIER.md §6.8, §4, §5.1, §5.3, §9.4):

* The window shows the manifest as the suite will write it, with a
  plain-words line under every field, and the pre-pack report
  (secrets, manifest, contributions, last test result).
* Builds run for the project's targets only; the wrong-target
  button is disabled with a plain reason.
* A wheel button added here is saved to the project and ships in
  the built pack's manifest.
* Bump version is one explicit action; the suite never bumps
  silently.
* Install copies the built file to a chosen folder and says
  exactly where it put it.
* With no project open, the window says so plainly and disables
  the actions.
"""

import json
import shutil
import tempfile
import time
import tomllib
import unittest
import zipfile
from pathlib import Path

try:
    from PySide6.QtCore import QSettings, Qt
    from PySide6.QtGui import QPixmap
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication, QPushButton
except ImportError:
    raise unittest.SkipTest("PySide6 is not installed")

from devsuite.packing.manifest import validate_manifest
from devsuite.projects.project import create_project, load_project
from devsuite.templates import template_dir
from devsuite.ui.chat_window import ChatWindow
from devsuite.ui.pack_window import PackWindow

TEMPLATE = template_dir("surprise")


def seed_template_files(project):
    """Copy the Surprise template into ``project``, as the suite
    does when a project starts from a template."""
    shutil.copytree(
        TEMPLATE / "src", project.root / "src", dirs_exist_ok=True
    )
    shutil.copy2(TEMPLATE / "README.md", project.root / "README.md")


class PackWindowTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._app = QApplication.instance() or QApplication([])

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        tmp = Path(self._tmp.name)
        project, error = create_project(
            tmp / "surprise",
            name="Surprise",
            description="Randomize a material for inspiration.",
            targets=["reblend", "blender"],
            version="1.0.0",
            author="Joshua Lofland",
        )
        self.assertIsNone(error)
        self.project = project
        seed_template_files(project)
        # A throwaway settings file and shelf path: the tests never
        # touch the real remembered install folders or the real
        # library shelf (builds record themselves in the shelf).
        self.settings = QSettings(
            str(tmp / "settings.ini"), QSettings.IniFormat
        )
        self.window = PackWindow(
            project=self.project, settings=self.settings,
            shelf_path=tmp / "shelf.json",
        )
        self.window.show()
        QTest.qWait(50)

    def tearDown(self):
        self.window.close()
        QTest.qWait(50)
        self._tmp.cleanup()

    # -- helpers --------------------------------------------------

    def _wait_until(self, predicate, timeout_ms=10000):
        """Pump events until ``predicate`` is true, or the timeout
        passes. Workers answer on the event loop, so the test has
        to wait the same way the user does."""
        deadline = time.monotonic() + timeout_ms / 1000
        while True:
            if predicate():
                return True
            if time.monotonic() >= deadline:
                return False
            QTest.qWait(20)

    def _preview_text(self):
        return "\n".join(self.window._preview_text_lines)

    def _status(self):
        return self.window._status_label.text()

    def _build_and_wait(self, button, built_name):
        QTest.mouseClick(button, Qt.LeftButton)
        built = self._wait_until(
            lambda: built_name in self._status()
        )
        self.assertTrue(built, f"the build never finished: {self._status()}")
        return self.project.packs_dir / built_name

    # -- the window itself ----------------------------------------

    def test_window_opens_with_project_and_shows_manifest(self):
        self.assertIn("Surprise", self.window.windowTitle())
        preview = self._preview_text()
        self.assertIn("Name: Surprise", preview)
        self.assertIn("Version: 1.0.0", preview)
        self.assertIn("Targets: reblend, blender", preview)
        self.assertIn("Reblend: >=0.2", preview)
        self.assertIn("Entry: addon.py", preview)
        self.assertIn("Permissions: network false, files project-only",
                      preview)
        self.assertIn("Nothing declared yet", preview)
        self.assertIn("Icon: none yet", self.window._icon_label.text())

    def test_project_icon_shows_when_it_loads(self):
        # setText after setPixmap clears the pixmap: the icon used
        # to never show. A project with a real icon file must show
        # it in the icon label.
        icon_path = self.project.root / "icon.png"
        pixmap = QPixmap(48, 48)
        pixmap.fill(Qt.GlobalColor.green)
        self.assertTrue(pixmap.save(str(icon_path), "PNG"))
        self.project.icon = "icon.png"
        self.window.set_project(self.project)
        shown = self.window._icon_label.pixmap()
        self.assertIsNotNone(shown)
        self.assertFalse(shown.isNull())

    def test_pre_pack_report_lines(self):
        report = self.window._report_text
        self.assertIn("Secrets check: nothing secret-looking", report)
        self.assertIn("Reblend manifest: valid.", report)
        self.assertIn("Blender manifest: valid.", report)
        self.assertIn("Contributions: nothing declared yet", report)
        self.assertIn("Last test result: no test run yet", report)

    def test_install_buttons_disabled_before_a_build(self):
        self.assertFalse(self.window._install_reblend_button.isEnabled())
        self.assertFalse(self.window._install_blender_button.isEnabled())
        self.assertIn(
            "Build the Reblend pack first",
            self.window._install_reblend_button.toolTip(),
        )

    def test_no_project_state_shows_plain_message(self):
        window = PackWindow(settings=self.settings)
        try:
            window.show()
            QTest.qWait(50)
            self.assertIn("No project open", window.windowTitle())
            self.assertTrue(window._no_project_label.isVisible())
            self.assertIn(
                "Open a project first", window._no_project_label.text()
            )
            self.assertFalse(window._content.isVisible())
        finally:
            window.close()

    # -- targets --------------------------------------------------

    def test_wrong_target_button_disabled_with_reason(self):
        project, error = create_project(
            Path(self._tmp.name) / "reblend-only",
            name="Reblend Only", targets=["reblend"],
        )
        self.assertIsNone(error)
        window = PackWindow(project=project, settings=self.settings)
        try:
            window.show()
            QTest.qWait(50)
            self.assertTrue(window._build_reblend_button.isEnabled())
            self.assertFalse(window._build_blender_button.isEnabled())
            self.assertIn(
                "does not target Blender",
                window._build_blender_button.toolTip(),
            )
            self.assertIn(
                "Targets: reblend", "\n".join(window._preview_text_lines)
            )
        finally:
            window.close()

    # -- builds ---------------------------------------------------

    def test_build_reblend_produces_a_real_pack(self):
        pack_path = self._build_and_wait(
            self.window._build_reblend_button,
            "surprise-1.0.0.rblpack",
        )
        self.assertTrue(pack_path.is_file())
        self.assertIn("packs folder", self._status())
        self.assertIn("unproven", self._status())
        with zipfile.ZipFile(pack_path) as zf:
            self.assertEqual(
                sorted(zf.namelist()),
                ["README.md", "addon.py", "code/pick.py", "manifest.json"],
            )
            manifest = json.loads(zf.read("manifest.json"))
        # The manifest inside the zip validates through the real
        # validator, checked from an extracted copy.
        extracted = Path(self._tmp.name) / "unzipped"
        with zipfile.ZipFile(pack_path) as zf:
            zf.extractall(extracted)
        ok, errors = validate_manifest(extracted / "manifest.json")
        self.assertTrue(ok, f"manifest in pack should validate: {errors}")

    def test_build_blender_produces_a_real_addon(self):
        zip_path = self._build_and_wait(
            self.window._build_blender_button,
            "surprise-1.0.0-blender.zip",
        )
        self.assertTrue(zip_path.is_file())
        with zipfile.ZipFile(zip_path) as zf:
            self.assertEqual(
                sorted(zf.namelist()),
                ["README.md", "__init__.py", "blender_manifest.toml",
                 "pick.py"],
            )
            manifest = tomllib.loads(
                zf.read("blender_manifest.toml").decode("utf-8")
            )
        self.assertEqual(manifest["id"], "surprise")
        self.assertEqual(manifest["version"], "1.0.0")
        self.assertEqual(manifest["type"], "add-on")

    def test_build_without_entry_point_fails_plainly(self):
        project, error = create_project(
            Path(self._tmp.name) / "empty",
            name="Empty", targets=["reblend"],
        )
        self.assertIsNone(error)
        window = PackWindow(project=project, settings=self.settings)
        try:
            window.show()
            QTest.qWait(50)
            QTest.mouseClick(
                window._build_reblend_button, Qt.LeftButton
            )
            failed = self._wait_until(
                lambda: "addon.py" in window._status_label.text()
            )
            self.assertTrue(
                failed, f"no plain failure: {window._status_label.text()}"
            )
            self.assertFalse(
                (project.packs_dir / "empty-0.1.0.rblpack").exists()
            )
        finally:
            window.close()

    # -- wheel buttons --------------------------------------------

    def test_add_wheel_entry_saves_and_ships(self):
        self.window._wheel_label_input.setText("Surprise")
        self.window._wheel_action_input.setText("surprise.randomize")
        QTest.mouseClick(self.window._add_wheel_button, Qt.LeftButton)
        QTest.qWait(50)
        # Saved to the project at once.
        loaded, error = load_project(self.project.root)
        self.assertIsNone(error)
        self.assertEqual(
            loaded.contributions["wheel"],
            [{"label": "Surprise", "action": "surprise.randomize"}],
        )
        self.assertIn("1 wheel button(s)", self.window._report_text)
        # And it ships in the built pack's manifest.
        pack_path = self._build_and_wait(
            self.window._build_reblend_button,
            "surprise-1.0.0.rblpack",
        )
        with zipfile.ZipFile(pack_path) as zf:
            manifest = json.loads(zf.read("manifest.json"))
        self.assertEqual(
            manifest["contributions"]["wheel"],
            [{"label": "Surprise", "action": "surprise.randomize"}],
        )

    def test_add_wheel_entry_needs_both_fields(self):
        self.window._wheel_label_input.setText("Surprise")
        QTest.mouseClick(self.window._add_wheel_button, Qt.LeftButton)
        QTest.qWait(50)
        self.assertIn("needs both a label and an action", self._status())
        loaded, _ = load_project(self.project.root)
        self.assertEqual(loaded.contributions, {})

    def test_remove_wheel_entry(self):
        self.project.contributions = {"wheel": [
            {"label": "Surprise", "action": "surprise.randomize"}
        ]}
        self.assertIsNone(self.project.save())
        self.window._refresh()
        QTest.qWait(50)
        remove_buttons = [
            button for button in self.window.findChildren(QPushButton)
            if button.text() == "Remove"
        ]
        self.assertEqual(len(remove_buttons), 1)
        QTest.mouseClick(remove_buttons[0], Qt.LeftButton)
        QTest.qWait(50)
        loaded, _ = load_project(self.project.root)
        self.assertEqual(loaded.contributions["wheel"], [])
        self.assertIn(
            "Contributions: nothing declared yet",
            self.window._report_text,
        )
        remaining = [
            button for button in self.window.findChildren(QPushButton)
            if button.text() == "Remove"
        ]
        self.assertEqual(remaining, [])

    # -- version --------------------------------------------------

    def test_bump_version_changes_project_and_preview(self):
        QTest.mouseClick(self.window._bump_button, Qt.LeftButton)
        QTest.qWait(50)
        loaded, error = load_project(self.project.root)
        self.assertIsNone(error)
        self.assertEqual(loaded.version, "1.0.1")
        self.assertIn("Version: 1.0.1", self._preview_text())
        self.assertIn("Version is now 1.0.1", self._status())

    # -- installs -------------------------------------------------

    def test_install_reblend_copies_and_names_where(self):
        self._build_and_wait(
            self.window._build_reblend_button,
            "surprise-1.0.0.rblpack",
        )
        packs_dir = Path(self._tmp.name) / "reblend-packs"
        self.window.set_install_folder("reblend", packs_dir)
        self.assertTrue(self.window._install_reblend_button.isEnabled())
        QTest.mouseClick(
            self.window._install_reblend_button, Qt.LeftButton
        )
        QTest.qWait(50)
        installed = packs_dir / "surprise-1.0.0.rblpack"
        self.assertTrue(installed.is_file())
        self.assertIn("Installed in Reblend", self._status())
        self.assertIn(str(installed), self._status())

    def test_install_blender_copies_and_names_where(self):
        self._build_and_wait(
            self.window._build_blender_button,
            "surprise-1.0.0-blender.zip",
        )
        addons_dir = Path(self._tmp.name) / "blender-addons"
        self.window.set_install_folder("blender", addons_dir)
        self.assertTrue(self.window._install_blender_button.isEnabled())
        QTest.mouseClick(
            self.window._install_blender_button, Qt.LeftButton
        )
        QTest.qWait(50)
        installed = addons_dir / "surprise-1.0.0-blender.zip"
        self.assertTrue(installed.is_file())
        self.assertIn("Installed in Blender", self._status())
        self.assertIn(str(installed), self._status())

    def test_install_remembers_the_folder(self):
        # The setter persists, so a fresh window reuses the folder
        # without asking again.
        self._build_and_wait(
            self.window._build_reblend_button,
            "surprise-1.0.0.rblpack",
        )
        packs_dir = Path(self._tmp.name) / "remembered-packs"
        self.window.set_install_folder("reblend", packs_dir)
        second = PackWindow(
            project=self.project, settings=self.settings
        )
        try:
            second.show()
            QTest.qWait(50)
            self.assertEqual(
                second._install_folder("reblend"), str(packs_dir)
            )
        finally:
            second.close()

    # -- chat window wiring ---------------------------------------

    def test_stale_build_result_does_not_stick_the_buttons(self):
        # A build that finishes after the window closed (or after a
        # project switch) must not leave the window thinking a build
        # is still running: the window is reused after closing, and
        # stuck buttons would look like a dead window.
        self.window._building = True
        self.window._build_token = 5
        self.window._on_build_done(4, "reblend", None, [], "old error")
        self.assertFalse(self.window._building)
        self.window._refresh_buttons()
        self.assertTrue(self.window._build_reblend_button.isEnabled())
        self.assertTrue(self.window._build_blender_button.isEnabled())

    def test_switching_project_invalidates_an_in_flight_build(self):
        token = self.window._build_token
        other, error = create_project(
            Path(self._tmp.name) / "other",
            name="Other",
            targets=["blender"],
        )
        self.assertIsNone(error)
        self.window.set_project(other)
        self.assertGreater(self.window._build_token, token)
        token = self.window._build_token
        self.window.set_project(other)
        self.assertEqual(self.window._build_token, token)

    def test_pack_window_follows_project_switch(self):
        chat = ChatWindow(project=self.project)
        try:
            chat.show()
            QTest.qWait(50)
            chat._pack_window_action.trigger()
            QTest.qWait(100)
            pack = chat._pack_window
            self.assertIn("Surprise", pack.windowTitle())
            other, error = create_project(
                Path(self._tmp.name) / "other",
                name="Other",
                targets=["blender"],
            )
            self.assertIsNone(error)
            chat.set_project(other)
            QTest.qWait(50)
            self.assertIn("Other", pack.windowTitle())
            self.assertIn("Name: Other", "\n".join(
                pack._preview_text_lines
            ))
            # The new project is Blender-only: the Reblend build
            # button must have followed the switch too.
            self.assertFalse(pack._build_reblend_button.isEnabled())
            self.assertTrue(pack._build_blender_button.isEnabled())
        finally:
            if chat._pack_window is not None:
                chat._pack_window.close()
            chat.close()

    def test_chat_window_pack_menu_opens_pack_window(self):
        chat = ChatWindow(project=self.project)
        try:
            chat.show()
            QTest.qWait(50)
            chat._pack_window_action.trigger()
            QTest.qWait(100)
            pack = chat._pack_window
            self.assertIsNotNone(pack)
            self.assertTrue(pack.isVisible())
            self.assertIn("Surprise", pack.windowTitle())
            self.assertIn("Name: Surprise", "\n".join(
                pack._preview_text_lines
            ))
        finally:
            if chat._pack_window is not None:
                chat._pack_window.close()
            chat.close()


if __name__ == "__main__":
    unittest.main()
