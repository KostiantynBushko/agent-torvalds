"""
The request the context-window proof makes must not reach a service the
operator never named.

The server is named by the operator, through ``TORVALDS_OLLAMA_HOST`` —
it is the operator's own configuration, not input that arrives over a
network.  Three things are still refused, because they are the way a
request reaches a service nobody named:

* a **redirect to another host** — the request stays on the server it
  was aimed at;
* the **link-local range**, where the metadata service of a cloud
  provider lives;
* a **body of any size** — the answer of an Ollama server is a few
  kilobytes, and the read is capped.

The proof is a script under ``investigate/``, and it is loaded here by
path: these checks are about that script, and they keep it honest.

Run with:
    pytest tests/test_context_window_request_safety.py -v
"""
import importlib.util
import json
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "investigate" / "context-window-proof" / "verify_context_window.py"


# ---------------------------------------------------------------------------
# The script under test
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def proof():
    """Load the proof script by path."""
    # The script reads the server URL at import time and refuses a URL
    # it may not ask, so the environment is set to a safe one first.
    previous = os.environ.get("TORVALDS_OLLAMA_HOST")
    os.environ["TORVALDS_OLLAMA_HOST"] = "http://localhost:11434"
    try:
        spec = importlib.util.spec_from_file_location("context_window_proof", SCRIPT)
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        yield module
    finally:
        if previous is None:
            os.environ.pop("TORVALDS_OLLAMA_HOST", None)
        else:
            os.environ["TORVALDS_OLLAMA_HOST"] = previous


# ---------------------------------------------------------------------------
# A server of our own, on the loopback
# ---------------------------------------------------------------------------


class _Handler(BaseHTTPRequestHandler):
    """Answers what the test asks it to answer."""

    def do_GET(self):  # noqa: N802 — the name is the framework's
        self.server.hits.append(self.path)
        if self.path == "/redirect-elsewhere":
            self.send_response(302)
            self.send_header("Location", self.server.redirect_to)
            self.end_headers()
            return
        if self.path == "/redirect-same-host":
            self.send_response(302)
            self.send_header("Location", self.server.base + "/the-answer")
            self.end_headers()
            return
        if self.path == "/huge":
            # Valid JSON, and bigger than the cap: a body that is read
            # without a cap parses, so the difference is visible.
            body = json.dumps({"padding": "x" * (1024 * 1024 + 64)}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        body = json.dumps({"models": [], "answer": "ok"}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):  # noqa: D102 — the server is quiet
        pass


@pytest.fixture
def make_server():
    """Start loopback servers, and shut them down afterwards.

    A test that needs *two* servers gets two: the one the request is
    aimed at, and the one a redirect would steer it to.  The second one
    has to be reachable — a redirect to an address that is not there
    fails either way, and the test would not know the difference.
    """
    servers = []

    def start():
        httpd = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        httpd.hits = []
        httpd.base = f"http://127.0.0.1:{httpd.server_address[1]}"
        httpd.redirect_to = ""
        servers.append(httpd)
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        return httpd

    yield start

    for httpd in servers:
        httpd.shutdown()
        httpd.server_close()


# ---------------------------------------------------------------------------
# The base URL
# ---------------------------------------------------------------------------


class TestTheBaseUrl:
    """The URL the script may ask."""

    @pytest.mark.parametrize(
        "url",
        [
            "http://169.254.169.254/latest/meta-data/",  # the metadata service
            "http://169.254.1.1:80",  # the link-local range
            "http://[fe80::1]:11434",  # link-local, IPv6
            "http://metadata.google.internal",  # the same, by name
            "http://0.0.0.0:11434",  # "every address"
        ],
    )
    def test_a_host_that_must_not_be_asked_is_refused(self, proof, url):
        with pytest.raises(ValueError):
            proof._validate_base_url(url)

    @pytest.mark.parametrize(
        "url",
        [
            "file:///etc/passwd",
            "ftp://localhost:11434",
            "gopher://localhost:11434",
        ],
    )
    def test_a_scheme_that_is_not_http_is_refused(self, proof, url):
        with pytest.raises(ValueError):
            proof._validate_base_url(url)

    @pytest.mark.parametrize(
        "url",
        [
            "http://localhost:11434",  # the default
            "http://127.0.0.1:11434",  # the loopback, by address
            "http://192.168.1.10:11434",  # the operator's own box
        ],
    )
    def test_the_server_of_the_operator_is_allowed(self, proof, url):
        assert proof._validate_base_url(url) == url


# ---------------------------------------------------------------------------
# The request
# ---------------------------------------------------------------------------


class TestTheRequest:
    """What the request may do."""

    def test_a_redirect_to_another_host_is_not_followed(self, proof, make_server):
        """The request must stay on the server it was aimed at.

        The redirect points at a server that is *there* and would
        answer: a redirect to an address that is not there fails either
        way, and the test would not know the difference.
        """
        other = make_server()
        server = make_server()
        server.redirect_to = other.base + "/the-answer"

        proof.BASE_URL = server.base
        answer = proof._get("/redirect-elsewhere")

        assert answer is None, "the redirect was followed"
        assert other.hits == [], "the other host was asked"

    def test_a_redirect_to_the_same_host_is_followed(self, proof, make_server):
        """A redirect that stays on the server is not a redirect away."""
        server = make_server()
        proof.BASE_URL = server.base
        answer = proof._get("/redirect-same-host")

        assert answer is not None
        assert answer.get("answer") == "ok"
        assert "/the-answer" in server.hits

    def test_a_body_over_the_cap_is_refused(self, proof, make_server):
        """The read is capped: a body of any size is not read.

        The body is valid JSON, so a read without a cap would parse it
        and the difference would be visible.
        """
        server = make_server()
        proof.BASE_URL = server.base
        answer = proof._get("/huge")

        assert answer is None
        assert proof.MAX_RESPONSE_BYTES == 1024 * 1024

    def test_the_answer_of_the_server_is_returned(self, proof, make_server):
        """The ordinary case still works."""
        server = make_server()
        proof.BASE_URL = server.base
        answer = proof._get("/api/tags")

        assert answer is not None
        assert answer.get("answer") == "ok"
