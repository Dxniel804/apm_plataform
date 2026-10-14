# ruff: noqa: E501  (SQL and long assertions)
"""The fee of the payment gateway (migration 0016): recorded when a Pix is confirmed, shown next to the
gross amount, and never able to change or to lie about the ledger."""

from typing import Any

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.exc import DBAPIError

from tests.authsupport import ApiFactory
from tests.campaigns.support import committed_manager
from tests.public.conftest import PublicSchool
from tests.public.support import contribute, txid_of


def _pay(api: Any, txid: str) -> None:
    assert api.post(f"/api/v1/dev/sandbox/pix/{txid}/pay", None, csrf=False).status_code == 200


def _fees(engine: Engine, school: PublicSchool) -> list[tuple[int, int, int, str]]:
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT gross_cents, gateway_fee_cents, net_cents, fee_payer FROM contribution_fees WHERE school_id = :s ORDER BY created_at"
            ),
            {"s": school.fresh.school},
        ).all()
    return [(int(r[0]), int(r[1]), int(r[2]), str(r[3])) for r in rows]


def test_a_confirmed_payment_records_gross_fee_and_net(
    apis: ApiFactory, school: PublicSchool, admin_engine: Engine
) -> None:
    api = apis.make()
    _pay(api, txid_of(contribute(api, school.slug, 3000)))

    assert _fees(admin_engine, school) == [(3000, 80, 2920, "SCHOOL")]


def test_a_payment_not_confirmed_records_no_fee(
    apis: ApiFactory, school: PublicSchool, admin_engine: Engine
) -> None:
    api = apis.make()
    contribute(api, school.slug, 3000)

    assert _fees(admin_engine, school) == []


def test_the_statement_and_the_summary_show_the_fee_and_the_ledger_stays_gross(
    apis: ApiFactory, school: PublicSchool, admin_engine: Engine
) -> None:
    gestao = committed_manager(apis, admin_engine, school)
    api = apis.make()
    _pay(api, txid_of(contribute(api, school.slug, 3000)))
    _pay(api, txid_of(contribute(api, school.slug, 2000)))

    entries = gestao.get("/statement").json()["items"]
    summary = gestao.get("/statement/summary").json()

    by_amount = {e["amount_cents"]: e for e in entries}
    assert by_amount[3000]["gateway_fee_cents"] == 80 and by_amount[3000]["net_cents"] == 2920
    assert by_amount[2000]["gateway_fee_cents"] == 80 and by_amount[2000]["net_cents"] == 1920
    assert summary["gateway_fees_cents"] == 160
    assert (
        summary["total_in_cents"] == 5000 and summary["closing_balance_cents"] == 5000
    )  # the ledger is the gross amount


def test_the_summary_without_payments_has_no_fees(
    apis: ApiFactory, school: PublicSchool, admin_engine: Engine
) -> None:
    gestao = committed_manager(apis, admin_engine, school)

    assert gestao.get("/statement/summary").json()["gateway_fees_cents"] == 0


def test_the_fee_is_recorded_once_even_if_the_notice_comes_twice(
    apis: ApiFactory, school: PublicSchool, admin_engine: Engine
) -> None:
    api = apis.make()
    txid = txid_of(contribute(api, school.slug, 3000))
    _pay(api, txid)
    api.post(f"/api/v1/dev/sandbox/pix/{txid}/pay", None, csrf=False)

    assert len(_fees(admin_engine, school)) == 1


def test_the_database_refuses_a_fee_that_lies(
    apis: ApiFactory, school: PublicSchool, admin_engine: Engine
) -> None:
    api = apis.make()
    _pay(api, txid_of(contribute(api, school.slug, 3000)))
    unpaid = contribute(api, school.slug, 4000)
    assert unpaid.status_code == 201
    fresh = school.fresh
    with admin_engine.connect() as conn:
        paid_tx: Any = conn.execute(
            text("SELECT transaction_id FROM contribution_fees WHERE school_id = :s"),
            {"s": fresh.school},
        ).scalar_one()
        unpaid_tx: Any = conn.execute(
            text(
                "SELECT c.transaction_id FROM contributions c JOIN financial_transactions f ON f.id = c.transaction_id WHERE c.school_id = :s AND f.status = 'PENDING_PAYMENT'"
            ),
            {"s": fresh.school},
        ).scalar_one()

    def insert(tx: Any, gross: int, fee: int, payer: str = "SCHOOL") -> None:
        with admin_engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO contribution_fees (organization_id, school_id, transaction_id, gross_cents, gateway_fee_cents, fee_payer) VALUES (:o, :s, :t, :g, :f, :p)"
                ),
                {"o": fresh.org, "s": fresh.school, "t": tx, "g": gross, "f": fee, "p": payer},
            )

    with pytest.raises(DBAPIError):  # an unpaid contribution has no fee
        insert(unpaid_tx, 4000, 80)
    with pytest.raises(DBAPIError):  # a gross amount that is not the ledger amount
        insert(paid_tx, 9999, 80)
    with pytest.raises(DBAPIError):  # the second row of the same contribution
        insert(paid_tx, 3000, 80)
    with pytest.raises(DBAPIError):  # a fee above the amount
        insert(unpaid_tx, 4000, 5000)
    with pytest.raises(DBAPIError), admin_engine.begin() as conn:  # never changed
        conn.execute(
            text("UPDATE contribution_fees SET gateway_fee_cents = 1 WHERE transaction_id = :t"),
            {"t": paid_tx},
        )


def test_when_the_payer_pays_the_fee_the_school_receives_the_gross(
    school: PublicSchool, admin_engine: Engine, apis: ApiFactory
) -> None:
    api = apis.make()
    _pay(api, txid_of(contribute(api, school.slug, 3000)))
    with admin_engine.begin() as conn:
        conn.execute(text("SET LOCAL session_replication_role = replica"))
        conn.execute(
            text("UPDATE contribution_fees SET fee_payer = 'PAYER' WHERE school_id = :s"),
            {"s": school.fresh.school},
        )

    assert _fees(admin_engine, school) == [
        (3000, 80, 3000, "PAYER")
    ]  # the generated column follows
