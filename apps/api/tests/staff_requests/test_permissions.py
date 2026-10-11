"""Each route, each role: the permission the route declares is the one it enforces. A role without
it gets `403 permission_denied` before anything about the request is looked at; a role with it gets
past the gate (a 404 for a request that does not exist, a 201 for a creation)."""

from typing import Any

import pytest

from app.auth.permissions import ROLE_PERMISSIONS, Permission
from tests.expenses.support import Scene, png
from tests.staff_requests.support import opened

ROLES = ["school_admin", "treasurer", "staff", "viewer"]
ANY = "00000000-0000-4000-8000-000000000001"
SUBMIT = {role for role in ROLES if Permission.REQUESTS_SUBMIT in ROLE_PERMISSIONS[role]}
READ = {
    role
    for role in ROLES
    if {Permission.REQUESTS_READ_OWN, Permission.REQUESTS_READ_ALL} & ROLE_PERMISSIONS[role]
}
MANAGE = {role for role in ROLES if Permission.REQUESTS_MANAGE in ROLE_PERMISSIONS[role]}


def _routes() -> list[tuple[str, str, dict[str, Any], set[str]]]:
    upload = {"files": {"file": ("a.png", png(), "image/png")}}
    return [
        ("POST", "/requests", {"json": {"category": "OTHER", "title": "Cola"}}, SUBMIT),
        ("GET", "/requests", {}, READ),
        ("GET", f"/requests/{ANY}", {}, READ),
        ("POST", f"/requests/{ANY}/attachments", upload, SUBMIT),
        ("GET", f"/requests/{ANY}/attachments/{ANY}", {}, READ),
        ("POST", f"/requests/{ANY}/start", {}, MANAGE),
        ("POST", f"/requests/{ANY}/resolve", {"json": {}}, MANAGE),
        ("POST", f"/requests/{ANY}/cancel", {}, SUBMIT),
    ]


def test_the_sets_of_roles_are_what_the_permission_map_says() -> None:
    """If the map of roles changes, this table must be looked at again."""
    assert {"school_admin", "staff"} == SUBMIT
    assert {"school_admin", "treasurer", "staff"} == READ
    assert {"school_admin", "treasurer"} == MANAGE
    assert "viewer" not in SUBMIT | READ | MANAGE


@pytest.mark.parametrize("role", ROLES)
def test_every_route_enforces_its_permission(scene: Scene, role: str) -> None:
    person = scene.person(role)
    checked = 0
    for method, tail, kwargs, allowed in _routes():
        response = person.request(method, tail, **kwargs)
        where = f"{role} {method} {tail}"
        if role in allowed:
            assert response.status_code != 403, (where, response.text)
            assert response.status_code in (200, 201, 404), (where, response.text)
        else:
            assert response.status_code == 403, (where, response.text)
            assert response.json()["code"] == "permission_denied", where
        checked += 1
    assert checked == 8


def test_the_staff_cannot_answer_a_request_not_even_their_own(scene: Scene) -> None:
    author = scene.person("staff", label="author")
    request = opened(author)

    for action in ("start", "resolve"):
        response = author.post(f"/requests/{request['id']}/{action}")
        assert (response.status_code, response.json()["code"]) == (403, "permission_denied")
    assert author.get(f"/requests/{request['id']}").json()["status"] == "OPEN"


def test_the_management_cannot_open_a_request(scene: Scene) -> None:
    gestao = scene.person("treasurer", label="gestao")

    response = gestao.post("/requests", {"category": "OTHER", "title": "Do tesoureiro"})

    assert (response.status_code, response.json()["code"]) == (403, "permission_denied")


def test_a_person_without_a_session_gets_a_401(scene: Scene) -> None:
    anonymous = scene.apis.make(configure=scene._configure)
    path = f"/api/v1/schools/{scene.world.school_a1}/requests"

    assert anonymous.client.get(path).status_code == 401
