# ruff: noqa: E501  (SQL and picture bytes)
"""The life of a campaign: written by the management, a draft until it goes on sale, ended for good."""

import uuid
from typing import Any

import pytest
from sqlalchemy import Engine, text

from tests.campaigns.images import make_jpeg, make_png, make_webp
from tests.campaigns.support import created, manager, on_sale, with_item
from tests.expenses.support import Scene, pdf, stored_files


def titles(response: Any) -> list[str]:
    return [item["title"] for item in response.json()["items"]]


def test_a_campaign_is_created_as_a_draft_with_nothing_on_sale(scene: Scene) -> None:
    gestao = manager(scene)

    response = gestao.post(
        "/campaigns",
        {"title": "  Festa Junina  ", "starts_on": "2026-06-01", "ends_on": "2026-06-30"},
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["status"] == "DRAFT" and body["title"] == "Festa Junina"  # trimmed
    assert body["description"] is None and body["items"] == []
    assert body["starts_on"] == "2026-06-01" and body["ends_on"] == "2026-06-30"
    assert body["has_cover"] is False and body["items_count"] == 0
    assert body["paid_orders_count"] == 0 and body["paid_cents"] == 0


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"title": ""},
        {"title": "   "},
        {"title": "x" * 121},
        {"title": "x\x00y"},
        {"title": "x", "description": ""},
        {"title": "x", "description": "d" * 2001},
        {"title": "x", "starts_on": "2026-07-01", "ends_on": "2026-06-01"},
        {"title": "x", "starts_on": "not a date"},
        # nothing about who, where or in which state comes from the body
        {"title": "x", "status": "ACTIVE"},
        {"title": "x", "school_id": "00000000-0000-4000-8000-000000000001"},
        {"title": "x", "created_by_user_id": "00000000-0000-4000-8000-000000000001"},
    ],
)
def test_a_malformed_campaign_is_a_422_and_creates_nothing(
    scene: Scene, body: dict[str, Any]
) -> None:
    gestao = manager(scene)
    before = gestao.get("/campaigns").json()["items"]

    response = gestao.post("/campaigns", body)

    assert response.status_code == 422, response.text
    assert response.json()["code"] == "validation_error"
    assert gestao.get("/campaigns").json()["items"] == before


def test_a_campaign_goes_on_sale_only_with_an_active_product(scene: Scene) -> None:
    gestao = manager(scene)
    campaign = created(gestao)

    refused = gestao.post(f"/campaigns/{campaign['id']}/activate")
    assert refused.status_code == 409 and refused.json()["code"] == "campaign_needs_a_product"

    detail = with_item(gestao, campaign["id"])
    item_id = detail["items"][0]["id"]
    gestao.patch(f"/campaigns/{campaign['id']}/items/{item_id}", {"is_active": False})
    assert gestao.post(f"/campaigns/{campaign['id']}/activate").status_code == 409  # switched off

    gestao.patch(f"/campaigns/{campaign['id']}/items/{item_id}", {"is_active": True})
    activated = gestao.post(f"/campaigns/{campaign['id']}/activate")
    assert activated.status_code == 200 and activated.json()["status"] == "ACTIVE"
    assert gestao.post(f"/campaigns/{campaign['id']}/activate").status_code == 409  # once


def test_a_campaign_with_an_end_date_in_the_past_does_not_go_on_sale(scene: Scene) -> None:
    gestao = manager(scene)
    campaign = created(gestao, starts_on="2020-01-01", ends_on="2020-12-31")
    with_item(gestao, campaign["id"])

    response = gestao.post(f"/campaigns/{campaign['id']}/activate")

    assert response.status_code == 422, response.text
    assert response.json()["errors"] == [{"field": "ends_on", "code": "in_the_past"}]


def test_ending_is_final_and_freezes_the_campaign_and_its_products(scene: Scene) -> None:
    gestao = manager(scene)
    campaign = on_sale(gestao)
    item_id = campaign["items"][0]["id"]

    ended = gestao.post(f"/campaigns/{campaign['id']}/end")

    assert ended.status_code == 200 and ended.json()["status"] == "ENDED"
    assert gestao.post(f"/campaigns/{campaign['id']}/end").status_code == 409
    assert gestao.post(f"/campaigns/{campaign['id']}/activate").status_code == 409
    for response in (
        gestao.patch(f"/campaigns/{campaign['id']}", {"title": "Outro"}),
        gestao.patch(f"/campaigns/{campaign['id']}/items/{item_id}", {"price_cents": 900}),
        gestao.post(f"/campaigns/{campaign['id']}/items", {"name": "Novo", "price_cents": 500}),
        gestao.put(
            f"/campaigns/{campaign['id']}/image", files={"file": ("a.png", make_png(), "image/png")}
        ),
        gestao.delete(f"/campaigns/{campaign['id']}/image"),
    ):
        assert response.status_code == 409, response.text
        assert response.json()["code"] == "invalid_state"
    assert gestao.get(f"/campaigns/{campaign['id']}").json()["title"] == campaign["title"]


def test_a_draft_can_be_ended_without_ever_being_on_sale(scene: Scene) -> None:
    gestao = manager(scene)
    campaign = created(gestao)

    assert gestao.post(f"/campaigns/{campaign['id']}/end").json()["status"] == "ENDED"


def test_the_text_and_the_dates_change_and_null_clears_an_optional_field(scene: Scene) -> None:
    gestao = manager(scene)
    campaign = created(gestao, starts_on="2026-06-01", ends_on="2026-06-30")

    changed = gestao.patch(
        f"/campaigns/{campaign['id']}",
        {"title": "Festa de Sao Joao", "description": None, "ends_on": None},
    )

    assert changed.status_code == 200, changed.text
    body = changed.json()
    assert body["title"] == "Festa de Sao Joao" and body["description"] is None
    assert body["starts_on"] == "2026-06-01" and body["ends_on"] is None  # untouched / cleared


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"title": None},
        {"title": ""},
        {"starts_on": "2026-08-01"},  # after the end date of the campaign (2026-06-30)
        {"status": "ENDED"},
        {"school_id": "00000000-0000-4000-8000-000000000001"},
    ],
)
def test_a_bad_change_is_a_422_and_changes_nothing(scene: Scene, body: dict[str, Any]) -> None:
    gestao = manager(scene)
    campaign = created(gestao, starts_on="2026-06-01", ends_on="2026-06-30")

    response = gestao.patch(f"/campaigns/{campaign['id']}", body)

    assert response.status_code == 422, response.text
    assert gestao.get(f"/campaigns/{campaign['id']}").json()["title"] == "Festa Junina"


def test_a_product_has_a_price_a_limit_and_a_place_and_is_never_removed(scene: Scene) -> None:
    gestao = manager(scene)
    campaign = created(gestao)
    first = with_item(gestao, campaign["id"], name="Camiseta", price_cents=4500, position=2)
    second = with_item(gestao, campaign["id"], name="Pamonha", price_cents=650, position=1)

    assert [item["name"] for item in second["items"]] == ["Pamonha", "Camiseta"]  # by position
    shirt = first["items"][0]
    assert shirt["price_cents"] == 4500 and shirt["max_per_order"] == 5
    assert shirt["is_active"] is True and shirt["has_image"] is False

    changed = gestao.patch(
        f"/campaigns/{campaign['id']}/items/{shirt['id']}",
        {"price_cents": 5000, "max_per_order": None, "is_active": False, "name": "Camiseta GG"},
    )

    assert changed.status_code == 200, changed.text
    after = {item["id"]: item for item in changed.json()["items"]}[shirt["id"]]
    assert after["price_cents"] == 5000 and after["max_per_order"] is None
    assert after["is_active"] is False and after["name"] == "Camiseta GG"
    assert changed.json()["active_items_count"] == 1 and changed.json()["items_count"] == 2
    assert gestao.delete(f"/campaigns/{campaign['id']}/items/{shirt['id']}").status_code in (
        404,
        405,
    )


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"price_cents": 800},
        {"name": "x"},
        {"name": "", "price_cents": 800},
        {"name": "x" * 121, "price_cents": 800},
        {"name": "x", "price_cents": 99},
        {"name": "x", "price_cents": 1_000_001},
        {"name": "x", "price_cents": -800},
        {"name": "x", "price_cents": 8.5},
        {"name": "x", "price_cents": 800, "max_per_order": 0},
        {"name": "x", "price_cents": 800, "max_per_order": 100},
        {"name": "x", "price_cents": 800, "position": 1000},
        {"name": "x", "price_cents": 800, "description": "d" * 501},
        {"name": "x", "price_cents": 800, "is_active": False},
        {"name": "x", "price_cents": 800, "campaign_id": "00000000-0000-4000-8000-000000000001"},
    ],
)
def test_a_malformed_product_is_a_422_and_creates_nothing(
    scene: Scene, body: dict[str, Any]
) -> None:
    gestao = manager(scene)
    campaign = created(gestao)

    response = gestao.post(f"/campaigns/{campaign['id']}/items", body)

    assert response.status_code == 422, response.text
    assert gestao.get(f"/campaigns/{campaign['id']}").json()["items"] == []


def test_a_campaign_has_at_most_fifty_products(scene: Scene) -> None:
    gestao = manager(scene)
    campaign = created(gestao)
    for number in range(50):
        with_item(gestao, campaign["id"], name=f"Produto {number}")

    response = gestao.post(
        f"/campaigns/{campaign['id']}/items", {"name": "a mais", "price_cents": 500}
    )

    assert response.status_code == 409 and response.json()["code"] == "item_limit"


def test_the_list_has_the_ones_on_sale_first_and_filters_by_status(scene: Scene) -> None:
    gestao = manager(scene)
    tag = uuid.uuid4().hex[:8]  # the school may hold campaigns of other tests: look only at ours
    draft = created(gestao, title=f"Rascunho {tag}")
    live = on_sale(gestao, title=f"No ar {tag}")
    ended = created(gestao, title=f"Encerrada {tag}")
    gestao.post(f"/campaigns/{ended['id']}/end")

    def mine(response: Any) -> list[str]:
        return [title for title in titles(response) if title.endswith(tag)]

    assert mine(gestao.get("/campaigns")) == [live["title"], draft["title"], ended["title"]]
    assert mine(gestao.get("/campaigns", params={"status": "DRAFT"})) == [draft["title"]]
    assert mine(gestao.get("/campaigns", params={"status": "ACTIVE"})) == [live["title"]]
    assert mine(gestao.get("/campaigns", params={"status": "ENDED"})) == [ended["title"]]
    assert gestao.get("/campaigns", params={"status": "NOPE"}).status_code == 422


# --- the pictures ---------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("name", "content_type", "build"),
    [
        ("a.png", "image/png", make_png),
        ("a.jpg", "image/jpeg", make_jpeg),
        ("a.webp", "image/webp", make_webp),
    ],
)
def test_a_cover_is_stored_without_its_metadata_and_read_back(
    scene: Scene, name: str, content_type: str, build: Any
) -> None:
    gestao = manager(scene)
    campaign = created(gestao)

    response = gestao.put(
        f"/campaigns/{campaign['id']}/image", files={"file": (name, build(), content_type)}
    )

    assert response.status_code == 200, response.text
    assert response.json()["has_cover"] is True and response.json()["cover_version"] == 1
    read = gestao.get(f"/campaigns/{campaign['id']}/image")
    assert read.status_code == 200 and read.headers["content-type"] == content_type
    assert read.headers["x-content-type-options"] == "nosniff"
    assert read.headers["cache-control"] == "private, no-store"
    assert b"GPS" not in read.content and b"Exif" not in read.content  # the metadata is gone
    assert len(stored_files(scene.directory)) == 1


def test_replacing_a_picture_removes_the_old_file_and_bumps_the_version(scene: Scene) -> None:
    gestao = manager(scene)
    campaign = on_sale(gestao)
    item_id = campaign["items"][0]["id"]
    path = f"/campaigns/{campaign['id']}/items/{item_id}/image"

    first = gestao.put(path, files={"file": ("a.png", make_png(), "image/png")})
    second = gestao.put(path, files={"file": ("b.png", make_png(3, 3), "image/png")})

    assert first.status_code == second.status_code == 200
    item = {i["id"]: i for i in second.json()["items"]}[item_id]
    assert item["has_image"] is True and item["image_version"] == 2
    assert len(stored_files(scene.directory)) == 1  # the first one is gone
    assert gestao.delete(path).status_code == 200
    assert stored_files(scene.directory) == [] and gestao.get(path).status_code == 404


@pytest.mark.parametrize(
    ("content", "code", "status"),
    [
        (pdf(), "attachment_type_not_allowed", 415),
        (b"GIF89a....", "attachment_type_not_allowed", 415),
        (b"", "validation_error", 422),
        (make_png()[:-10], "validation_error", 422),  # a PNG that is cut
        (make_png(9000, 10), "validation_error", 422),  # too big in pixels
    ],
)
def test_a_file_that_is_not_a_good_picture_is_refused_and_nothing_is_stored(
    scene: Scene, content: bytes, code: str, status: int
) -> None:
    gestao = manager(scene)
    campaign = created(gestao)

    response = gestao.put(
        f"/campaigns/{campaign['id']}/image", files={"file": ("x.png", content, "image/png")}
    )

    assert response.status_code == status, response.text
    assert response.json()["code"] == code
    assert stored_files(scene.directory) == []
    assert gestao.get(f"/campaigns/{campaign['id']}").json()["has_cover"] is False


def test_a_picture_over_the_limit_is_a_413(scene: Scene) -> None:
    gestao = manager(scene)
    campaign = created(gestao)
    huge = make_png(extra=((b"zzZz", b"\x00" * (6 * 1024 * 1024)),))

    response = gestao.put(
        f"/campaigns/{campaign['id']}/image", files={"file": ("x.png", huge, "image/png")}
    )

    assert response.status_code == 413, response.text
    assert stored_files(scene.directory) == []


def test_the_type_comes_from_the_bytes_not_from_the_name(scene: Scene) -> None:
    gestao = manager(scene)
    campaign = created(gestao)

    response = gestao.put(
        f"/campaigns/{campaign['id']}/image",
        files={"file": ("foto.pdf", make_png(), "application/pdf")},
    )

    assert response.status_code == 200, response.text  # it IS a PNG, whatever it was called
    assert gestao.get(f"/campaigns/{campaign['id']}/image").headers["content-type"] == "image/png"


def test_the_actions_leave_an_audit_trail_without_free_text(
    scene: Scene, admin_engine: Engine
) -> None:
    gestao = manager(scene)
    campaign = on_sale(gestao, title="Titulo secreto da festa")

    with admin_engine.connect() as connection:
        rows = connection.execute(
            text(
                "SELECT action, after_data::text FROM audit_logs WHERE entity_id = :id "
                "ORDER BY occurred_at, id"
            ),
            {"id": campaign["id"]},
        ).all()
    actions = [row[0] for row in rows]
    assert "campaign.created" in actions and "campaign.activated" in actions
    assert actions.count("campaign.item_added") == 2
    assert all("Titulo secreto" not in (row[1] or "") for row in rows)
    assert all("Cachorro" not in (row[1] or "") for row in rows)
