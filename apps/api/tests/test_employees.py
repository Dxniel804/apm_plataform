"""The team of the school (/employees): the management brings employees in, sees who is in and what
is pending, resends or cancels an invitation, and suspends or brings back an employee."""

from pathlib import Path

from tests.authsupport import Api, ApiFactory, UserFactory, read_outbox

BASE = "/api/v1/employees"
_MAILS: dict[tuple[str, str], str] = {}


def mail(users: UserFactory, label: str) -> str:
    """The same address for the same label inside one test (the world cleans these on teardown)."""
    return _MAILS.setdefault((users.world.suffix, label), users.world.email(label))


def _as(apis: ApiFactory, users: UserFactory, role: str, **kwargs: object) -> Api:
    api = apis.make()
    assert api.login(users.make(role, **kwargs)).status_code == 200  # type: ignore[arg-type]
    return api


def test_the_management_creates_an_employee_and_the_e_mail_names_them(
    apis: ApiFactory, users: UserFactory, tmp_path: Path
) -> None:
    gestao = _as(apis, users, "secretaria")

    made = gestao.post(BASE, {"full_name": "Maria Silva", "email": mail(users, "maria")})

    assert made.status_code == 201, made.text
    assert made.json()["role"] == "staff" and made.json()["email"] == mail(users, "maria")
    message = read_outbox(tmp_path)[-1]
    assert message.kind == "invitation" and message.to == mail(users, "maria")
    assert "Maria Silva" in message.body and "token=" in message.body


def test_the_employee_accepts_and_then_appears_among_the_people_of_the_school(
    apis: ApiFactory, users: UserFactory, tmp_path: Path
) -> None:
    gestao = _as(apis, users, "secretaria")
    gestao.post(BASE, {"full_name": "João Souza", "email": mail(users, "joao")})
    token = read_outbox(tmp_path)[-1].token
    before = gestao.get(BASE).json()

    accepted = apis.make().post(
        "/api/v1/invitations/accept",
        {"token": token, "full_name": "João Souza", "password": "uma-senha-bem-longa-123"},
    )
    after = gestao.get(BASE).json()

    assert mail(users, "joao") in [p["email"] for p in before["pending"]]
    assert accepted.status_code == 201, accepted.text
    assert mail(users, "joao") not in [p["email"] for p in after["pending"]]
    joao = next(m for m in after["members"] if m["email"] == mail(users, "joao"))
    assert joao["role"] == "staff" and joao["status"] == "active" and joao["can_manage"] is True


def test_the_secretaria_brings_secretarias_and_employees_in_and_an_employee_nobody(
    apis: ApiFactory, users: UserFactory
) -> None:
    gestao = _as(apis, users, "secretaria")
    staff = _as(apis, users, "staff")

    other_secretaria = gestao.post(
        BASE, {"full_name": "Fulano", "email": mail(users, "fulano"), "role": "secretaria"}
    )
    gone_role = gestao.post(
        BASE, {"full_name": "Fulano", "email": mail(users, "fulano3"), "role": "viewer"}
    )
    by_staff = staff.post(BASE, {"full_name": "Fulano", "email": mail(users, "fulano2")})
    listing_by_staff = staff.get(BASE)

    assert other_secretaria.status_code == 201 and gone_role.status_code == 422
    assert by_staff.status_code == 403 and listing_by_staff.status_code == 403


def test_the_same_e_mail_twice_is_refused_and_so_is_a_person_already_in(
    apis: ApiFactory, users: UserFactory
) -> None:
    gestao = _as(apis, users, "secretaria")
    member = users.make("staff", label="already")
    body = {"full_name": "Ana Paula", "email": mail(users, "ana")}

    first = gestao.post(BASE, body)
    again = gestao.post(BASE, body)
    inside = gestao.post(BASE, {"full_name": "Quem Ja Esta", "email": member.email})

    assert first.status_code == 201
    assert again.status_code == 409 and again.json()["code"] == "invitation_pending"
    assert inside.status_code == 409 and inside.json()["code"] == "already_member"


def test_resending_makes_a_new_link_and_the_old_one_stops_working(
    apis: ApiFactory, users: UserFactory, tmp_path: Path
) -> None:
    gestao = _as(apis, users, "secretaria")
    made = gestao.post(BASE, {"full_name": "Rita Lima", "email": mail(users, "rita")})
    old = read_outbox(tmp_path)[-1].token

    again = gestao.post(f"{BASE}/invitations/{made.json()['id']}/resend")
    new = read_outbox(tmp_path)[-1].token
    stale = apis.make().post(
        "/api/v1/invitations/accept",
        {"token": old, "full_name": "Rita Lima", "password": "uma-senha-bem-longa-123"},
    )

    assert again.status_code == 201 and old != new
    assert stale.status_code == 400 and stale.json()["code"] == "invitation_invalid"
    waiting = [p for p in gestao.get(BASE).json()["pending"] if p["email"] == mail(users, "rita")]
    assert len(waiting) == 1


def test_cancelling_an_invitation_takes_it_off_the_list_and_kills_the_link(
    apis: ApiFactory, users: UserFactory, tmp_path: Path
) -> None:
    gestao = _as(apis, users, "secretaria")
    made = gestao.post(BASE, {"full_name": "Paulo Reis", "email": mail(users, "paulo")})
    token = read_outbox(tmp_path)[-1].token

    cancelled = gestao.client.delete(
        f"{BASE}/invitations/{made.json()['id']}",
        headers={"Origin": gestao.origin, "X-CSRF-Token": gestao.csrf or ""},
    )
    accepted = apis.make().post(
        "/api/v1/invitations/accept",
        {"token": token, "full_name": "Paulo Reis", "password": "uma-senha-bem-longa-123"},
    )

    assert cancelled.status_code == 204
    assert mail(users, "paulo") not in [p["email"] for p in gestao.get(BASE).json()["pending"]]
    assert accepted.status_code == 400


def test_suspending_ends_the_access_and_bringing_back_gives_it_again(
    apis: ApiFactory, users: UserFactory
) -> None:
    gestao = _as(apis, users, "secretaria")
    employee = users.make("staff", label="employee")
    session = apis.make()
    assert session.login(employee).status_code == 200
    membership = next(m for m in gestao.get(BASE).json()["members"] if m["email"] == employee.email)

    suspended = gestao.post(f"{BASE}/{membership['membership_id']}/suspend")
    blocked = session.get("/api/v1/auth/me")
    brought_back = gestao.post(f"{BASE}/{membership['membership_id']}/activate")

    assert suspended.status_code == 204
    assert blocked.status_code in (401, 403)
    assert brought_back.status_code == 204
    assert apis.make().login(employee).status_code == 200


def test_nobody_suspends_themselves_but_a_secretaria_may_suspend_another(
    apis: ApiFactory, users: UserFactory
) -> None:
    gestao_user = users.make("secretaria")
    gestao = apis.make()
    gestao.login(gestao_user)
    members = gestao.get(BASE).json()["members"]
    me = next(m for m in members if m["email"] == gestao_user.email)
    admin = users.make("secretaria", label="admin")
    members = gestao.get(BASE).json()["members"]
    above = next(m for m in members if m["email"] == admin.email)

    on_myself = gestao.post(f"{BASE}/{me['membership_id']}/suspend")
    on_admin = gestao.post(f"{BASE}/{above['membership_id']}/suspend")

    assert me["is_you"] and me["can_manage"] is False and above["can_manage"] is True
    assert on_myself.status_code == 404 and on_admin.status_code == 204


def test_another_school_does_not_see_the_team(apis: ApiFactory, users: UserFactory) -> None:
    mine = _as(apis, users, "secretaria")
    other = _as(apis, users, "secretaria", org="a", school="2", label="other")
    users.make("staff", label="mine-staff")

    seen = [m["email"] for m in other.get(BASE).json()["members"]]

    assert all("mine-staff" not in email for email in seen)
    assert len(mine.get(BASE).json()["members"]) >= 2


def test_the_team_says_which_roles_the_caller_may_bring_in(
    apis: ApiFactory, users: UserFactory
) -> None:
    management = _as(apis, users, "secretaria").get(BASE).json()
    director = _as(apis, users, "secretaria", label="director").get(BASE).json()

    assert management["invitable_roles"] == ["secretaria", "staff"]
    assert director["invitable_roles"] == ["secretaria", "staff"]
