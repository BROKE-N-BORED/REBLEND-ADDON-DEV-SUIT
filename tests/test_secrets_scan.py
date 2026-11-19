"""Tests for devsuite.packing.secrets_scan.

The scan's job: catch anything secret-like before a pack is built, and
never repeat the secret itself. All "secrets" planted here are made-up
values that could never be real credentials.
"""

import tempfile
import unittest
from pathlib import Path

from devsuite.packing.secrets_scan import scan_pack

FAKE_API_KEY = "ak_live_9f2z7q_not_a_real_key"
FAKE_PASSWORD = "hunter2-not-a-real-password"
FAKE_TOKEN = "tok_4k9_not_a_real_token"


def write_pack(tmp, files):
    """Create a pack folder from {relative path: text or bytes}."""
    root = Path(tmp) / "pack"
    root.mkdir()
    for rel, content in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, bytes):
            path.write_bytes(content)
        else:
            path.write_text(content, encoding="utf-8")
    return root


class TestPlantedSecrets(unittest.TestCase):
    def test_api_key_line_is_caught(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = write_pack(tmp, {
                "addon.py": f'API_KEY = "{FAKE_API_KEY}"\n',
            })
            findings = scan_pack(root)
            self.assertEqual(len(findings), 1)
            self.assertEqual(findings[0]["file"], "addon.py")
            self.assertEqual(findings[0]["line"], 1)
            self.assertIn("API key", findings[0]["description"])

    def test_password_line_is_caught(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = write_pack(tmp, {
                "config.py": (
                    "# settings\n"
                    "# keep these safe\n"
                    f'password = "{FAKE_PASSWORD}"\n'
                ),
            })
            findings = scan_pack(root)
            self.assertEqual(len(findings), 1)
            self.assertEqual(findings[0]["file"], "config.py")
            self.assertEqual(findings[0]["line"], 3)
            self.assertIn("password", findings[0]["description"])

    def test_private_key_block_is_caught(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = write_pack(tmp, {
                "keys/id_rsa": (
                    "-----BEGIN RSA PRIVATE KEY-----\n"
                    "MIIEogIBAAKCAQEA7notarealkey0000000000000000000000000\n"
                    "-----END RSA PRIVATE KEY-----\n"
                ),
            })
            findings = scan_pack(root)
            self.assertEqual(len(findings), 1)
            self.assertEqual(findings[0]["file"], "keys/id_rsa")
            self.assertEqual(findings[0]["line"], 1)
            self.assertIn("private key", findings[0]["description"])

    def test_token_line_is_caught(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = write_pack(tmp, {
                "addon.py": f"token = '{FAKE_TOKEN}'\n",
            })
            findings = scan_pack(root)
            self.assertEqual(len(findings), 1)
            self.assertIn("token", findings[0]["description"])

    def test_bare_pass_with_equals_is_caught(self):
        # "pass =" is an assignment, unlike prose "pass:".
        with tempfile.TemporaryDirectory() as tmp:
            root = write_pack(tmp, {
                "addon.py": f'pass = "{FAKE_PASSWORD}"\n',
            })
            findings = scan_pack(root)
            self.assertEqual(len(findings), 1)
            self.assertIn("password", findings[0]["description"])

    def test_bare_word_token_value_is_caught(self):
        # An unquoted bare word still flags: in a config file a bare
        # word is a literal value, not a variable reference.
        with tempfile.TemporaryDirectory() as tmp:
            root = write_pack(tmp, {
                "config.txt": f"token = {FAKE_TOKEN}\n",
            })
            findings = scan_pack(root)
            self.assertEqual(len(findings), 1)
            self.assertIn("token", findings[0]["description"])

    def test_secret_value_never_appears_in_findings(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = write_pack(tmp, {
                "addon.py": (
                    f'API_KEY = "{FAKE_API_KEY}"\n'
                    f'password = "{FAKE_PASSWORD}"\n'
                    f"token = '{FAKE_TOKEN}'\n"
                ),
            })
            findings = scan_pack(root)
            self.assertEqual(len(findings), 3)
            blob = repr(findings)
            for secret in (FAKE_API_KEY, FAKE_PASSWORD, FAKE_TOKEN):
                self.assertNotIn(secret, blob)

    def test_findings_carry_file_line_and_description(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = write_pack(tmp, {
                "addon.py": f'API_KEY = "{FAKE_API_KEY}"\n',
            })
            findings = scan_pack(root)
            self.assertEqual(
                set(findings[0].keys()), {"file", "line", "description"}
            )
            self.assertIsInstance(findings[0]["line"], int)


class TestCleanTrees(unittest.TestCase):
    def test_clean_tree_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = write_pack(tmp, {
                "addon.py": (
                    "def register(api):\n"
                    "    api.wheel.add('Surprise', surprise.randomize)\n"
                ),
                "manifest.json": '{"id": "surprise", "name": "Surprise"}\n',
                "README.md": "# Surprise\n\nRandomize a material.\n",
            })
            self.assertEqual(scan_pack(root), [])

    def test_empty_folder_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "pack"
            root.mkdir()
            self.assertEqual(scan_pack(root), [])

    def test_placeholder_values_are_not_flagged(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = write_pack(tmp, {
                "addon.py": (
                    'API_KEY = "change-me"\n'
                    'password = ""\n'
                    'token = "your-token-here"\n'
                ),
            })
            self.assertEqual(scan_pack(root), [])

    def test_environment_reads_are_not_flagged(self):
        # Reading a secret from the environment at run time does not
        # put the secret in the pack.
        with tempfile.TemporaryDirectory() as tmp:
            root = write_pack(tmp, {
                "addon.py": (
                    'API_KEY = os.environ["MY_API_KEY"]\n'
                    'token = os.getenv("MY_TOKEN")\n'
                ),
            })
            self.assertEqual(scan_pack(root), [])

    def test_value_that_is_code_not_a_secret_is_not_flagged(self):
        # A variable named "token" holding a counter, a call result,
        # or a number is not a credential — the suite's own windows
        # do exactly this (token = self._build_token). The secret is
        # not in the file.
        with tempfile.TemporaryDirectory() as tmp:
            root = write_pack(tmp, {
                "addon.py": (
                    "token = self._build_token\n"
                    "token = get_token()\n"
                    "token = 0\n"
                ),
            })
            self.assertEqual(scan_pack(root), [])

    def test_bare_pass_with_colon_is_prose_not_a_password(self):
        # "The test it must pass:" is a sentence, not a credential.
        with tempfile.TemporaryDirectory() as tmp:
            root = write_pack(tmp, {
                "README.md": (
                    "# Surprise\n\n"
                    "The test it must pass: a child could open it.\n"
                ),
            })
            self.assertEqual(scan_pack(root), [])

    def test_mentioning_a_secret_word_without_a_value_is_not_flagged(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = write_pack(tmp, {
                "README.md": (
                    "# Surprise\n\n"
                    "Never put an API key or password in a pack.\n"
                ),
            })
            self.assertEqual(scan_pack(root), [])


class TestSkippedContent(unittest.TestCase):
    def test_binary_file_is_skipped(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = write_pack(tmp, {
                # Not valid UTF-8: treated as binary and skipped.
                "assets/texture.bin": (
                    b"\x00\x01\x02\xff\xfe" + FAKE_PASSWORD.encode()
                ),
            })
            self.assertEqual(scan_pack(root), [])

    def test_pycache_is_skipped(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = write_pack(tmp, {
                "__pycache__/addon.cpython-312.pyc": (
                    f'API_KEY = "{FAKE_API_KEY}"\n'.encode()
                ),
                "addon.py": "# clean\n",
            })
            self.assertEqual(scan_pack(root), [])

    def test_secret_in_subfolder_is_found(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = write_pack(tmp, {
                "code/helpers.py": f'password = "{FAKE_PASSWORD}"\n',
            })
            findings = scan_pack(root)
            self.assertEqual(len(findings), 1)
            self.assertEqual(findings[0]["file"], "code/helpers.py")


if __name__ == "__main__":
    unittest.main()
