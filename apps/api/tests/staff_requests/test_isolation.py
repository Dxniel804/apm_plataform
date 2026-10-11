"""A request never crosses a school: another school, another account and a person who may not see
somebody else's request all get the same 404 as a request that never existed."""

import uuid
from typing import Any

from httpx2 import Response

from tests.expenses.support import Scene
from tests.staff_requests.support import manager, opened, with_photo

NOTHING = "00000000-0000-4000-8000-000000000099"


def same_404(answers: list[Response]) -> None:
    bodies: list[dict[str, Any]] = []
    for response in answers:
        assert response.status_code == 404, response.text
        body = response.json()
        body.pop("request_id")
        bodies.append(body)
    assert all(body == bodies[0] for body in bodies)
    assert bodies[0]["code"] == "not_found"


def every_way_to_touch(
    client: Any, request_id: str, attachment_id: str, *, manages: bool = False
) -> list[Response]:
    ways = [
        client.get(f"/requests/{request_id}"),
        client.get(f"/requests/{request_id}/attachments/{attachment_id}"),
        client.post(f"/requests/{request_id}/cancel"),
    ]
    if manages:  # the routes of the management answer 403 before anything else to everybody else
        ways += [
            client.post(f"/requests/{request_id}/start"),
            client.post(f"/requests/{request_id}/resolve", {}),
        ]
    return ways


def test_a_school_outside_the_session_is_the_same_404_as_one_that_never_existed(
    scene: Scene,
) -> None:
    ana = scene.person("staff", school="1", label="ana")
    other = scene.person("staff", school="2", label="other")
    foreign = opened(other)

    for school in (other.school, scene.world.school_b1, uuid.uuid4(), NOTHING):
        same_404(
            [
                ana.get("/requests", school=school),
                ana.get(f"/requests/{foreign['id']}", school=school),
                ana.post("/requests", {"category": "OTHER", "title": "x"}, school=school),
            ]
        )
    assert ana.get("/requests").json()["items"] == []  # nothing was made in her school
    assert other.get("/requests").json()["items"][0]["id"] == foreign["id"]


def test_the_request_of_another_school_is_not_there_for_the_school_in_the_path(
    scene: Scene,
) -> None:
    ana = scene.person("staff", school="1", label="ana")
    other = scene.person("staff", school="2", label="other")
    foreign = opened(other)
    photo = with_photo(other, foreign["id"])

    mine = every_way_to_touch(ana, foreign["id"], photo["id"])
    nothing = every_way_to_touch(ana, NOTHING, NOTHING)

    same_404(mine + nothing)
    assert other.get(f"/requests/{foreign['id']}").json()["status"] == "OPEN"


def test_the_management_of_one_school_reaches_nothing_of_another(scene: Scene) -> None:
    other = scene.person("staff", school="2", label="other")
    foreign = opened(other)
    gestao = manager(scene)  # school A1
    gestao_b = scene.person("treasurer", org="b", label="gestao-b")

    for outsider in (gestao, gestao_b):
        same_404(
            [
                outsider.get("/requests", school=other.school),
                outsider.get(f"/requests/{foreign['id']}", school=other.school),
                outsider.post(f"/requests/{foreign['id']}/resolve", {}, school=other.school),
            ]
        )
    assert other.get(f"/requests/{foreign['id']}").json()["status"] == "OPEN"


def test_a_colleague_cannot_see_a_request_that_is_not_theirs(scene: Scene) -> None:
    author = scene.person("staff", label="author")
    colleague = scene.person("staff", label="colleague")
    request = opened(author)
    photo = with_photo(author, request["id"])

    answers = every_way_to_touch(colleague, request["id"], photo["id"])
    answers += every_way_to_touch(colleague, NOTHING, NOTHING)

    same_404(answers)
    assert colleague.get("/requests").json()["items"] == []
    assert author.get(f"/requests/{request['id']}").json()["status"] == "OPEN"


def test_the_tenant_is_not_taken_from_headers_either(scene: Scene) -> None:
    ana = scene.person("staff", school="1", label="ana")
    other = scene.person("staff", school="2", label="other")
    foreign = opened(other)
    forged = {
        "X-Organization-Id": str(scene.world.org_a2),
        "X-School-Id": str(scene.world.school_a2),
        "X-Tenant": str(scene.world.org_a2),
    }

    response = ana.get(f"/requests/{foreign['id']}", headers=forged)

    assert response.status_code == 404
