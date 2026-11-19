"""A small client for Ollama, the local model runner (DOSSIER.md §7).

Ollama runs on this computer and nowhere else: the client only ever
talks to localhost, uses no API key, and touches no cloud. Every
method returns a ``(value, error)`` pair — ``error`` is None when the
call worked, and a plain-words sentence when it did not. Ollama being
down, slow, or missing a model is an ordinary answer, never a crash
or a stack trace.

Two calls:

* ``list_models()`` — GET /api/tags, the models installed here.
* ``chat(model, messages)`` — POST /api/chat, one reply, no
  streaming (streaming belongs to the chat window, a later item).
"""

from __future__ import annotations

import json
import socket
import urllib.error
import urllib.parse
import urllib.request

DEFAULT_BASE_URL = "http://127.0.0.1:11434"

# Hosts the client will talk to. Localhost only, always.
LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1"}


class OllamaClient:
    """Talk to a local Ollama server."""

    def __init__(self, base_url: str = DEFAULT_BASE_URL, timeout: float = 120):
        """Create a client for the Ollama server at ``base_url``.

        ``base_url`` must point at this computer (127.0.0.1, localhost,
        or ::1) — anything else is refused, because the suite never
        talks to a model over the network. ``timeout`` is the default
        wait for a chat reply, in seconds; small local models on this
        PC can take a while to answer.

        Raises ValueError only when ``base_url`` is not local — that is
        a mistake in the suite's own code, not a runtime failure.
        """
        host = urllib.parse.urlparse(base_url).hostname
        if host is None or host.lower() not in LOCAL_HOSTS:
            raise ValueError(
                "Ollama must run on this computer. "
                f"'{base_url}' does not point at localhost, so I refused it."
            )
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def list_models(self, timeout: float = 10) -> tuple[list[str], str | None]:
        """Return the names of the models installed in Ollama.

        Returns ``(names, error)``. ``names`` is a list like
        ["qwen3.5:4b"]; ``error`` is None on success, or a
        plain-words sentence when Ollama could not be reached or
        could not be understood.
        """
        data, error = self._request("GET", "/api/tags", None, timeout)
        if error is not None:
            return [], error
        models = data.get("models")
        if not isinstance(models, list):
            return [], (
                "Ollama answered about its models in a form "
                "I could not read."
            )
        names = [
            model["name"]
            for model in models
            if isinstance(model, dict) and isinstance(model.get("name"), str)
        ]
        return names, None

    def chat(
        self,
        model: str,
        messages: list[dict],
        timeout: float | None = None,
    ) -> tuple[str | None, str | None]:
        """Send a chat request to ``model`` and return its reply text.

        ``messages`` is a list of {"role": ..., "content": ...} dicts,
        in Ollama's form. Returns ``(reply, error)``: ``reply`` is the
        model's answer as text, or None when the call failed; ``error``
        is None on success, or a plain-words sentence saying what went
        wrong — Ollama down, the model not installed, the answer too
        slow, or an answer I could not read.
        """
        body = {"model": model, "messages": messages, "stream": False}
        data, error = self._request(
            "POST", "/api/chat", body, self.timeout if timeout is None else timeout
        )
        if error is not None:
            return None, error
        message = data.get("message") if isinstance(data, dict) else None
        content = message.get("content") if isinstance(message, dict) else None
        if not isinstance(content, str):
            return None, (
                "Ollama answered in a form I could not read. "
                "The reply had no message text in it."
            )
        return content, None

    def _request(
        self, method: str, path: str, body: dict | None, timeout: float
    ) -> tuple[dict, str | None]:
        """One HTTP call to Ollama. Returns ``(data, error)``.

        ``data`` is the parsed JSON answer ({} when the call failed);
        ``error`` is None on success, or a plain-words sentence.
        Never raises.
        """
        url = self.base_url + path
        payload = None
        headers = {}
        if body is not None:
            payload = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(url, data=payload, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                raw = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            return {}, self._http_error(exc, body)
        except urllib.error.URLError as exc:
            return {}, self._url_error(exc)
        except (TimeoutError, socket.timeout):
            return {}, (
                "Ollama took too long to answer. It may be busy loading "
                "a model. Wait a moment and try again."
            )
        except OSError:
            return {}, (
                "I could not reach Ollama on this computer. "
                "Check that Ollama is running and try again."
            )
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return {}, (
                "Ollama answered in a form I could not read. "
                "The reply was not the usual JSON shape."
            )
        if not isinstance(data, dict):
            return {}, (
                "Ollama answered in a form I could not read. "
                "The reply was not the usual JSON shape."
            )
        return data, None

    def _http_error(self, exc: urllib.error.HTTPError, body: dict | None) -> str:
        """A plain-words sentence for an HTTP error status from Ollama."""
        if exc.code == 404 and body is not None and "model" in body:
            return (
                f"The model '{body['model']}' is not installed in Ollama. "
                "Pick one of the installed models, or install this one, "
                "and try again."
            )
        return (
            f"Ollama answered with an error (status {exc.code}). "
            "Ollama may be starting up, or the request may have been "
            "one it could not handle. Wait a moment and try again."
        )

    def _url_error(self, exc: urllib.error.URLError) -> str:
        """A plain-words sentence for a failure to reach Ollama."""
        reason = exc.reason
        if isinstance(reason, ConnectionRefusedError):
            return (
                "Ollama is not running on this computer. "
                "Start Ollama and try again."
            )
        if isinstance(reason, (TimeoutError, socket.timeout)):
            return (
                "Ollama took too long to answer. It may be busy loading "
                "a model. Wait a moment and try again."
            )
        return (
            "I could not reach Ollama on this computer. "
            "Check that Ollama is running and try again."
        )
