# ruff: noqa: E501  (SQL and picture bytes)
"""A campaign never crosses a school: another school, another account and a made-up id all get the
same 404 as a campaign that never existed."""

import uuid
from typing import Any

from httpx2 import Response

from tests.campaigns.images import make_png
from tests.campaigns.support import created, manager, on_sale
from tests.expenses.support import Scene

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


def every_way_to_touch(client: Any, campaign_id: str, item_id: str) -> list[Response]:
    picture = {"files": {"file": ("a.png", make_png(), "image/png")}}
    return [
        client.get(f"/campaigns/{campaign_id}"),
        client.patch(f"/campaigns/{campaign_id}", {"title": "Sequestrada"}),
        client.post(f"/campaigns/{campaign_id}/activate"),
        client.post(f"/campaigns/{campaign_id}/end"),
        client.post(f"/campaigns/{campaign_id}/items", {"name": "Intruso", "price_cents": 500}),
        client.patch(f"/campaigns/{campaign_id}/items/{item_id}", {"price_cents": 100}),
        client.put(f"/campaigns/{campaign_id}/image", **picture),
        client.delete(f"/campaigns/{campaign_id}/image"),
        client.get(f"/campaigns/{campaign_id}/image"),
        client.put(f"/campaigns/{campaign_id}/items/{item_id}/image", **picture),
        client.get(f"/campaigns/{campaign_id}/items/{item_id}/image"),
    ]


def test_a_school_outside_the_session_is_the_same_404_as_one_that_never_existed(
    scene: Scene,
) -> None:
    ana = manager(scene, "ana")
    other = scene.person("secretaria", school="2", label="other")
    foreign = on_sale(other)

    for school in (other.school, scene.world.school_b1, uuid.uuid4(), NOTHING):
        same_404(
            [
                ana.get("/campaigns", school=school),
                ana.get(f"/campaigns/{foreign['id']}", school=school),
                ana.post("/campaigns", {"title": "x"}, school=school),
            ]
        )
    # nothing of the other school shows in hers, and nothing was made in hers
    assert foreign["id"] not in {i["id"] for i in ana.get("/campaigns").json()["items"]}
    assert foreign["id"] in {i["id"] for i in other.get("/campaigns").json()["items"]}


def test_the_campaign_of_another_school_is_a_404_for_every_way_to_touch_it(scene: Scene) -> None:
    ana = manager(scene, "ana")
    other = scene.person("secretaria", school="2", label="other")
    foreign = on_sale(other)
    mine = created(ana, title="Minha")

    # In her own school, with the id of a campaign (and a product) of the other one.
    same_404(every_way_to_touch(ana, foreign["id"], foreign["items"][0]["id"]))
    # In her own school, with her campaign and a product of the other one.
    same_404(
        [
            ana.patch(
                f"/campaigns/{mine['id']}/items/{foreign['items'][0]['id']}", {"price_cents": 100}
            ),
            ana.get(f"/campaigns/{mine['id']}/items/{foreign['items'][0]['id']}/image"),
        ]
    )
    # Nothing of the other school changed.
    after = other.get(f"/campaigns/{foreign['id']}").json()
    assert after["title"] == foreign["title"] and after["status"] == "ACTIVE"
    assert [i["price_cents"] for i in after["items"]] == [
        i["price_cents"] for i in foreign["items"]
    ]


def test_another_account_sees_none_of_it_and_cannot_name_a_product_of_it(scene: Scene) -> None:
    ana = manager(scene, "ana")
    mine = on_sale(ana)
    stranger = scene.person("secretaria", org="b", label="stranger")

    same_404(every_way_to_touch(stranger, mine["id"], mine["items"][0]["id"]))
    assert stranger.get("/campaigns").json()["items"] == []
