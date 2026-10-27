"""Demonstration data (0035): marked when it is made in a sandbox, hidden once in production.

docs/adr-ambiente-sandbox.md. The sandbox school makes real rows (a contribution, its Pix
charge, its ledger transaction); the database marks them `is_demo`; when the Central says
`production` the school no longer sees them (a restrictive policy, so no query has to know),
and when it says `sandbox` again they are back. A school that is not from the Central is never
marked and never hidden.
"""

import uuid
from collections.abc import Callable
from typing import Any

from sqlalchemy import Engine, text

from app.pix.provider import sandbox_provider
from tests.authsupport import ApiFactory
from tests.public.conftest import (  # noqa: F401  (a fixture of the public tests)
    PublicSchool,
    school,
)
from tests.public.support import contribute, txid_of
from tests.test_forklin_sso import (
    Central,
    cleanup,  # noqa: F401  (a fixture of the SSO tests)
    forklin,  # noqa: F401  (a fixture of the SSO tests)
)
from tests.test_sandbox_public_flow import _clean_sandbox, change, make  # noqa: F401

DEMO_TABLES = (
    "financial_transactions", "contributions", "contribution_items", "contribution_fees",
    "pix_charges", "webhook_events", "refunds", "reimbursements", "expenses", "expense_attachments",
    "monthly_closings", "campaigns", "campaign_items", "campaign_deliveries", "staff_requests",
    "staff_request_attachments", "bank_statement_imports", "bank_statement_lines",
    "bank_line_resolutions", "balancete_balances", "pdde_classifications", "pdde_documents",
    "pdde_carryovers", "tax_retentions",
)  # fmt: skip


def counts_as_the_school(
    app_engine: Engine, admin_engine: Engine, org: uuid.UUID
) -> dict[str, int]:
    """What the school itself sees (the application role, with the tenant bound)."""
    with admin_engine.connect() as conn:
        org_id, school_id = conn.execute(
            text(
                "SELECT o.id, s.id FROM organizations o JOIN schools s ON s.organization_id = o.id "
                "WHERE o.central_org_id = :c"
            ),
            {"c": org},
        ).one()
    with app_engine.begin() as conn:
        conn.execute(
            text(
                "SELECT set_config('app.organization_id', :o, true), "
                "set_config('app.school_id', :s, true)"
            ),
            {"o": str(org_id), "s": str(school_id)},
        )
        counts: dict[str, int] = {}
        for table in ("financial_transactions", "contributions", "pix_charges"):
            sql = f"SELECT count(*) FROM {table}"  # noqa: S608  (constant names)
            counts[table] = conn.execute(text(sql)).scalar_one()
        return counts


def paid_contribution(api: Any, slug: str) -> None:
    created = contribute(api, slug, 3000)
    assert created.status_code == 201
    paid = api.post(f"/api/v1/dev/sandbox/pix/{txid_of(created)}/pay", None, csrf=False)
    assert paid.json() == {"status": "PAID"}


def test_what_a_sandbox_school_makes_is_marked_hidden_in_production_and_back_in_sandbox(
    apis: ApiFactory,
    forklin: Central,  # noqa: F811
    cleanup: Callable[[uuid.UUID], None],  # noqa: F811
    admin_engine: Engine,
    app_engine: Engine,
) -> None:
    api, org, slug = make(apis, forklin, cleanup, admin_engine, "sandbox")
    paid_contribution(api, slug)

    with admin_engine.connect() as conn:
        marks = {}
        for table in ("financial_transactions", "contributions", "pix_charges"):
            sql = (
                f"SELECT bool_and(t.is_demo) FROM {table} t JOIN organizations o "  # noqa: S608
                "ON o.id = t.organization_id WHERE o.central_org_id = :c"
            )
            marks[table] = conn.execute(text(sql), {"c": org}).scalar_one()
    assert marks == {"financial_transactions": True, "contributions": True, "pix_charges": True}
    in_sandbox = counts_as_the_school(app_engine, admin_engine, org)
    assert all(count >= 1 for count in in_sandbox.values())

    change(api, forklin, org, "production")
    assert counts_as_the_school(app_engine, admin_engine, org) == {
        "financial_transactions": 0,
        "contributions": 0,
        "pix_charges": 0,
    }

    change(api, forklin, org, "sandbox")  # the operator put it back: they are visible again
    assert counts_as_the_school(app_engine, admin_engine, org) == in_sandbox


def test_a_school_that_is_not_from_the_central_is_never_marked_nor_hidden(
    apis: ApiFactory,
    school: PublicSchool,  # noqa: F811
    admin_engine: Engine,
) -> None:
    sandbox_provider().reset()
    api = apis.make()
    paid_contribution(api, school.slug)
    with admin_engine.connect() as conn:
        marked = conn.execute(
            text("SELECT count(*) FROM financial_transactions WHERE school_id = :s AND is_demo"),
            {"s": school.fresh.school},
        ).scalar_one()
    assert marked == 0


def test_every_table_of_activity_has_the_mark_the_trigger_and_the_policy(
    admin_engine: Engine,
) -> None:
    with admin_engine.connect() as conn:
        columns = {
            r[0]
            for r in conn.execute(
                text(
                    "SELECT table_name FROM information_schema.columns "
                    "WHERE table_schema = 'public' AND column_name = 'is_demo' "
                    "AND is_nullable = 'NO' AND column_default = 'false'"
                )
            )
        }
        triggers = {
            r[0]
            for r in conn.execute(
                text(
                    "SELECT c.relname FROM pg_trigger t JOIN pg_class c ON c.oid = t.tgrelid "
                    "WHERE t.tgname = c.relname || '_10_is_demo' AND NOT t.tgisinternal"
                )
            )
        }
        policies = {
            r[0]
            for r in conn.execute(
                text(
                    "SELECT tablename FROM pg_policies "
                    "WHERE policyname = tablename || '_hide_demo' "
                    "AND permissive = 'RESTRICTIVE' AND cmd = 'SELECT'"
                )
            )
        }
    assert columns == triggers == policies == set(DEMO_TABLES)


def test_the_business_keys_only_bind_the_real_rows(admin_engine: Engine) -> None:
    with admin_engine.connect() as conn:
        definitions = dict(
            conn.execute(
                text(
                    "SELECT indexname, indexdef FROM pg_indexes WHERE indexname IN ("
                    "'uq_financial_transactions_school_id_reference_code', "
                    "'uq_monthly_closings_active_period', "
                    "'uq_bank_statement_imports_school_id_file_sha256', "
                    "'uq_bank_statement_lines_school_id_bank_account_id_bank_ref', "
                    "'uq_pdde_documents_school_id_access_key')"
                )
            ).all()
        )
    assert len(definitions) == 5
    assert all("NOT is_demo" in definition for definition in definitions.values())


def test_with_no_tenant_nothing_is_hidden(app_engine: Engine) -> None:
    with app_engine.connect() as conn:
        assert conn.execute(text("SELECT public.hides_demo()")).scalar_one() is False


# --- the school comes with made-up data (app/demo.py) ---------------------------------------------


def sign_in_secretaria(api: Any, fake: Central, org: uuid.UUID, environment: str) -> Any:
    from tests.test_forklin_sso import land

    code = fake.code_for(fake.token(org=str(org), org_env=environment))
    return land(api, code)


def test_the_first_secretaria_of_a_sandbox_school_finds_it_with_made_up_data(
    apis: ApiFactory,
    forklin: Central,  # noqa: F811
    cleanup: Callable[[uuid.UUID], None],  # noqa: F811
    admin_engine: Engine,
    app_engine: Engine,
) -> None:
    api, org, _slug = make(apis, forklin, cleanup, admin_engine, "sandbox")
    assert counts_as_the_school(app_engine, admin_engine, org)["financial_transactions"] == 0

    assert sign_in_secretaria(api, forklin, org, "sandbox").headers["location"] == "/painel"

    seen = counts_as_the_school(app_engine, admin_engine, org)
    assert seen["financial_transactions"] > 40 and seen["contributions"] > 30
    with admin_engine.connect() as conn:
        not_marked = conn.execute(
            text(
                "SELECT count(*) FROM financial_transactions t JOIN organizations o "
                "ON o.id = t.organization_id WHERE o.central_org_id = :c AND NOT t.is_demo"
            ),
            {"c": org},
        ).scalar_one()
    assert not_marked == 0  # every row of the made-up data is demonstration

    # A second sign-in does not fill it twice.
    sign_in_secretaria(sso_second(apis), forklin, org, "sandbox")
    assert counts_as_the_school(app_engine, admin_engine, org) == seen

    # In production the school sees none of it.
    change(api, forklin, org, "production")
    assert counts_as_the_school(app_engine, admin_engine, org)["financial_transactions"] == 0


def sso_second(apis: ApiFactory) -> Any:
    from tests.test_sandbox_public_flow import production_api

    return production_api(apis)


def test_a_production_school_is_not_filled(
    apis: ApiFactory,
    forklin: Central,  # noqa: F811
    cleanup: Callable[[uuid.UUID], None],  # noqa: F811
    admin_engine: Engine,
    app_engine: Engine,
) -> None:
    api, org, _slug = make(apis, forklin, cleanup, admin_engine, "production")
    assert sign_in_secretaria(api, forklin, org, "production").headers["location"] == "/painel"
    with admin_engine.connect() as conn:
        total = conn.execute(
            text(
                "SELECT count(*) FROM financial_transactions t JOIN organizations o "
                "ON o.id = t.organization_id WHERE o.central_org_id = :c"
            ),
            {"c": org},
        ).scalar_one()
    assert total == 0


def test_a_school_that_already_has_movement_is_never_filled(
    apis: ApiFactory,
    forklin: Central,  # noqa: F811
    cleanup: Callable[[uuid.UUID], None],  # noqa: F811
    admin_engine: Engine,
    app_engine: Engine,
) -> None:
    api, org, slug = make(apis, forklin, cleanup, admin_engine, "sandbox")
    paid_contribution(api, slug)  # one movement of the family page, before anybody signed in
    before = counts_as_the_school(app_engine, admin_engine, org)
    sign_in_secretaria(api, forklin, org, "sandbox")
    assert counts_as_the_school(app_engine, admin_engine, org) == before
