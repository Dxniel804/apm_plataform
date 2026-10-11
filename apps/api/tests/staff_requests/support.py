"""Builders of the staff request tests."""

from typing import Any

from tests.expenses.support import Client, Scene, png


def opened(client: Client, **overrides: Any) -> dict[str, Any]:
    """A request opened by `client` (OPEN) and returned."""
    body: dict[str, Any] = {
        "category": "SUPPLIES",
        "title": "Faltou papel higienico",
        "description": "Acabou no banheiro do segundo andar.",
        **overrides,
    }
    response = client.post("/requests", body)
    assert response.status_code == 201, response.text
    created: dict[str, Any] = response.json()
    return created


def with_photo(client: Client, request_id: str) -> dict[str, Any]:
    response = client.post(
        f"/requests/{request_id}/attachments",
        files={"file": ("foto.png", png(), "image/png")},
    )
    assert response.status_code == 201, response.text
    created: dict[str, Any] = response.json()
    return created


def manager(scene: Scene, label: str = "gestao") -> Client:
    """The management (role `treasurer`) of school A1."""
    return scene.person("treasurer", label=label)
