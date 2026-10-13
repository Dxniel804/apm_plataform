"""Settings of the OCR service, from the environment. It refuses to start without a real secret."""

import os
from dataclasses import dataclass

MIN_TOKEN_LENGTH = 24


class ConfigError(RuntimeError):
    """The service must not start like this. The message never quotes a value."""


@dataclass(frozen=True)
class Config:
    token: str
    max_bytes: int
    max_pixels: int
    engine: str
    model_id: str
    model_revision: str
    models_dir: str
    env: str = "development"

    @staticmethod
    def from_env(environ: dict[str, str] | None = None) -> "Config":
        env = dict(os.environ if environ is None else environ)
        token = env.get("OCR_TOKEN", "")
        if len(token) < MIN_TOKEN_LENGTH:
            raise ConfigError(f"OCR_TOKEN must have at least {MIN_TOKEN_LENGTH} characters")
        try:
            max_bytes = int(env.get("OCR_MAX_BYTES", str(10 * 1024 * 1024)))
            max_pixels = int(env.get("OCR_MAX_PIXELS", str(50_000_000)))
        except ValueError:
            raise ConfigError("OCR_MAX_BYTES and OCR_MAX_PIXELS must be integers") from None
        if not 1 <= max_bytes <= 20 * 1024 * 1024 or max_pixels < 1:
            raise ConfigError("OCR_MAX_BYTES must be 1..20971520 and OCR_MAX_PIXELS positive")
        engine = env.get("OCR_ENGINE", "stub")
        if engine not in ("stub", "demo", "huggingface"):
            raise ConfigError("OCR_ENGINE must be 'stub', 'demo' or 'huggingface'")
        environment = env.get("ENV", "development")
        if engine == "demo" and environment == "production":
            raise ConfigError("the demo engine reads a made-up receipt: never with ENV=production")
        return Config(
            token=token,
            max_bytes=max_bytes,
            max_pixels=max_pixels,
            engine=engine,
            model_id=env.get("OCR_MODEL_ID", ""),
            model_revision=env.get("OCR_MODEL_REVISION", ""),
            models_dir=env.get("OCR_MODELS_DIR", "/models"),
            env=environment,
        )
