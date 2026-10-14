# ruff: noqa: E501  (SQL and long assertions)
"""The month a contribution is FOR (migration 0015): chosen by the family among the months the server
offers, kept with the contribution for good, and shown on the receipt and in the statement."""

from datetime import date
from typing import Any

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.exc import DBAPIError

from tests.authsupport import ApiFactory
from tests.campaigns.support import committed_manager
from tests.public.conftest import PublicSchool
from tests.public.support import charge_url, contribute, txid_of


def _months_ago(count: int) -> str:
    today = date.today()
    index = today.year * 12 + today.month - 1 - count
    return f"{index // 12:04d}-{index % 12 + 1:02d}"


def _pay(api: Any, txid: str) -> None:
    assert api.post(f"/api/v1/dev/sandbox/pix/{txid}/pay", None, csrf=False).status_code == 200


def test_the_month_chosen_is_stored_as_the_first_day_and_shown_on_the_receipt(
    apis: ApiFactory, school: PublicSchool, admin_engine: Engine
) -> None:
    api = apis.make()
    chosen = _months_ago(1)

    created = contribute(api, school.slug, 3000, reference_month=chosen)
    assert created.status_code == 201, created.text
    _pay(api, txid_of(created))
    receipt = api.get(charge_url(school.slug, created.json()["token"], "receipt")).json()

    assert receipt["reference_month"] == chosen
    with admin_engine.connect() as conn:
        stored: date = conn.execute(
            text("SELECT reference_month FROM contributions WHERE school_id = :s"),
            {"s": school.fresh.school},
        ).scalar_one()
    assert stored.isoformat() == f"{chosen}-01"


def test_without_a_month_nothing_is_stored_and_the_receipt_has_none(
    apis: ApiFactory, school: PublicSchool
) -> None:
    api = apis.make()
    created = contribute(api, school.slug, 3000)
    _pay(api, txid_of(created))

    receipt = api.get(charge_url(school.slug, created.json()["token"], "receipt")).json()

    assert receipt["reference_month"] is None


@pytest.mark.parametrize(
    "month",
    ["2999-01", "1999-01", "2026-13", "2026-00", "2026-1", "outubro", "2026-10-01", ""],
)
def test_a_month_the_server_does_not_offer_is_refused_and_nothing_is_created(
    apis: ApiFactory, school: PublicSchool, admin_engine: Engine, month: str
) -> None:
    api = apis.make()

    response = contribute(api, school.slug, 3000, reference_month=month)

    assert response.status_code == 422, response.text
    assert any(error["field"] == "reference_month" for error in response.json()["errors"])
    with admin_engine.connect() as conn:
        assert (
            conn.execute(
                text("SELECT count(*) FROM contributions WHERE school_id = :s"),
                {"s": school.fresh.school},
            ).scalar_one()
            == 0
        )


def test_the_months_offered_are_this_one_and_the_eleven_before_and_no_other(
    apis: ApiFactory, school: PublicSchool
) -> None:
    api = apis.make()
    page = api.get(f"/api/v1/public/schools/{school.slug}").json()
    offered = page["reference_months"]

    assert offered[-1] == _months_ago(0) and offered[0] == _months_ago(11) and len(offered) == 12
    assert (
        contribute(api, school.slug, 3000, reference_month=_months_ago(11)).status_code == 201
    )  # the oldest
    assert (
        contribute(api, school.slug, 3000, reference_month=_months_ago(12)).status_code == 422
    )  # one more


def test_the_statement_shows_the_month_of_a_contribution(
    apis: ApiFactory, school: PublicSchool, admin_engine: Engine
) -> None:
    gestao = committed_manager(apis, admin_engine, school)
    api = apis.make()
    chosen = _months_ago(2)
    _pay(api, txid_of(contribute(api, school.slug, 3000, reference_month=chosen)))
    _pay(api, txid_of(contribute(api, school.slug, 2000)))

    items = gestao.get("/statement").json()["items"]

    months = sorted(
        str(item["reference_month"]) for item in items if item["kind"] == "CONTRIBUTION"
    )
    assert months == sorted([chosen, "None"])  # one has a month, the other none
    assert all(item["reference_month"] is None for item in items if item["kind"] != "CONTRIBUTION")


def test_the_month_of_a_contribution_never_changes(
    apis: ApiFactory, school: PublicSchool, admin_engine: Engine
) -> None:
    api = apis.make()
    assert contribute(api, school.slug, 3000, reference_month=_months_ago(1)).status_code == 201

    with pytest.raises(DBAPIError), admin_engine.begin() as conn:
        conn.execute(
            text("UPDATE contributions SET reference_month = '2020-01-01' WHERE school_id = :s"),
            {"s": school.fresh.school},
        )
