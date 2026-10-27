"""The environment (sandbox or production) the Central names for an organization (0033).

docs/adr-ambiente-sandbox.md. The product only RECORDS what the Central says (in the notice of the
contract, in the change event and in every access token); what depends on it is behind
`FORKLIN_ENVIRONMENT_ENABLED`. Like the SSO tests: real EdDSA tokens, real database, fake network.
"""

import uuid
from collections.abc import Callable
from typing import Any

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.exc import DBAPIError

from app.forklin import central
from tests.authsupport import ApiFactory
from tests.test_forklin_sso import (
    EVENTS,
    Central,
    cleanup,  # noqa: F401  (a fixture of the SSO tests)
    forklin,  # noqa: F401  (a fixture of the SSO tests)
    land,
    sso_api,
)


def environment_of(engine: Engine, central_org: uuid.UUID) -> str | None:
    with engine.connect() as connection:
        return connection.execute(
            text("SELECT environment FROM organizations WHERE central_org_id = :c"),
            {"c": central_org},
        ).scalar_one_or_none()


def changed(fake: Central, org: uuid.UUID, environment: Any) -> str:
    return fake.event(
        org, name=None, event=central.EVENT_ENVIRONMENT_CHANGED, environment=environment
    )


def test_a_new_organization_without_a_word_from_the_central_is_a_sandbox(
    apis: ApiFactory,
    forklin: Central,  # noqa: F811
    cleanup: Callable[[uuid.UUID], None],  # noqa: F811
    admin_engine: Engine,
) -> None:
    org = uuid.uuid4()
    cleanup(org)
    api = sso_api(apis)
    assert (
        api.post(EVENTS, {"token": forklin.event(org)}, origin=False, csrf=False).status_code == 200
    )
    assert environment_of(admin_engine, org) == "sandbox"


def test_the_notice_of_the_contract_carries_the_environment(
    apis: ApiFactory,
    forklin: Central,  # noqa: F811
    cleanup: Callable[[uuid.UUID], None],  # noqa: F811
    admin_engine: Engine,
) -> None:
    org = uuid.uuid4()
    cleanup(org)
    api = sso_api(apis)
    notice = forklin.event(org, environment="production")
    assert api.post(EVENTS, {"token": notice}, origin=False, csrf=False).json() == {
        "status": "created"
    }
    assert environment_of(admin_engine, org) == "production"


def test_a_value_that_is_not_one_of_the_two_is_ignored_in_the_notice(
    apis: ApiFactory,
    forklin: Central,  # noqa: F811
    cleanup: Callable[[uuid.UUID], None],  # noqa: F811
    admin_engine: Engine,
) -> None:
    org = uuid.uuid4()
    cleanup(org)
    api = sso_api(apis)
    notice = forklin.event(org, environment="staging")
    assert api.post(EVENTS, {"token": notice}, origin=False, csrf=False).status_code == 200
    assert environment_of(admin_engine, org) == "sandbox"


def test_the_change_event_moves_the_organization_and_repeating_it_is_harmless(
    apis: ApiFactory,
    forklin: Central,  # noqa: F811
    cleanup: Callable[[uuid.UUID], None],  # noqa: F811
    admin_engine: Engine,
) -> None:
    org = uuid.uuid4()
    cleanup(org)
    api = sso_api(apis)
    api.post(EVENTS, {"token": forklin.event(org)}, origin=False, csrf=False)

    for _ in range(2):
        response = api.post(
            EVENTS, {"token": changed(forklin, org, "production")}, origin=False, csrf=False
        )
        assert response.status_code == 200 and response.json() == {"status": "processed"}
        assert environment_of(admin_engine, org) == "production"

    # The operator of the Central may put it back; the product follows what it is told.
    api.post(EVENTS, {"token": changed(forklin, org, "sandbox")}, origin=False, csrf=False)
    assert environment_of(admin_engine, org) == "sandbox"


def test_a_change_for_an_unknown_organization_creates_nothing_and_answers_like_a_hit(
    apis: ApiFactory,
    forklin: Central,  # noqa: F811
    admin_engine: Engine,
) -> None:
    org = uuid.uuid4()
    api = sso_api(apis)
    response = api.post(
        EVENTS, {"token": changed(forklin, org, "production")}, origin=False, csrf=False
    )
    assert response.status_code == 200 and response.json() == {"status": "processed"}
    assert environment_of(admin_engine, org) is None


@pytest.mark.parametrize("value", [None, "staging", "", 7])
def test_a_change_event_without_a_known_environment_is_refused(
    apis: ApiFactory,
    forklin: Central,  # noqa: F811
    value: Any,
) -> None:
    api = sso_api(apis)
    response = api.post(
        EVENTS, {"token": changed(forklin, uuid.uuid4(), value)}, origin=False, csrf=False
    )
    assert response.status_code == 400 and response.json()["code"] == "invalid_event"


def test_the_token_of_a_sign_in_catches_the_environment_up(
    apis: ApiFactory,
    forklin: Central,  # noqa: F811
    cleanup: Callable[[uuid.UUID], None],  # noqa: F811
    admin_engine: Engine,
) -> None:
    org = uuid.uuid4()
    cleanup(org)
    api = sso_api(apis)
    code = forklin.code_for(forklin.token(org=str(org), org_env="production"))
    assert land(api, code).headers["location"] == "/painel"
    assert environment_of(admin_engine, org) == "production"

    again = sso_api(apis)
    later = forklin.code_for(forklin.token(org=str(org), org_env="sandbox"))
    assert land(again, later).headers["location"] == "/painel"
    assert environment_of(admin_engine, org) == "sandbox"


def test_a_token_without_the_claim_leaves_the_environment_alone(
    apis: ApiFactory,
    forklin: Central,  # noqa: F811
    cleanup: Callable[[uuid.UUID], None],  # noqa: F811
    admin_engine: Engine,
) -> None:
    org = uuid.uuid4()
    cleanup(org)
    api = sso_api(apis)
    api.post(
        EVENTS, {"token": forklin.event(org, environment="production")}, origin=False, csrf=False
    )
    code = forklin.code_for(forklin.token(org=str(org)))
    assert land(sso_api(apis), code).headers["location"] == "/painel"
    assert environment_of(admin_engine, org) == "production"


def test_the_endpoint_answers_null_while_the_switch_is_off_and_the_value_when_on(
    apis: ApiFactory,
    forklin: Central,  # noqa: F811
    cleanup: Callable[[uuid.UUID], None],  # noqa: F811
) -> None:
    org = uuid.uuid4()
    cleanup(org)
    off = sso_api(apis)
    code = forklin.code_for(forklin.token(org=str(org), org_env="sandbox"))
    assert land(off, code).headers["location"] == "/painel"
    assert off.get("/api/v1/environment").json() == {"environment": None}

    on = sso_api(apis, forklin_environment_enabled=True)
    code = forklin.code_for(forklin.token(org=str(org), org_env="sandbox"))
    assert land(on, code).headers["location"] == "/painel"
    assert on.get("/api/v1/environment").json() == {"environment": "sandbox"}

    on.post(EVENTS, {"token": changed(forklin, org, "production")}, origin=False, csrf=False)
    assert on.get("/api/v1/environment").json() == {"environment": "production"}


def test_the_endpoint_needs_a_session(apis: ApiFactory) -> None:
    assert (
        sso_api(apis, forklin_environment_enabled=True).get("/api/v1/environment").status_code
        == 401
    )


def test_the_application_role_cannot_change_the_environment_nor_the_link_to_the_central(
    app_engine: Engine,
    admin_engine: Engine,
) -> None:
    with admin_engine.connect() as connection:
        grants = {
            column: connection.execute(
                text("SELECT has_column_privilege('apm_app', 'organizations', :c, 'UPDATE')"),
                {"c": column},
            ).scalar_one()
            for column in ("environment", "central_org_id", "slug", "name", "updated_at")
        }
    assert grants == {
        "environment": False,
        "central_org_id": False,
        "slug": False,
        "name": True,
        "updated_at": True,
    }
    with app_engine.connect() as connection, pytest.raises(DBAPIError):
        connection.execute(text("UPDATE organizations SET environment = 'production'"))


def test_the_function_refuses_what_is_not_one_of_the_two_values(
    app_engine: Engine,
) -> None:
    with app_engine.connect() as connection:
        for value in ("staging", "", "PRODUCTION"):
            assert (
                connection.execute(
                    text("SELECT public.set_forklin_environment(gen_random_uuid(), :v)"),
                    {"v": value},
                ).scalar_one()
                is False
            )
        assert (
            connection.execute(
                text("SELECT public.set_forklin_environment(NULL, 'production')")
            ).scalar_one()
            is False
        )
