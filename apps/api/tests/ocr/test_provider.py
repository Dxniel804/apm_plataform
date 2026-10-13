"""The HTTP provider against a REAL server on the loopback (a thread in the test): what it sends,
and what it makes of everything the other side can do wrong."""

import json
import threading
import time
from collections.abc import Callable, Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

import pytest
from pydantic import SecretStr

from app.ocr.config import OcrSettings
from app.ocr.provider import (
    MAX_RESPONSE_BYTES,
    HttpOcrProvider,
    OcrTimeoutError,
    OcrUnavailableError,
)

TOKEN = "t" * 32
GOOD = {
    "fields": {
        "total_cents": {"value": 8750, "confidence": 0.95},
        "date": {"value": "2026-09-10", "confidence": 0.9},
        "merchant": {"value": "PAPELARIA", "confidence": 0.7},
        "nonsense": "not a field",
        7: {"value": 1},
    },
    "model": "reader@abc123",
    "elapsed_ms": 412,
}


class Server:
    """A tiny OCR service: `reply(handler, body)` decides the answer; every request is recorded."""

    def __init__(self, reply: Callable[[BaseHTTPRequestHandler, bytes], None]) -> None:
        self.requests: list[dict[str, Any]] = []
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:
                length = int(self.headers.get("Content-Length", "0"))
                body = self.rfile.read(length)
                outer.requests.append(
                    {"path": self.path, "headers": dict(self.headers.items()), "body": body}
                )
                reply(self, body)

            def log_message(self, *args: object) -> None:
                pass

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.httpd.server_address[1]}"

    def close(self) -> None:
        self.httpd.shutdown()
        self.httpd.server_close()


def send(handler: BaseHTTPRequestHandler, status: int, body: bytes, **headers: str) -> None:
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(body)))
    for key, value in headers.items():
        handler.send_header(key.replace("_", "-"), value)
    handler.end_headers()
    handler.wfile.write(body)


@pytest.fixture
def serve() -> Iterator[Callable[[Callable[[BaseHTTPRequestHandler, bytes], None]], Server]]:
    servers: list[Server] = []

    def start(reply: Callable[[BaseHTTPRequestHandler, bytes], None]) -> Server:
        server = Server(reply)
        servers.append(server)
        return server

    yield start
    for server in servers:
        server.close()


def provider_for(url: str, timeout: float = 5.0) -> HttpOcrProvider:
    return HttpOcrProvider(
        OcrSettings(
            ocr_enabled=True, ocr_url=url, ocr_token=SecretStr(TOKEN), ocr_timeout_seconds=timeout
        )
    )


def test_it_sends_the_photo_as_the_body_with_the_token_and_reads_the_fields(serve: Any) -> None:
    server = serve(lambda h, body: send(h, 200, json.dumps(GOOD).encode()))
    image = b"\xff\xd8\xff\xe0" + b"photo" * 100

    result = provider_for(server.url).extract(image, "image/jpeg")

    (request,) = server.requests
    assert request["path"] == "/v1/extract"
    assert request["body"] == image
    assert request["headers"]["Authorization"] == f"Bearer {TOKEN}"
    assert request["headers"]["Content-Type"] == "image/jpeg"
    # an item that is not an object is dropped; names it does not know are carried and ignored later
    assert {"total_cents", "date", "merchant"} <= set(result.fields)
    assert "nonsense" not in result.fields
    assert (
        result.fields["total_cents"].value == 8750
        and result.fields["total_cents"].confidence == 0.95
    )
    assert result.model == "reader@abc123" and result.elapsed_ms == 412


def test_the_path_of_the_url_is_kept(serve: Any) -> None:
    server = serve(lambda h, body: send(h, 200, json.dumps(GOOD).encode()))

    provider_for(server.url + "/ocr/").extract(b"x", "image/png")

    assert server.requests[0]["path"] == "/ocr/v1/extract"


@pytest.mark.parametrize(
    "answer",
    [
        lambda h, b: send(h, 401, b'{"detail":"no"}'),
        lambda h, b: send(h, 500, b"boom"),
        lambda h, b: send(h, 302, b"", Location="http://elsewhere.invalid/"),  # never followed
        lambda h, b: send(h, 200, b"not json"),
        lambda h, b: send(h, 200, b"[1, 2, 3]"),
        lambda h, b: send(h, 200, b'{"fields": [1, 2]}'),
        lambda h, b: send(h, 200, b'{"nofields": {}}'),
        lambda h, b: send(h, 200, b"x" * (MAX_RESPONSE_BYTES + 1)),
    ],
    ids=["401", "500", "redirect", "not-json", "list", "fields-list", "no-fields", "too-big"],
)
def test_anything_but_the_contract_is_unavailable(serve: Any, answer: Any) -> None:
    server = serve(answer)

    with pytest.raises(OcrUnavailableError):
        provider_for(server.url).extract(b"x", "image/png")


def test_a_slow_service_is_a_timeout(serve: Any) -> None:
    def slow(handler: BaseHTTPRequestHandler, body: bytes) -> None:
        time.sleep(1.5)
        send(handler, 200, json.dumps(GOOD).encode())

    server = serve(slow)

    started = time.monotonic()
    with pytest.raises(OcrTimeoutError):
        provider_for(server.url, timeout=0.3).extract(b"x", "image/png")
    assert time.monotonic() - started < 1.2


def test_a_service_that_is_not_there_is_unavailable() -> None:
    with pytest.raises(OcrUnavailableError):
        provider_for("http://127.0.0.1:9").extract(b"x", "image/png")  # nothing listens on port 9


def test_a_server_that_hangs_up_is_unavailable(serve: Any) -> None:
    def hang_up(handler: BaseHTTPRequestHandler, body: bytes) -> None:
        handler.connection.close()

    server = serve(hang_up)

    with pytest.raises(OcrUnavailableError):
        provider_for(server.url).extract(b"x", "image/png")


def test_a_confidence_that_is_not_a_number_counts_as_zero(serve: Any) -> None:
    answer = {"fields": {"total_cents": {"value": 100, "confidence": "high"}}}
    server = serve(lambda h, body: send(h, 200, json.dumps(answer).encode()))

    result = provider_for(server.url).extract(b"x", "image/png")

    assert result.fields["total_cents"].confidence == 0.0
