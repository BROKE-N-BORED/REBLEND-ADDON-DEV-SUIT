"""Tests for devsuite.packing.installer (Phase 4, pulled forward).

Install and uninstall are file operations (DOSSIER.md §5.1): install
copies a .rblpack file or an unzipped pack folder into the packs
folder, uninstall deletes it, and no code ever runs. These tests check
that install copies and uninstall removes, that the packs folder is
always the one passed in, and that every failure — a missing file, a
file that is not a pack, a pack that is not installed — comes back in
plain words instead of a crash.
"""

import json
import shutil
import tempfile
import unittest
import zipfile
from pathlib import Path

from devsuite.packing.builder import build_pack
from devsuite.packing.installer import (
    install_blender_addon,
    install_pack,
    uninstall_pack,
)
from devsuite.projects.project import create_project
from devsuite.templates import template_dir

TEMPLATE = template_dir("surprise")


def make_pack_file(tmp, name="surprise-1.0.0.rblpack"):
    """Write a small .rblpack file and return its path."""
    path = Path(tmp) / name
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("manifest.json", '{"id": "surprise"}\n')
        zf.writestr("addon.py", "# entry point\n")
    return path


def make_pack_folder(tmp, name="surprise"):
    """Write a small unzipped pack folder and return its path."""
    folder = Path(tmp) / name
    folder.mkdir()
    (folder / "manifest.json").write_text(
        '{"id": "surprise"}\n', encoding="utf-8"
    )
    (folder / "addon.py").write_text("# entry point\n", encoding="utf-8")
    return folder


class TestInstallPack(unittest.TestCase):
    def test_install_copies_a_pack_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            pack = make_pack_file(tmp)
            packs_dir = Path(tmp) / "packs"
            installed, error = install_pack(pack, packs_dir)
            self.assertIsNone(error)
            self.assertEqual(installed, packs_dir / "surprise-1.0.0.rblpack")
            self.assertTrue(installed.is_file())
            with zipfile.ZipFile(installed) as zf:
                self.assertEqual(
                    sorted(zf.namelist()), ["addon.py", "manifest.json"]
                )
            # The original is still there: install copies, not moves.
            self.assertTrue(pack.is_file())

    def test_install_creates_the_packs_folder(self):
        with tempfile.TemporaryDirectory() as tmp:
            pack = make_pack_file(tmp)
            packs_dir = Path(tmp) / "deep" / "packs"
            self.assertFalse(packs_dir.exists())
            installed, error = install_pack(pack, packs_dir)
            self.assertIsNone(error)
            self.assertTrue(installed.is_file())

    def test_install_copies_an_unzipped_pack_folder(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = make_pack_folder(tmp)
            packs_dir = Path(tmp) / "packs"
            installed, error = install_pack(folder, packs_dir)
            self.assertIsNone(error)
            self.assertEqual(installed, packs_dir / "surprise")
            self.assertTrue((installed / "manifest.json").is_file())
            self.assertTrue((installed / "addon.py").is_file())

    def test_reinstall_replaces_the_copy_already_there(self):
        with tempfile.TemporaryDirectory() as tmp:
            pack = make_pack_file(tmp)
            packs_dir = Path(tmp) / "packs"
            install_pack(pack, packs_dir)
            # Rebuild the pack with a new file in it, then reinstall.
            with zipfile.ZipFile(pack, "a") as zf:
                zf.writestr("README.md", "# Surprise\n")
            installed, error = install_pack(pack, packs_dir)
            self.assertIsNone(error)
            with zipfile.ZipFile(installed) as zf:
                self.assertIn("README.md", zf.namelist())

    def test_reinstall_replaces_an_unzipped_folder_cleanly(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = make_pack_folder(tmp)
            packs_dir = Path(tmp) / "packs"
            install_pack(folder, packs_dir)
            # A stale file in the installed copy must not survive.
            (packs_dir / "surprise" / "stale.txt").write_text("old\n")
            installed, error = install_pack(folder, packs_dir)
            self.assertIsNone(error)
            self.assertFalse((installed / "stale.txt").exists())

    def test_install_of_a_missing_pack_fails_plainly(self):
        with tempfile.TemporaryDirectory() as tmp:
            installed, error = install_pack(
                Path(tmp) / "nope-1.0.0.rblpack", Path(tmp) / "packs"
            )
            self.assertIsNone(installed)
            self.assertIn("could not find", error)

    def test_install_of_a_file_that_is_not_a_pack_fails_plainly(self):
        with tempfile.TemporaryDirectory() as tmp:
            text_file = Path(tmp) / "notes.txt"
            text_file.write_text("not a pack\n", encoding="utf-8")
            installed, error = install_pack(text_file, Path(tmp) / "packs")
            self.assertIsNone(installed)
            self.assertIn(".rblpack", error)


class TestInstallBlenderAddon(unittest.TestCase):
    def test_install_copies_a_blender_zip(self):
        with tempfile.TemporaryDirectory() as tmp:
            zip_path = Path(tmp) / "surprise-1.0.0-blender.zip"
            with zipfile.ZipFile(zip_path, "w") as zf:
                zf.writestr("__init__.py", "# entry point\n")
                zf.writestr("blender_manifest.toml", 'id = "surprise"\n')
            addons_dir = Path(tmp) / "addons"
            installed, error = install_blender_addon(zip_path, addons_dir)
            self.assertIsNone(error)
            self.assertEqual(
                installed, addons_dir / "surprise-1.0.0-blender.zip"
            )
            self.assertTrue(installed.is_file())
            # The original is still there: install copies, not moves.
            self.assertTrue(zip_path.is_file())

    def test_reinstall_replaces_the_copy(self):
        with tempfile.TemporaryDirectory() as tmp:
            zip_path = Path(tmp) / "surprise-1.0.0-blender.zip"
            with zipfile.ZipFile(zip_path, "w") as zf:
                zf.writestr("__init__.py", "# version one\n")
            addons_dir = Path(tmp) / "addons"
            install_blender_addon(zip_path, addons_dir)
            with zipfile.ZipFile(zip_path, "w") as zf:
                zf.writestr("__init__.py", "# version two\n")
            installed, error = install_blender_addon(zip_path, addons_dir)
            self.assertIsNone(error)
            with zipfile.ZipFile(installed) as zf:
                self.assertEqual(
                    zf.read("__init__.py").decode(), "# version two\n"
                )

    def test_a_file_that_is_not_a_zip_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            other = Path(tmp) / "surprise-1.0.0.rblpack"
            other.write_bytes(b"not a zip")
            installed, error = install_blender_addon(
                other, Path(tmp) / "addons"
            )
            self.assertIsNone(installed)
            self.assertIn("zip", error)

    def test_missing_file_fails_plainly(self):
        with tempfile.TemporaryDirectory() as tmp:
            installed, error = install_blender_addon(
                Path(tmp) / "missing.zip", Path(tmp) / "addons"
            )
            self.assertIsNone(installed)
            self.assertIn("could not find", error)


class TestUninstallPack(unittest.TestCase):
    def test_uninstall_removes_an_installed_pack_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            pack = make_pack_file(tmp)
            packs_dir = Path(tmp) / "packs"
            install_pack(pack, packs_dir)
            removed, error = uninstall_pack(packs_dir, "surprise")
            self.assertIsNone(error)
            self.assertEqual(removed, [packs_dir / "surprise-1.0.0.rblpack"])
            self.assertFalse((packs_dir / "surprise-1.0.0.rblpack").exists())

    def test_uninstall_removes_an_unzipped_pack_folder(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = make_pack_folder(tmp)
            packs_dir = Path(tmp) / "packs"
            install_pack(folder, packs_dir)
            removed, error = uninstall_pack(packs_dir, "surprise")
            self.assertIsNone(error)
            self.assertEqual(removed, [packs_dir / "surprise"])
            self.assertFalse((packs_dir / "surprise").exists())

    def test_uninstall_removes_every_version(self):
        with tempfile.TemporaryDirectory() as tmp:
            packs_dir = Path(tmp) / "packs"
            install_pack(make_pack_file(tmp, "surprise-1.0.0.rblpack"), packs_dir)
            install_pack(make_pack_file(tmp, "surprise-1.1.0.rblpack"), packs_dir)
            removed, error = uninstall_pack(packs_dir, "surprise")
            self.assertIsNone(error)
            self.assertEqual(len(removed), 2)
            self.assertEqual(list(packs_dir.iterdir()), [])

    def test_uninstall_of_a_pack_that_is_not_installed_fails_plainly(self):
        with tempfile.TemporaryDirectory() as tmp:
            packs_dir = Path(tmp) / "packs"
            packs_dir.mkdir()
            removed, error = uninstall_pack(packs_dir, "surprise")
            self.assertEqual(removed, [])
            self.assertIn("not installed", error)

    def test_uninstall_twice_fails_the_second_time(self):
        with tempfile.TemporaryDirectory() as tmp:
            pack = make_pack_file(tmp)
            packs_dir = Path(tmp) / "packs"
            install_pack(pack, packs_dir)
            uninstall_pack(packs_dir, "surprise")
            removed, error = uninstall_pack(packs_dir, "surprise")
            self.assertEqual(removed, [])
            self.assertIn("not installed", error)

    def test_uninstall_leaves_other_packs_alone(self):
        with tempfile.TemporaryDirectory() as tmp:
            packs_dir = Path(tmp) / "packs"
            install_pack(make_pack_file(tmp, "surprise-1.0.0.rblpack"), packs_dir)
            install_pack(make_pack_file(tmp, "water-2.0.0.rblpack"), packs_dir)
            removed, error = uninstall_pack(packs_dir, "surprise")
            self.assertIsNone(error)
            self.assertTrue((packs_dir / "water-2.0.0.rblpack").is_file())

    def test_uninstall_with_a_bad_id_fails_plainly(self):
        with tempfile.TemporaryDirectory() as tmp:
            removed, error = uninstall_pack(Path(tmp) / "packs", "../escape")
            self.assertEqual(removed, [])
            self.assertIn("pack id", error)


class TestBuildInstallUninstallRoundTrip(unittest.TestCase):
    def test_build_install_uninstall_from_the_template(self):
        with tempfile.TemporaryDirectory() as tmp:
            project, error = create_project(
                Path(tmp) / "surprise",
                name="Surprise",
                description="Randomize a material for inspiration.",
                targets=["reblend"],
                version="1.0.0",
                author="Joshua Lofland",
            )
            assert error is None, error
            shutil.copytree(TEMPLATE / "src", project.root / "src", dirs_exist_ok=True)
            shutil.copy2(TEMPLATE / "README.md", project.root / "README.md")
            out_dir = Path(tmp) / "out"
            pack_path, _, error = build_pack(
                project, out_dir,
                contributions={"wheel": [
                    {"label": "Surprise", "action": "surprise.randomize"}
                ]},
            )
            assert error is None, error
            packs_dir = Path(tmp) / "packs"
            installed, error = install_pack(pack_path, packs_dir)
            self.assertIsNone(error)
            self.assertTrue(installed.is_file())
            removed, error = uninstall_pack(packs_dir, "surprise")
            self.assertIsNone(error)
            self.assertEqual(removed, [packs_dir / "surprise-1.0.0.rblpack"])
            self.assertFalse(installed.exists())
            self.assertEqual(list(packs_dir.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
