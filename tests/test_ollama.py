"""Tests for devsuite.chat.ollama.

The client talks to Ollama over plain HTTP on localhost. These tests
run against a fake Ollama — a small stdlib HTTP server on localhost
returning canned answers — because the sandbox has no real Ollama.
A real-PC run with real models is Joshua's verdict later.

Every failure mode is checked the plain-words way: Ollama down, slow,
or missing a model must come back as a sentence, never as an
exception or a stack trace.
"""

import json
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from devsuite.chat.ollama import OllamaClient


class FakeOllamaHandler(BaseHTTPRequestHandler):
    """Canned Ollama. Class attributes are the script the tests set."""

    # What GET /api/tags answers with: a dict, a raw string, or None
    # to answer with an HTTP 500 instead.
    tags_answer = {"models": [{"name": "qwen3.5:4b"}, {"name": "qwen3-vl:2b-instruct"}]}
    # What POST /api/chat answers with: a dict, a raw string, or None
    # to answer with an HTTP 404 (model not installed).
    chat_answer = {"message": {"role": "assistant", "content": "Hello from the model."}}
    # Seconds to wait before answering (for the timeout test).
    delay = 0.0

    def log_message(self, *args):
        # Keep the test output quiet.
        pass

    def _answer(self, payload, status=200):
        if self.delay:
            time.sleep(self.delay)
        if isinstance(payload, dict):
            body = json.dumps(payload).encode("utf-8")
        else:
            body = payload.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            # The client gave up (timeout test) — nothing to do.
            pass

    def do_GET(self):
        if self.path == "/api/tags":
            if self.tags_answer is None:
                self._answer({"error": "boom"}, status=500)
            else:
                self._answer(self.tags_answer)
        else:
            self._answer({"error": "not found"}, status=404)

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        self.rfile.read(length)  # The request body; canned answers ignore it.
        if self.path == "/api/chat":
            if self.chat_answer is None:
                self._answer({"error": "model not found"}, status=404)
            else:
                self._answer(self.chat_answer)
        else:
            self._answer({"error": "not found"}, status=404)


class OllamaTestCase(unittest.TestCase):
    def setUp(self):
        FakeOllamaHandler.tags_answer = {
            "models": [{"name": "qwen3.5:4b"}, {"name": "qwen3-vl:2b-instruct"}]
        }
        FakeOllamaHandler.chat_answer = {
            "message": {"role": "assistant", "content": "Hello from the model."}
        }
        FakeOllamaHandler.delay = 0.0
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), FakeOllamaHandler)
        self.thread = threading.Thread(
            target=lambda: self.server.serve_forever(poll_interval=0.05),
            daemon=True,
        )
        self.thread.start()
        port = self.server.server_address[1]
        self.client = OllamaClient(f"http://127.0.0.1:{port}")

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)


class TestListModels(OllamaTestCase):
    def test_lists_installed_models(self):
        names, error = self.client.list_models()
        self.assertIsNone(error)
        self.assertEqual(names, ["qwen3.5:4b", "qwen3-vl:2b-instruct"])

    def test_empty_model_list(self):
        FakeOllamaHandler.tags_answer = {"models": []}
        names, error = self.client.list_models()
        self.assertIsNone(error)
        self.assertEqual(names, [])

    def test_server_error_is_plain_words(self):
        FakeOllamaHandler.tags_answer = None  # Answer with a 500.
        names, error = self.client.list_models()
        self.assertEqual(names, [])
        self.assertIn("error", error)
        self.assertIn("500", error)

    def test_unreadable_answer_is_plain_words(self):
        FakeOllamaHandler.tags_answer = "this is not json"
        names, error = self.client.list_models()
        self.assertEqual(names, [])
        self.assertIn("could not read", error)

    def test_answer_without_models_is_plain_words(self):
        FakeOllamaHandler.tags_answer = {"something": "else"}
        names, error = self.client.list_models()
        self.assertEqual(names, [])
        self.assertIn("could not read", error)


class TestChat(OllamaTestCase):
    def test_chat_returns_reply_text(self):
        reply, error = self.client.chat(
            "qwen3.5:4b", [{"role": "user", "content": "Hi."}]
        )
        self.assertIsNone(error)
        self.assertEqual(reply, "Hello from the model.")

    def test_missing_model_is_plain_words(self):
        FakeOllamaHandler.chat_answer = None  # Answer with a 404.
        reply, error = self.client.chat(
            "not-a-model:1b", [{"role": "user", "content": "Hi."}]
        )
        self.assertIsNone(reply)
        self.assertIn("not-a-model:1b", error)
        self.assertIn("not installed", error)

    def test_unreadable_reply_is_plain_words(self):
        FakeOllamaHandler.chat_answer = "this is not json"
        reply, error = self.client.chat(
            "qwen3.5:4b", [{"role": "user", "content": "Hi."}]
        )
        self.assertIsNone(reply)
        self.assertIn("could not read", error)

    def test_reply_without_message_is_plain_words(self):
        FakeOllamaHandler.chat_answer = {"done": True}
        reply, error = self.client.chat(
            "qwen3.5:4b", [{"role": "user", "content": "Hi."}]
        )
        self.assertIsNone(reply)
        self.assertIn("could not read", error)


class TestOllamaDown(unittest.TestCase):
    def test_connection_refused_is_plain_words(self):
        # A port with nothing listening on it: Ollama is down.
        server = ThreadingHTTPServer(("127.0.0.1", 0), FakeOllamaHandler)
        port = server.server_address[1]
        server.server_close()
        client = OllamaClient(f"http://127.0.0.1:{port}")
        names, error = client.list_models()
        self.assertEqual(names, [])
        self.assertIn("not running", error)
        reply, error = client.chat("qwen3.5:4b", [{"role": "user", "content": "Hi."}])
        self.assertIsNone(reply)
        self.assertIn("not running", error)

    def test_slow_ollama_is_plain_words(self):
        FakeOllamaHandler.delay = 0.5
        server = ThreadingHTTPServer(("127.0.0.1", 0), FakeOllamaHandler)
        thread = threading.Thread(
            target=lambda: server.serve_forever(poll_interval=0.05), daemon=True
        )
        thread.start()
        try:
            port = server.server_address[1]
            client = OllamaClient(f"http://127.0.0.1:{port}")
            reply, error = client.chat(
                "qwen3.5:4b", [{"role": "user", "content": "Hi."}], timeout=0.05
            )
            self.assertIsNone(reply)
            self.assertIn("too long", error)
        finally:
            FakeOllamaHandler.delay = 0.0
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)


class TestLocalhostOnly(unittest.TestCase):
    def test_remote_url_is_refused(self):
        with self.assertRaises(ValueError):
            OllamaClient("http://example.com:11434")

    def test_localhost_names_are_allowed(self):
        for url in (
            "http://127.0.0.1:11434",
            "http://localhost:11434",
            "http://[::1]:11434",
        ):
            client = OllamaClient(url)
            self.assertEqual(client.base_url, url)


if __name__ == "__main__":
    unittest.main()
