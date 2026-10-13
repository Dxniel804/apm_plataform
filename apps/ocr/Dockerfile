# The OCR service (docs/ocr.md). Two targets:
#   dev  : the tests (`docker build --target dev`), stub engine only
#   run  : what runs; INSTALL_HF=1 adds transformers and torch (CPU wheels) for a Hugging Face model
# The container runs as a user with no privileges, with no network of its own besides the private
# one of docker-compose, and loads models ONLY from the read-only volume /models.
FROM python:3.12-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /srv
COPY pyproject.toml ./
RUN pip install --no-cache-dir "fastapi>=0.115" "pillow>=11.0" "uvicorn>=0.32"

FROM base AS dev
RUN pip install --no-cache-dir "httpx2>=2.0" "pytest>=8.3" "ruff>=0.8"
COPY ocr_service ./ocr_service
COPY tests ./tests
CMD ["pytest", "-q", "-p", "no:cacheprovider"]

FROM base AS run
ARG INSTALL_HF=0
RUN if [ "$INSTALL_HF" = "1" ]; then \
      pip install --no-cache-dir --extra-index-url https://download.pytorch.org/whl/cpu \
        "transformers>=4.46" "torch>=2.4"; \
    fi
COPY ocr_service ./ocr_service
RUN useradd --system --no-create-home --uid 10001 ocr
USER ocr
ENV HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 OCR_MODELS_DIR=/models
EXPOSE 8080
# One worker: the engine reads one photo at a time anyway, and a second process would load the model twice.
CMD ["uvicorn", "ocr_service.main:app_from_env", "--factory", "--host", "0.0.0.0", "--port", "8080", "--workers", "1"]
