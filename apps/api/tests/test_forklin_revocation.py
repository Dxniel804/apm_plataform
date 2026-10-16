"""The Central ends a person's open sessions (docs/adr-forklin-sso.md, section 9).

Same arrangement as tests/test_forklin_sso.py: real EdDSA tokens verified by the real code, the real
database, only the network faked. The events carry no session and no Origin: the signed token is the
whole authentication.
"""

import time
import uuid
from collections.abc import Callable
from typing import Any

import jwt
import pytest
from sqlalchemy import Engine, text

from app.forklin import central
from tests import test_forklin_sso as sso
from tests.authsupport import Api, ApiFactory, UserFactory
from tests.test_forklin_sso import EVENTS, SLUG, Central, land, sso_api

# The fixtures of the sign-in tests (the fake Central and the cleanup), reused by name.
forklin = sso.forklin
cleanup = sso.cleanup

ME = "/api/v1/auth/me"
PROCESSED = {"status": "processed"}

REVOKING = sorted(central.REVOKING_EVENTS)


def revocation(
    forklin: Central, org: uuid.UUID, person: uuid.UUID | str | None, event: str, **overrides: Any
) -> str:
    claims: dict[str, Any] = {"event": event, "user_id": None if person is None else str(person)}
    return forklin.event(org, name=None, **{**claims, **overrides})


def send(api: Api, token: str) -> Any:
    """Server to server: no Origin, no CSRF header, no cookie of anybody."""
    return api.post(EVENTS, {"token": token}, origin=False, csrf=False)


class Scene:
    """Ana (secretaria) and Beto (funcionario) of one organization, Carla of another."""

    def __init__(self, apis: ApiFactory, forklin: Central, engine: Engine) -> None:
        self.apis, self.forklin, self.engine = apis, forklin, engine
        self.org, self.other_org = uuid.uuid4(), uuid.uuid4()
        self.ana, self.beto, self.carla = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()

    def sign_in(self, person: uuid.UUID, org: uuid.UUID, role: str = "secretaria") -> Api:
        api = sso_api(self.apis)
        code = self.forklin.code_for(
            self.forklin.token(sub=str(person), org=str(org), role=role, org_name="Escola Ipê")
        )
        assert land(api, code).headers["location"] == "/painel"
        assert api.get(ME).status_code == 200
        return api

    def sessions(self, person: uuid.UUID) -> list[tuple[Any, Any]]:
        with self.engine.connect() as connection:
            rows = connection.execute(
                text(
                    "SELECT s.revoked_at IS NOT NULL, s.revoked_reason FROM sessions s "
                    "JOIN users u ON u.id = s.user_id WHERE u.central_user_id = :p "
                    "ORDER BY s.created_at"
                ),
                {"p": person},
            ).all()
        return [tuple(row) for row in rows]

    def state_of(self, person: uuid.UUID) -> tuple[Any, ...]:
        """What the revocation must never change: the account, the password and the memberships."""
        with self.engine.connect() as connection:
            row = connection.execute(
                text(
                    "SELECT u.is_active, u.password_hash, u.email, "
                    "(SELECT array_agg(m.status || ':' || m.role ORDER BY m.id) FROM memberships m "
                    " WHERE m.user_id = u.id) FROM users u WHERE u.central_user_id = :p"
                ),
                {"p": person},
            ).one()
        return tuple(row)


@pytest.fixture
def scene(
    apis: ApiFactory,
    forklin: Central,
    cleanup: Callable[[uuid.UUID], None],
    admin_engine: Engine,
) -> Scene:
    made = Scene(apis, forklin, admin_engine)
    cleanup(made.org)
    cleanup(made.other_org)
    return made


@pytest.mark.parametrize("event", REVOKING)
def test_each_revoking_event_ends_the_sessions_of_that_person_and_of_nobody_else(
    event: str, scene: Scene, apis: ApiFactory, forklin: Central
) -> None:
    ana_phone = scene.sign_in(scene.ana, scene.org)
    ana_laptop = scene.sign_in(scene.ana, scene.org)
    beto = scene.sign_in(scene.beto, scene.org, "funcionario")
    carla = scene.sign_in(scene.carla, scene.other_org)
    before = {p: scene.state_of(p) for p in (scene.ana, scene.beto, scene.carla)}

    response = send(sso_api(apis), revocation(forklin, scene.org, scene.ana, event))

    assert response.status_code == 200 and response.json() == PROCESSED, response.text
    assert ana_phone.get(ME).status_code == 401
    assert ana_laptop.get(ME).status_code == 401
    assert beto.get(ME).status_code == 200  # a colleague of the same school
    assert carla.get(ME).status_code == 200  # another school
    assert scene.sessions(scene.ana) == [(True, "central_revoked")] * 2
    assert scene.sessions(scene.beto) == [(False, None)]
    assert scene.sessions(scene.carla) == [(False, None)]
    # Nothing but the sessions changed: the person, password and memberships are as they were.
    assert {p: scene.state_of(p) for p in (scene.ana, scene.beto, scene.carla)} == before


def test_the_person_can_come_back_through_the_central_afterwards(
    scene: Scene, apis: ApiFactory, forklin: Central
) -> None:
    ana = scene.sign_in(scene.ana, scene.org)
    suspended = send(sso_api(apis), revocation(forklin, scene.org, scene.ana, "access.suspended"))
    assert suspended.status_code == 200
    assert ana.get(ME).status_code == 401

    again = scene.sign_in(scene.ana, scene.org)  # the Central re-granted: a new sign-in works
    assert again.get(ME).status_code == 200
    assert ana.get(ME).status_code == 401  # the old cookie stays dead
    assert [revoked for revoked, _ in scene.sessions(scene.ana)] == [True, False]


def test_a_replay_is_harmless_and_answers_the_same(
    scene: Scene, apis: ApiFactory, forklin: Central
) -> None:
    ana = scene.sign_in(scene.ana, scene.org)
    gate = sso_api(apis)
    token = revocation(forklin, scene.org, scene.ana, "access.revoked")
    first, replay = send(gate, token), send(gate, token)
    assert (first.status_code, first.json()) == (200, PROCESSED)
    assert (replay.status_code, replay.json()) == (200, PROCESSED)
    assert ana.get(ME).status_code == 401
    assert scene.sessions(scene.ana) == [(True, "central_revoked")]


def test_an_unknown_person_or_another_organization_is_a_no_op_that_answers_like_a_hit(
    scene: Scene, apis: ApiFactory, forklin: Central
) -> None:
    ana = scene.sign_in(scene.ana, scene.org)
    carla = scene.sign_in(scene.carla, scene.other_org)
    gate = sso_api(apis)

    stranger = send(gate, revocation(forklin, scene.org, uuid.uuid4(), "user.disabled"))
    wrong_org = send(gate, revocation(forklin, scene.other_org, scene.ana, "user.disabled"))
    unknown_org = send(gate, revocation(forklin, uuid.uuid4(), scene.ana, "user.disabled"))

    hit = send(gate, revocation(forklin, scene.other_org, scene.carla, "user.disabled"))
    for response in (stranger, wrong_org, unknown_org, hit):
        assert (response.status_code, response.json()) == (200, PROCESSED)
    assert ana.get(ME).status_code == 200  # none of the three no-ops touched her
    assert carla.get(ME).status_code == 401  # and the hit did what it should
    assert scene.sessions(scene.ana) == [(False, None)]


def test_a_revoking_event_without_a_valid_person_is_refused_and_ends_nothing(
    scene: Scene, apis: ApiFactory, forklin: Central
) -> None:
    ana = scene.sign_in(scene.ana, scene.org)
    gate = sso_api(apis)
    for token in (
        revocation(forklin, scene.org, None, "access.revoked"),
        revocation(forklin, scene.org, "not-a-uuid", "access.revoked"),
        revocation(forklin, scene.org, scene.ana, "access.revoked", organization_id=None),
        revocation(forklin, scene.org, scene.ana, "access.revoked", organization_id="nope"),
    ):
        response = send(gate, token)
        assert response.status_code == 400, response.text
        assert response.json()["code"] == "invalid_event"
    assert ana.get(ME).status_code == 200


def test_an_unknown_event_is_ignored_with_a_200_and_does_nothing(
    scene: Scene, apis: ApiFactory, forklin: Central, caplog: pytest.LogCaptureFixture
) -> None:
    ana = scene.sign_in(scene.ana, scene.org)
    gate = sso_api(apis)
    with caplog.at_level("INFO", logger="app.routers.v1.forklin"):
        for name in ("user.password_changed", "organization.renamed", "organization.active"):
            response = send(gate, revocation(forklin, scene.org, scene.ana, name))
            assert (response.status_code, response.json()) == (200, {"status": "ignored"})
    assert ana.get(ME).status_code == 200
    log = caplog.text
    assert "user.password_changed" in log  # the name, and only the name
    assert str(scene.ana) not in log and str(scene.org) not in log


def test_the_log_of_a_hit_has_the_event_and_a_count_but_nobody_s_identity(
    scene: Scene, apis: ApiFactory, forklin: Central, caplog: pytest.LogCaptureFixture
) -> None:
    scene.sign_in(scene.ana, scene.org)
    with caplog.at_level("INFO", logger="app.routers.v1.forklin"):
        send(sso_api(apis), revocation(forklin, scene.org, scene.ana, "access.revoked"))
    assert "access.revoked: 1 session(s) ended" in caplog.text
    assert str(scene.ana) not in caplog.text and str(scene.org) not in caplog.text


def _raw(
    forklin: Central, claims: dict[str, Any], algorithm: str = "EdDSA", key: Any = None
) -> str:
    if algorithm == "none":
        return jwt.encode(claims, None, algorithm="none")  # type: ignore[arg-type]
    return jwt.encode(claims, key or forklin.key, algorithm=algorithm)


@pytest.mark.parametrize(
    "tamper",
    [
        pytest.param(lambda f, c: _raw(f, c, key=f.other_key), id="wrong-signature"),
        pytest.param(lambda f, c: _raw(f, {**c, "aud": "diario-digital"}), id="wrong-audience"),
        pytest.param(lambda f, c: _raw(f, {**c, "iss": "someone-else"}), id="wrong-issuer"),
        pytest.param(
            lambda f, c: _raw(f, {**c, "iat": int(time.time()) - 500, "exp": int(time.time()) - 5}),
            id="expired",
        ),
        pytest.param(
            lambda f, c: _raw(f, {**c, "exp": int(time.time()) + 3600}), id="lives-too-long"
        ),
        pytest.param(lambda f, c: _raw(f, c, algorithm="none"), id="alg-none"),
        pytest.param(lambda f, c: _raw(f, {k: v for k, v in c.items() if k != "jti"}), id="no-jti"),
        pytest.param(
            lambda f, c: _raw(f, {k: v for k, v in c.items() if k != "event"}), id="no-event"
        ),
    ],
)
def test_an_event_that_is_not_exactly_right_is_refused_and_ends_nothing(
    tamper: Callable[[Central, dict[str, Any]], str],
    scene: Scene,
    apis: ApiFactory,
    forklin: Central,
) -> None:
    ana = scene.sign_in(scene.ana, scene.org)
    now = int(time.time())
    claims = {
        "iss": "forklin",
        "aud": SLUG,
        "iat": now,
        "exp": now + 120,
        "jti": uuid.uuid4().hex,
        "event": "access.revoked",
        "organization_id": str(scene.org),
        "user_id": str(scene.ana),
    }
    response = send(sso_api(apis), tamper(forklin, claims))
    assert response.status_code == 401, response.text
    assert ana.get(ME).status_code == 200
    assert scene.sessions(scene.ana) == [(False, None)]


def test_the_endpoint_still_answers_404_while_the_flag_is_off(
    apis: ApiFactory, forklin: Central
) -> None:
    api = apis.make()
    token = revocation(forklin, uuid.uuid4(), uuid.uuid4(), "access.revoked")
    assert send(api, token).status_code == 404


def test_the_endpoint_needs_no_session_and_no_origin_but_a_browser_page_cannot_use_it_either(
    scene: Scene, apis: ApiFactory, forklin: Central
) -> None:
    ana = scene.sign_in(scene.ana, scene.org)
    anonymous = sso_api(apis)
    assert anonymous.session_token is None
    token = revocation(forklin, scene.org, scene.ana, "product.inactive")
    # No cookie, no Origin, no CSRF: accepted. The token is what a browser page does not have.
    assert send(anonymous, token).status_code == 200
    assert ana.get(ME).status_code == 401


def test_a_session_of_a_person_who_never_came_from_the_central_is_out_of_reach(
    admin_engine: Engine, users: UserFactory
) -> None:
    """The policy, tried on its own as the definer: only people with a `central_user_id` have
    sessions it can see or end, so a password-only account cannot be touched even by mistake."""
    local = users.make("secretaria")
    linked = users.make("secretaria")
    with admin_engine.begin() as connection:
        connection.execute(
            text("UPDATE users SET central_user_id = gen_random_uuid() WHERE id = :u"),
            {"u": linked.id},
        )
        for person in (local, linked):
            connection.execute(
                text(
                    "INSERT INTO sessions (id, user_id, expires_at) "
                    "VALUES (decode(md5(:u), 'hex') || decode(md5(:u || 'x'), 'hex'), "
                    "CAST(:u AS uuid), now() + interval '1 hour')"
                ),
                {"u": str(person.id)},
            )
    seen: dict[str, int] = {}
    connection = admin_engine.connect()
    transaction = connection.begin()
    try:
        connection.exec_driver_sql("SET LOCAL ROLE apm_definer")
        for label, person in (("local", local), ("linked", linked)):
            seen[label] = connection.execute(
                text(
                    "UPDATE sessions SET revoked_at = now(), revoked_reason = 'central_revoked' "
                    "WHERE user_id = :u"
                ),
                {"u": person.id},
            ).rowcount
    finally:
        transaction.rollback()
        connection.close()
    assert seen == {"local": 0, "linked": 1}


def test_the_application_role_still_cannot_end_the_sessions_of_other_people(
    app_engine: Engine, admin_engine: Engine, users: UserFactory
) -> None:
    mine, theirs = users.make("secretaria"), users.make("secretaria")
    with admin_engine.begin() as connection:
        for person in (mine, theirs):
            connection.execute(
                text(
                    "INSERT INTO sessions (id, user_id, expires_at) "
                    "VALUES (decode(md5(:u), 'hex') || decode(md5(:u || 'x'), 'hex'), "
                    "CAST(:u AS uuid), now() + interval '1 hour')"
                ),
                {"u": str(person.id)},
            )
    update = text(
        "UPDATE sessions SET revoked_at = now(), revoked_reason = 'logout' WHERE user_id = :u"
    )

    def attempt(context_user: uuid.UUID | None, target: uuid.UUID) -> int:
        connection = app_engine.connect()
        transaction = connection.begin()
        try:
            if context_user is not None:
                connection.execute(
                    text("SELECT set_config('app.user_id', :u, true)"), {"u": str(context_user)}
                )
            return connection.execute(update, {"u": target}).rowcount
        finally:
            transaction.rollback()
            connection.close()

    assert attempt(mine.id, theirs.id) == 0
    assert attempt(None, theirs.id) == 0  # no context at all
    assert attempt(mine.id, mine.id) == 1  # and her own, the thing the application may do

    # The function is callable by the application role and, for anybody it does not know, harmless.
    connection = app_engine.connect()
    try:
        none_ended: int = connection.execute(
            text("SELECT public.revoke_forklin_sessions(gen_random_uuid(), gen_random_uuid())")
        ).scalar_one()
        assert none_ended == 0
    finally:
        connection.rollback()
        connection.close()
