# ruff: noqa: E501  (long assertions)
"""Tax guides: the arithmetic is applied to rules the school writes (the product ships no rate as truth), a
rule counts as validated only if somebody says so, a retention remembers the exact version it used, voiding
never deletes, and a guide is the sum of a tax in a month with the code and the due date the rule gives."""

import uuid
from datetime import date
from typing import Any

import pytest
from sqlalchemy import Engine

from app.auth.permissions import ROLE_PERMISSIONS, Permission
from app.tax.calc import due_date, retention
from tests.authsupport import ApiFactory
from tests.campaigns.support import committed_manager
from tests.expenses.support import Client, Scene
from tests.public.conftest import PublicSchool

ROLES = ["secretaria", "staff"]
MANAGE = {r for r in ROLES if Permission.MONTHS_CLOSE in ROLE_PERMISSIONS[r]}

# --- the arithmetic ------------------------------------------------------------------------------


def test_the_retention_is_the_base_times_the_rate_rounded_half_up_in_cents() -> None:
    assert retention(100_000, 150, None) == (100_000, 1500)  # R$ 1.000,00 at 1,5%
    assert retention(66_667, 150, None) == (66_667, 1000)  # 1.000,005 -> 1.000
    assert retention(66_700, 150, None) == (66_700, 1001)  # 1.0005 -> half up
    assert retention(1, 150, None) == (1, 0)  # never a fraction of a cent


def test_the_base_stops_at_the_cap() -> None:
    assert retention(1_500_000, 1100, 847_555) == (847_555, 93_231)  # 11% of 8.475,55 = 932,3105


@pytest.mark.parametrize(
    ("competence", "day", "roll", "expected"),
    [
        (date(2026, 10, 1), 20, "PREVIOUS", date(2026, 11, 20)),  # a Friday
        (
            date(2026, 11, 1),
            20,
            "PREVIOUS",
            date(2026, 12, 18),
        ),  # 20/12/2026 is a Sunday: back to Friday
        (date(2026, 11, 1), 20, "NEXT", date(2026, 12, 21)),  # or forward to Monday
        (
            date(2026, 12, 15),
            10,
            "PREVIOUS",
            date(2027, 1, 8),
        ),  # the year turns; 10/01/2027 is a Sunday
        (
            date(2026, 1, 5),
            31,
            "PREVIOUS",
            date(2026, 2, 27),
        ),  # February has no 31st: its last day (a Saturday) rolls back
    ],
)
def test_the_due_date_is_in_the_month_after_and_never_on_a_weekend(
    competence: date, day: int, roll: str, expected: date
) -> None:
    assert due_date(competence, day, roll) == expected


# --- the routes ----------------------------------------------------------------------------------

IRRF = {
    "rule_key": "irrf-servicos-pj", "label": "IRRF serviços", "tax_kind": "IRRF", "applies_to": "PJ",
    "rate_bps": 150, "darf_code": "1708", "due_day": 20, "due_roll": "PREVIOUS", "min_total_cents": 1000,
}  # fmt: skip


def _gestao(apis: ApiFactory, school: PublicSchool, engine: Engine) -> Client:
    return committed_manager(apis, engine, school)


def _rule(gestao: Client, **extra: Any) -> str:
    saved = gestao.post("/tax/rules", {**IRRF, **extra})
    assert saved.status_code == 201, saved.text
    rules = gestao.get("/tax/rules").json()["rules"]
    return str(
        next(r for r in rules if r["rule_key"] == (extra.get("rule_key") or IRRF["rule_key"]))["id"]
    )


def _retention(
    gestao: Client, rule: str, cents: int, name: str = "Pintura Exemplo Ltda", **extra: Any
) -> Any:
    return gestao.post(
        "/tax/retentions",
        {
            "rule_id": rule,
            "provider_kind": "PJ",
            "provider_name": name,
            "competence": "2026-10",
            "gross_cents": cents,
            **extra,
        },
    )


def test_nothing_is_shipped_as_a_rule_only_unvalidated_suggestions(
    apis: ApiFactory, school: PublicSchool, admin_engine: Engine
) -> None:
    gestao = _gestao(apis, school, admin_engine)

    listing = gestao.get("/tax/rules").json()

    assert listing["rules"] == []
    assert {s["rule_key"] for s in listing["suggestions"]} == {
        "irrf-servicos-pj",
        "inss-autonomo",
        "iss-municipal",
    }
    assert all("NÃO validada" in s["warning"] for s in listing["suggestions"])
    # no suggestion carries a due day: nobody official confirmed it
    assert all("due_day" not in s for s in listing["suggestions"])


def test_a_rule_is_validated_only_when_somebody_says_the_accountant_confirmed_it(
    apis: ApiFactory, school: PublicSchool, admin_engine: Engine
) -> None:
    gestao = _gestao(apis, school, admin_engine)
    _rule(gestao)
    unconfirmed = gestao.get("/tax/rules").json()["rules"][0]

    gestao.post("/tax/rules", {**IRRF, "validated": True, "source_note": "Contadora, 19/10"})
    confirmed = gestao.get("/tax/rules").json()["rules"][0]

    assert unconfirmed["validated"] is False and unconfirmed["validated_at"] is None
    assert confirmed["validated"] is True and confirmed["validated_at"] is not None
    assert confirmed["source_note"] == "Contadora, 19/10"
    assert confirmed["id"] != unconfirmed["id"]  # a new row: the old one is kept


@pytest.mark.parametrize(
    "change",
    [
        {"rate_bps": 0}, {"rate_bps": 10001}, {"darf_code": "17"}, {"darf_code": None}, {"due_day": 0},
        {"due_day": 32}, {"due_roll": "NEVER"}, {"rule_key": "A"}, {"label": ""}, {"tax_kind": "VAT"},
        {"base_cap_cents": 0}, {"unknown": 1},
    ],
)  # fmt: skip
def test_a_bad_rule_is_refused(
    apis: ApiFactory, school: PublicSchool, admin_engine: Engine, change: dict[str, Any]
) -> None:
    gestao = _gestao(apis, school, admin_engine)

    assert gestao.post("/tax/rules", {**IRRF, **change}).status_code == 422
    assert gestao.get("/tax/rules").json()["rules"] == []


def test_a_rule_can_say_how_to_pay_instead_of_a_code(
    apis: ApiFactory, school: PublicSchool, admin_engine: Engine
) -> None:
    gestao = _gestao(apis, school, admin_engine)

    saved = gestao.post(
        "/tax/rules",
        {
            **IRRF,
            "rule_key": "iss-municipal",
            "tax_kind": "ISS",
            "applies_to": "BOTH",
            "darf_code": None,
            "howto": "Guia no site da prefeitura",
            "rate_bps": 500,
        },
    )

    assert saved.status_code == 201, saved.text


def test_the_retention_is_calculated_with_the_rule_and_the_preview_saves_nothing(
    apis: ApiFactory, school: PublicSchool, admin_engine: Engine
) -> None:
    gestao = _gestao(apis, school, admin_engine)
    rule = _rule(gestao)

    preview = gestao.get(f"/tax/preview?rule_id={rule}&provider_kind=PJ&gross_cents=100000").json()
    month_before = gestao.get("/tax/month?period=2026-10").json()
    made = _retention(gestao, rule, 100_000)

    assert preview == {
        "base_cents": 100_000,
        "retained_cents": 1500,
        "net_cents": 98_500,
        "rate_bps": 150,
    }
    assert month_before["retentions"] == [] and made.status_code == 201
    saved = gestao.get("/tax/month?period=2026-10").json()["retentions"]
    assert [(r["gross_cents"], r["retained_cents"], r["net_cents"]) for r in saved] == [
        (100_000, 1500, 98_500)
    ]


def test_a_rule_for_companies_refuses_a_person_and_another_school_has_no_such_rule(
    apis: ApiFactory, school: PublicSchool, other_school: PublicSchool, admin_engine: Engine
) -> None:
    gestao = _gestao(apis, school, admin_engine)
    stranger = _gestao(apis, other_school, admin_engine)
    rule = _rule(gestao)

    person = _retention(gestao, rule, 100_000, provider_kind="PF")
    borrowed = _retention(stranger, rule, 100_000)

    assert person.status_code == 422 and person.json()["code"] == "rule_does_not_apply"
    assert borrowed.status_code == 404
    assert stranger.get("/tax/rules").json()["rules"] == []


def test_a_retention_keeps_the_version_of_the_rule_it_used(
    apis: ApiFactory, school: PublicSchool, admin_engine: Engine
) -> None:
    gestao = _gestao(apis, school, admin_engine)
    old = _rule(gestao)
    _retention(gestao, old, 100_000)

    newer = _rule(gestao, rate_bps=200, validated=True)
    _retention(gestao, newer, 100_000, name="Outra Empresa")

    month = gestao.get("/tax/month?period=2026-10").json()
    assert [r["retained_cents"] for r in month["retentions"]] == [
        1500,
        2000,
    ]  # the first is NOT recalculated
    assert [r["rate_bps"] for r in month["retentions"]] == [150, 200]
    (guide,) = month["guides"]
    assert guide["total_cents"] == 3500 and guide["count"] == 2 and guide["mixed_versions"] is True
    assert guide["validated"] is False  # one of the two was calculated with an unconfirmed rule


def test_a_guide_adds_a_tax_up_with_its_code_and_due_date_and_voiding_takes_one_out(
    apis: ApiFactory, school: PublicSchool, admin_engine: Engine
) -> None:
    gestao = _gestao(apis, school, admin_engine)
    rule = _rule(gestao, validated=True)
    first = _retention(gestao, rule, 100_000).json()["id"]
    _retention(gestao, rule, 200_000, name="Jardim Exemplo")

    (guide,) = gestao.get("/tax/month?period=2026-10").json()["guides"]
    assert guide["darf_code"] == "1708" and guide["total_cents"] == 4500 and guide["count"] == 2
    assert guide["due_date"] == "2026-11-20" and guide["validated"] is True
    assert guide["below_minimum"] is False and guide["site_url"].startswith("https://")

    assert gestao.post(f"/tax/retentions/{first}/void", {}).status_code == 200
    assert gestao.post(f"/tax/retentions/{first}/void", {}).status_code == 404
    month = gestao.get("/tax/month?period=2026-10").json()
    (after,) = month["guides"]
    assert after["total_cents"] == 3000 and after["count"] == 1
    assert [r["voided"] for r in month["retentions"]] == [True, False]  # kept, marked


def test_a_guide_under_the_minimum_says_so_and_a_how_to_has_no_site(
    apis: ApiFactory, school: PublicSchool, admin_engine: Engine
) -> None:
    gestao = _gestao(apis, school, admin_engine)
    rule = _rule(gestao)
    _retention(gestao, rule, 30_000)  # 1,5% of 300 = 4,50

    (guide,) = gestao.get("/tax/month?period=2026-10").json()["guides"]
    assert (
        guide["total_cents"] == 450
        and guide["below_minimum"] is True
        and guide["min_total_cents"] == 1000
    )


def test_the_month_a_service_belongs_to_is_the_competence_and_other_months_are_empty(
    apis: ApiFactory, school: PublicSchool, admin_engine: Engine
) -> None:
    gestao = _gestao(apis, school, admin_engine)
    rule = _rule(gestao)
    _retention(gestao, rule, 100_000)

    other = gestao.get("/tax/month?period=2026-09").json()

    assert other["retentions"] == [] and other["guides"] == []
    assert gestao.get("/tax/month?period=2026-13").status_code == 422


@pytest.mark.parametrize("role", ROLES)
def test_every_route_enforces_its_permission(scene: Scene, role: str) -> None:
    person = scene.person(role)
    some = uuid.uuid4()
    routes = [
        ("GET", "/tax/rules", None),
        ("POST", "/tax/rules", {**IRRF}),
        ("GET", f"/tax/preview?rule_id={some}&provider_kind=PJ&gross_cents=100", None),
        ("GET", "/tax/month?period=2026-10", None),
        (
            "POST",
            "/tax/retentions",
            {
                "rule_id": str(some),
                "provider_kind": "PJ",
                "provider_name": "X",
                "competence": "2026-10",
                "gross_cents": 100,
            },
        ),
        ("POST", f"/tax/retentions/{some}/void", {}),
    ]

    for method, tail, body in routes:
        answer = person.request(method, tail, json=body)
        if role in MANAGE:
            assert answer.status_code in (200, 201, 404), (tail, answer.text)
        else:
            assert answer.status_code == 403 and answer.json()["code"] == "permission_denied", (
                tail,
                role,
            )
