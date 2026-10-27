"""The link of the families works for a SANDBOX organization, in production too (0034).

docs/adr-ambiente-sandbox.md. There is no gateway: the fake bank is the only bank. In
production it is served only to an organization the Central put in `sandbox`; every other
organization keeps getting "payment unavailable", and the "pay" route of the fake bank answers
404 for it. The API here is built in `production` mode (the same settings object the real one
has) with the switch on, unless a test says otherwise.
"""

import uuid
from collections.abc import Callable
from typing import Any

import pytest
from sqlalchemy import Engine, text

from app.core.errors import ProblemError
from app.forklin import central
from app.pix.provider import SANDBOX, get_provider, sandbox_provider
from tests.authsupport import Api, ApiFactory
from tests.public.support import charge_url, contribute, txid_of
from tests.test_forklin_sso import (
    EVENTS,
    Central,
    cleanup,  # noqa: F401  (a fixture of the SSO tests)
    forklin,  # noqa: F401  (a fixture of the SSO tests)
    sso_api,
)


@pytest.fixture(autouse=True)
def _clean_sandbox() -> Any:
    sandbox_provider().reset()
    yield
    sandbox_provider().reset()


def production_api(apis: ApiFactory, **overrides: Any) -> Api:
    values = {"env": "production", "forklin_environment_enabled": True, **overrides}
    return sso_api(apis, **values)


def change(api: Api, fake: Central, org: uuid.UUID, environment: str) -> None:
    token = fake.event(
        org, name=None, event=central.EVENT_ENVIRONMENT_CHANGED, environment=environment
    )
    assert api.post(EVENTS, {"token": token}, origin=False, csrf=False).status_code == 200


def school_slug(engine: Engine, org: uuid.UUID) -> str:
    with engine.connect() as conn:
        return conn.execute(
            text(
                "SELECT s.slug FROM schools s JOIN organizations o ON o.id = s.organization_id "
                "WHERE o.central_org_id = :c"
            ),
            {"c": org},
        ).scalar_one()


def account_status(engine: Engine, org: uuid.UUID) -> str | None:
    with engine.connect() as conn:
        return conn.execute(
            text(
                "SELECT a.status FROM payment_accounts a JOIN organizations o "
                "ON o.id = a.organization_id WHERE o.central_org_id = :c AND a.provider = 'SANDBOX'"
            ),
            {"c": org},
        ).scalar_one_or_none()


def make(
    apis: ApiFactory,
    fake: Central,
    cleanup_: Callable[[uuid.UUID], None],
    engine: Engine,
    environment: str,
    **overrides: Any,
) -> tuple[Api, uuid.UUID, str]:
    org = uuid.uuid4()
    cleanup_(org)
    api = production_api(apis, **overrides)
    token = fake.event(org, name="Escola Demo", environment=environment)
    assert api.post(EVENTS, {"token": token}, origin=False, csrf=False).status_code == 200
    return api, org, school_slug(engine, org)


# --- the provider ---------------------------------------------------------------------------------


def test_the_fake_bank_is_served_in_production_only_to_a_sandbox_organization() -> None:
    with pytest.raises(ProblemError) as refused:
        get_provider(SANDBOX, "production")
    assert refused.value.status == 501
    assert get_provider(SANDBOX, "production", sandbox_org=True) is sandbox_provider()
    assert get_provider(SANDBOX, "development") is sandbox_provider()  # as always, locally


# --- the link opens and the payment goes through, all of it fake ----------------------------------


def test_a_sandbox_school_gets_the_simulated_account_and_its_link_opens(
    apis: ApiFactory,
    forklin: Central,  # noqa: F811
    cleanup: Callable[[uuid.UUID], None],  # noqa: F811
    admin_engine: Engine,
) -> None:
    api, org, slug = make(apis, forklin, cleanup, admin_engine, "sandbox")
    assert account_status(admin_engine, org) == "ACTIVE"
    page = api.get(f"/api/v1/public/schools/{slug}")
    assert page.status_code == 200 and page.json()["environment"] == "sandbox"


def test_the_family_pays_a_fake_pix_in_production_mode_and_the_school_books_it(
    apis: ApiFactory,
    forklin: Central,  # noqa: F811
    cleanup: Callable[[uuid.UUID], None],  # noqa: F811
    admin_engine: Engine,
) -> None:
    api, org, slug = make(apis, forklin, cleanup, admin_engine, "sandbox")
    created = contribute(api, slug, 3000)
    assert created.status_code == 201
    assert created.json()["charge"]["emv_payload"].startswith("PIX-SANDBOX:")
    token = created.json()["token"]

    paid = api.post(f"/api/v1/dev/sandbox/pix/{txid_of(created)}/pay", None, csrf=False)
    assert paid.status_code == 200 and paid.json() == {"status": "PAID"}
    state = api.get(charge_url(slug, token))
    assert state.status_code == 200 and state.json()["status"] == "PAID"


# --- everything else stays closed ---------------------------------------------------------


def test_a_production_school_has_no_account_no_page_and_no_fake_bank(
    apis: ApiFactory,
    forklin: Central,  # noqa: F811
    cleanup: Callable[[uuid.UUID], None],  # noqa: F811
    admin_engine: Engine,
) -> None:
    api, org, slug = make(apis, forklin, cleanup, admin_engine, "production")
    assert account_status(admin_engine, org) is None
    assert api.get(f"/api/v1/public/schools/{slug}").status_code == 404


def test_going_to_production_turns_the_simulated_account_off_and_the_fake_bank_stops(
    apis: ApiFactory,
    forklin: Central,  # noqa: F811
    cleanup: Callable[[uuid.UUID], None],  # noqa: F811
    admin_engine: Engine,
) -> None:
    api, org, slug = make(apis, forklin, cleanup, admin_engine, "sandbox")
    created = contribute(api, slug, 3000)
    assert created.status_code == 201
    txid = txid_of(created)

    change(api, forklin, org, "production")

    assert account_status(admin_engine, org) == "INACTIVE"
    assert api.get(f"/api/v1/public/schools/{slug}").status_code == 404
    # The charge made while it was a sandbox cannot be paid any more: the route is a 404 for it.
    assert api.post(f"/api/v1/dev/sandbox/pix/{txid}/pay", None, csrf=False).status_code == 404

    change(api, forklin, org, "sandbox")  # the operator put it back
    assert account_status(admin_engine, org) == "ACTIVE"
    assert api.get(f"/api/v1/public/schools/{slug}").status_code == 200


def test_the_fake_bank_does_not_pay_a_charge_this_process_does_not_know(
    apis: ApiFactory,
    forklin: Central,  # noqa: F811
    cleanup: Callable[[uuid.UUID], None],  # noqa: F811
    admin_engine: Engine,
) -> None:
    api, _org, _slug = make(apis, forklin, cleanup, admin_engine, "sandbox")
    unknown = "a" * 32
    assert api.post(f"/api/v1/dev/sandbox/pix/{unknown}/pay", None, csrf=False).status_code == 404


def test_with_the_switch_off_production_behaves_as_before(
    apis: ApiFactory,
    forklin: Central,  # noqa: F811
    cleanup: Callable[[uuid.UUID], None],  # noqa: F811
    admin_engine: Engine,
) -> None:
    api, org, slug = make(
        apis, forklin, cleanup, admin_engine, "sandbox", forklin_environment_enabled=False
    )
    assert account_status(admin_engine, org) is None
    assert api.get(f"/api/v1/public/schools/{slug}").status_code == 404
    assert api.post(f"/api/v1/dev/sandbox/pix/{'b' * 32}/pay", None, csrf=False).status_code == 404


def test_the_page_says_nothing_about_the_environment_while_the_switch_is_off(
    apis: ApiFactory,
    forklin: Central,  # noqa: F811
    cleanup: Callable[[uuid.UUID], None],  # noqa: F811
    admin_engine: Engine,
) -> None:
    org = uuid.uuid4()
    cleanup(org)
    on = production_api(apis)
    token = forklin.event(org, name="Escola Demo", environment="sandbox")
    on.post(EVENTS, {"token": token}, origin=False, csrf=False)
    slug = school_slug(admin_engine, org)
    off = sso_api(apis, env="production", forklin_environment_enabled=False)
    # The account exists (made while the switch was on) so the page opens, but it stays silent.
    body = off.get(f"/api/v1/public/schools/{slug}").json()
    assert body["environment"] is None
