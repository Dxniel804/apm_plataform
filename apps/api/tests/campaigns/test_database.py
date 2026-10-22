# ruff: noqa: E501, S608  (SQL text; the f-strings below only splice constants of this file)
"""What the database itself guarantees about the campaigns, whatever the application does: the grants
by column, the states, what never changes, that an order copies the CURRENT name and price of a
product that is on sale, that its amount is the sum of its items, and that nothing is deleted."""

import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import Connection, Engine, text
from sqlalchemy.exc import DBAPIError

from app.db.tenant import TenantContext, apply_tenant_context
from tests.dbsupport import transaction
from tests.financial.support import Fresh, check_consistency, make_school

CAMPAIGN_COLUMNS = [
    "id", "organization_id", "school_id", "created_by_user_id", "title", "description", "status",
    "starts_on", "ends_on", "ended_at", "cover_storage_key", "cover_content_type",
    "cover_size_bytes", "cover_sha256", "cover_version", "created_at", "updated_at",
]  # fmt: skip
ITEM_COLUMNS = [
    "id", "organization_id", "school_id", "campaign_id", "name", "description", "price_cents",
    "max_per_order", "position", "is_active", "image_storage_key", "image_content_type",
    "image_size_bytes", "image_sha256", "image_version", "created_at", "updated_at",
]  # fmt: skip
COPY_COLUMNS = [
    "id", "organization_id", "school_id", "transaction_id", "campaign_id", "campaign_item_id",
    "item_name", "unit_price_cents", "quantity", "created_at",
]  # fmt: skip
COLUMNS = {
    "campaigns": CAMPAIGN_COLUMNS,
    "campaign_items": ITEM_COLUMNS,
    "contribution_items": COPY_COLUMNS,
}
INSERTABLE = {
    "campaigns": {"organization_id", "school_id", "created_by_user_id", "title", "description", "starts_on", "ends_on"},
    "campaign_items": {"organization_id", "school_id", "campaign_id", "name", "description", "price_cents", "max_per_order", "position"},
    "contribution_items": {"organization_id", "school_id", "transaction_id", "campaign_id", "campaign_item_id", "item_name", "unit_price_cents", "quantity"},
}  # fmt: skip
UPDATABLE = {
    "campaigns": {"title", "description", "status", "starts_on", "ends_on", "ended_at", "cover_storage_key", "cover_content_type", "cover_size_bytes", "cover_sha256", "cover_version", "updated_at"},
    "campaign_items": {"name", "description", "price_cents", "max_per_order", "position", "is_active", "image_storage_key", "image_content_type", "image_size_bytes", "image_sha256", "image_version", "updated_at"},
    "contribution_items": set(),
}  # fmt: skip


@pytest.fixture
def world(admin_engine: Engine) -> Iterator[tuple[Connection, Fresh]]:
    """A transaction of the admin (a superuser: every trigger fires, row level security does not
    apply) with a school of its own. Always rolled back, so nothing is left behind. Not the `world`
    of the authentication tests: this module does not log anybody in."""
    with transaction(admin_engine) as conn:
        yield conn, make_school(conn)


def _privileges(engine: Engine, table: str, privilege: str) -> set[str]:
    with engine.connect() as connection:
        return {
            column
            for column in COLUMNS[table]
            if connection.execute(
                text("SELECT has_column_privilege('apm_app', :t, :c, :p)"),
                {"t": table, "c": column, "p": privilege},
            ).scalar_one()
        }


@pytest.mark.parametrize("table", list(COLUMNS))
def test_the_application_role_writes_by_column_and_never_deletes(
    admin_engine: Engine, table: str
) -> None:
    assert _privileges(admin_engine, table, "SELECT") == set(COLUMNS[table])
    assert _privileges(admin_engine, table, "INSERT") == INSERTABLE[table]
    assert _privileges(admin_engine, table, "UPDATE") == UPDATABLE[table]
    with admin_engine.connect() as connection:
        for privilege in ("DELETE", "TRUNCATE", "REFERENCES", "TRIGGER"):
            allowed: Any = connection.execute(
                text("SELECT has_table_privilege('apm_app', :t, :p)"),
                {"t": table, "p": privilege},
            ).scalar_one()
            assert allowed is False, privilege


def test_the_campaign_of_a_contribution_is_written_with_the_row_and_readable(
    admin_engine: Engine,
) -> None:
    with admin_engine.connect() as connection:
        for privilege in ("SELECT", "INSERT"):
            assert connection.execute(
                text("SELECT has_column_privilege('apm_app', 'contributions', 'campaign_id', :p)"),
                {"p": privilege},
            ).scalar_one()
        assert not connection.execute(
            text("SELECT has_column_privilege('apm_app', 'contributions', 'campaign_id', 'UPDATE')")
        ).scalar_one()


# --- builders -----------------------------------------------------------------------------------

ITEMS = (("Cachorro-quente", 800, 5), ("Pamonha", 650, None))


def campaign(
    conn: Connection,
    f: Fresh,
    *,
    status: str = "ACTIVE",
    items: tuple[tuple[str, int, int | None], ...] = ITEMS,
    starts_on: date | None = None,
    ends_on: date | None = None,
) -> tuple[uuid.UUID, list[uuid.UUID]]:
    campaign_id: uuid.UUID = conn.execute(
        text(
            "INSERT INTO campaigns (organization_id, school_id, created_by_user_id, title, "
            "starts_on, ends_on) VALUES (:o, :s, :u, 'Festa', :starts_on, :ends_on) RETURNING id"
        ),
        {"o": f.org, "s": f.school, "u": f.treasurer, "starts_on": starts_on, "ends_on": ends_on},
    ).scalar_one()
    ids: list[uuid.UUID] = [
        conn.execute(
            text(
                "INSERT INTO campaign_items (organization_id, school_id, campaign_id, name, "
                "price_cents, max_per_order, position) VALUES (:o, :s, :c, :n, :p, :l, :i) RETURNING id"
            ),
            {
                "o": f.org,
                "s": f.school,
                "c": campaign_id,
                "n": name,
                "p": price,
                "l": limit,
                "i": position,
            },
        ).scalar_one()
        for position, (name, price, limit) in enumerate(items)
    ]
    if status == "ACTIVE":
        conn.execute(
            text("UPDATE campaigns SET status = 'ACTIVE' WHERE id = :c"), {"c": campaign_id}
        )
    elif status == "ENDED":
        conn.execute(
            text("UPDATE campaigns SET status = 'ENDED', ended_at = now() WHERE id = :c"),
            {"c": campaign_id},
        )
    return campaign_id, ids


def order(conn: Connection, f: Fresh, campaign_id: uuid.UUID | None, amount: int) -> uuid.UUID:
    """A contribution (cash, born PAID: no charge to build) of the campaign, with NO items yet."""
    category: uuid.UUID = conn.execute(
        text("SELECT id FROM categories WHERE school_id = :s AND key = 'campaign_sales'"),
        {"s": f.school},
    ).scalar_one()
    tx: uuid.UUID = conn.execute(
        text(
            "INSERT INTO financial_transactions (organization_id, school_id, kind, direction, "
            "amount_cents, status, category_id, origin_type, occurred_at, settled_at, created_by_user_id) "
            "VALUES (:o, :s, 'CONTRIBUTION', 'IN', :a, 'PAID', :cat, 'GUARDIAN', now(), now(), :u) RETURNING id"
        ),
        {"o": f.org, "s": f.school, "a": amount, "cat": category, "u": f.treasurer},
    ).scalar_one()
    conn.execute(
        text(
            "INSERT INTO contributions (transaction_id, organization_id, school_id, method, campaign_id) "
            "VALUES (:t, :o, :s, 'CASH', :c)"
        ),
        {"t": tx, "o": f.org, "s": f.school, "c": campaign_id},
    )
    return tx


def line(
    conn: Connection, f: Fresh, tx: uuid.UUID, campaign_id: uuid.UUID, item_id: uuid.UUID,
    name: str, price: int, quantity: int,
) -> None:  # fmt: skip
    conn.execute(
        text(
            "INSERT INTO contribution_items (organization_id, school_id, transaction_id, campaign_id, "
            "campaign_item_id, item_name, unit_price_cents, quantity) VALUES (:o, :s, :t, :c, :i, :n, :p, :q)"
        ),
        {
            "o": f.org,
            "s": f.school,
            "t": tx,
            "c": campaign_id,
            "i": item_id,
            "n": name,
            "p": price,
            "q": quantity,
        },
    )


@contextmanager
def refused(conn: Connection, match: str) -> Iterator[None]:
    """The block must fail with a database error that matches; the transaction stays usable."""
    with pytest.raises(DBAPIError, match=match), conn.begin_nested():
        yield


def _scalar(conn: Connection, sql: str, **params: object) -> Any:
    return conn.execute(text(sql), params).scalar_one()


# --- the default category -----------------------------------------------------------------------


def test_a_new_school_gets_the_category_of_the_campaigns(world: tuple[Connection, Fresh]) -> None:
    conn, f = world
    row = conn.execute(
        text(
            "SELECT name, applies_to, report_group FROM categories "
            "WHERE school_id = :s AND key = 'campaign_sales'"
        ),
        {"s": f.school},
    ).one()
    assert tuple(row) == ("Vendas de campanha", "IN", "OTHER_INCOME")


# --- the states of a campaign -------------------------------------------------------------------


def test_a_campaign_goes_on_sale_only_with_an_active_product(
    world: tuple[Connection, Fresh],
) -> None:
    conn, f = world
    campaign_id, items = campaign(conn, f, status="DRAFT", items=())
    with refused(conn, "needs an active product"):
        conn.execute(
            text("UPDATE campaigns SET status = 'ACTIVE' WHERE id = :c"), {"c": campaign_id}
        )
    conn.execute(
        text(
            "INSERT INTO campaign_items (organization_id, school_id, campaign_id, name, price_cents, is_active) "
            "VALUES (:o, :s, :c, 'Off', 500, false)"
        ),
        {"o": f.org, "s": f.school, "c": campaign_id},
    )
    with refused(conn, "needs an active product"):  # a switched off product does not count
        conn.execute(
            text("UPDATE campaigns SET status = 'ACTIVE' WHERE id = :c"), {"c": campaign_id}
        )
    conn.execute(
        text("UPDATE campaign_items SET is_active = true WHERE campaign_id = :c"),
        {"c": campaign_id},
    )
    conn.execute(text("UPDATE campaigns SET status = 'ACTIVE' WHERE id = :c"), {"c": campaign_id})


@pytest.mark.parametrize(
    ("start", "target", "message"),
    [
        ("ACTIVE", "DRAFT", "cannot go from"),
        ("ENDED", "ACTIVE", "can never|cannot go from|final"),
        ("ENDED", "DRAFT", "can never|cannot go from|final"),
    ],
)
def test_a_campaign_never_goes_back(
    world: tuple[Connection, Fresh], start: str, target: str, message: str
) -> None:
    conn, f = world
    campaign_id, _ = campaign(conn, f, status=start)
    with refused(conn, message):
        conn.execute(
            text("UPDATE campaigns SET status = :t, ended_at = NULL WHERE id = :c"),
            {"t": target, "c": campaign_id},
        )


def test_an_ended_campaign_changes_in_no_column_and_its_products_do_not_either(
    world: tuple[Connection, Fresh],
) -> None:
    conn, f = world
    campaign_id, items = campaign(conn, f, status="ENDED")
    for sql in (
        "UPDATE campaigns SET title = 'Outra' WHERE id = :c",
        "UPDATE campaigns SET description = 'x' WHERE id = :c",
        "UPDATE campaigns SET cover_version = cover_version + 1 WHERE id = :c",
    ):
        with refused(conn, "final|can never"):
            conn.execute(text(sql), {"c": campaign_id})
    with refused(conn, "ended campaign"):
        conn.execute(
            text("UPDATE campaign_items SET price_cents = 900 WHERE id = :i"), {"i": items[0]}
        )
    with refused(conn, "ended campaign"):
        conn.execute(
            text(
                "INSERT INTO campaign_items (organization_id, school_id, campaign_id, name, price_cents) "
                "VALUES (:o, :s, :c, 'Novo', 500)"
            ),
            {"o": f.org, "s": f.school, "c": campaign_id},
        )


def test_it_ended_means_it_has_an_end_time_and_only_then(world: tuple[Connection, Fresh]) -> None:
    conn, f = world
    campaign_id, _ = campaign(conn, f)
    with refused(conn, "ended_iff_status"):
        conn.execute(
            text("UPDATE campaigns SET status = 'ENDED' WHERE id = :c"), {"c": campaign_id}
        )
    with refused(conn, "ended_iff_status"):
        conn.execute(
            text("UPDATE campaigns SET ended_at = now() WHERE id = :c"), {"c": campaign_id}
        )


@pytest.mark.parametrize(
    "column",
    ["id", "organization_id", "school_id", "created_by_user_id", "created_at"],
)
def test_what_the_campaign_was_born_with_never_changes(
    world: tuple[Connection, Fresh], column: str
) -> None:
    conn, f = world
    campaign_id, _ = campaign(conn, f, status="DRAFT")
    value = "now() - interval '1 day'" if column == "created_at" else "gen_random_uuid()"
    with refused(conn, "can never change|foreign key|invalid user|violates"):
        conn.execute(
            text(f"UPDATE campaigns SET {column} = {value} WHERE id = :c"), {"c": campaign_id}
        )  # noqa: S608


def test_an_author_must_be_an_active_member_of_the_school(world: tuple[Connection, Fresh]) -> None:
    conn, f = world
    with refused(conn, "invalid user reference"):
        conn.execute(
            text(
                "INSERT INTO campaigns (organization_id, school_id, created_by_user_id, title) "
                "VALUES (:o, :s, :u, 'Festa')"
            ),
            {"o": f.org, "s": f.school, "u": f.outsider},
        )


@pytest.mark.parametrize(
    ("column", "value", "match"),
    [
        ("title", "''", "title_length"),
        ("title", "repeat('x', 121)", "title_length"),
        ("description", "repeat('x', 2001)", "description_length"),
        ("status", "'LIVE'", "status_valid|cannot go from"),
        ("ends_on", "current_date - 1", "dates_in_order"),  # with starts_on = today below
    ],
)
def test_the_limits_of_a_campaign_are_in_the_database(
    world: tuple[Connection, Fresh], column: str, value: str, match: str
) -> None:
    conn, f = world
    campaign_id, _ = campaign(conn, f, status="DRAFT", starts_on=date.today())
    with refused(conn, match):
        conn.execute(
            text(f"UPDATE campaigns SET {column} = {value} WHERE id = :c"), {"c": campaign_id}
        )  # noqa: S608


@pytest.mark.parametrize(
    ("column", "value", "match"),
    [
        ("name", "''", "name_length"),
        ("name", "repeat('x', 121)", "name_length"),
        ("description", "repeat('x', 501)", "description_length"),
        ("price_cents", "99", "price_range"),
        ("price_cents", "1000001", "price_range"),
        ("max_per_order", "0", "max_per_order_range"),
        ("max_per_order", "100", "max_per_order_range"),
        ("position", "1000", "position_range"),
        ("position", "-1", "position_range"),
    ],
)
def test_the_limits_of_a_product_are_in_the_database(
    world: tuple[Connection, Fresh], column: str, value: str, match: str
) -> None:
    conn, f = world
    _, items = campaign(conn, f, status="DRAFT")
    with refused(conn, match):
        conn.execute(
            text(f"UPDATE campaign_items SET {column} = {value} WHERE id = :i"), {"i": items[0]}
        )  # noqa: S608


def test_a_picture_is_all_five_columns_or_none(world: tuple[Connection, Fresh]) -> None:
    conn, f = world
    campaign_id, _ = campaign(conn, f, status="DRAFT")
    with refused(conn, "cover_all_or_none"):
        conn.execute(
            text("UPDATE campaigns SET cover_storage_key = 'k/1' WHERE id = :c"), {"c": campaign_id}
        )
    for column, value, match in (
        ("cover_content_type", "'image/gif'", "content_type_image"),
        ("cover_size_bytes", "5242881", "size_range"),
        ("cover_sha256", "'xyz'", "sha256_format"),
        ("cover_storage_key", "'/absolute'", "key_length"),
    ):
        sets = {
            "cover_storage_key": "'k/1'", "cover_content_type": "'image/png'",
            "cover_size_bytes": "10", "cover_sha256": f"'{'a' * 64}'",
        }  # fmt: skip
        sets[column] = value
        with refused(conn, match):
            conn.execute(
                text(
                    "UPDATE campaigns SET "
                    + ", ".join(f"{k} = {v}" for k, v in sets.items())
                    + " WHERE id = :c"
                ),  # noqa: S608
                {"c": campaign_id},
            )


def test_nothing_is_ever_deleted_not_even_by_the_owner(world: tuple[Connection, Fresh]) -> None:
    conn, f = world
    campaign_id, items = campaign(conn, f)
    tx = order(conn, f, campaign_id, 800)
    line(conn, f, tx, campaign_id, items[0], "Cachorro-quente", 800, 1)
    for sql in (
        "DELETE FROM campaigns WHERE id = :c",
        "DELETE FROM campaign_items WHERE campaign_id = :c",
        "DELETE FROM contribution_items WHERE campaign_id = :c",
    ):  # (the trigger that refuses TRUNCATE is in the inventory of test_triggers)
        with refused(conn, "never deleted|cannot be deleted|forbid|not allowed"):
            conn.execute(text(sql), {"c": campaign_id})


# --- what an order copies -----------------------------------------------------------------------


def test_an_order_that_copies_the_current_name_and_price_and_adds_up_is_accepted(
    world: tuple[Connection, Fresh],
) -> None:
    conn, f = world
    campaign_id, items = campaign(conn, f)
    tx = order(conn, f, campaign_id, 3 * 800 + 2 * 650)
    line(conn, f, tx, campaign_id, items[0], "Cachorro-quente", 800, 3)
    line(conn, f, tx, campaign_id, items[1], "Pamonha", 650, 2)

    check_consistency(conn)

    assert (
        _scalar(
            conn,
            "SELECT sum(quantity * unit_price_cents) FROM contribution_items WHERE transaction_id = :t",
            t=tx,
        )
        == 3700
    )


@pytest.mark.parametrize(
    ("name", "price", "quantity"),
    [
        (
            "Cachorro-quente",
            700,
            1,
        ),  # a price that is not the current one (a cheaper one from the browser)
        ("Cachorro-quente", 900, 1),
        ("Outro nome", 800, 1),  # a name that is not the current one
        ("Cachorro-quente", 800, 6),  # over the limit of 5 per order
    ],
)
def test_a_copy_that_is_not_the_current_name_and_price_is_refused(
    world: tuple[Connection, Fresh], name: str, price: int, quantity: int
) -> None:
    conn, f = world
    campaign_id, items = campaign(conn, f)
    tx = order(conn, f, campaign_id, price * quantity)
    with refused(conn, "not on sale as written"):
        line(conn, f, tx, campaign_id, items[0], name, price, quantity)


def test_a_product_that_is_not_on_sale_cannot_be_copied(world: tuple[Connection, Fresh]) -> None:
    conn, f = world
    for status in ("DRAFT", "ENDED"):
        campaign_id, items = campaign(conn, f, status=status)
        tx = order(conn, f, campaign_id, 800)
        with refused(conn, "not on sale as written"):
            line(conn, f, tx, campaign_id, items[0], "Cachorro-quente", 800, 1)
    campaign_id, items = campaign(conn, f)
    conn.execute(text("UPDATE campaign_items SET is_active = false WHERE id = :i"), {"i": items[0]})
    tx = order(conn, f, campaign_id, 800)
    with refused(conn, "not on sale as written"):  # switched off
        line(conn, f, tx, campaign_id, items[0], "Cachorro-quente", 800, 1)


def school_today() -> date:
    """Today as the DATABASE sees it for these schools (America/Sao_Paulo, the default time zone): a
    campaign is on sale by the date of the school, not by the clock of the machine that runs the test.
    With `date.today()` (UTC in the CI) the test failed every day from 21:00 to midnight in Brasília."""
    return datetime.now(ZoneInfo("America/Sao_Paulo")).date()


@pytest.mark.parametrize(
    ("starts", "ends"),
    [(1, None), (None, -1), (2, 3), (-5, -2)],  # days from today: not yet, already over
)
def test_a_campaign_outside_its_dates_cannot_be_ordered(
    world: tuple[Connection, Fresh], starts: int | None, ends: int | None
) -> None:
    conn, f = world
    today = school_today()
    campaign_id, items = campaign(
        conn, f,
        starts_on=None if starts is None else today + timedelta(days=starts),
        ends_on=None if ends is None else today + timedelta(days=ends),
    )  # fmt: skip
    tx = order(conn, f, campaign_id, 800)
    with refused(conn, "not on sale as written"):
        line(conn, f, tx, campaign_id, items[0], "Cachorro-quente", 800, 1)


def test_a_campaign_inside_its_dates_can_be_ordered(world: tuple[Connection, Fresh]) -> None:
    conn, f = world
    today = school_today()
    campaign_id, items = campaign(
        conn, f, starts_on=today - timedelta(days=1), ends_on=today + timedelta(days=1)
    )
    tx = order(conn, f, campaign_id, 800)
    line(conn, f, tx, campaign_id, items[0], "Cachorro-quente", 800, 1)
    check_consistency(conn)


def test_the_amount_of_an_order_is_the_sum_of_its_items_at_commit(
    world: tuple[Connection, Fresh],
) -> None:
    conn, f = world
    campaign_id, items = campaign(conn, f)
    for amount in (1, 799, 1600):  # less, a little less, more
        with refused(conn, "sum of its items"):
            tx = order(conn, f, campaign_id, amount)
            line(conn, f, tx, campaign_id, items[0], "Cachorro-quente", 800, 1)
            check_consistency(conn)


def test_an_order_of_a_campaign_with_no_item_is_refused_at_commit(
    world: tuple[Connection, Fresh],
) -> None:
    conn, f = world
    campaign_id, _ = campaign(conn, f)
    with refused(conn, "sum of its items"):
        order(conn, f, campaign_id, 800)
        check_consistency(conn)


def test_a_contribution_without_a_campaign_has_no_items(world: tuple[Connection, Fresh]) -> None:
    conn, f = world
    campaign_id, items = campaign(conn, f)
    with refused(conn, "only the contribution of a campaign has items"):
        tx = order(conn, f, None, 800)
        line(conn, f, tx, campaign_id, items[0], "Cachorro-quente", 800, 1)
        check_consistency(conn)


def test_the_items_must_belong_to_the_campaign_of_the_order(
    world: tuple[Connection, Fresh],
) -> None:
    conn, f = world
    campaign_id, _ = campaign(conn, f)
    other_id, other_items = campaign(conn, f, items=(("Intruso", 800, None),))
    with refused(conn, "sum of its items|foreign key|not on sale as written"):
        tx = order(conn, f, campaign_id, 800)
        line(conn, f, tx, other_id, other_items[0], "Intruso", 800, 1)
        check_consistency(conn)
    with refused(
        conn, "foreign key|not on sale as written"
    ):  # a product named with another campaign
        tx = order(conn, f, campaign_id, 800)
        line(conn, f, tx, campaign_id, other_items[0], "Intruso", 800, 1)


def test_a_product_appears_once_per_order(world: tuple[Connection, Fresh]) -> None:
    conn, f = world
    campaign_id, items = campaign(conn, f)
    tx = order(conn, f, campaign_id, 1600)
    line(conn, f, tx, campaign_id, items[0], "Cachorro-quente", 800, 1)
    with refused(conn, "uq_contribution_items"):
        line(conn, f, tx, campaign_id, items[0], "Cachorro-quente", 800, 1)


@pytest.mark.parametrize(("price", "quantity"), [(800, 0), (800, 100), (800, -1)])
def test_the_quantity_of_a_line_is_between_one_and_ninety_nine(
    world: tuple[Connection, Fresh], price: int, quantity: int
) -> None:
    conn, f = world
    campaign_id, items = campaign(conn, f, items=(("Cachorro-quente", 800, None),))
    tx = order(conn, f, campaign_id, 800)
    with refused(conn, "quantity_range|not on sale as written"):
        line(conn, f, tx, campaign_id, items[0], "Cachorro-quente", price, quantity)


def test_what_an_order_bought_never_changes_and_a_later_price_does_not_touch_it(
    world: tuple[Connection, Fresh],
) -> None:
    conn, f = world
    campaign_id, items = campaign(conn, f)
    tx = order(conn, f, campaign_id, 1600)
    line(conn, f, tx, campaign_id, items[0], "Cachorro-quente", 800, 2)
    check_consistency(conn)

    conn.execute(
        text("UPDATE campaign_items SET price_cents = 1000, name = 'Hot-dog' WHERE id = :i"),
        {"i": items[0]},
    )

    copy = conn.execute(
        text(
            "SELECT item_name, unit_price_cents FROM contribution_items WHERE transaction_id = :t"
        ),
        {"t": tx},
    ).one()
    assert tuple(copy) == ("Cachorro-quente", 800)  # the order keeps what it bought
    for sql in (
        "UPDATE contribution_items SET unit_price_cents = 100 WHERE transaction_id = :t",
        "UPDATE contribution_items SET quantity = 1 WHERE transaction_id = :t",
        "UPDATE contribution_items SET item_name = 'x' WHERE transaction_id = :t",
    ):
        with refused(conn, "insert-only|cannot be updated|forbid|not allowed"):
            conn.execute(text(sql), {"t": tx})
    check_consistency(conn)  # and the ledger still adds up


def test_the_campaign_of_a_contribution_never_changes(world: tuple[Connection, Fresh]) -> None:
    conn, f = world
    campaign_id, items = campaign(conn, f)
    other_id, _ = campaign(conn, f)
    tx = order(conn, f, campaign_id, 800)
    line(conn, f, tx, campaign_id, items[0], "Cachorro-quente", 800, 1)
    check_consistency(conn)
    for value in ("NULL", f"'{other_id}'"):
        with refused(conn, "can never change"):
            conn.execute(
                text(f"UPDATE contributions SET campaign_id = {value} WHERE transaction_id = :t"),  # noqa: S608
                {"t": tx},
            )


# --- row level security -------------------------------------------------------------------------


def test_a_school_sees_and_writes_only_its_own_campaigns(admin_engine: Engine) -> None:
    with transaction(admin_engine) as conn:
        mine, theirs = make_school(conn), make_school(conn)
        my_campaign, my_items = campaign(conn, mine)
        their_campaign, their_items = campaign(conn, theirs)
        tx = order(conn, theirs, their_campaign, 800)
        line(conn, theirs, tx, their_campaign, their_items[0], "Cachorro-quente", 800, 1)
        conn.exec_driver_sql("SET LOCAL ROLE apm_app")
        apply_tenant_context(conn, TenantContext(mine.org, mine.school))

        for table in ("campaigns", "campaign_items", "contribution_items"):
            visible = _scalar(
                conn, f"SELECT count(*) FROM {table} WHERE school_id = :s", s=theirs.school
            )  # noqa: S608
            assert visible == 0, table
        assert _scalar(conn, "SELECT count(*) FROM campaigns") == 1
        assert _scalar(conn, "SELECT id FROM campaigns") == my_campaign
        # nor can it write into the other school, or touch what it cannot see
        with refused(conn, "row-level security|invalid user reference"):
            conn.execute(
                text(
                    "INSERT INTO campaigns (organization_id, school_id, created_by_user_id, title) "
                    "VALUES (:o, :s, :u, 'Invasora')"
                ),
                {"o": theirs.org, "s": theirs.school, "u": mine.treasurer},
            )
        updated = conn.execute(
            text("UPDATE campaigns SET title = 'Sequestrada' WHERE id = :c"), {"c": their_campaign}
        ).rowcount
        assert updated == 0
        assert my_items  # (the campaign of this school is complete)
