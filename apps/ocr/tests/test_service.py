"""The service as a client sees it: the token, the type, the size, the image, and the answer."""

import io
import threading
import time
from typing import Any

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from ocr_service.config import Config, ConfigError
from ocr_service.engines import DemoEngine, HuggingFaceEngine, StubEngine, make_engine
from ocr_service.main import create_app

TOKEN = "t" * 32
RECEIPT_TEXT = """MERCADO BOM PRECO LTDA
CNPJ 11.222.333/0001-81
EMISSAO 10/09/2026
VALOR A PAGAR R$ 87,50"""


def config(**overrides: Any) -> Config:
    base: dict[str, Any] = {
        "token": TOKEN,
        "max_bytes": 100_000,
        "max_pixels": 1_000_000,
        "engine": "stub",
        "model_id": "",
        "model_revision": "",
        "models_dir": "/models",
    }
    return Config(**{**base, **overrides})


class TextEngine:
    name = "text-engine"

    def __init__(self, text: str = RECEIPT_TEXT, delay: float = 0.0) -> None:
        self.text, self.delay, self.running, self.peak = text, delay, 0, 0
        self.lock = threading.Lock()

    def read(self, image: Image.Image) -> str:
        with self.lock:
            self.running += 1
            self.peak = max(self.peak, self.running)
        time.sleep(self.delay)
        with self.lock:
            self.running -= 1
        return self.text


def image_bytes(format: str = "PNG", size: tuple[int, int] = (20, 20)) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", size, "white").save(buffer, format=format)
    return buffer.getvalue()


def client(engine: Any = None, **overrides: Any) -> TestClient:
    return TestClient(create_app(config(**overrides), engine or TextEngine()))


def post(
    c: TestClient, body: bytes, content_type: str = "image/png", token: str | None = TOKEN
) -> Any:
    headers = {"Content-Type": content_type}
    if token is not None:
        headers["Authorization"] = f"Bearer {token}"
    return c.post("/v1/extract", content=body, headers=headers)


def test_a_photo_in_the_fields_out() -> None:
    response = post(client(), image_bytes())

    assert response.status_code == 200
    body = response.json()
    assert body["fields"] == {
        "total_cents": {"value": 8750, "confidence": 0.9},
        "date": {"value": "2026-09-10", "confidence": 0.9},
        "document_number": {"value": "11.222.333/0001-81", "confidence": 0.9},
        "merchant": {"value": "MERCADO BOM PRECO LTDA", "confidence": 0.7},
    }
    assert body["model"] == "text-engine" and isinstance(body["elapsed_ms"], int)
    assert "text" not in body and "MERCADO" not in str(body.get("text", ""))
    assert response.headers["cache-control"] == "no-store"


@pytest.mark.parametrize(
    "format_, content_type", [("PNG", "image/png"), ("JPEG", "image/jpeg"), ("WEBP", "image/webp")]
)
def test_the_three_formats(format_: str, content_type: str) -> None:
    assert post(client(), image_bytes(format_), content_type).status_code == 200


def test_the_stub_engine_answers_with_no_field_instead_of_failing() -> None:
    response = post(TestClient(create_app(config(), StubEngine())), image_bytes())

    assert response.status_code == 200 and response.json()["fields"] == {}


@pytest.mark.parametrize("token", [None, "", "wrong", TOKEN + "x", TOKEN[:-1]])
def test_without_the_secret_nothing_is_read(token: str | None) -> None:
    engine = TextEngine()

    response = post(client(engine), image_bytes(), token=token)

    assert response.status_code == 401
    assert engine.peak == 0


def test_the_secret_is_a_bearer_and_nothing_else() -> None:
    c = client()
    for header in (f"Basic {TOKEN}", TOKEN, "Bearer"):
        response = c.post(
            "/v1/extract",
            content=image_bytes(),
            headers={"Content-Type": "image/png", "Authorization": header},
        )
        assert response.status_code == 401, header


@pytest.mark.parametrize(
    "content_type", ["application/pdf", "image/gif", "image/svg+xml", "text/html", ""]
)
def test_only_png_jpeg_and_webp(content_type: str) -> None:
    assert post(client(), image_bytes(), content_type).status_code == 415


def test_the_bytes_must_be_the_declared_image() -> None:
    assert post(client(), image_bytes("JPEG"), "image/png").status_code == 422  # a JPEG called PNG
    assert post(client(), b"not an image at all", "image/png").status_code == 422
    assert post(client(), image_bytes()[:40], "image/png").status_code == 422  # truncated


def test_an_empty_body_is_a_422_and_a_big_one_a_413() -> None:
    assert post(client(), b"").status_code == 422
    assert (
        post(client(max_bytes=500), image_bytes(size=(200, 200)) + b"0" * 1000).status_code == 413
    )


def test_an_image_with_too_many_pixels_is_refused_not_decompressed() -> None:
    response = post(client(max_pixels=1000), image_bytes(size=(100, 100)))

    assert response.status_code == 422


def test_only_one_photo_is_read_at_a_time() -> None:
    engine = TextEngine(delay=0.15)
    c = client(engine)
    results: list[int] = []

    def go() -> None:
        results.append(post(c, image_bytes()).status_code)

    threads = [threading.Thread(target=go) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert results == [200] * 4
    assert engine.peak == 1


def test_health_needs_no_secret_and_reveals_nothing_but_the_engine() -> None:
    response = client().get("/health")

    assert response.status_code == 200 and response.json() == {
        "status": "ok",
        "engine": "text-engine",
    }


def test_there_is_no_documentation_to_browse() -> None:
    c = client()
    assert c.get("/docs").status_code == 404 and c.get("/openapi.json").status_code == 404


# --- configuration and engines -------------------------------------------------------------------


@pytest.mark.parametrize("token", ["", "short", "x" * 23])
def test_it_refuses_to_start_without_a_real_secret(token: str) -> None:
    with pytest.raises(ConfigError):
        Config.from_env({"OCR_TOKEN": token})


def test_the_configuration_from_the_environment() -> None:
    cfg = Config.from_env(
        {
            "OCR_TOKEN": TOKEN,
            "OCR_ENGINE": "huggingface",
            "OCR_MODEL_ID": "a/b",
            "OCR_MODEL_REVISION": "abc123",
        }
    )

    assert (cfg.engine, cfg.model_id, cfg.max_bytes) == ("huggingface", "a/b", 10 * 1024 * 1024)
    for bad in (
        {"OCR_ENGINE": "magic"},
        {"OCR_MAX_BYTES": "x"},
        {"OCR_MAX_BYTES": "0"},
        {"OCR_MAX_BYTES": str(10**9)},
    ):
        with pytest.raises(ConfigError):
            Config.from_env({"OCR_TOKEN": TOKEN, **bad})


def test_the_huggingface_engine_needs_a_pinned_model() -> None:
    for model, revision in (("", "abc"), ("a/b", ""), ("a/b", "main"), ("a/b", "HEAD")):
        with pytest.raises(ConfigError):
            make_engine(config(engine="huggingface", model_id=model, model_revision=revision))


def test_the_huggingface_engine_reads_through_its_pipeline() -> None:
    calls: list[Image.Image] = []

    def fake_pipeline(image: Image.Image) -> list[dict[str, str]]:
        calls.append(image)
        return [{"generated_text": "VALOR TOTAL 10,00"}]

    engine = HuggingFaceEngine("a/b", "0123456789abcdef", "/models", pipeline=fake_pipeline)

    assert engine.name == "a/b@0123456789ab"
    assert engine.read(Image.new("RGBA", (5, 5))) == "VALOR TOTAL 10,00"
    assert calls[0].mode == "RGB"  # the model always gets RGB
    assert (
        HuggingFaceEngine("a/b", "x", "/m", pipeline=lambda image: []).read(
            Image.new("RGB", (1, 1))
        )
        == ""
    )
    assert (
        HuggingFaceEngine("a/b", "x", "/m", pipeline=lambda image: [{"generated_text": 5}]).read(
            Image.new("RGB", (1, 1))
        )
        == ""
    )


def test_the_demo_engine_reads_a_made_up_receipt_and_never_in_production() -> None:
    response = post(TestClient(create_app(config(engine="demo"), DemoEngine())), image_bytes())

    assert response.json()["fields"]["total_cents"]["value"] == 8750
    assert response.json()["model"] == "demo"
    assert isinstance(make_engine(config(engine="demo")), DemoEngine)
    with pytest.raises(ConfigError):
        Config.from_env({"OCR_TOKEN": TOKEN, "OCR_ENGINE": "demo", "ENV": "production"})
    assert (
        Config.from_env({"OCR_TOKEN": TOKEN, "OCR_ENGINE": "demo", "ENV": "development"}).engine
        == "demo"
    )
