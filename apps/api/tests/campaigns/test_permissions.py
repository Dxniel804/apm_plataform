# ruff: noqa: E501  (SQL and picture bytes)
"""Each route, each role: only `campaigns:manage` writes or reads a campaign of the management. A
role without it gets `403 permission_denied` before anything about the request is looked at."""

from typing import Any

import pytest

from app.auth.permissions import ROLE_PERMISSIONS, Permission
from tests.campaigns.images import make_png
from tests.campaigns.support import on_sale
from tests.expenses.support import Scene

ROLES = ["school_admin", "treasurer", "staff", "viewer"]
ANY = "00000000-0000-4000-8000-000000000001"
MANAGE = {role for role in ROLES if Permission.CAMPAIGNS_MANAGE in ROLE_PERMISSIONS[role]}


def _routes() -> list[tuple[str, str, dict[str, Any]]]:
    picture = {"files": {"file": ("a.png", make_png(), "image/png")}}
    item = {"json": {"name": "Pamonha", "price_cents": 650}}
    return [
        ("POST", "/campaigns", {"json": {"title": "Festa"}}),
        ("GET", "/campaigns", {}),
        ("GET", f"/campaigns/{ANY}", {}),
        ("PATCH", f"/campaigns/{ANY}", {"json": {"title": "Outra"}}),
        ("POST", f"/campaigns/{ANY}/activate", {}),
        ("POST", f"/campaigns/{ANY}/end", {}),
        ("POST", f"/campaigns/{ANY}/items", item),
        ("PATCH", f"/campaigns/{ANY}/items/{ANY}", {"json": {"price_cents": 700}}),
        ("PUT", f"/campaigns/{ANY}/image", picture),
        ("DELETE", f"/campaigns/{ANY}/image", {}),
        ("GET", f"/campaigns/{ANY}/image", {}),
        ("PUT", f"/campaigns/{ANY}/items/{ANY}/image", picture),
        ("DELETE", f"/campaigns/{ANY}/items/{ANY}/image", {}),
        ("GET", f"/campaigns/{ANY}/items/{ANY}/image", {}),
    ]


def test_the_set_of_roles_is_what_the_permission_map_says() -> None:
    """If the map of roles changes, this table must be looked at again."""
    assert {"school_admin", "treasurer"} == MANAGE
    assert "staff" not in MANAGE and "viewer" not in MANAGE


@pytest.mark.parametrize("role", ROLES)
def test_every_route_enforces_its_permission(scene: Scene, role: str) -> None:
    person = scene.person(role)
    checked = 0
    for method, tail, kwargs in _routes():
        response = person.request(method, tail, **kwargs)
        where = f"{role} {method} {tail}"
        if role in MANAGE:
            assert response.status_code != 403, (where, response.text)
            assert response.status_code in (200, 201, 404), (where, response.text)
        else:
            assert response.status_code == 403, (where, response.text)
            assert response.json()["code"] == "permission_denied", where
        checked += 1
    assert checked == 14


@pytest.mark.parametrize("role", ["staff", "viewer"])
def test_the_ones_without_the_permission_change_nothing_not_even_by_guessing_the_id(
    scene: Scene, role: str
) -> None:
    campaign = on_sale(scene.person("treasurer", label="gestao"))
    outsider = scene.person(role)

    for method, tail, kwargs in (
        ("PATCH", f"/campaigns/{campaign['id']}", {"json": {"title": "Sequestrada"}}),
        ("POST", f"/campaigns/{campaign['id']}/end", {}),
        ("PATCH", f"/campaigns/{campaign['id']}/items/{campaign['items'][0]['id']}",
         {"json": {"price_cents": 100}}),
    ):  # fmt: skip
        assert outsider.request(method, tail, **kwargs).status_code == 403
    after = scene.person("treasurer", label="gestao2").get(f"/campaigns/{campaign['id']}").json()
    assert after["title"] == campaign["title"] and after["status"] == "ACTIVE"
    assert after["items"][0]["price_cents"] == campaign["items"][0]["price_cents"]


def test_a_person_without_a_session_gets_a_401(scene: Scene) -> None:
    anonymous = scene.apis.make(configure=scene._configure)

    response = anonymous.client.get(f"/api/v1/schools/{scene.world.school_a1}/campaigns")

    assert response.status_code == 401
