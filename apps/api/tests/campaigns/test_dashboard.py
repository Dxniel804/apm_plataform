# ruff: noqa: E501  (SQL)
"""The dashboard of a campaign, its orders and their delivery (migration 0014): what the management
follows after the families bought. The figures come from the ledger and from the copy each order kept."""

import uuid
from typing import Any

from sqlalchemy import Engine, text

from tests.authsupport import ApiFactory
from tests.campaigns.support import committed_manager, seed_campaign
from tests.campaigns.test_public import _pay, order
from tests.public.conftest import PublicSchool
from tests.public.support import txid_of


def _paid_order(
    apis: ApiFactory,
    school: PublicSchool,
    campaign: uuid.UUID,
    lines: list[tuple[uuid.UUID, int]],
    **who: Any,
) -> str:
    """An order a family made and paid: returns the id of the contribution."""
    api = apis.make()
    created = order(api, school.slug, campaign, lines, **who)
    assert created.status_code == 201, created.text
    assert _pay(api, txid_of(created)).status_code == 200
    return str(created.json().get("id") or _order_id(created))


def _order_id(created: Any) -> str:  # pragma: no cover - the id is read from the database below
    raise AssertionError("the order has no id in the answer")


def _ids(engine: Engine, school: PublicSchool) -> list[str]:
    """The ids of the contributions of the school, the newest first."""
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT transaction_id FROM contributions WHERE school_id = :s ORDER BY created_at DESC, transaction_id DESC"
            ),
            {"s": school.fresh.school},
        ).all()
    return [str(row[0]) for row in rows]


def _pay_two_orders(
    apis: ApiFactory, school: PublicSchool, engine: Engine, seeded: Any
) -> tuple[str, str]:
    """Two PAID orders; returns their ids (oldest, newest)."""
    a, b = seeded.items
    for lines, who in (
        ([(a, 2), (b, 1)], {"student_name": "Ana", "class_name": "3A", "guardian_name": "Maria"}),
        ([(a, 1)], {"student_name": "Beto", "class_name": "5B", "guardian_name": "Joao"}),
    ):
        api = apis.make()
        created = order(api, school.slug, seeded.campaign, lines, **who)
        assert created.status_code == 201, created.text
        assert _pay(api, txid_of(created)).status_code == 200
    newest, oldest = _ids(engine, school)[:2]
    return oldest, newest


def test_the_cost_is_copied_when_the_order_is_made_and_never_changes(
    apis: ApiFactory, school: PublicSchool, admin_engine: Engine
) -> None:
    seeded = seed_campaign(admin_engine, school.fresh, costs=(300, None))
    api = apis.make()
    assert (
        order(
            api, school.slug, seeded.campaign, [(seeded.items[0], 2), (seeded.items[1], 1)]
        ).status_code
        == 201
    )

    with admin_engine.begin() as conn:  # the cost changes afterwards
        conn.execute(
            text("UPDATE campaign_items SET unit_cost_cents = 999 WHERE id = :i"),
            {"i": seeded.items[0]},
        )
        copies: dict[str, int | None] = dict(
            conn.execute(
                text(
                    "SELECT item_name, unit_cost_cents FROM contribution_items WHERE school_id = :s"
                ),
                {"s": school.fresh.school},
            ).all()
        )

    assert copies == {
        "Cachorro-quente": 300,
        "Pamonha": None,
    }  # the cost of the day, and unknown stays unknown


def test_the_dashboard_adds_up_what_the_orders_brought_and_cost(
    apis: ApiFactory, school: PublicSchool, admin_engine: Engine
) -> None:
    seeded = seed_campaign(admin_engine, school.fresh, costs=(300, 200))
    gestao = committed_manager(apis, admin_engine, school)
    _pay_two_orders(apis, school, admin_engine, seeded)
    pending = apis.make()
    assert order(pending, school.slug, seeded.campaign, [(seeded.items[1], 1)]).status_code == 201

    body = gestao.get(f"/campaigns/{seeded.campaign}/dashboard").json()

    # order 1: 2 x 8,00 + 1 x 6,50 = 22,50; order 2: 1 x 8,00. The pending order is not counted as money.
    assert (
        body["paid_orders_count"] == 2
        and body["pending_orders_count"] == 1
        and body["cancelled_orders_count"] == 0
    )
    assert body["collected_cents"] == 3050 and body["units_sold"] == 4
    # cost: 3 x 3,00 + 1 x 2,00 = 11,00; profit 30,50 - 11,00
    assert (
        body["cost_cents"] == 1100
        and body["cost_complete"] is True
        and body["profit_cents"] == 1950
    )
    by_name = {item["name"]: item for item in body["items"]}
    assert (
        by_name["Cachorro-quente"]["units_sold"] == 3
        and by_name["Cachorro-quente"]["revenue_cents"] == 2400
    )
    assert by_name["Pamonha"]["units_sold"] == 1 and by_name["Pamonha"]["cost_cents"] == 200
    assert body["delivered_orders_count"] == 0 and body["to_deliver_orders_count"] == 2
    # the figure is the one the ledger holds (the list of campaigns reads it there)
    summary = gestao.get(f"/campaigns/{seeded.campaign}").json()
    assert summary["paid_cents"] == body["collected_cents"] and summary["paid_orders_count"] == 2


def test_there_is_no_profit_when_a_product_sold_has_no_cost(
    apis: ApiFactory, school: PublicSchool, admin_engine: Engine
) -> None:
    seeded = seed_campaign(
        admin_engine, school.fresh, costs=(300, None)
    )  # the second product has no cost
    gestao = committed_manager(apis, admin_engine, school)
    _pay_two_orders(apis, school, admin_engine, seeded)

    body = gestao.get(f"/campaigns/{seeded.campaign}/dashboard").json()

    assert body["cost_complete"] is False and body["profit_cents"] is None
    assert body["cost_cents"] == 900  # what is known: 3 x 3,00
    by_name = {item["name"]: item for item in body["items"]}
    assert by_name["Pamonha"]["cost_known"] is False


def test_a_campaign_with_no_sale_has_a_profit_of_zero_and_lists_its_products(
    apis: ApiFactory, school: PublicSchool, admin_engine: Engine
) -> None:
    seeded = seed_campaign(admin_engine, school.fresh)
    gestao = committed_manager(apis, admin_engine, school)

    body = gestao.get(f"/campaigns/{seeded.campaign}/dashboard").json()

    assert body["collected_cents"] == 0 and body["units_sold"] == 0
    assert body["cost_complete"] is True and body["profit_cents"] == 0
    assert [item["name"] for item in body["items"]] == ["Cachorro-quente", "Pamonha"]


def test_the_orders_show_who_bought_what_with_the_payment_and_the_delivery(
    apis: ApiFactory, school: PublicSchool, admin_engine: Engine
) -> None:
    seeded = seed_campaign(admin_engine, school.fresh, ask_student_class=True)
    gestao = committed_manager(apis, admin_engine, school)
    oldest, newest = _pay_two_orders(apis, school, admin_engine, seeded)
    api = apis.make()
    assert (
        order(
            api,
            school.slug,
            seeded.campaign,
            [(seeded.items[1], 1)],
            student_name="Caio",
            class_name="1C",
        ).status_code
        == 201
    )

    listing = gestao.get(f"/campaigns/{seeded.campaign}/orders").json()

    assert listing["total"] == 3 and len(listing["items"]) == 3
    first = next(item for item in listing["items"] if item["order_id"] == oldest)
    assert first["student_name"] == "Ana" and first["class_name"] == "3A"
    assert (
        first["amount_cents"] == 2250
        and first["payment_status"] == "PAID"
        and first["delivery_status"] == "PENDING"
    )
    assert first["lines"] == [
        {"item_name": "Cachorro-quente", "quantity": 2, "unit_price_cents": 800},
        {"item_name": "Pamonha", "quantity": 1, "unit_price_cents": 650},
    ]
    waiting = next(item for item in listing["items"] if item["payment_status"] == "PENDING")
    assert waiting["delivery_status"] is None  # an unpaid order has no delivery to follow
    assert waiting["student_name"] == "Caio"


def test_the_orders_filter_by_payment_delivery_and_search(
    apis: ApiFactory, school: PublicSchool, admin_engine: Engine
) -> None:
    seeded = seed_campaign(admin_engine, school.fresh, ask_student_class=True)
    gestao = committed_manager(apis, admin_engine, school)
    oldest, newest = _pay_two_orders(apis, school, admin_engine, seeded)
    api = apis.make()
    created = order(
        api,
        school.slug,
        seeded.campaign,
        [(seeded.items[1], 1)],
        student_name="Caio",
        class_name="1C",
    )
    assert created.status_code == 201
    gestao.post(
        f"/campaigns/{seeded.campaign}/orders/delivery", {"order_ids": [oldest], "delivered": True}
    )
    base = f"/campaigns/{seeded.campaign}/orders"

    def ids(query: str) -> set[str]:
        return {item["order_id"] for item in gestao.get(f"{base}?{query}").json()["items"]}

    assert ids("payment=PAID") == {oldest, newest}
    assert len(ids("payment=PENDING")) == 1 and ids("payment=CANCELLED") == set()
    assert ids("delivery=DELIVERED") == {oldest}
    assert ids("delivery=PENDING") == {newest}  # to deliver: only PAID orders
    assert ids("search=beto") == {newest}  # the student, any case
    assert ids("search=5B") == {newest}  # the class
    assert ids("search=Maria") == {oldest}  # the guardian
    assert ids("search=%25") == set()  # a percent sign is a percent sign, not "everything"
    assert gestao.get(f"{base}?limit=1&offset=1").json()["total"] == 3
    assert len(gestao.get(f"{base}?limit=1&offset=1").json()["items"]) == 1
    code = gestao.get(f"{base}?payment=PAID").json()["items"][0]["reference_code"]
    assert ids(f"search={code}") != set()  # the number of the order (APM-000042 -> 42)


def test_a_cancelled_or_expired_order_is_shown_as_cancelled(
    apis: ApiFactory, school: PublicSchool, admin_engine: Engine
) -> None:
    seeded = seed_campaign(admin_engine, school.fresh)
    gestao = committed_manager(apis, admin_engine, school)
    api = apis.make()
    assert order(api, school.slug, seeded.campaign, [(seeded.items[0], 1)]).status_code == 201
    with admin_engine.begin() as conn:  # the expiry job would do this; here it is written directly
        conn.execute(text("SET LOCAL session_replication_role = replica"))
        conn.execute(
            text("UPDATE financial_transactions SET status = 'EXPIRED' WHERE school_id = :s"),
            {"s": school.fresh.school},
        )

    body = gestao.get(f"/campaigns/{seeded.campaign}/dashboard").json()
    listing = gestao.get(f"/campaigns/{seeded.campaign}/orders?payment=CANCELLED").json()

    assert (
        body["cancelled_orders_count"] == 1
        and body["pending_orders_count"] == 0
        and body["collected_cents"] == 0
    )
    assert listing["total"] == 1 and listing["items"][0]["delivery_status"] is None


# --- the delivery -----------------------------------------------------------------------------------


def test_delivery_is_marked_in_batch_undone_and_idempotent(
    apis: ApiFactory, school: PublicSchool, admin_engine: Engine
) -> None:
    seeded = seed_campaign(admin_engine, school.fresh)
    gestao = committed_manager(apis, admin_engine, school)
    oldest, newest = _pay_two_orders(apis, school, admin_engine, seeded)
    path = f"/campaigns/{seeded.campaign}/orders/delivery"

    first = gestao.post(path, {"order_ids": [oldest, newest], "delivered": True})
    again = gestao.post(path, {"order_ids": [oldest, newest], "delivered": True})
    undone = gestao.post(path, {"order_ids": [newest], "delivered": False})

    assert first.status_code == 200 and first.json() == {"changed": 2, "unchanged": 0, "skipped": 0}
    assert again.json() == {"changed": 0, "unchanged": 2, "skipped": 0}  # nothing changes twice
    assert undone.json() == {"changed": 1, "unchanged": 0, "skipped": 0}
    body = gestao.get(f"/campaigns/{seeded.campaign}/dashboard").json()
    assert body["delivered_orders_count"] == 1 and body["to_deliver_orders_count"] == 1
    states = {
        item["order_id"]: item["delivery_status"]
        for item in gestao.get(f"/campaigns/{seeded.campaign}/orders").json()["items"]
    }
    assert states == {oldest: "DELIVERED", newest: "PENDING"}


def test_only_a_paid_order_of_this_campaign_can_be_delivered(
    apis: ApiFactory, school: PublicSchool, admin_engine: Engine
) -> None:
    seeded = seed_campaign(admin_engine, school.fresh)
    other = seed_campaign(admin_engine, school.fresh, title="Outra campanha")
    gestao = committed_manager(apis, admin_engine, school)
    oldest, _ = _pay_two_orders(apis, school, admin_engine, seeded)
    api = apis.make()
    assert order(api, school.slug, seeded.campaign, [(seeded.items[0], 1)]).status_code == 201
    unpaid = _ids(admin_engine, school)[0]
    path = f"/campaigns/{other.campaign}/orders/delivery"

    # an order of ANOTHER campaign, an unpaid one and an id that does not exist: all skipped
    result = gestao.post(
        f"/campaigns/{seeded.campaign}/orders/delivery",
        {"order_ids": [unpaid, str(uuid.uuid4())], "delivered": True},
    )
    foreign = gestao.post(path, {"order_ids": [oldest], "delivered": True})

    assert result.json() == {"changed": 0, "unchanged": 0, "skipped": 2}
    assert foreign.json() == {"changed": 0, "unchanged": 0, "skipped": 1}
    with admin_engine.connect() as conn:
        assert (
            conn.execute(
                text("SELECT count(*) FROM campaign_deliveries WHERE school_id = :s"),
                {"s": school.fresh.school},
            ).scalar_one()
            == 0
        )


def test_the_database_itself_refuses_to_deliver_an_unpaid_order(
    apis: ApiFactory, school: PublicSchool, admin_engine: Engine
) -> None:
    seeded = seed_campaign(admin_engine, school.fresh)
    api = apis.make()
    assert order(api, school.slug, seeded.campaign, [(seeded.items[0], 1)]).status_code == 201
    unpaid = _ids(admin_engine, school)[0]
    fresh = school.fresh

    import pytest
    from sqlalchemy.exc import DBAPIError

    with (
        pytest.raises(DBAPIError, match="only a paid order of a campaign can be delivered"),
        admin_engine.begin() as conn,
    ):
        conn.execute(
            text(
                "INSERT INTO campaign_deliveries (organization_id, school_id, transaction_id, status, changed_by_user_id) VALUES (:o, :s, :t, 'DELIVERED', :u)"
            ),
            {"o": fresh.org, "s": fresh.school, "t": unpaid, "u": fresh.treasurer},
        )


def test_a_batch_has_at_most_one_hundred_orders_without_repeats(
    apis: ApiFactory, school: PublicSchool, admin_engine: Engine
) -> None:
    seeded = seed_campaign(admin_engine, school.fresh)
    gestao = committed_manager(apis, admin_engine, school)
    path = f"/campaigns/{seeded.campaign}/orders/delivery"
    one = str(uuid.uuid4())

    assert gestao.post(path, {"order_ids": [], "delivered": True}).status_code == 422
    assert (
        gestao.post(
            path, {"order_ids": [str(uuid.uuid4()) for _ in range(101)], "delivered": True}
        ).status_code
        == 422
    )
    repeated = gestao.post(path, {"order_ids": [one, one], "delivered": True})
    assert repeated.status_code == 422 and repeated.json()["errors"] == [
        {"field": "order_ids", "code": "duplicate"}
    ]
    assert gestao.post(path, {"order_ids": [one]}).status_code == 422  # `delivered` is required
    assert (
        gestao.post(path, {"order_ids": [one], "delivered": True, "status": "x"}).status_code == 422
    )


def test_every_delivery_change_is_audited_without_free_text(
    apis: ApiFactory, school: PublicSchool, admin_engine: Engine
) -> None:
    seeded = seed_campaign(admin_engine, school.fresh)
    gestao = committed_manager(apis, admin_engine, school)
    oldest, _ = _pay_two_orders(apis, school, admin_engine, seeded)
    path = f"/campaigns/{seeded.campaign}/orders/delivery"
    gestao.post(path, {"order_ids": [oldest], "delivered": True})
    gestao.post(path, {"order_ids": [oldest], "delivered": False})

    with admin_engine.connect() as conn:
        actions = [
            row[0]
            for row in conn.execute(
                text(
                    "SELECT action FROM audit_logs WHERE school_id = :s AND (action LIKE 'campaign_deliveries.%' OR action LIKE 'campaign.delivery_%') ORDER BY occurred_at, id"
                ),
                {"s": school.fresh.school},
            ).all()
        ]
        who = conn.execute(
            text(
                "SELECT changed_by_user_id, status FROM campaign_deliveries WHERE transaction_id = :t"
            ),
            {"t": oldest},
        ).one()

    assert "campaign_deliveries.insert" in actions and "campaign_deliveries.update" in actions
    assert "campaign.delivery_marked" in actions and "campaign.delivery_undone" in actions
    assert (
        who[0] == school.fresh.treasurer and who[1] == "PENDING"
    )  # who touched it last, and the state


# --- the PDF ----------------------------------------------------------------------------------------


def test_the_pdf_of_the_campaign_has_the_totals_and_every_order(
    apis: ApiFactory, school: PublicSchool, admin_engine: Engine
) -> None:
    seeded = seed_campaign(admin_engine, school.fresh, costs=(300, 200))
    gestao = committed_manager(apis, admin_engine, school)
    _pay_two_orders(apis, school, admin_engine, seeded)

    response = gestao.get(f"/campaigns/{seeded.campaign}/report.pdf")

    assert response.status_code == 200 and response.headers["content-type"] == "application/pdf"
    assert response.content.startswith(b"%PDF-")
    assert response.headers["cache-control"] == "private, no-store"
    from io import BytesIO

    from pypdf import PdfReader

    text_of_pdf = " ".join(
        page.extract_text() for page in PdfReader(BytesIO(response.content)).pages
    )
    for expected in (
        "Relatório da campanha",
        "Festa Junina",
        "R$ 30,50",
        "R$ 19,50",
        "Cachorro-quente",
        "Aprovado",
    ):
        assert expected in text_of_pdf, expected
    assert "Aprovado" in text_of_pdf and "A entregar" in text_of_pdf


# --- who can see it ---------------------------------------------------------------------------------


def test_another_school_sees_nothing_of_the_campaign(
    apis: ApiFactory, school: PublicSchool, other_school: PublicSchool, admin_engine: Engine
) -> None:
    seeded = seed_campaign(admin_engine, school.fresh)
    oldest, _ = _pay_two_orders(apis, school, admin_engine, seeded)
    stranger = committed_manager(apis, admin_engine, other_school)
    gone = {"status_code": 404, "code": "not_found"}

    answers = [
        stranger.get(f"/campaigns/{seeded.campaign}/dashboard"),
        stranger.get(f"/campaigns/{seeded.campaign}/orders"),
        stranger.get(f"/campaigns/{seeded.campaign}/report.pdf"),
        stranger.post(
            f"/campaigns/{seeded.campaign}/orders/delivery",
            {"order_ids": [oldest], "delivered": True},
        ),
        stranger.get(
            f"/campaigns/{uuid.uuid4()}/dashboard"
        ),  # one that never existed answers the same
    ]

    for answer in answers:
        assert answer.status_code == gone["status_code"] and answer.json()["code"] == gone["code"]
    with admin_engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM campaign_deliveries")).scalar_one() == 0
    # and the school in the path must be the school of the session
    other_path = stranger.get(f"/campaigns/{seeded.campaign}/orders", school=school.fresh.school)
    assert other_path.status_code in (403, 404)


def test_only_who_manages_campaigns_reaches_the_dashboard(
    apis: ApiFactory, school: PublicSchool, admin_engine: Engine
) -> None:
    seeded = seed_campaign(admin_engine, school.fresh)
    from tests.authsupport import PASSWORD_HASH, TestUser
    from tests.expenses.support import Client

    with admin_engine.begin() as conn:
        conn.execute(
            text("UPDATE users SET password_hash = :h WHERE id = :i"),
            {"h": PASSWORD_HASH, "i": school.fresh.staff},
        )
        email: str = conn.execute(
            text("SELECT email FROM users WHERE id = :i"), {"i": school.fresh.staff}
        ).scalar_one()
    api = apis.make()
    assert api.login(email).status_code == 200
    staff = Client(api, TestUser(school.fresh.staff, email, ()), apis.world, school.fresh.school)

    for answer in (
        staff.get(f"/campaigns/{seeded.campaign}/dashboard"),
        staff.get(f"/campaigns/{seeded.campaign}/orders"),
        staff.get(f"/campaigns/{seeded.campaign}/report.pdf"),
        staff.post(
            f"/campaigns/{seeded.campaign}/orders/delivery",
            {"order_ids": [str(uuid.uuid4())], "delivered": True},
        ),
    ):
        assert answer.status_code == 403, answer.text


# --- student and class ------------------------------------------------------------------------------


def test_a_campaign_that_asks_for_student_and_class_requires_them_and_stores_them(
    apis: ApiFactory, school: PublicSchool, admin_engine: Engine
) -> None:
    seeded = seed_campaign(admin_engine, school.fresh, ask_student_class=True)
    api = apis.make()
    lines = [(seeded.items[0], 1)]

    missing = order(api, school.slug, seeded.campaign, lines)
    half = order(api, school.slug, seeded.campaign, lines, student_name="Ana")
    good = order(api, school.slug, seeded.campaign, lines, student_name="  Ana  ", class_name="3A")

    assert missing.status_code == 422
    assert {"field": "student_name", "code": "required"} in missing.json()["errors"]
    assert {"field": "class_name", "code": "required"} in missing.json()["errors"]
    assert half.status_code == 422 and half.json()["errors"] == [
        {"field": "class_name", "code": "required"}
    ]
    assert good.status_code == 201
    with admin_engine.connect() as conn:
        stored = conn.execute(
            text("SELECT student_name, class_name FROM contributions WHERE school_id = :s"),
            {"s": school.fresh.school},
        ).all()
    assert [tuple(row) for row in stored] == [
        ("Ana", "3A")
    ]  # trimmed; and only the order that was accepted


def test_a_campaign_that_does_not_ask_takes_the_order_without_them(
    apis: ApiFactory, school: PublicSchool, admin_engine: Engine
) -> None:
    seeded = seed_campaign(admin_engine, school.fresh, ask_student_class=False)

    assert (
        order(apis.make(), school.slug, seeded.campaign, [(seeded.items[0], 1)]).status_code == 201
    )


def test_the_public_page_of_the_campaign_says_whether_it_asks(
    apis: ApiFactory, school: PublicSchool, admin_engine: Engine
) -> None:
    asking = seed_campaign(admin_engine, school.fresh, ask_student_class=True)
    plain = seed_campaign(admin_engine, school.fresh, ask_student_class=False, title="Rifa")
    api = apis.make()

    one = api.get(f"/api/v1/public/schools/{school.slug}/campaigns/{asking.campaign}").json()
    two = api.get(f"/api/v1/public/schools/{school.slug}/campaigns/{plain.campaign}").json()

    assert one["ask_student_class"] is True and two["ask_student_class"] is False


# --- the new fields of the management --------------------------------------------------------------


def test_the_cost_of_a_product_and_the_flag_of_the_campaign_are_written_by_the_management(
    scene: Any,
) -> None:
    from tests.campaigns.support import created, manager, with_item

    gestao = manager(scene)
    campaign = created(gestao, ask_student_class=False)
    assert campaign["ask_student_class"] is False
    detail = with_item(gestao, campaign["id"], unit_cost_cents=300)
    item = detail["items"][0]
    assert item["unit_cost_cents"] == 300

    cleared = gestao.patch(
        f"/campaigns/{campaign['id']}/items/{item['id']}", {"unit_cost_cents": None}
    )
    free = gestao.patch(f"/campaigns/{campaign['id']}/items/{item['id']}", {"unit_cost_cents": 0})
    flag = gestao.patch(f"/campaigns/{campaign['id']}", {"ask_student_class": True})

    assert cleared.json()["items"][0]["unit_cost_cents"] is None  # null clears: "not informed"
    assert free.json()["items"][0]["unit_cost_cents"] == 0  # a gift costs nothing
    assert flag.json()["ask_student_class"] is True
    assert (
        gestao.patch(f"/campaigns/{campaign['id']}", {"ask_student_class": None}).status_code == 422
    )
    for bad in (-1, 1_000_001, "x", 1.5):
        assert (
            gestao.patch(
                f"/campaigns/{campaign['id']}/items/{item['id']}", {"unit_cost_cents": bad}
            ).status_code
            == 422
        )
