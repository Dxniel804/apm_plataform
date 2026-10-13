"""The OCR service: `POST /v1/extract` takes the photo as the body and answers the fields.

It lives on a private network, with no way out, behind a shared secret. It stores nothing, logs
nothing of the photo or of what was read, and reads one photo at a time. The API (apps/api) is its
only client and treats the answer as untrusted data.
"""

import hmac
import io
import logging
import threading
import time

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse
from PIL import Image, UnidentifiedImageError

from ocr_service.config import Config
from ocr_service.engines import Engine, make_engine
from ocr_service.parser import parse_receipt

logger = logging.getLogger("ocr_service")

ACCEPTED = {"image/png": "PNG", "image/jpeg": "JPEG", "image/webp": "WEBP"}


def create_app(config: Config | None = None, engine: Engine | None = None) -> FastAPI:
    settings = config or Config.from_env()
    chosen = engine or make_engine(settings)
    Image.MAX_IMAGE_PIXELS = settings.max_pixels  # Pillow refuses a "decompression bomb"
    one_at_a_time = threading.Lock()  # a CPU (or one GPU) reads a photo at a time
    app = FastAPI(title="APM OCR", docs_url=None, redoc_url=None, openapi_url=None)

    def authorised(request: Request) -> None:
        header = request.headers.get("authorization", "")
        scheme, _, token = header.partition(" ")
        if scheme.lower() != "bearer" or not hmac.compare_digest(
            token.encode(), settings.token.encode()
        ):
            raise HTTPException(status_code=401, detail="unauthorized")

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "engine": chosen.name}

    @app.post("/v1/extract", dependencies=[Depends(authorised)])
    async def extract(request: Request) -> JSONResponse:
        content_type = request.headers.get("content-type", "").split(";")[0].strip().lower()
        if content_type not in ACCEPTED:
            raise HTTPException(status_code=415, detail="only PNG, JPEG and WebP")
        declared = request.headers.get("content-length", "")
        if not (declared.isascii() and declared.isdigit()):
            raise HTTPException(status_code=411, detail="length required")
        if int(declared) > settings.max_bytes:
            raise HTTPException(status_code=413, detail="too large")
        body = bytearray()
        async for chunk in request.stream():
            body += chunk
            if len(body) > settings.max_bytes:
                raise HTTPException(status_code=413, detail="too large")
        if not body:
            raise HTTPException(status_code=422, detail="empty")
        return await run_in_threadpool(_read, bytes(body), content_type)

    def _read(data: bytes, content_type: str) -> JSONResponse:
        try:
            image = Image.open(io.BytesIO(data))
            if image.format != ACCEPTED[content_type]:
                raise HTTPException(status_code=422, detail="not the declared type")
            image.load()
        except HTTPException:
            raise
        except (UnidentifiedImageError, OSError, Image.DecompressionBombError, ValueError):
            raise HTTPException(status_code=422, detail="not a readable image") from None
        started = time.monotonic()
        with one_at_a_time:
            text = chosen.read(image)
        fields = parse_receipt(text)
        elapsed = int((time.monotonic() - started) * 1000)
        logger.info("read a photo: %d fields in %d ms", len(fields), elapsed)  # never the text
        return JSONResponse(
            {
                "fields": {
                    name: {"value": field.value, "confidence": field.confidence}
                    for name, field in fields.items()
                },
                "model": chosen.name,
                "elapsed_ms": elapsed,
            },
            headers={"Cache-Control": "no-store"},
        )

    return app


def app_from_env() -> FastAPI:  # `uvicorn ocr_service.main:app_from_env --factory`
    return create_app()
