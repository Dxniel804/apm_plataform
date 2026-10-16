"""Sign-in through the Forklin Central and the notice of a new organization.

docs/adr-forklin-sso.md. The network is the only thing that is faked: the tokens are real EdDSA JWTs
signed with a test key and verified by the real code (algorithm, audience, issuer, lifetime,
claims), and the database is the real one.
"""

import time
import urllib.parse
import uuid
from collections.abc import Callable, Iterator
from typing import Any

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text

from app.forklin import central
from app.forklin.central import CentralError
from tests.authsupport import PASSWORD, Api, ApiFactory, UserFactory, World
from tests.dbsupport import purge_financial

CALLBACK = "/api/v1/forklin/sso/callback"
START = "/api/v1/forklin/sso/start"
EVENTS = "/api/v1/forklin/events"
SLUG = "apm-digital"
FORKLIN: dict[str, Any] = {
    "forklin_core_enabled": True,
    "api_central_url": "http://central.test",
    "forklin_app_url": "http://app.test",
    "forklin_product_secret": "a-product-secret-for-the-tests",
}


class Central:
    """Stands in for the Central: signs tokens and answers the exchange of a code."""

    def __init__(self) -> None:
        self.key = Ed25519PrivateKey.generate()
        self.other_key = Ed25519PrivateKey.generate()
        self.codes: dict[str, str | CentralError] = {}
        self.exchanged: list[str] = []

    def token(
        self,
        *,
        key: Ed25519PrivateKey | None = None,
        algorithm: str = "EdDSA",
        **overrides: Any,
    ) -> str:
        now = int(time.time())
        claims: dict[str, Any] = {
            "iss": "forklin",
            "aud": SLUG,
            "sub": str(uuid.uuid4()),
            "org": str(uuid.uuid4()),
            "role": "secretaria",
            "email": f"sso-{uuid.uuid4().hex[:8]}@example.test",
            "name": "Ana da Central",
            "iat": now,
            "exp": now + 600,
            "jti": uuid.uuid4().hex,
            **overrides,
        }
        claims = {k: v for k, v in claims.items() if v is not None}
        if algorithm == "none":
            return jwt.encode(claims, None, algorithm="none")  # type: ignore[arg-type]
        return jwt.encode(claims, key or self.key, algorithm=algorithm)

    def code_for(self, token: str | CentralError) -> str:
        code = uuid.uuid4().hex
        self.codes[code] = token
        return code

    def event(self, org: uuid.UUID, *, name: str | None = "Escola Nova", **overrides: Any) -> str:
        now = int(time.time())
        claims: dict[str, Any] = {
            "iss": "forklin",
            "aud": SLUG,
            "iat": now,
            "exp": now + 120,
            "jti": uuid.uuid4().hex,
            "event": central.EVENT_PRODUCT_CONTRACTED,
            "organization_id": str(org),
            "organization_name": name,
            **overrides,
        }
        claims = {k: v for k, v in claims.items() if v is not None}
        return jwt.encode(claims, self.key, algorithm="EdDSA")


@pytest.fixture
def forklin(monkeypatch: pytest.MonkeyPatch) -> Central:
    fake = Central()

    def exchange(_settings: Any, code: str) -> str:
        fake.exchanged.append(code)
        answer = fake.codes.get(code, CentralError("expirado", "unknown code"))
        if isinstance(answer, CentralError):
            raise answer
        return answer

    monkeypatch.setattr(central, "exchange_code", exchange)
    monkeypatch.setattr(central, "_signing_key", lambda _s, _t: fake.key.public_key())
    return fake


@pytest.fixture
def cleanup(admin_engine: Engine) -> Iterator[Callable[[uuid.UUID], None]]:
    """Whatever a test made for an organization of the Central is removed afterwards."""
    made: list[uuid.UUID] = []
    yield made.append
    with admin_engine.begin() as connection:
        rows = connection.execute(
            text("SELECT id FROM organizations WHERE central_org_id = ANY(:c)"), {"c": made}
        ).all()
        orgs = [row[0] for row in rows]
        purge_financial(connection, orgs)
        user_ids = [
            row[0]
            for row in connection.execute(
                text(
                    "SELECT DISTINCT user_id FROM memberships WHERE organization_id = ANY(:o) "
                    "UNION SELECT id FROM users WHERE central_user_id IS NOT NULL "
                    "AND email LIKE 'sso-%@example.test'"
                ),
                {"o": orgs},
            )
        ]
        connection.execute(text("DELETE FROM sessions WHERE user_id = ANY(:u)"), {"u": user_ids})
        connection.execute(
            text("DELETE FROM memberships WHERE organization_id = ANY(:o)"), {"o": orgs}
        )
        connection.execute(text("DELETE FROM users WHERE id = ANY(:u)"), {"u": user_ids})
        connection.execute(text("DELETE FROM schools WHERE organization_id = ANY(:o)"), {"o": orgs})
        connection.execute(text("DELETE FROM organizations WHERE id = ANY(:o)"), {"o": orgs})


def sso_api(apis: ApiFactory, **overrides: Any) -> Api:
    return apis.make(**{**FORKLIN, **overrides})


def counts(engine: Engine, central_org: uuid.UUID) -> dict[str, int]:
    with engine.connect() as connection:
        row = connection.execute(
            text(
                "SELECT (SELECT count(*) FROM organizations WHERE central_org_id = :c), "
                "(SELECT count(*) FROM schools s JOIN organizations o ON o.id = s.organization_id "
                " WHERE o.central_org_id = :c), "
                "(SELECT count(*) FROM school_settings t JOIN organizations o "
                " ON o.id = t.organization_id WHERE o.central_org_id = :c), "
                "(SELECT count(*) FROM categories t JOIN organizations o "
                " ON o.id = t.organization_id WHERE o.central_org_id = :c), "
                "(SELECT count(*) FROM memberships t JOIN organizations o "
                " ON o.id = t.organization_id WHERE o.central_org_id = :c)"
            ),
            {"c": central_org},
        ).one()
    return dict(zip(("orgs", "schools", "settings", "categories", "memberships"), row, strict=True))


def land(api: Api, code: str | None, **params: str) -> Any:
    query = {**({"code": code} if code else {}), **params}
    return api.client.get(CALLBACK, params=query, follow_redirects=False)


def error_of(response: Any) -> str:
    assert response.status_code == 302, response.text
    location = response.headers["location"]
    assert location.startswith("/login?"), location
    erro: str = urllib.parse.parse_qs(urllib.parse.urlsplit(location).query)["erro"][0]
    return erro


# --- the way in ---------------------------------------------------------------------------------


def test_everything_answers_404_while_the_flag_is_off(apis: ApiFactory, forklin: Central) -> None:
    api = apis.make()
    assert api.client.get(START, follow_redirects=False).status_code == 404
    assert api.client.get(CALLBACK, params={"code": "x"}, follow_redirects=False).status_code == 404
    assert api.post(EVENTS, {"token": "x" * 40}, origin=False, csrf=False).status_code == 404


def test_start_sends_the_browser_to_the_app_with_a_state_it_also_keeps(
    apis: ApiFactory,
) -> None:
    api = sso_api(apis)
    response = api.client.get(START, follow_redirects=False)
    assert response.status_code == 302
    target = urllib.parse.urlsplit(response.headers["location"])
    query = urllib.parse.parse_qs(target.query)
    assert f"{target.scheme}://{target.netloc}{target.path}" == "http://app.test/entrar"
    assert query["produto"] == [SLUG]
    assert query["state"][0] == api.client.cookies.get("apm_sso_state")
    assert len(query["state"][0]) >= 40
    assert response.headers["cache-control"] == "no-store"


def test_a_first_secretaria_makes_the_empty_school_and_gets_a_session(
    apis: ApiFactory,
    forklin: Central,
    cleanup: Callable[[uuid.UUID], None],
    admin_engine: Engine,
) -> None:
    org = uuid.uuid4()
    cleanup(org)
    api = sso_api(apis)
    code = forklin.code_for(forklin.token(org=str(org), org_name="Escola Estadual Ipê"))

    response = land(api, code)

    assert response.status_code == 302 and response.headers["location"] == "/painel"
    assert response.headers["cache-control"] == "no-store"
    assert counts(admin_engine, org) == {
        "orgs": 1,
        "schools": 1,
        "settings": 1,
        "categories": 12,
        "memberships": 1,
    }
    me = api.get("/api/v1/auth/me")
    assert me.status_code == 200, me.text
    body = me.json()
    assert body["active_membership"]["role"] == "secretaria"
    assert body["active_membership"]["school"]["name"] == "Escola Estadual Ipê"
    with admin_engine.connect() as connection:
        slug: Any = connection.execute(
            text(
                "SELECT s.slug FROM schools s JOIN organizations o ON o.id = s.organization_id "
                "WHERE o.central_org_id = :c"
            ),
            {"c": org},
        ).scalar_one()
        password: Any = connection.execute(
            text("SELECT password_hash FROM users WHERE email = :e"), {"e": body["user"]["email"]}
        ).scalar_one()
    assert slug == "escola-estadual-ipe"
    assert password is None  # nobody can log in with a password they never chose


def test_the_same_person_coming_back_makes_nothing_new(
    apis: ApiFactory,
    forklin: Central,
    cleanup: Callable[[uuid.UUID], None],
    admin_engine: Engine,
) -> None:
    org, person = uuid.uuid4(), uuid.uuid4()
    cleanup(org)
    claims: dict[str, Any] = {"org": str(org), "sub": str(person)}
    first = sso_api(apis)
    assert land(first, forklin.code_for(forklin.token(**claims))).status_code == 302
    second = sso_api(apis)
    assert land(second, forklin.code_for(forklin.token(**claims))).headers["location"] == "/painel"
    assert counts(admin_engine, org)["memberships"] == 1
    assert counts(admin_engine, org)["schools"] == 1
    assert second.get("/api/v1/auth/me").status_code == 200


def test_the_notice_makes_the_school_before_anybody_comes_and_an_employee_may_enter(
    apis: ApiFactory,
    forklin: Central,
    cleanup: Callable[[uuid.UUID], None],
    admin_engine: Engine,
) -> None:
    org = uuid.uuid4()
    cleanup(org)
    api = sso_api(apis)
    notice = api.post(EVENTS, {"token": forklin.event(org)}, origin=False, csrf=False)
    assert notice.status_code == 200 and notice.json() == {"status": "created"}
    assert counts(admin_engine, org) == {
        "orgs": 1,
        "schools": 1,
        "settings": 1,
        "categories": 12,
        "memberships": 0,
    }

    employee = sso_api(apis)
    code = forklin.code_for(forklin.token(org=str(org), role="funcionario"))
    assert land(employee, code).headers["location"] == "/painel"
    assert employee.get("/api/v1/auth/me").json()["active_membership"]["role"] == "staff"


def test_an_employee_never_makes_a_school_it_has_to_exist_first(
    apis: ApiFactory,
    forklin: Central,
    cleanup: Callable[[uuid.UUID], None],
    admin_engine: Engine,
) -> None:
    org = uuid.uuid4()
    cleanup(org)
    api = sso_api(apis)
    code = forklin.code_for(forklin.token(org=str(org), role="funcionario"))
    assert error_of(land(api, code)) == "org"
    assert counts(admin_engine, org)["orgs"] == 0
    assert api.get("/api/v1/auth/me").status_code == 401


def test_the_role_of_the_central_wins_on_every_entry(
    apis: ApiFactory, forklin: Central, cleanup: Callable[[uuid.UUID], None]
) -> None:
    org, person = uuid.uuid4(), uuid.uuid4()
    cleanup(org)
    claims: dict[str, Any] = {"org": str(org), "sub": str(person)}
    first = sso_api(apis)
    land(first, forklin.code_for(forklin.token(role="secretaria", **claims)))
    later = sso_api(apis)
    land(later, forklin.code_for(forklin.token(role="funcionario", **claims)))
    assert later.get("/api/v1/auth/me").json()["active_membership"]["role"] == "staff"


def test_a_person_who_already_has_an_account_is_linked_by_e_mail_and_the_password_stops_working(
    apis: ApiFactory,
    users: UserFactory,
    world: World,
    forklin: Central,
    admin_engine: Engine,
    cleanup: Callable[[uuid.UUID], None],
) -> None:
    local = users.make("secretaria", school="1")
    org = uuid.uuid4()
    cleanup(org)
    with admin_engine.begin() as connection:
        connection.execute(
            text("UPDATE organizations SET central_org_id = :c WHERE id = :o"),
            {"c": org, "o": world.org_a},
        )
    person = uuid.uuid4()
    try:
        api = sso_api(apis)
        code = forklin.code_for(
            forklin.token(org=str(org), sub=str(person), email=local.email.upper())
        )
        assert land(api, code).headers["location"] == "/painel"
        me = api.get("/api/v1/auth/me").json()
        assert me["user"]["id"] == str(local.id)
        with admin_engine.connect() as connection:
            linked: Any = connection.execute(
                text("SELECT central_user_id FROM users WHERE id = :u"), {"u": local.id}
            ).scalar_one()
        assert linked == person
        # The hash stays in the row (nothing is deleted), but from now on the password no longer
        # opens a session: the person enters through the Central (ADR forklin-sso, section 7).
        with admin_engine.connect() as connection:
            kept: Any = connection.execute(
                text("SELECT password_hash IS NOT NULL FROM users WHERE id = :u"), {"u": local.id}
            ).scalar_one()
        assert kept is True
        assert sso_api(apis).login(local.email, PASSWORD).status_code == 401
    finally:
        with admin_engine.begin() as connection:
            connection.execute(
                text("UPDATE organizations SET central_org_id = NULL WHERE id = :o"),
                {"o": world.org_a},
            )
            connection.execute(
                text("UPDATE users SET central_user_id = NULL WHERE id = :u"), {"u": local.id}
            )


def test_an_e_mail_tied_to_another_person_of_the_central_is_a_conflict_and_nothing_merges(
    apis: ApiFactory, forklin: Central, cleanup: Callable[[uuid.UUID], None]
) -> None:
    org = uuid.uuid4()
    cleanup(org)
    shared = f"sso-{uuid.uuid4().hex[:8]}@example.test"
    land(sso_api(apis), forklin.code_for(forklin.token(org=str(org), email=shared)))
    other = forklin.token(org=str(org), email=shared)  # another `sub`, the same e-mail
    assert error_of(land(sso_api(apis), forklin.code_for(other))) == "conflito"


def test_a_membership_the_secretaria_suspended_stays_out(
    apis: ApiFactory,
    forklin: Central,
    cleanup: Callable[[uuid.UUID], None],
    admin_engine: Engine,
) -> None:
    org, person = uuid.uuid4(), uuid.uuid4()
    cleanup(org)
    claims: dict[str, Any] = {"org": str(org), "sub": str(person)}
    land(sso_api(apis), forklin.code_for(forklin.token(**claims)))
    with admin_engine.begin() as connection:
        connection.execute(
            text(
                "UPDATE memberships SET status = 'suspended' WHERE organization_id IN "
                "(SELECT id FROM organizations WHERE central_org_id = :c)"
            ),
            {"c": org},
        )
    assert error_of(land(sso_api(apis), forklin.code_for(forklin.token(**claims)))) == "acesso"


# --- what is refused ----------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("label", "build"),
    [
        ("another audience", lambda c: c.token(aud="diario-digital")),
        ("another issuer", lambda c: c.token(iss="someone-else")),
        ("expired", lambda c: c.token(iat=int(time.time()) - 900, exp=int(time.time()) - 300)),
        ("signed by another key", lambda c: c.token(key=c.other_key)),
        ("no signature at all", lambda c: c.token(algorithm="none")),
        ("no e-mail", lambda c: c.token(email=None)),
        ("no name", lambda c: c.token(name=None)),
        ("no org", lambda c: c.token(org=None)),
        ("org that is not a UUID", lambda c: c.token(org="not-a-uuid")),
    ],
)
def test_a_token_that_is_not_exactly_right_is_refused_and_creates_nothing(
    label: str,
    build: Callable[[Central], str],
    apis: ApiFactory,
    forklin: Central,
    admin_engine: Engine,
) -> None:
    api = sso_api(apis)
    token = build(forklin)
    response = land(api, forklin.code_for(token))
    assert error_of(response) in {"expirado", "indisponivel"}, label
    assert api.get("/api/v1/auth/me").status_code == 401
    with admin_engine.connect() as connection:
        assert (
            connection.execute(
                text(
                    "SELECT count(*) FROM users WHERE email LIKE 'sso-%@example.test' "
                    "AND central_user_id IS NOT NULL AND created_at > now() - interval '1 minute'"
                )
            ).scalar_one()
            == 0
        )


def test_a_role_this_product_does_not_know_is_refused(
    apis: ApiFactory, forklin: Central, admin_engine: Engine
) -> None:
    org = uuid.uuid4()
    api = sso_api(apis)
    response = land(api, forklin.code_for(forklin.token(org=str(org), role="administrador")))
    assert error_of(response) == "cargo"
    assert counts(admin_engine, org)["orgs"] == 0


@pytest.mark.parametrize(
    ("raised", "word"),
    [
        (CentralError("indisponivel", "down"), "indisponivel"),
        (CentralError("org", "org inactive"), "org"),
        (CentralError("acesso", "no access"), "acesso"),
        (CentralError("expirado", "used"), "expirado"),
    ],
)
def test_what_the_exchange_says_is_what_the_person_sees(
    raised: CentralError, word: str, apis: ApiFactory, forklin: Central
) -> None:
    api = sso_api(apis)
    assert error_of(land(api, forklin.code_for(raised))) == word


def test_no_code_a_wrong_state_or_a_state_without_the_button_is_refused(
    apis: ApiFactory, forklin: Central
) -> None:
    api = sso_api(apis)
    assert error_of(land(api, None)) == "expirado"
    token = forklin.token()
    # Came from the button (has the cookie) but the App returned another state.
    api.client.get(START, follow_redirects=False)
    assert error_of(land(api, forklin.code_for(token), state="forged")) == "expirado"
    assert forklin.exchanged == []  # refused before spending the code
    # A state without ever having started here.
    other = sso_api(apis)
    assert error_of(land(other, forklin.code_for(token), state="forged")) == "expirado"


def test_the_state_of_the_button_is_accepted_once_and_dropped(
    apis: ApiFactory, forklin: Central, cleanup: Callable[[uuid.UUID], None]
) -> None:
    org = uuid.uuid4()
    cleanup(org)
    api = sso_api(apis)
    start = api.client.get(START, follow_redirects=False)
    state = urllib.parse.parse_qs(urllib.parse.urlsplit(start.headers["location"]).query)["state"][
        0
    ]
    code = forklin.code_for(forklin.token(org=str(org)))
    response = land(api, code, state=state)
    assert response.headers["location"] == "/painel"
    assert api.client.cookies.get("apm_sso_state") is None


def test_a_session_the_browser_came_with_is_ended_not_adopted(
    apis: ApiFactory,
    users: UserFactory,
    forklin: Central,
    cleanup: Callable[[uuid.UUID], None],
) -> None:
    org = uuid.uuid4()
    cleanup(org)
    api = sso_api(apis)
    assert api.login(users.make("secretaria")).status_code == 200
    before = api.session_token
    land(api, forklin.code_for(forklin.token(org=str(org))))
    assert api.session_token and api.session_token != before


def test_nothing_personal_or_secret_reaches_the_log(
    apis: ApiFactory, forklin: Central, caplog: pytest.LogCaptureFixture
) -> None:
    api = sso_api(apis)
    mail = f"sso-{uuid.uuid4().hex[:8]}@example.test"
    token = forklin.token(email=mail, name="Nome Secreto Da Silva", role="administrador")
    with caplog.at_level("DEBUG"):
        land(api, forklin.code_for(token))
    text_logged: str = " ".join(record.getMessage() for record in caplog.records)
    for secret in (mail, "Nome Secreto", token, FORKLIN["forklin_product_secret"]):
        assert secret not in text_logged


# --- the notice ---------------------------------------------------------------------------------


def test_the_notice_is_idempotent(
    apis: ApiFactory,
    forklin: Central,
    cleanup: Callable[[uuid.UUID], None],
    admin_engine: Engine,
) -> None:
    org = uuid.uuid4()
    cleanup(org)
    api = sso_api(apis)
    first = api.post(EVENTS, {"token": forklin.event(org)}, origin=False, csrf=False)
    again = api.post(EVENTS, {"token": forklin.event(org)}, origin=False, csrf=False)
    assert (first.json()["status"], again.json()["status"]) == ("created", "exists")
    assert counts(admin_engine, org)["schools"] == 1


def test_two_organizations_with_the_same_name_get_two_different_addresses(
    apis: ApiFactory,
    forklin: Central,
    cleanup: Callable[[uuid.UUID], None],
    admin_engine: Engine,
) -> None:
    a, b = uuid.uuid4(), uuid.uuid4()
    cleanup(a)
    cleanup(b)
    api = sso_api(apis)
    for org in (a, b):
        sent = api.post(
            EVENTS, {"token": forklin.event(org, name="Escola Sol")}, origin=False, csrf=False
        )
        assert sent.status_code == 200, sent.text
    with admin_engine.connect() as connection:
        slugs: Any = (
            connection.execute(
                text(
                    "SELECT s.slug FROM schools s JOIN organizations o ON o.id = s.organization_id "
                    "WHERE o.central_org_id = ANY(:c)"
                ),
                {"c": [a, b]},
            )
            .scalars()
            .all()
        )
    assert len(set(slugs)) == 2 and all(s.startswith("escola-sol") for s in slugs)


@pytest.mark.parametrize(
    "build",
    [
        lambda c, org: c.event(org, aud="diario-digital"),
        lambda c, org: c.event(org, event=None),  # no name at all
        lambda c, org: c.event(org, exp=int(time.time()) + 3600),  # lives too long
        lambda c, org: c.event(org, exp=int(time.time()) - 10, iat=int(time.time()) - 100),
        lambda c, org: c.event(org, organization_id="not-a-uuid"),
        lambda c, org: jwt.encode(
            {"iss": "forklin", "aud": SLUG, "event": "x"}, c.other_key, algorithm="EdDSA"
        ),
    ],
)
def test_a_notice_that_is_not_exactly_right_is_refused_and_makes_nothing(
    build: Callable[[Central, uuid.UUID], str],
    apis: ApiFactory,
    forklin: Central,
    admin_engine: Engine,
) -> None:
    org = uuid.uuid4()
    api = sso_api(apis)
    response = api.post(EVENTS, {"token": build(forklin, org)}, origin=False, csrf=False)
    assert response.status_code == 401, response.text
    assert counts(admin_engine, org)["orgs"] == 0


def test_the_notice_needs_no_browser_headers_but_a_browser_cannot_forge_one(
    apis: ApiFactory, forklin: Central
) -> None:
    api = sso_api(apis)
    garbage = {"token": "x" * 40}
    assert api.post(EVENTS, garbage, origin=False, csrf=False).status_code == 401
    assert api.post(EVENTS, {"token": "short"}, origin=False, csrf=False).status_code == 422
    assert (
        api.post(EVENTS, {"token": "x" * 40, "more": 1}, origin=False, csrf=False).status_code
        == 422
    )


def test_the_application_role_cannot_write_the_accounts_itself(
    app_engine: Engine, admin_engine: Engine
) -> None:
    """Only the two functions can: a direct insert by apm_app stays refused (row level security)."""
    with app_engine.connect() as connection:
        with pytest.raises(Exception) as error:  # noqa: PT011
            connection.execute(
                text(
                    "INSERT INTO organizations (name, slug, central_org_id) "
                    "VALUES ('x', 'x-direct', gen_random_uuid())"
                )
            )
        assert "permission denied" in str(error.value) or "row-level security" in str(error.value)


def test_the_client_helpers_do_not_leak_between_tests(client: TestClient) -> None:
    assert client.get("/api/v1/forklin/sso/start", follow_redirects=False).status_code == 404
