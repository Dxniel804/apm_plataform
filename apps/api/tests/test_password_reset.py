"""Forgot the password (docs/adr-password-reset.md): a link by e-mail, one use, 30 minutes, the same
answer for any e-mail, every session ended and nothing kept if a step fails."""

from pathlib import Path

import pytest
from sqlalchemy import Engine, text

from tests.authsupport import PASSWORD, ApiFactory, OutboxMessage, UserFactory, read_outbox

REQUEST = "/api/v1/auth/password-reset/request"
CONFIRM = "/api/v1/auth/password-reset/confirm"
NEW = "uma-senha-nova-e-bem-longa"


def _reset_mails(tmp_path: Path) -> list[OutboxMessage]:
    return [m for m in read_outbox(tmp_path) if m.kind == "password-reset"]


def test_the_whole_flow_changes_the_password_ends_the_sessions_and_warns(
    apis: ApiFactory, users: UserFactory, tmp_path: Path
) -> None:
    user = users.make("staff")
    logged = apis.make()
    assert logged.login(user).status_code == 200
    forgetful = apis.make()

    asked = forgetful.post(REQUEST, {"email": user.email})
    token = _reset_mails(tmp_path)[-1].token
    done = forgetful.post(CONFIRM, {"token": token, "new_password": NEW})

    assert asked.status_code == 202 and asked.json() == {"status": "accepted"}
    assert _reset_mails(tmp_path)[-1].to == user.email
    assert done.status_code == 204
    assert logged.get("/api/v1/auth/me").status_code == 401  # the old session is over
    assert apis.make().login(user, PASSWORD).status_code == 401  # the old password no longer works
    assert apis.make().login(user, NEW).status_code == 200
    assert read_outbox(tmp_path)[-1].kind == "password-changed"


def test_an_unknown_e_mail_gets_exactly_the_same_answer_and_no_mail(
    apis: ApiFactory, users: UserFactory, tmp_path: Path
) -> None:
    known = users.make("staff")
    api = apis.make()

    for_known = api.post(REQUEST, {"email": known.email})
    for_unknown = apis.make().post(REQUEST, {"email": "nobody-here@example.test"})

    assert (for_known.status_code, for_known.json()) == (
        for_unknown.status_code,
        for_unknown.json(),
    )
    assert [m.to for m in _reset_mails(tmp_path)] == [known.email]


def test_an_inactive_account_gets_the_same_answer_and_no_mail(
    apis: ApiFactory, users: UserFactory, tmp_path: Path
) -> None:
    gone = users.make("staff", active=False)

    answer = apis.make().post(REQUEST, {"email": gone.email})

    assert answer.status_code == 202 and _reset_mails(tmp_path) == []


def test_a_link_works_once_only(apis: ApiFactory, users: UserFactory, tmp_path: Path) -> None:
    user = users.make("staff")
    api = apis.make()
    api.post(REQUEST, {"email": user.email})
    token = _reset_mails(tmp_path)[-1].token

    first = api.post(CONFIRM, {"token": token, "new_password": NEW})
    again = apis.make().post(CONFIRM, {"token": token, "new_password": "outra-senha-bem-longa-2"})

    assert first.status_code == 204
    assert again.status_code == 400 and again.json()["code"] == "reset_invalid"
    assert apis.make().login(user, NEW).status_code == 200  # the second attempt changed nothing


def test_a_new_request_cancels_the_previous_link(
    apis: ApiFactory, users: UserFactory, tmp_path: Path
) -> None:
    user = users.make("staff")
    api = apis.make()
    api.post(REQUEST, {"email": user.email})
    old = _reset_mails(tmp_path)[-1].token
    api.post(REQUEST, {"email": user.email})
    new = _reset_mails(tmp_path)[-1].token

    refused = apis.make().post(CONFIRM, {"token": old, "new_password": NEW})
    accepted = apis.make().post(CONFIRM, {"token": new, "new_password": NEW})

    assert old != new and refused.status_code == 400 and accepted.status_code == 204


def test_an_expired_link_is_refused(
    apis: ApiFactory, users: UserFactory, tmp_path: Path, admin_engine: Engine
) -> None:
    user = users.make("staff")
    api = apis.make()
    api.post(REQUEST, {"email": user.email})
    token = _reset_mails(tmp_path)[-1].token
    with admin_engine.begin() as connection:
        connection.execute(
            text(
                "UPDATE password_reset_tokens SET created_at = now() - interval '2 hours', "
                "expires_at = now() - interval '1 hour' WHERE user_id = "
                "(SELECT id FROM users WHERE email = :e)"
            ),
            {"e": user.email},
        )

    answer = apis.make().post(CONFIRM, {"token": token, "new_password": NEW})

    assert answer.status_code == 400 and answer.json()["code"] == "reset_invalid"


@pytest.mark.parametrize("token", ["", "short", "x" * 43, "A" * 300])
def test_a_token_that_is_not_one_of_ours_is_the_same_refusal(apis: ApiFactory, token: str) -> None:
    answer = apis.make().post(CONFIRM, {"token": token, "new_password": NEW})

    assert answer.status_code in (400, 422)
    if answer.status_code == 400:
        assert answer.json()["code"] == "reset_invalid"


def test_a_weak_password_is_refused_and_the_link_stays_good(
    apis: ApiFactory, users: UserFactory, tmp_path: Path
) -> None:
    user = users.make("staff")
    api = apis.make()
    api.post(REQUEST, {"email": user.email})
    token = _reset_mails(tmp_path)[-1].token

    weak = api.post(CONFIRM, {"token": token, "new_password": "curta"})
    strong = apis.make().post(CONFIRM, {"token": token, "new_password": NEW})

    assert weak.status_code == 422 and weak.json()["code"] == "weak_password"
    assert strong.status_code == 204


def test_asking_over_and_over_is_slowed_down_the_same_for_any_e_mail(
    apis: ApiFactory,
) -> None:
    api = apis.make()

    answers = [api.post(REQUEST, {"email": "someone@example.test"}).status_code for _ in range(7)]

    assert answers[:5] == [202] * 5 and 429 in answers[5:]
