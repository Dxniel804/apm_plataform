"""With the Forklin Central ON, people exist only there (docs/adr-forklin-sso.md, sections 7 and 8).

* the APM registers no staff: the team and invitation-creation routes answer 404, and an invitation
  sent before the switch no longer works;
* the password never opens a session for a person who has a `central_user_id` (the answer is the
  one of a wrong password), and the recovery flow neither makes nor spends a reset for them;
* people WITHOUT a link (demo, legacy, emergency) keep working, and with the switch OFF (the
  default) everything is as it always was.
"""

import uuid
from pathlib import Path
from typing import Any

import pytest
from httpx2 import Response
from sqlalchemy import Engine, text
from sqlalchemy.exc import ProgrammingError

from app.auth import passwords
from tests.authsupport import (
    OTHER_PASSWORD,
    PASSWORD,
    ApiFactory,
    OutboxMessage,
    TestUser,
    UserFactory,
    read_outbox,
)
from tests.test_forklin_sso import sso_api

LOGIN = "/api/v1/auth/login"
ME = "/api/v1/auth/me"
CHANGE = "/api/v1/auth/password"
REQUEST = "/api/v1/auth/password-reset/request"
CONFIRM = "/api/v1/auth/password-reset/confirm"
TEAM = "/api/v1/employees"
ACCEPT = "/api/v1/invitations/accept"
NEW = "uma-senha-nova-e-bem-longa"


def link(engine: Engine, user: TestUser) -> uuid.UUID:
    """Makes the person one of the Central's (the password they had stays in the row)."""
    central_id = uuid.uuid4()
    with engine.begin() as connection:
        connection.execute(
            text("UPDATE users SET central_user_id = :c WHERE id = :u"),
            {"c": central_id, "u": user.id},
        )
    return central_id


def password_hash(engine: Engine, user: TestUser) -> str | None:
    with engine.connect() as connection:
        value: Any = connection.execute(
            text("SELECT password_hash FROM users WHERE id = :u"), {"u": user.id}
        ).scalar_one()
    return None if value is None else str(value)


def resets(engine: Engine, user: TestUser) -> int:
    with engine.connect() as connection:
        return int(
            connection.execute(
                text("SELECT count(*) FROM password_reset_tokens WHERE user_id = :u"),
                {"u": user.id},
            ).scalar_one()
        )


def mails(tmp_path: Path, kind: str) -> list[OutboxMessage]:
    return [m for m in read_outbox(tmp_path) if m.kind == kind]


def shape(response: Response) -> tuple[int, dict[str, Any], bool]:
    body = dict(response.json())
    body.pop("request_id", None)
    return response.status_code, body, "set-cookie" in response.headers


# --- the staff-registration surface is closed ---------------------------------------------------


def test_with_the_central_on_every_route_that_registers_or_manages_staff_answers_404(
    apis: ApiFactory, users: UserFactory
) -> None:
    boss = users.make("secretaria")
    other = users.make("staff", label="other")
    api = sso_api(apis)
    assert api.login(boss).status_code == 200
    anonymous = sso_api(apis)
    fake = uuid.uuid4()
    calls = [
        ("get", TEAM, None),
        ("post", TEAM, {"full_name": "Maria Silva", "email": users.world.email("maria")}),
        ("post", f"{TEAM}/invitations/{fake}/resend", None),
        ("delete", f"{TEAM}/invitations/{fake}", None),
        ("post", f"{TEAM}/{other.membership_ids[0]}/suspend", None),
        ("post", f"{TEAM}/{other.membership_ids[0]}/activate", None),
        ("post", "/api/v1/invitations", {"email": users.world.email("x"), "role": "staff"}),
    ]
    for who in (api, anonymous):
        for method, path, body in calls:
            if method == "get":
                response = who.get(path)
            elif method == "delete":
                response = who.client.delete(
                    path, headers={"Origin": who.origin, "X-CSRF-Token": who.csrf or ""}
                )
            else:
                response = who.post(path, body)
            assert response.status_code == 404, (method, path, response.text)
            assert response.json()["code"] == "not_found"


def test_with_the_central_on_nothing_is_changed_by_those_calls(
    apis: ApiFactory, users: UserFactory, tmp_path: Path, admin_engine: Engine
) -> None:
    boss = users.make("secretaria")
    other = users.make("staff", label="other")
    api = sso_api(apis)
    assert api.login(boss).status_code == 200

    api.post(TEAM, {"full_name": "Maria Silva", "email": users.world.email("maria")})
    api.post(f"{TEAM}/{other.membership_ids[0]}/suspend")

    assert mails(tmp_path, "invitation") == []
    with admin_engine.connect() as connection:
        status: Any = connection.execute(
            text("SELECT status FROM memberships WHERE id = :m"), {"m": other.membership_ids[0]}
        ).scalar_one()
    assert status == "active"


def test_an_invitation_sent_before_the_switch_cannot_be_accepted_any_more(
    apis: ApiFactory, users: UserFactory, tmp_path: Path
) -> None:
    old_api = apis.make()  # the Central OFF: the invitation was made the old way
    assert old_api.login(users.make("secretaria")).status_code == 200
    email = users.world.email("late")
    assert old_api.post(TEAM, {"full_name": "Late Person", "email": email}).status_code == 201
    token = mails(tmp_path, "invitation")[-1].token
    body = {"token": token, "full_name": "Late Person", "password": "uma-senha-bem-longa-123"}

    refused = sso_api(apis).post(ACCEPT, body)
    nonsense = sso_api(apis).post(ACCEPT, {**body, "token": "x" * 43})

    assert refused.status_code == 400 and refused.json()["code"] == "invitation_invalid"
    assert shape(refused) == shape(nonsense)
    # With the switch off it still works: nothing was deleted, nothing was spent.
    assert apis.make().post(ACCEPT, body).status_code == 201


def test_with_the_central_off_the_team_and_the_invitations_work_as_always(
    apis: ApiFactory, users: UserFactory, tmp_path: Path
) -> None:
    api = apis.make()
    assert api.login(users.make("secretaria")).status_code == 200
    email = users.world.email("maria")

    assert api.get(TEAM).status_code == 200
    assert api.post(TEAM, {"full_name": "Maria Silva", "email": email}).status_code == 201
    assert api.invite(users.world.email("viewer"), "staff").status_code == 201
    token = mails(tmp_path, "invitation")[0].token
    accepted = apis.make().post(
        ACCEPT, {"token": token, "full_name": "Maria Silva", "password": "uma-senha-bem-longa-123"}
    )
    assert accepted.status_code == 201


# --- the password does not open a session for a person of the Central --------------------------


def test_a_linked_person_with_the_right_password_is_refused_like_a_wrong_password(
    apis: ApiFactory, users: UserFactory, admin_engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    linked = users.make("secretaria", label="linked")
    unlinked = users.make("secretaria", label="plain")
    link(admin_engine, linked)
    calls: list[str] = []
    real = passwords.verify_hash

    def spy(stored: str, password: str) -> bool:
        calls.append(stored)
        return real(stored, password)

    monkeypatch.setattr(passwords, "verify_hash", spy)

    answers: dict[str, Response] = {}
    verified: dict[str, list[str]] = {}
    attempts = {
        "linked": (linked.email, PASSWORD),
        "linked-wrong": (linked.email, OTHER_PASSWORD),
        "wrong": (unlinked.email, OTHER_PASSWORD),
        "unknown": (users.world.email("nobody"), PASSWORD),
    }
    for label, (email, password) in attempts.items():
        calls.clear()
        answers[label] = sso_api(apis).post(LOGIN, {"email": email, "password": password})
        verified[label] = list(calls)

    reference = shape(answers["wrong"])
    for label, response in answers.items():
        assert response.status_code == 401, label
        assert shape(response) == reference, label
        assert len(verified[label]) == 1, label  # one verification whatever the account is
    assert reference[1]["code"] == "invalid_credentials" and reference[2] is False
    # The linked account is treated as one with no password: the dummy hash is what is verified.
    assert verified["linked"] == [passwords._DUMMY_HASH]  # noqa: SLF001


def test_a_refused_linked_login_counts_as_a_failed_attempt_and_creates_no_session(
    apis: ApiFactory, users: UserFactory, admin_engine: Engine
) -> None:
    linked = users.make("secretaria", label="linked")
    link(admin_engine, linked)
    api = sso_api(apis)

    assert api.login(linked).status_code == 401

    assert api.session_token is None and api.get(ME).status_code == 401
    with admin_engine.connect() as connection:
        sessions: Any = connection.execute(
            text("SELECT count(*) FROM sessions WHERE user_id = :u"), {"u": linked.id}
        ).scalar_one()
    assert sessions == 0


def test_a_person_without_a_link_still_logs_in_with_the_central_on(
    apis: ApiFactory, users: UserFactory
) -> None:
    api = sso_api(apis)

    assert api.login(users.make("secretaria", label="plain")).status_code == 200
    assert api.get(ME).status_code == 200


def test_a_person_with_a_link_logs_in_with_the_password_when_the_central_is_off(
    apis: ApiFactory, users: UserFactory, admin_engine: Engine
) -> None:
    linked = users.make("secretaria", label="linked")
    link(admin_engine, linked)

    assert apis.make().login(linked).status_code == 200  # the default: as it has always been


def test_the_link_is_found_whatever_the_case_of_the_e_mail(
    apis: ApiFactory, users: UserFactory, admin_engine: Engine
) -> None:
    linked = users.make("secretaria", label="linked")
    link(admin_engine, linked)

    answer = sso_api(apis).post(LOGIN, {"email": linked.email.upper(), "password": PASSWORD})

    assert answer.status_code == 401


def test_a_linked_session_cannot_set_a_local_password(
    apis: ApiFactory, users: UserFactory, admin_engine: Engine
) -> None:
    person = users.make("secretaria", label="linked")
    api = sso_api(apis)
    assert api.login(person).status_code == 200  # a session, as the Central's sign-in makes one
    link(admin_engine, person)
    before = password_hash(admin_engine, person)

    answer = api.post(CHANGE, {"current_password": PASSWORD, "new_password": NEW})

    assert answer.status_code == 403 and answer.json()["code"] == "current_password_incorrect"
    assert password_hash(admin_engine, person) == before


# --- "forgot the password" cannot make or change a password for a person of the Central ---------


def test_forgot_for_a_linked_person_answers_as_always_sends_nothing_and_makes_nothing(
    apis: ApiFactory, users: UserFactory, admin_engine: Engine, tmp_path: Path
) -> None:
    linked = users.make("secretaria", label="linked")
    link(admin_engine, linked)
    plain = users.make("secretaria", label="plain")

    for_linked = sso_api(apis).post(REQUEST, {"email": linked.email})
    for_unknown = sso_api(apis).post(REQUEST, {"email": users.world.email("nobody")})
    for_plain = sso_api(apis).post(REQUEST, {"email": plain.email})

    assert for_linked.status_code == 202 and for_linked.json() == {"status": "accepted"}
    assert shape(for_linked) == shape(for_unknown) == shape(for_plain)
    assert [m.to for m in mails(tmp_path, "password-reset")] == [plain.email]  # only the plain one
    assert resets(admin_engine, linked) == 0
    assert resets(admin_engine, plain) == 1


def test_a_link_made_before_the_person_came_from_the_central_changes_nothing(
    apis: ApiFactory, users: UserFactory, admin_engine: Engine, tmp_path: Path
) -> None:
    person = users.make("secretaria", label="late")
    assert apis.make().post(REQUEST, {"email": person.email}).status_code == 202  # Central OFF
    token = mails(tmp_path, "password-reset")[-1].token
    link(admin_engine, person)
    before = password_hash(admin_engine, person)
    session = sso_api(apis)
    assert session.login(users.make("secretaria", label="witness")).status_code == 200

    refused = sso_api(apis).post(CONFIRM, {"token": token, "new_password": NEW})
    nonsense = sso_api(apis).post(CONFIRM, {"token": "x" * 43, "new_password": NEW})

    assert refused.status_code == 400 and refused.json()["code"] == "reset_invalid"
    assert shape(refused) == shape(nonsense)
    assert password_hash(admin_engine, person) == before
    assert mails(tmp_path, "password-changed") == []
    assert session.get(ME).status_code == 200  # nobody's sessions were touched either


def test_forgot_and_reset_work_as_always_for_a_person_without_a_link(
    apis: ApiFactory, users: UserFactory, tmp_path: Path
) -> None:
    person = users.make("secretaria", label="plain")
    api = sso_api(apis)

    assert api.post(REQUEST, {"email": person.email}).status_code == 202
    token = mails(tmp_path, "password-reset")[-1].token
    assert api.post(CONFIRM, {"token": token, "new_password": NEW}).status_code == 204
    assert sso_api(apis).login(person, NEW).status_code == 200


def test_with_the_central_off_a_linked_person_recovers_the_password_as_before(
    apis: ApiFactory, users: UserFactory, admin_engine: Engine, tmp_path: Path
) -> None:
    person = users.make("secretaria", label="linked")
    link(admin_engine, person)
    api = apis.make()

    assert api.post(REQUEST, {"email": person.email}).status_code == 202
    token = mails(tmp_path, "password-reset")[-1].token
    assert api.post(CONFIRM, {"token": token, "new_password": NEW}).status_code == 204
    assert apis.make().login(person, NEW).status_code == 200


# --- the function behind it ---------------------------------------------------------------------


def test_is_central_linked_answers_by_id_by_e_mail_and_for_nobody(
    users: UserFactory, admin_engine: Engine
) -> None:
    linked = users.make("staff", label="linked")
    plain = users.make("staff", label="plain")
    link(admin_engine, linked)

    def ask(user_id: uuid.UUID | None, email: str | None) -> bool:
        with admin_engine.connect() as connection:
            return bool(
                connection.execute(
                    text("SELECT public.is_central_linked(:u, :e)"), {"u": user_id, "e": email}
                ).scalar_one()
            )

    assert ask(linked.id, None) and ask(None, linked.email) and ask(None, linked.email.upper())
    assert not ask(plain.id, None) and not ask(None, plain.email)
    assert not ask(None, None) and not ask(uuid.uuid4(), "nobody@example.test")


def test_the_application_role_may_run_the_function_but_reads_nothing_else_of_the_link(
    app_engine: Engine, users: UserFactory, admin_engine: Engine
) -> None:
    linked = users.make("staff", label="linked")
    link(admin_engine, linked)
    with app_engine.connect() as connection:
        assert connection.execute(
            text("SELECT public.is_central_linked(NULL, :e)"), {"e": linked.email}
        ).scalar_one()
        with pytest.raises(ProgrammingError, match="permission denied"):
            connection.execute(text("SELECT central_user_id FROM users"))
