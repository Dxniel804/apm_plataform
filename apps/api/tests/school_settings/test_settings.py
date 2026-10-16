# ruff: noqa: E501  (SQL and long assertions)
"""The settings of a school and its public link (migration 0015): what the management edits, who may,
what the families then see, and the printable poster."""

from io import BytesIO
from typing import Any

import pytest
from pypdf import PdfReader
from sqlalchemy import Engine, text

from app.auth.permissions import ROLE_PERMISSIONS, Permission
from tests.expenses.support import Scene

ROLES = ["secretaria", "staff"]
MANAGE = {role for role in ROLES if Permission.SCHOOL_SETTINGS_MANAGE in ROLE_PERMISSIONS[role]}


def test_the_set_of_roles_is_what_the_permission_map_says() -> None:
    assert {"secretaria"} == MANAGE


def test_the_settings_come_with_their_defaults(scene: Scene) -> None:
    gestao = scene.person("secretaria")

    body = gestao.get("/settings").json()

    assert body["suggested_amounts_cents"] == [2000, 3000, 4000]
    assert body["allow_custom_amount"] is True
    assert body["min_contribution_cents"] == 1000 and body["max_contribution_cents"] == 500000
    assert (
        body["free_amount_text"] is None
        and body["monthly_goal_cents"] is None
        and body["expected_contributions"] is None
    )


def test_the_management_changes_the_amounts_the_text_and_the_goals(scene: Scene) -> None:
    gestao = scene.person("secretaria")

    changed = gestao.patch(
        "/settings",
        {
            "suggested_amounts_cents": [5000, 1500, 3000],
            "allow_custom_amount": False,
            "free_amount_text": "  Qualquer valor ajuda a nossa festa.  ",
            "monthly_goal_cents": 1_500_000,
            "expected_contributions": 120,
        },
    )

    assert changed.status_code == 200, changed.text
    body = changed.json()
    assert body["suggested_amounts_cents"] == [1500, 3000, 5000]  # in order, whatever was sent
    assert body["allow_custom_amount"] is False
    assert body["free_amount_text"] == "Qualquer valor ajuda a nossa festa."  # trimmed
    assert body["monthly_goal_cents"] == 1_500_000 and body["expected_contributions"] == 120
    assert gestao.get("/settings").json() == body  # and it stayed


def test_only_what_is_sent_changes_and_null_clears_the_optional_fields(scene: Scene) -> None:
    gestao = scene.person("secretaria")
    gestao.patch(
        "/settings",
        {
            "free_amount_text": "Obrigado!",
            "monthly_goal_cents": 100000,
            "expected_contributions": 10,
        },
    )

    only_goal = gestao.patch("/settings", {"monthly_goal_cents": 200000}).json()
    cleared = gestao.patch(
        "/settings",
        {"free_amount_text": None, "monthly_goal_cents": None, "expected_contributions": None},
    ).json()

    assert (
        only_goal["free_amount_text"] == "Obrigado!" and only_goal["expected_contributions"] == 10
    )
    assert only_goal["suggested_amounts_cents"] == [2000, 3000, 4000]
    assert (
        cleared["free_amount_text"] is None
        and cleared["monthly_goal_cents"] is None
        and cleared["expected_contributions"] is None
    )


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"suggested_amounts_cents": []},
        {"suggested_amounts_cents": [1000, 2000, 3000, 4000, 5000, 6000, 7000]},  # at most six
        {"suggested_amounts_cents": [500]},  # below the minimum of the school
        {"suggested_amounts_cents": [600000]},  # above the maximum of the school
        {"suggested_amounts_cents": [2000, 2000]},  # repeated
        {"suggested_amounts_cents": None},
        {"allow_custom_amount": None},
        {"free_amount_text": ""},
        {"free_amount_text": "x" * 301},
        {"free_amount_text": "a\x00b"},
        {"monthly_goal_cents": 99},
        {"monthly_goal_cents": "muito"},
        {"expected_contributions": 0},
        {"expected_contributions": 100001},
        # nothing about who or what else is open to change
        {"timezone": "America/Manaus"},
        {"min_contribution_cents": 100},
        {"approval_limit_cents": 100},
        {"school_id": "00000000-0000-4000-8000-000000000001"},
    ],
)
def test_a_bad_change_is_a_422_and_changes_nothing(scene: Scene, body: dict[str, Any]) -> None:
    gestao = scene.person("secretaria")
    before = gestao.get("/settings").json()

    response = gestao.patch("/settings", body)

    assert response.status_code == 422, response.text
    assert response.json()["code"] == "validation_error"
    assert gestao.get("/settings").json() == before


def test_the_family_sees_the_new_amounts_the_text_and_the_months(
    apis: Any, school: Any, admin_engine: Engine
) -> None:
    from tests.campaigns.support import committed_manager

    gestao = committed_manager(apis, admin_engine, school)
    gestao.patch(
        "/settings",
        {"suggested_amounts_cents": [2500, 4500], "free_amount_text": "Ajude como puder."},
    )

    page = apis.make().get(f"/api/v1/public/schools/{school.slug}").json()

    assert page["suggested_amounts_cents"] == [2500, 4500]
    assert page["free_amount_text"] == "Ajude como puder."
    assert len(page["reference_months"]) == 12  # this month and the eleven before it, oldest first
    assert page["reference_months"] == sorted(page["reference_months"])


@pytest.mark.parametrize("role", ROLES)
def test_every_route_enforces_its_permission(scene: Scene, role: str) -> None:
    person = scene.person(role)
    routes = [
        ("GET", "/settings", None),
        ("PATCH", "/settings", {"monthly_goal_cents": 100000}),
        ("GET", "/public-link", None),
        ("GET", "/public-link/poster.pdf", None),
    ]

    for method, tail, body in routes:
        answer = person.request(method, tail, json=body)
        if role in MANAGE:
            assert answer.status_code == 200, (method, tail, answer.text)
        else:
            assert answer.status_code == 403, (method, tail, role)
            assert answer.json()["code"] == "permission_denied"


def test_another_school_cannot_be_reached(scene: Scene) -> None:
    gestao = scene.person("secretaria")
    other = scene.person("secretaria", org="b")

    for method, tail, body in (
        ("GET", "/settings", None),
        ("PATCH", "/settings", {"monthly_goal_cents": 100000}),
        ("GET", "/public-link", None),
        ("GET", "/public-link/poster.pdf", None),
    ):
        answer = gestao.request(method, tail, json=body, school=other.school)
        assert answer.status_code == 404 and answer.json()["code"] == "not_found", (method, tail)
    assert other.get("/settings").json()["monthly_goal_cents"] is None  # untouched


def test_a_change_is_audited_without_the_free_text(scene: Scene, admin_engine: Engine) -> None:
    gestao = scene.person("secretaria")
    gestao.patch(
        "/settings", {"free_amount_text": "texto livre da escola", "monthly_goal_cents": 123400}
    )

    with admin_engine.connect() as conn:
        after: dict[str, Any] = conn.execute(
            text(
                "SELECT after_data FROM audit_logs WHERE school_id = :s AND action = 'school_settings.update' ORDER BY occurred_at DESC LIMIT 1"
            ),
            {"s": gestao.school},
        ).scalar_one()

    assert after["monthly_goal_cents"] == 123400
    assert after["free_amount_text_present"] is True
    assert "texto livre da escola" not in str(after)  # the sentence is never copied into the trail


# --- the public link and the poster -----------------------------------------------------------------


def test_the_public_link_is_the_base_address_and_the_slug(
    scene: Scene, admin_engine: Engine
) -> None:
    gestao = scene.person("secretaria")
    with admin_engine.connect() as conn:
        slug, name = conn.execute(
            text("SELECT slug, name FROM schools WHERE id = :s"), {"s": gestao.school}
        ).one()

    link = gestao.get("/public-link").json()

    assert link["slug"] == slug and link["school_name"] == name
    assert link["url"].endswith(f"/escola/{slug}") and link["url"].startswith("http")
    assert "//escola" not in link["url"]  # no doubled slash from a trailing one in the base address


def test_the_poster_is_an_a4_pdf_with_the_name_and_the_address(scene: Scene) -> None:
    gestao = scene.person("secretaria")
    link = gestao.get("/public-link").json()

    response = gestao.get("/public-link/poster.pdf")

    assert response.status_code == 200 and response.headers["content-type"] == "application/pdf"
    assert response.content.startswith(b"%PDF-")
    assert response.headers["cache-control"] == "private, no-store"
    assert f"cartaz-{link['slug']}.pdf" in response.headers["content-disposition"]
    pages = PdfReader(BytesIO(response.content)).pages
    assert len(pages) == 1
    written = pages[0].extract_text()
    assert link["school_name"] in written
    assert link["url"].removeprefix("http://").removeprefix("https://") in written
    assert (
        gestao.get("/public-link/poster.pdf").content == response.content
    )  # the same link, the same bytes


def test_the_application_changes_the_slug_only_through_the_rules_of_the_database(
    admin_engine: Engine,
) -> None:
    """The slug is in every printed QR code: the application may change it (migration 0024), but the
    rules (two free changes, then 15 days, every old address kept) are a trigger, and the counters
    are not writable by the application (tests/school_settings/test_identity.py)."""
    with admin_engine.connect() as conn:
        can_slug: bool = conn.execute(
            text("SELECT has_column_privilege('apm_app', 'schools', 'slug', 'UPDATE')")
        ).scalar_one()
        can_org: bool = conn.execute(
            text("SELECT has_column_privilege('apm_app', 'schools', 'organization_id', 'UPDATE')")
        ).scalar_one()
        can_row: bool = conn.execute(
            text("SELECT has_table_privilege('apm_app', 'schools', 'UPDATE')")
        ).scalar_one()
    assert can_slug is True and can_org is False and can_row is False
