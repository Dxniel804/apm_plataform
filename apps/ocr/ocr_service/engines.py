"""The engines: from a photo to TEXT. The fields and the checks are not the engine's job.

* `StubEngine` reads nothing: the service answers with no field. It lets the whole chain (the API,
  the network, the form) be tried before a model is installed, and is what the tests use.
* `DemoEngine` always reads the same made-up receipt (development and browser tests only).
* `HuggingFaceEngine` runs a model of the Hugging Face hub that was DOWNLOADED beforehand into the
  models volume. It never reaches the network (`local_files_only`, no remote code) and asks for a
  pinned revision, so what runs is exactly what was downloaded and reviewed.

Which model reads Brazilian receipts well is decided by the spike with real photos (docs/ocr.md); a
new model is a new class here (or just another `OCR_MODEL_ID` when `image-to-text` fits).
"""

from typing import Any, Protocol

from PIL import Image

from ocr_service.config import Config, ConfigError


class Engine(Protocol):
    name: str

    def read(self, image: Image.Image) -> str: ...


class StubEngine:
    name = "stub"

    def read(self, image: Image.Image) -> str:
        return ""


class DemoEngine:
    """A made-up receipt, always the same: to see the whole chain (and the form) work in development
    and in the tests of the browser, with no model. The config refuses it with ENV=production."""

    name = "demo"
    TEXT = (
        "PAPELARIA CENTRAL LTDA\nCNPJ: 11.222.333/0001-81\nCUPOM FISCAL ELETRONICO\n"
        "Data de emissao: 10/09/2026 14:32:10\nCANETA AZUL 10 2,50 25,00\n"
        "PAPEL SULFITE 5 12,40 62,00\nSUBTOTAL 87,00\nVALOR A PAGAR R$ 87,50\n"
    )

    def read(self, image: Image.Image) -> str:
        return self.TEXT


class HuggingFaceEngine:
    """`transformers` pipeline `image-to-text` over a local, pinned model."""

    def __init__(self, model_id: str, revision: str, models_dir: str, pipeline: Any = None) -> None:
        self.name = f"{model_id}@{revision[:12]}"
        if pipeline is None:  # the heavy import happens only when this engine is chosen
            import os

            from transformers import pipeline as make_pipeline

            os.environ.setdefault("HF_HUB_OFFLINE", "1")
            pipeline = make_pipeline(
                "image-to-text",
                model=model_id,
                revision=revision,
                trust_remote_code=False,
                model_kwargs={"local_files_only": True, "cache_dir": models_dir},
            )
        self._pipeline = pipeline

    def read(self, image: Image.Image) -> str:
        result = self._pipeline(image.convert("RGB"))
        if isinstance(result, list) and result and isinstance(result[0], dict):
            text = result[0].get("generated_text", "")
            return text if isinstance(text, str) else ""
        return ""


def make_engine(config: Config) -> Engine:
    if config.engine == "stub":
        return StubEngine()
    if config.engine == "demo":
        return DemoEngine()
    if not config.model_id or not config.model_revision:
        raise ConfigError(
            "OCR_MODEL_ID and OCR_MODEL_REVISION are required for the huggingface engine"
        )
    if config.model_revision in ("main", "master", "latest", "HEAD"):
        raise ConfigError("OCR_MODEL_REVISION must be a commit hash or tag, never a moving branch")
    return HuggingFaceEngine(config.model_id, config.model_revision, config.models_dir)
