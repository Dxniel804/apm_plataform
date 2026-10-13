# ruff: noqa: E501  (SQL and picture bytes)
"""The campaigns on sale, seen by a family with no login: the page, the cart, the order and the pictures.
The rule that matters: the order carries which products and how many, never a price or a total."""

import hashlib
import uuid
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pytest
from httpx2 import Response
from sqlalchemy import Engine, text

from app.storage import LocalDiskStore
from tests.authsupport import Api, ApiFactory
from tests.campaigns.images import make_png
from tests.campaigns.support import seed_campaign
from tests.expenses.support import storage_overrides
from tests.public.conftest import PublicSchool
from tests.public.support import charge_url, row, txid_of


def base(slug: str) -> str:
    return f"/api/v1/public/schools/{slug}/campaigns"


def order(
    api: Api,
    slug: str,
    campaign: uuid.UUID,
    lines: list[tuple[uuid.UUID, int]],
    *,
    key: uuid.UUID | str | None = None,
    **fields: Any,
) -> Response:
    headers = {} if key == "" else {"Idempotency-Key": str(key or uuid.uuid4())}
    body = {"lines": [{"item_id": str(item), "quantity": qty} for item, qty in lines], **fields}
    return api.post(f"{base(slug)}/{campaign}/orders", body, csrf=False, headers=headers)


def _pay(api: Api, txid: str) -> Response:
    return api.post(f"/api/v1/dev/sandbox/pix/{txid}/pay", None, csrf=False)


def count(engine: Engine, sql: str, **params: Any) -> int:
    found = row(engine, sql, **params)
    return int(found[0])


def contributions(engine: Engine, school: PublicSchool) -> int:
    return count(
        engine, "SELECT count(*) FROM contributions WHERE school_id = :s", s=school.fresh.school
    )


# --- the page -------------------------------------------------------------------------------------


def test_the_campaigns_on_sale_are_listed_and_no_internal_id_leaks(
    apis: ApiFactory, school: PublicSchool, admin_engine: Engine
) -> None:
    seeded = seed_campaign(admin_engine, school.fresh)

    response = apis.make().get(base(school.slug))

    assert response.status_code == 200, response.text
    campaigns = response.json()["campaigns"]
    assert [c["id"] for c in campaigns] == [str(seeded.campaign)]
    assert campaigns[0]["title"] == "Festa Junina" and campaigns[0]["items_count"] == 2
    assert campaigns[0]["has_cover"] is False and campaigns[0]["ends_on"] is None
    for internal in (str(school.fresh.school), str(school.fresh.org), str(school.fresh.treasurer)):
        assert internal not in response.text
    assert response.headers["cache-control"] == "private, no-store"
    assert response.headers["referrer-policy"] == "no-referrer"


def test_a_campaign_shows_its_active_products_with_their_current_prices(
    apis: ApiFactory, school: PublicSchool, admin_engine: Engine
) -> None:
    seeded = seed_campaign(admin_engine, school.fresh)
    with admin_engine.begin() as conn:
        conn.execute(
            text("UPDATE campaign_items SET is_active = false WHERE id = :i"),
            {"i": seeded.items[1]},
        )
        conn.execute(
            text("UPDATE campaign_items SET price_cents = 900 WHERE id = :i"),
            {"i": seeded.items[0]},
        )

    response = apis.make().get(f"{base(school.slug)}/{seeded.campaign}")

    assert response.status_code == 200, response.text
    items = response.json()["items"]
    assert [(i["name"], i["price_cents"], i["max_per_order"]) for i in items] == [
        ("Cachorro-quente", 900, 5)
    ]  # the switched off product is not offered
    assert set(items[0]) == {
        "id", "name", "description", "price_cents", "max_per_order", "has_image", "image_version"
    }  # fmt: skip
    assert str(school.fresh.school) not in response.text


@pytest.mark.parametrize(
    "kwargs",
    [
        {"status": "DRAFT"},
        {"status": "ENDED"},
        {"starts_on": date.today() + timedelta(days=2)},  # not yet
        {"ends_on": date.today() - timedelta(days=2)},  # already over
    ],
    ids=["draft", "ended", "not-yet", "over"],
)
def test_a_campaign_that_is_not_on_sale_is_not_listed_and_is_the_same_404(
    apis: ApiFactory, school: PublicSchool, admin_engine: Engine, kwargs: dict[str, Any]
) -> None:
    seeded = seed_campaign(admin_engine, school.fresh, **kwargs)
    api = apis.make()

    assert api.get(base(school.slug)).json() == {"campaigns": []}
    closed = api.get(f"{base(school.slug)}/{seeded.campaign}")
    unknown = api.get(f"{base(school.slug)}/{uuid.uuid4()}")
    for response in (closed, unknown):
        assert response.status_code == 404 and response.json()["code"] == "not_found"
    assert {k: v for k, v in closed.json().items() if k != "request_id"} == {
        k: v for k, v in unknown.json().items() if k != "request_id"
    }
    ordered = order(api, school.slug, seeded.campaign, [(seeded.items[0], 1)])
    assert ordered.status_code == 404 and ordered.json()["code"] == "not_found"


def test_a_campaign_whose_products_are_all_off_is_not_offered(
    apis: ApiFactory, school: PublicSchool, admin_engine: Engine
) -> None:
    seeded = seed_campaign(admin_engine, school.fresh)
    with admin_engine.begin() as conn:
        conn.execute(
            text("UPDATE campaign_items SET is_active = false WHERE campaign_id = :c"),
            {"c": seeded.campaign},
        )

    assert apis.make().get(base(school.slug)).json() == {"campaigns": []}


def test_a_campaign_of_another_school_is_a_404(
    apis: ApiFactory, school: PublicSchool, other_school: PublicSchool, admin_engine: Engine
) -> None:
    mine = seed_campaign(admin_engine, school.fresh)
    api = apis.make()

    assert api.get(f"{base(other_school.slug)}/{mine.campaign}").status_code == 404
    assert api.get(base(other_school.slug)).json() == {"campaigns": []}
    by_other = order(api, other_school.slug, mine.campaign, [(mine.items[0], 1)])
    assert by_other.status_code == 404
    assert contributions(admin_engine, other_school) == 0


@pytest.mark.parametrize("slug", ["no-such-school", "UPPER", "a" * 100, "bad_slug!"])
def test_an_unknown_school_is_the_same_404(apis: ApiFactory, slug: str) -> None:
    assert apis.make().get(base(slug)).status_code == 404


# --- the order ------------------------------------------------------------------------------------


def test_an_order_is_the_sum_of_the_prices_the_server_read_and_is_kept_as_a_copy(
    apis: ApiFactory, school: PublicSchool, admin_engine: Engine
) -> None:
    seeded = seed_campaign(admin_engine, school.fresh)
    key = uuid.uuid4()

    response = order(
        apis.make(), school.slug, seeded.campaign, [(seeded.items[0], 3), (seeded.items[1], 2)],
        key=key, guardian_name=" Maria Exemplo ",
    )  # fmt: skip

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["status"] == "PENDING_PAYMENT" and body["amount_cents"] == 3 * 800 + 2 * 650
    assert body["charge"]["amount_cents"] == 3700 and body["charge"]["status"] == "PENDING"
    assert len(body["token"]) == 43 and response.headers["cache-control"] == "private, no-store"

    stored = row(
        admin_engine,
        "SELECT f.amount_cents, f.status, cat.key, cat.report_group, c.campaign_id, c.method, "
        "c.guardian_name, c.idempotency_key FROM financial_transactions f "
        "JOIN contributions c ON c.transaction_id = f.id JOIN categories cat ON cat.id = f.category_id "
        "WHERE c.school_id = :s",
        s=school.fresh.school,
    )
    assert tuple(stored) == (
        3700, "PENDING_PAYMENT", "campaign_sales", "OTHER_INCOME", seeded.campaign, "PIX",
        "Maria Exemplo", key,
    )  # fmt: skip
    with admin_engine.connect() as conn:
        copy = conn.execute(
            text(
                "SELECT item_name, unit_price_cents, quantity FROM contribution_items "
                "WHERE school_id = :s ORDER BY unit_price_cents DESC"
            ),
            {"s": school.fresh.school},
        ).all()
    assert [tuple(line) for line in copy] == [("Cachorro-quente", 800, 3), ("Pamonha", 650, 2)]


@pytest.mark.parametrize(
    "extra",
    [
        {"amount_cents": 1},  # a total from the page
        {"total_cents": 1},
        {"category_id": "00000000-0000-4000-8000-000000000001"},
    ],
)
def test_the_page_cannot_name_a_total(
    apis: ApiFactory, school: PublicSchool, admin_engine: Engine, extra: dict[str, Any]
) -> None:
    seeded = seed_campaign(admin_engine, school.fresh)

    response = order(apis.make(), school.slug, seeded.campaign, [(seeded.items[0], 1)], **extra)

    assert response.status_code == 422, response.text
    assert contributions(admin_engine, school) == 0


def test_the_page_cannot_name_a_price_for_a_line(
    apis: ApiFactory, school: PublicSchool, admin_engine: Engine
) -> None:
    seeded = seed_campaign(admin_engine, school.fresh)
    body = {"lines": [{"item_id": str(seeded.items[0]), "quantity": 1, "price_cents": 1}]}

    response = apis.make().post(
        f"{base(school.slug)}/{seeded.campaign}/orders",
        body, csrf=False, headers={"Idempotency-Key": str(uuid.uuid4())},
    )  # fmt: skip

    assert response.status_code == 422, response.text
    assert contributions(admin_engine, school) == 0


def test_the_price_of_today_is_the_price_charged(
    apis: ApiFactory, school: PublicSchool, admin_engine: Engine
) -> None:
    seeded = seed_campaign(admin_engine, school.fresh)
    api = apis.make()
    with admin_engine.begin() as conn:
        conn.execute(
            text("UPDATE campaign_items SET price_cents = 1000 WHERE id = :i"),
            {"i": seeded.items[0]},
        )

    response = order(api, school.slug, seeded.campaign, [(seeded.items[0], 2)])

    assert response.status_code == 201 and response.json()["amount_cents"] == 2000


def test_a_price_changed_between_reading_and_writing_is_refused_by_the_database(
    apis: ApiFactory, school: PublicSchool, admin_engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The server read R$ 8,00; before it wrote the copy somebody raised the price. The database
    refuses a copy that is not the CURRENT price, so nothing is created and the family is told."""
    from app.public import campaign_service

    seeded = seed_campaign(admin_engine, school.fresh)
    real = campaign_service._order_lines

    def raised_right_after_reading(*args: Any, **kwargs: Any) -> Any:
        lines = real(*args, **kwargs)
        with admin_engine.begin() as conn:
            conn.execute(
                text("UPDATE campaign_items SET price_cents = 900 WHERE id = :i"),
                {"i": seeded.items[0]},
            )
        return lines

    monkeypatch.setattr(campaign_service, "_order_lines", raised_right_after_reading)

    response = order(apis.make(), school.slug, seeded.campaign, [(seeded.items[0], 1)])

    assert response.status_code == 409, response.text
    assert response.json()["code"] == "campaign_changed"
    assert contributions(admin_engine, school) == 0
    monkeypatch.setattr(campaign_service, "_order_lines", real)
    again = order(apis.make(), school.slug, seeded.campaign, [(seeded.items[0], 1)])
    assert (
        again.status_code == 201 and again.json()["amount_cents"] == 900
    )  # and the next one pays the new price


def _bad_orders() -> list[tuple[str, Any, str, str]]:
    """(id, lines builder, field, code): the lines are made from the items of the seeded campaign."""
    return [
        ("unknown-product", lambda s: [(uuid.uuid4(), 1)], "lines[0].item_id", "unavailable"),
        ("over-the-limit", lambda s: [(s.items[0], 6)], "lines[0].quantity", "over_limit"),
        (
            "duplicated",
            lambda s: [(s.items[0], 1), (s.items[0], 2)],
            "lines[1].item_id",
            "duplicate",
        ),
    ]


@pytest.mark.parametrize(
    ("build", "field", "code"),
    [pytest.param(b, f, c, id=i) for i, b, f, c in _bad_orders()],
)
def test_a_bad_cart_is_a_422_with_the_field_and_creates_nothing(
    apis: ApiFactory, school: PublicSchool, admin_engine: Engine, build: Any, field: str, code: str
) -> None:
    seeded = seed_campaign(admin_engine, school.fresh)

    response = order(apis.make(), school.slug, seeded.campaign, build(seeded))

    assert response.status_code == 422, response.text
    assert {"field": field, "code": code} in response.json()["errors"]
    assert contributions(admin_engine, school) == 0


@pytest.mark.parametrize(
    "lines",
    [
        [],
        [{"item_id": "not-a-uuid", "quantity": 1}],
        [{"quantity": 1}],
        [{"item_id": None, "quantity": 1}],
    ],
)
def test_a_malformed_cart_is_a_422(
    apis: ApiFactory, school: PublicSchool, admin_engine: Engine, lines: list[Any]
) -> None:
    seeded = seed_campaign(admin_engine, school.fresh)

    response = apis.make().post(
        f"{base(school.slug)}/{seeded.campaign}/orders",
        {"lines": lines}, csrf=False, headers={"Idempotency-Key": str(uuid.uuid4())},
    )  # fmt: skip

    assert response.status_code == 422, response.text
    assert contributions(admin_engine, school) == 0


@pytest.mark.parametrize("quantity", [0, -1, 100, 1.5, "two"])
def test_the_quantity_is_a_whole_number_from_one_to_ninety_nine(
    apis: ApiFactory, school: PublicSchool, admin_engine: Engine, quantity: Any
) -> None:
    seeded = seed_campaign(admin_engine, school.fresh, items=(("Caneta", 500, None),))

    response = order(apis.make(), school.slug, seeded.campaign, [(seeded.items[0], quantity)])

    assert response.status_code == 422, response.text
    assert contributions(admin_engine, school) == 0


def test_twenty_one_lines_are_too_many(
    apis: ApiFactory, school: PublicSchool, admin_engine: Engine
) -> None:
    seeded = seed_campaign(admin_engine, school.fresh)

    response = order(apis.make(), school.slug, seeded.campaign, [(uuid.uuid4(), 1)] * 21)

    assert response.status_code == 422 and contributions(admin_engine, school) == 0


def test_a_product_of_another_campaign_or_switched_off_is_unavailable(
    apis: ApiFactory, school: PublicSchool, admin_engine: Engine
) -> None:
    seeded = seed_campaign(admin_engine, school.fresh)
    other = seed_campaign(admin_engine, school.fresh, title="Outra", items=(("Rifa", 500, None),))
    with admin_engine.begin() as conn:
        conn.execute(
            text("UPDATE campaign_items SET is_active = false WHERE id = :i"),
            {"i": seeded.items[1]},
        )
    api = apis.make()

    for item in (other.items[0], seeded.items[1]):
        response = order(api, school.slug, seeded.campaign, [(item, 1)])
        assert response.status_code == 422, response.text
        assert {"field": "lines[0].item_id", "code": "unavailable"} in response.json()["errors"]
    assert contributions(admin_engine, school) == 0


def test_an_order_over_fifty_thousand_reais_is_refused(
    apis: ApiFactory, school: PublicSchool, admin_engine: Engine
) -> None:
    seeded = seed_campaign(admin_engine, school.fresh, items=(("Pacote", 1_000_000, None),))
    api = apis.make()

    refused = order(api, school.slug, seeded.campaign, [(seeded.items[0], 6)])
    allowed = order(api, school.slug, seeded.campaign, [(seeded.items[0], 5)])

    assert refused.status_code == 422
    assert {"field": "lines", "code": "total_out_of_range"} in refused.json()["errors"]
    assert allowed.status_code == 201 and allowed.json()["amount_cents"] == 5_000_000


def test_the_identification_follows_the_settings_of_the_school(
    apis: ApiFactory, school: PublicSchool, admin_engine: Engine
) -> None:
    seeded = seed_campaign(admin_engine, school.fresh)
    with admin_engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE school_settings SET required_fields = '{guardian_name}', "
                "optional_fields = '{}' WHERE school_id = :s"
            ),
            {"s": school.fresh.school},
        )
    api = apis.make()
    lines = [(seeded.items[0], 1)]

    missing = order(api, school.slug, seeded.campaign, lines)
    bad = order(
        api, school.slug, seeded.campaign, lines, guardian_name="Maria", contributor_email="x"
    )
    good = order(
        api,
        school.slug,
        seeded.campaign,
        lines,
        guardian_name="Maria",
        contributor_email="m@e.test",
    )

    assert missing.status_code == 422
    assert {"field": "guardian_name", "code": "required"} in missing.json()["errors"]
    assert bad.status_code == 201  # the e-mail is not asked by this school: ignored, not validated
    assert good.status_code == 201
    stored = row(
        admin_engine,
        "SELECT contributor_email FROM contributions WHERE school_id = :s AND guardian_name = 'Maria' LIMIT 1",
        s=school.fresh.school,
    )
    assert stored[0] is None  # never stored


def test_an_order_needs_an_idempotency_key(
    apis: ApiFactory, school: PublicSchool, admin_engine: Engine
) -> None:
    seeded = seed_campaign(admin_engine, school.fresh)
    api = apis.make()

    for key in ("", "not-a-uuid"):
        response = order(api, school.slug, seeded.campaign, [(seeded.items[0], 1)], key=key)
        assert response.status_code == 422, response.text
    assert contributions(admin_engine, school) == 0


def test_the_same_key_with_the_same_cart_is_the_same_order(
    apis: ApiFactory, school: PublicSchool, admin_engine: Engine
) -> None:
    seeded = seed_campaign(admin_engine, school.fresh)
    api = apis.make()
    key = uuid.uuid4()
    lines = [(seeded.items[0], 2), (seeded.items[1], 1)]

    first = order(api, school.slug, seeded.campaign, lines, key=key)
    again = order(api, school.slug, seeded.campaign, list(reversed(lines)), key=key)

    assert first.status_code == again.status_code == 201
    assert again.json()["token"] == first.json()["token"]
    assert again.json()["charge"]["emv_payload"] == first.json()["charge"]["emv_payload"]
    assert contributions(admin_engine, school) == 1
    assert (
        count(
            admin_engine,
            "SELECT count(*) FROM contribution_items WHERE school_id = :s",
            s=school.fresh.school,
        )
        == 2
    )


@pytest.mark.parametrize("other", ["quantity", "product", "extra-line"])
def test_the_same_key_with_another_cart_is_a_conflict(
    apis: ApiFactory, school: PublicSchool, admin_engine: Engine, other: str
) -> None:
    seeded = seed_campaign(admin_engine, school.fresh)
    api = apis.make()
    key = uuid.uuid4()
    assert (
        order(api, school.slug, seeded.campaign, [(seeded.items[0], 2)], key=key).status_code == 201
    )
    different = {
        "quantity": [(seeded.items[0], 3)],
        "product": [(seeded.items[1], 2)],
        "extra-line": [(seeded.items[0], 2), (seeded.items[1], 1)],
    }[other]

    response = order(api, school.slug, seeded.campaign, different, key=key)

    assert response.status_code == 409 and response.json()["code"] == "idempotency_key_reused"
    assert contributions(admin_engine, school) == 1


def test_a_key_used_for_a_free_contribution_cannot_be_reused_for_an_order(
    apis: ApiFactory, school: PublicSchool, admin_engine: Engine
) -> None:
    from tests.public.support import contribute

    seeded = seed_campaign(admin_engine, school.fresh)
    api = apis.make()
    key = uuid.uuid4()
    assert contribute(api, school.slug, 1600, key=key).status_code == 201

    response = order(api, school.slug, seeded.campaign, [(seeded.items[0], 2)], key=key)

    assert response.status_code == 409 and response.json()["code"] == "idempotency_key_reused"


def test_a_school_without_the_category_cannot_receive_an_order(
    apis: ApiFactory, school: PublicSchool, admin_engine: Engine
) -> None:
    seeded = seed_campaign(admin_engine, school.fresh)
    with admin_engine.begin() as conn:
        conn.execute(text("SET LOCAL session_replication_role = replica"))
        conn.execute(
            text("DELETE FROM categories WHERE school_id = :s AND key = 'campaign_sales'"),
            {"s": school.fresh.school},
        )

    response = order(apis.make(), school.slug, seeded.campaign, [(seeded.items[0], 1)])

    assert response.status_code == 409 and response.json()["code"] == "payment_unavailable"
    assert contributions(admin_engine, school) == 0


# --- paying: the rest of the flow is the one of every contribution ---------------------------------


def test_paid_orders_keep_the_price_of_their_day_and_the_receipt_lists_what_was_bought(
    apis: ApiFactory, school: PublicSchool, admin_engine: Engine
) -> None:
    seeded = seed_campaign(admin_engine, school.fresh)
    api = apis.make()
    created = order(api, school.slug, seeded.campaign, [(seeded.items[0], 2), (seeded.items[1], 1)])
    token = created.json()["token"]
    assert _pay(api, txid_of(created)).status_code == 200

    with admin_engine.begin() as conn:  # the management raises the price and renames the product
        conn.execute(
            text("UPDATE campaign_items SET price_cents = 2000, name = 'Hot-dog' WHERE id = :i"),
            {"i": seeded.items[0]},
        )

    state = api.get(charge_url(school.slug, token))
    receipt = api.get(charge_url(school.slug, token, "receipt"))
    assert state.json()["status"] == "PAID" and state.json()["amount_cents"] == 2250
    assert receipt.status_code == 200, receipt.text
    body = receipt.json()
    assert body["amount_cents"] == 2250 and body["campaign_title"] == "Festa Junina"
    assert body["items"] == [
        {"name": "Cachorro-quente", "unit_price_cents": 800, "quantity": 2},
        {"name": "Pamonha", "unit_price_cents": 650, "quantity": 1},
    ]  # what was bought, as it was bought
    new = order(api, school.slug, seeded.campaign, [(seeded.items[0], 1)])
    assert new.json()["amount_cents"] == 2000  # and the next order pays the new price
    paid = count(
        admin_engine,
        "SELECT count(*) FROM financial_transactions f JOIN categories c ON c.id = f.category_id "
        "WHERE f.school_id = :s AND f.status = 'PAID' AND c.key = 'campaign_sales'",
        s=school.fresh.school,
    )
    assert paid == 1  # it is revenue of the campaign category


def test_the_receipt_of_a_plain_contribution_has_no_items(
    apis: ApiFactory, school: PublicSchool
) -> None:
    from tests.public.support import contribute

    api = apis.make()
    created = contribute(api, school.slug, 3000)
    assert _pay(api, txid_of(created)).status_code == 200

    body = api.get(charge_url(school.slug, created.json()["token"], "receipt")).json()

    assert body["campaign_title"] is None and body["items"] == []


# --- the pictures ---------------------------------------------------------------------------------


def _with_cover(
    engine: Engine, store: LocalDiskStore, fresh: Any, campaign: uuid.UUID, data: bytes
) -> None:
    key = f"{fresh.org}/{fresh.school}/campaigns/{campaign}/{uuid.uuid4().hex}"
    store.put(key, [data])
    with engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE campaigns SET cover_storage_key = :k, cover_content_type = 'image/png', "
                "cover_size_bytes = :n, cover_sha256 = :h, cover_version = 1 WHERE id = :c"
            ),
            {"k": key, "n": len(data), "h": hashlib.sha256(data).hexdigest(), "c": campaign},
        )


def test_the_picture_of_a_campaign_on_sale_is_public_cacheable_and_never_executed(
    apis: ApiFactory, school: PublicSchool, admin_engine: Engine, tmp_path: Path
) -> None:
    seeded = seed_campaign(admin_engine, school.fresh)
    data = make_png()
    _with_cover(
        admin_engine, LocalDiskStore(tmp_path / "files"), school.fresh, seeded.campaign, data
    )
    api = apis.make(configure=storage_overrides(tmp_path / "files", 1024 * 1024))
    url = f"{base(school.slug)}/{seeded.campaign}/cover"

    response = api.get(url)

    assert response.status_code == 200 and response.content == data
    assert response.headers["content-type"] == "image/png"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["content-security-policy"] == "default-src 'none'; sandbox"
    assert response.headers["cache-control"] == "public, max-age=300, must-revalidate"
    assert response.headers["cross-origin-resource-policy"] == "same-origin"
    etag = response.headers["etag"]
    assert etag == f'"{hashlib.sha256(data).hexdigest()[:32]}"'
    again = api.get(url, headers={"If-None-Match": etag})
    assert again.status_code == 304 and again.content == b""
    assert api.get(url, headers={"If-None-Match": '"other"'}).status_code == 200
    detail = api.get(f"{base(school.slug)}/{seeded.campaign}").json()
    assert detail["has_cover"] is True and detail["cover_version"] == 1


@pytest.mark.parametrize("status", ["DRAFT", "ENDED"])
def test_the_picture_of_a_campaign_that_is_not_on_sale_is_a_404(
    apis: ApiFactory, school: PublicSchool, admin_engine: Engine, tmp_path: Path, status: str
) -> None:
    seeded = seed_campaign(admin_engine, school.fresh, status="DRAFT")
    _with_cover(
        admin_engine, LocalDiskStore(tmp_path / "files"), school.fresh, seeded.campaign, make_png()
    )
    if status == "ENDED":  # a picture is set while it can still change, then the campaign ends
        with admin_engine.begin() as conn:
            conn.execute(
                text("UPDATE campaigns SET status = 'ENDED', ended_at = now() WHERE id = :c"),
                {"c": seeded.campaign},
            )
    api = apis.make(configure=storage_overrides(tmp_path / "files", 1024 * 1024))

    assert api.get(f"{base(school.slug)}/{seeded.campaign}/cover").status_code == 404


def test_a_missing_picture_and_a_picture_of_another_school_are_the_same_404(
    apis: ApiFactory,
    school: PublicSchool,
    other_school: PublicSchool,
    admin_engine: Engine,
    tmp_path: Path,
) -> None:
    seeded = seed_campaign(admin_engine, school.fresh)
    _with_cover(
        admin_engine, LocalDiskStore(tmp_path / "files"), school.fresh, seeded.campaign, make_png()
    )
    api = apis.make(configure=storage_overrides(tmp_path / "files", 1024 * 1024))

    answers = [
        api.get(f"{base(school.slug)}/{uuid.uuid4()}/cover"),
        api.get(f"{base(other_school.slug)}/{seeded.campaign}/cover"),
        api.get(f"{base(school.slug)}/{seeded.campaign}/items/{seeded.items[0]}/image"),  # none set
        api.get(f"{base(school.slug)}/{seeded.campaign}/items/{uuid.uuid4()}/image"),
    ]
    for response in answers:
        assert response.status_code == 404 and response.json()["code"] == "not_found"


def test_a_file_that_vanished_from_the_store_is_a_404_not_a_500(
    apis: ApiFactory, school: PublicSchool, admin_engine: Engine, tmp_path: Path
) -> None:
    seeded = seed_campaign(admin_engine, school.fresh)
    _with_cover(
        admin_engine, LocalDiskStore(tmp_path / "files"), school.fresh, seeded.campaign, make_png()
    )
    for file in (tmp_path / "files").rglob("*"):
        if file.is_file():
            file.unlink()
    api = apis.make(configure=storage_overrides(tmp_path / "files", 1024 * 1024))

    assert api.get(f"{base(school.slug)}/{seeded.campaign}/cover").status_code == 404
