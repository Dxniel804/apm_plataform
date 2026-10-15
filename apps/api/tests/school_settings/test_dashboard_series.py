# ruff: noqa: E501  (SQL and long assertions)
"""The data of the dashboard (M3): the evolution of the last months and the goal and adhesion card.
Both come from `statement_summary`, so they always agree with the cards and the closing."""

from typing import Any

from sqlalchemy import Engine

from tests.authsupport import ApiFactory
from tests.campaigns.support import committed_manager
from tests.public.conftest import PublicSchool
from tests.public.support import contribute, txid_of


def _pay(api: Any, txid: str) -> None:
    assert api.post(f"/api/v1/dev/sandbox/pix/{txid}/pay", None, csrf=False).status_code == 200


def test_the_series_has_one_point_per_month_and_ends_at_the_month_asked(
    apis: ApiFactory, school: PublicSchool, admin_engine: Engine
) -> None:
    gestao = committed_manager(apis, admin_engine, school)

    body = gestao.get("/statement/series?period=2026-03&months=4").json()

    assert body["period"] == "2026-03"
    assert [p["period"] for p in body["points"]] == [
        "2025-12",
        "2026-01",
        "2026-02",
        "2026-03",
    ]  # across the new year
    assert all(
        set(p) == {"period", "total_in_cents", "total_out_cents", "closing_balance_cents"}
        for p in body["points"]
    )


def test_a_paid_contribution_shows_in_this_month_and_in_the_balance_of_the_next(
    apis: ApiFactory, school: PublicSchool, admin_engine: Engine
) -> None:
    gestao = committed_manager(apis, admin_engine, school)
    api = apis.make()
    _pay(api, txid_of(contribute(api, school.slug, 3000)))
    current = gestao.get("/statement/summary").json()

    series = gestao.get("/statement/series?months=3").json()
    last = series["points"][-1]

    assert last["period"] == current["period"]
    assert last["total_in_cents"] == current["total_in_cents"] == 3000
    assert last["closing_balance_cents"] == current["closing_balance_cents"]
    assert series["points"][0]["total_in_cents"] == 0  # two months ago: nothing


def test_the_series_months_are_bounded_and_the_period_must_be_valid(
    apis: ApiFactory, school: PublicSchool, admin_engine: Engine
) -> None:
    gestao = committed_manager(apis, admin_engine, school)

    assert gestao.get("/statement/series?months=1").status_code == 422
    assert gestao.get("/statement/series?months=13").status_code == 422
    assert gestao.get("/statement/series?period=2026-13").status_code == 422
    assert len(gestao.get("/statement/series?months=12").json()["points"]) == 12


def test_the_goal_card_without_goals_says_null_and_counts_the_paid_contributions(
    apis: ApiFactory, school: PublicSchool, admin_engine: Engine
) -> None:
    gestao = committed_manager(apis, admin_engine, school)
    api = apis.make()
    _pay(api, txid_of(contribute(api, school.slug, 3000)))
    _pay(api, txid_of(contribute(api, school.slug, 2000)))
    contribute(api, school.slug, 4000)  # not paid: not counted

    body = gestao.get("/statement/goal").json()

    assert body["goal_cents"] is None and body["expected_contributions"] is None
    assert body["collected_cents"] == 5000 and body["paid_contributions"] == 2


def test_the_goal_card_reads_the_goals_the_school_set(
    apis: ApiFactory, school: PublicSchool, admin_engine: Engine
) -> None:
    gestao = committed_manager(apis, admin_engine, school)
    assert (
        gestao.patch(
            "/settings", {"monthly_goal_cents": 1_000_000, "expected_contributions": 80}
        ).status_code
        == 200
    )
    api = apis.make()
    _pay(api, txid_of(contribute(api, school.slug, 3000)))

    body = gestao.get("/statement/goal").json()

    assert body["goal_cents"] == 1_000_000 and body["expected_contributions"] == 80
    assert body["collected_cents"] == 3000 and body["paid_contributions"] == 1


def test_campaign_sales_are_not_counted_as_contributions(
    apis: ApiFactory, school: PublicSchool, admin_engine: Engine
) -> None:
    from tests.campaigns.support import seed_campaign
    from tests.campaigns.test_public import order

    gestao = committed_manager(apis, admin_engine, school)
    seeded = seed_campaign(admin_engine, school.fresh)
    api = apis.make()
    created = order(api, school.slug, seeded.campaign, [(seeded.items[0], 1)])
    _pay(api, txid_of(created))

    body = gestao.get("/statement/goal").json()

    assert (
        body["collected_cents"] == 0 and body["paid_contributions"] == 0
    )  # the campaign has its own page


def test_another_school_cannot_read_the_series_or_the_goal(
    apis: ApiFactory, school: PublicSchool, other_school: PublicSchool, admin_engine: Engine
) -> None:
    stranger = committed_manager(apis, admin_engine, other_school)

    for tail in ("/statement/series", "/statement/goal"):
        answer = stranger.get(tail, school=school.fresh.school)
        assert answer.status_code == 404 and answer.json()["code"] == "not_found"
