# ruff: noqa: E501  (long assertions)
"""The balancete of the month, in the shape of the accountant's sheet: the sheet is the ledger's (checked
against the summary), the balances the ledger does not know are typed and insert-only, the bank is what
is left, and the PDF carries the lines of the president and of the treasurer."""

from datetime import UTC, date, datetime
from typing import Any

import pytest

from app.reports.balancete import Balances, build_balancete
from app.reports.closing_report import ReportMismatch
from tests.statement.conftest import Login, Scene
from tests.statement.pdftext import text_of


def _entry(key: str, signed: int) -> dict[str, Any]:
    return {"category_key": key, "signed_amount_cents": signed}


def _summary(opening: int, entries: list[dict[str, Any]]) -> dict[str, Any]:
    money_in = sum(e["signed_amount_cents"] for e in entries if e["signed_amount_cents"] > 0)
    money_out = -sum(e["signed_amount_cents"] for e in entries if e["signed_amount_cents"] < 0)
    return {
        "timezone": "America/Sao_Paulo",
        "opening_balance_cents": opening,
        "closing_balance_cents": opening + money_in - money_out,
        "total_in_cents": money_in,
        "total_out_cents": money_out,
    }


def _build(entries: list[dict[str, Any]], opening: int, balances: Balances) -> Any:
    return build_balancete(
        entries=entries,
        summary=_summary(opening, entries),
        category_names={
            "parent_contribution": "Contribuição de pais",
            "stationery": "Impressos e material de expediente",
            "capital_furniture": "Compra de móveis",
            "bank_fees": "Tarifas bancárias",
        },
        balances=balances,
        organization_name="APM Exemplo",
        school_name="Escola Exemplo",
        period_start=date(2026, 7, 1),
        period_end=date(2026, 7, 31),
        generated_at=datetime(2026, 8, 1, tzinfo=UTC),
    )


ENTRIES = [
    _entry("parent_contribution", 3000),
    _entry("parent_contribution", 2000),
    _entry("stationery", -1200),
    _entry("capital_furniture", -800),
    _entry("bank_fees", -217),
]


def test_the_sheet_splits_revenue_permanent_goods_and_expenses_and_adds_up() -> None:
    sheet = _build(ENTRIES, 10000, Balances(None, None, None))

    assert [(x.name, x.cents) for x in sheet.revenue] == [("Contribuição de pais", 5000)]
    assert [(x.name, x.cents) for x in sheet.capital] == [("Compra de móveis", 800)]
    assert [(x.name, x.cents) for x in sheet.expenses] == [
        ("Impressos e material de expediente", 1200),
        ("Tarifas bancárias", 217),
    ]
    assert sheet.balance_of_month == 10000 + 5000 - 800 - 1417 == 12783
    # Nobody typed cash or invested: everything is in the bank, and the sheet says it is not typed
    assert sheet.closing.bank_cents == 12783 and sheet.closing.total_cents == 12783
    assert not sheet.closing_typed


def test_what_the_school_had_before_the_ledger_started_is_part_of_every_balance() -> None:
    opening = {"bank_cents": 8000, "cash_cents": 1500, "investment_cents": 500}

    sheet = _build(ENTRIES, 0, Balances(opening, None, None))

    # 10000 from before + the month: the ledger alone would have shown 2783
    assert sheet.opening.total_cents == 10000
    assert (sheet.opening.bank_cents, sheet.opening.cash_cents, sheet.opening.investment_cents) == (
        8000,
        1500,
        500,
    )
    assert sheet.closing.total_cents == 12783 == sheet.balance_of_month


def test_cash_and_invested_typed_for_the_month_leave_the_bank_as_the_rest() -> None:
    previous = {"cash_cents": 1000, "investment_cents": 500}
    current = {"cash_cents": 1800, "investment_cents": 500}

    sheet = _build(ENTRIES, 10000, Balances(None, previous, current))

    assert (sheet.opening.bank_cents, sheet.opening.cash_cents, sheet.opening.investment_cents) == (
        8500,
        1000,
        500,
    )
    assert (sheet.closing.bank_cents, sheet.closing.cash_cents, sheet.closing.investment_cents) == (
        10483,
        1800,
        500,
    )
    assert sheet.closing_typed
    assert sheet.closing.total_cents == 12783


def test_a_summary_that_does_not_match_the_lines_is_refused() -> None:
    summary = _summary(10000, ENTRIES)
    summary["total_out_cents"] += 1  # a late adjustment landed between the two reads

    with pytest.raises(ReportMismatch):
        build_balancete(
            entries=ENTRIES, summary=summary, category_names={}, balances=Balances(None, None, None),
            organization_name="A", school_name="B", period_start=date(2026, 7, 1),
            period_end=date(2026, 7, 31), generated_at=datetime(2026, 8, 1, tzinfo=UTC),
        )  # fmt: skip


# --- the routes -----------------------------------------------------------------------------------


def _url(school: object, tail: str = "balancete", period: str | None = "2025-03") -> str:
    base = f"/api/v1/schools/{school}/{tail}"
    return base if period is None else f"{base}?period={period}"


def test_the_numbers_are_the_ledgers_and_the_bank_is_everything_until_somebody_types_more(
    scene: Scene, login: Login
) -> None:
    api = login(scene.users["secretaria"])
    summary = api.get(
        f"/api/v1/schools/{scene.fresh.school}/statement/summary", params={"period": "2025-03"}
    ).json()

    sheet = api.get(_url(scene.fresh.school))

    assert sheet.status_code == 200, sheet.text
    body = sheet.json()
    assert body["period"] == "2025-03"
    assert body["opening"]["total_cents"] == summary["opening_balance_cents"]
    assert body["closing"]["total_cents"] == summary["closing_balance_cents"]
    assert body["balance_of_month_cents"] == summary["closing_balance_cents"]
    assert body["closing"]["bank_cents"] == summary["closing_balance_cents"]
    assert body["total_revenue_cents"] == summary["total_in_cents"]
    assert body["total_capital_cents"] + body["total_expenses_cents"] == summary["total_out_cents"]
    assert body["has_opening"] is False and body["closing_typed"] is False


def test_typed_balances_change_the_sheet_and_the_latest_one_counts(
    scene: Scene, login: Login
) -> None:
    api = login(scene.users["secretaria"])
    school = scene.fresh.school
    before = api.get(_url(school)).json()

    start = api.post(
        f"/api/v1/schools/{school}/balancete/balances",
        json={"kind": "OPENING", "bank_cents": 5000, "cash_cents": 700, "investment_cents": 300},
    )
    first = api.post(
        f"/api/v1/schools/{school}/balancete/balances",
        json={"kind": "MONTH", "period": "2025-03", "cash_cents": 900, "investment_cents": 300},
    )
    second = api.post(  # a correction is a new row: the latest counts
        f"/api/v1/schools/{school}/balancete/balances",
        json={"kind": "MONTH", "period": "2025-03", "cash_cents": 1000, "investment_cents": 300},
    )

    assert start.status_code == first.status_code == second.status_code == 201, (
        start.text,
        first.text,
        second.text,
    )
    after = api.get(_url(school)).json()
    assert after["has_opening"] and after["closing_typed"]
    assert after["closing"]["total_cents"] == before["closing"]["total_cents"] + 6000
    assert after["closing"]["cash_cents"] == 1000 and after["closing"]["investment_cents"] == 300
    assert after["closing"]["bank_cents"] == after["closing"]["total_cents"] - 1300


def test_the_shape_of_a_balance_is_checked(scene: Scene, login: Login) -> None:
    api = login(scene.users["secretaria"])
    path = f"/api/v1/schools/{scene.fresh.school}/balancete/balances"

    no_bank = api.post(path, json={"kind": "OPENING", "cash_cents": 1, "investment_cents": 1})
    month_with_bank = api.post(
        path,
        json={
            "kind": "MONTH",
            "period": "2025-03",
            "bank_cents": 1,
            "cash_cents": 1,
            "investment_cents": 1,
        },
    )
    negative = api.post(
        path, json={"kind": "MONTH", "period": "2025-03", "cash_cents": -1, "investment_cents": 1}
    )

    assert no_bank.status_code == month_with_bank.status_code == negative.status_code == 422


def test_only_who_closes_the_month_types_balances_and_the_staff_reads_nothing(
    scene: Scene, login: Login
) -> None:
    staff = login(scene.users["staff"])
    school = scene.fresh.school

    wrote = staff.post(
        f"/api/v1/schools/{school}/balancete/balances",
        json={"kind": "MONTH", "period": "2025-03", "cash_cents": 1, "investment_cents": 1},
    )
    read = staff.get(_url(school))

    assert wrote.status_code == 403 and read.status_code == 403


def test_the_pdf_follows_the_accountants_sheet(scene: Scene, login: Login) -> None:
    api = login(scene.users["secretaria"])

    response = api.get(_url(scene.fresh.school, "balancete.pdf"))

    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == "application/pdf"
    assert response.headers["content-disposition"] == 'attachment; filename="balancete-2025-03.pdf"'
    assert response.headers["cache-control"] == "private, no-store"
    text = text_of(response.content)
    for part in (
        "BALANCETE REFERENTE AO PERÍODO DE MARÇO DE 2025",
        "SALDO ANTERIOR",
        "RECEITAS",
        "TOTAL DE RECEITAS",
        "BENS PERMANENTES",
        "TOTAL DAS DESPESAS",
        "SALDO DO MÊS",
        "DEMONSTRAÇÃO DO SALDO FINAL",
        "SALDO FINAL",
        "PRESIDENTE",
        "TESOUREIRO",
    ):
        assert part in text, part


def test_another_school_never_sees_this_ledger_and_a_bad_month_is_refused(
    scene: Scene, login: Login
) -> None:
    api = login(scene.users["secretaria"])

    other_school = api.get(_url(scene.other.school))
    bad_month = api.get(_url(scene.fresh.school, period="2025-13"))

    assert other_school.status_code == 404
    assert bad_month.status_code == 422
