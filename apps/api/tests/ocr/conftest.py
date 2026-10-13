"""A scene like the one of the expenses, with the reading of receipts pointed at a provider the test
chooses (a fake one, so no model and no network)."""

from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import Engine

from app.ocr.limits import ConcurrencyGate, UserRateLimiter
from app.ocr.provider import FakeOcrProvider, OcrProvider
from app.ocr.router import OcrRuntime, get_ocr_runtime
from tests.authsupport import ApiFactory, UserFactory
from tests.expenses.support import Scene, storage_overrides

DEFAULT_LIMIT = 1024 * 1024


class OpenGate(ConcurrencyGate):
    """A gate with one slot that is already taken: every reading finds the reading busy at once."""

    def acquire(self, wait: float = 0.0) -> bool:
        return False


def make_runtime(
    provider: OcrProvider | None, *, per_minute: int = 100, gate: ConcurrencyGate | None = None
) -> OcrRuntime:
    return OcrRuntime(
        provider=provider, limiter=UserRateLimiter(per_minute), gate=gate or ConcurrencyGate(2)
    )


@pytest.fixture
def ocr_scene(
    apis: ApiFactory, users: UserFactory, admin_engine: Engine, tmp_path: Path
) -> Callable[..., Scene]:
    """`ocr_scene(runtime)` -> a Scene whose apps read receipts through `runtime`."""

    def build(runtime: OcrRuntime | None = None, max_bytes: int = DEFAULT_LIMIT) -> Scene:
        directory = tmp_path / "files"
        storage = storage_overrides(directory, max_bytes)
        chosen = runtime or make_runtime(FakeOcrProvider())

        def configure(app: Any) -> None:
            storage(app)
            app.dependency_overrides[get_ocr_runtime] = lambda: chosen

        return Scene(apis, users, admin_engine, directory, configure)

    return build
