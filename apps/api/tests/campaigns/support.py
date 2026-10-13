# ruff: noqa: E501  (SQL and picture bytes)
"""Builders of the campaign tests."""

import uuid
from dataclasses import dataclass
from datetime import date
from typing import Any

from sqlalchemy import Engine, text

from tests.campaigns.images import make_png
from tests.expenses.support import Client, Scene
from tests.financial.support import Fresh

ITEMS = (("Cachorro-quente", 800, 5), ("Pamonha", 650, None))


def created(client: Client, **overrides: Any) -> dict[str, Any]:
    """A campaign created by `client` (a DRAFT) and returned."""
    body: dict[str, Any] = {
        "title": "Festa Junina",
        "description": "Barracas, jogos e a camiseta da turma.",
        **overrides,
    }
    response = client.post("/campaigns", body)
    assert response.status_code == 201, response.text
    made: dict[str, Any] = response.json()
    return made


def with_item(client: Client, campaign_id: str, **overrides: Any) -> dict[str, Any]:
    """A product added to the campaign; the whole campaign is returned."""
    body: dict[str, Any] = {
        "name": "Cachorro-quente",
        "description": "Pao, salsicha e molho.",
        "price_cents": 800,
        "max_per_order": 5,
        **overrides,
    }
    response = client.post(f"/campaigns/{campaign_id}/items", body)
    assert response.status_code == 201, response.text
    detail: dict[str, Any] = response.json()
    return detail


def on_sale(client: Client, **overrides: Any) -> dict[str, Any]:
    """A campaign with two products, already on sale."""
    campaign = created(client, **overrides)
    for name, price, limit in ITEMS:
        with_item(client, campaign["id"], name=name, price_cents=price, max_per_order=limit)
    response = client.post(f"/campaigns/{campaign['id']}/activate")
    assert response.status_code == 200, response.text
    detail: dict[str, Any] = response.json()
    return detail


def manager(scene: Scene, label: str = "gestao") -> Client:
    """The management (role `treasurer`) of school A1."""
    return scene.person("treasurer", label=label)


def picture() -> tuple[str, bytes, str]:
    return ("capa.png", make_png(), "image/png")


@dataclass(frozen=True)
class Seeded:
    campaign: uuid.UUID
    items: list[uuid.UUID]


def seed_campaign(
    engine: Engine,
    fresh: Fresh,
    *,
    items: tuple[tuple[str, int, int | None], ...] = ITEMS,
    status: str = "ACTIVE",
    starts_on: date | None = None,
    ends_on: date | None = None,
    title: str = "Festa Junina",
) -> Seeded:
    """A COMMITTED campaign of a fresh school, written as the admin (the API sees it)."""
    with engine.begin() as connection:
        campaign: uuid.UUID = connection.execute(
            text(
                "INSERT INTO campaigns (organization_id, school_id, created_by_user_id, title, "
                "description, starts_on, ends_on) VALUES (:org, :school, :user, :title, "
                "'Barracas e jogos', :starts_on, :ends_on) RETURNING id"
            ),
            {
                "org": fresh.org,
                "school": fresh.school,
                "user": fresh.treasurer,
                "title": title,
                "starts_on": starts_on,
                "ends_on": ends_on,
            },
        ).scalar_one()
        ids: list[uuid.UUID] = [
            connection.execute(
                text(
                    "INSERT INTO campaign_items (organization_id, school_id, campaign_id, name, "
                    "price_cents, max_per_order, position) VALUES (:org, :school, :campaign, "
                    ":name, :price, :limit, :position) RETURNING id"
                ),
                {
                    "org": fresh.org,
                    "school": fresh.school,
                    "campaign": campaign,
                    "name": name,
                    "price": price,
                    "limit": limit,
                    "position": position,
                },
            ).scalar_one()
            for position, (name, price, limit) in enumerate(items)
        ]
        if status == "ACTIVE":
            connection.execute(
                text("UPDATE campaigns SET status = 'ACTIVE' WHERE id = :id"), {"id": campaign}
            )
        elif status == "ENDED":
            connection.execute(
                text("UPDATE campaigns SET status = 'ENDED', ended_at = now() WHERE id = :id"),
                {"id": campaign},
            )
    return Seeded(campaign, ids)
