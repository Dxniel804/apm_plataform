# ruff: noqa: E501  (SQL and long assertions)
"""The bank reconciliation end to end: accounts, the import of an OFX file and the comparison with
the ledger. Nothing is ever written to the ledger by it."""

import uuid
from datetime import date
from typing import Any

import pytest
from sqlalchemy import Engine, text

from app.auth.permissions import ROLE_PERMISSIONS, Permission
from tests.authsupport import ApiFactory
from tests.campaigns.support import committed_manager
from tests.expenses.support import Client, Scene
from tests.public.conftest import PublicSchool
from tests.public.support import contribute, txid_of
from tests.reconciliation.ofx_samples import e2e, sgml

ROLES = ["school_admin", "treasurer", "staff", "viewer"]
MANAGE = {r for r in ROLES if Permission.RECONCILIATION_MANAGE in ROLE_PERMISSIONS[r]}


def _account(gestao: Client, nickname: str = "Conta principal") -> str:
    made = gestao.post(
        "/reconciliation/accounts",
        {"nickname": nickname, "bank_name": "Banco do Brasil", "account_last4": "4567"},
    )
    assert made.status_code == 201, made.text
    return str(made.json()["id"])


def _upload(gestao: Client, account_id: str, data: bytes, name: str = "extrato.ofx") -> Any:
    return gestao.post(
        "/reconciliation/imports",
        data={"bank_account_id": account_id},
        files={"file": (name, data, "application/x-ofx")},
    )


def _paid(
    apis: ApiFactory, school: PublicSchool, engine: Engine, cents: int = 3000
) -> tuple[str, date]:
    """A contribution paid by Pix: returns its end-to-end id and the day it was settled."""
    api = apis.make()
    txid = txid_of(contribute(api, school.slug, cents))
    assert api.post(f"/api/v1/dev/sandbox/pix/{txid}/pay", None, csrf=False).status_code == 200
    with engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT pc.end_to_end_id, (f.settled_at AT TIME ZONE 'America/Sao_Paulo')::date FROM pix_charges pc JOIN financial_transactions f ON f.id = pc.transaction_id WHERE pc.school_id = :s ORDER BY pc.created_at DESC LIMIT 1"
            ),
            {"s": school.fresh.school},
        ).one()
    return str(row[0]), row[1]


# --- accounts ---------------------------------------------------------------------------------------


def test_a_school_has_accounts_and_only_keeps_the_last_digits(
    apis: ApiFactory, school: PublicSchool, admin_engine: Engine
) -> None:
    gestao = committed_manager(apis, admin_engine, school)
    _account(gestao)
    pdde = gestao.post(
        "/reconciliation/accounts", {"nickname": "PDDE", "bank_name": "Caixa", "purpose": "PDDE"}
    )

    listing = gestao.get("/reconciliation/accounts").json()

    assert pdde.status_code == 201 and pdde.json()["purpose"] == "PDDE"
    assert {a["nickname"] for a in listing} == {"Conta principal", "PDDE"}
    assert next(a for a in listing if a["nickname"] == "Conta principal")["account_last4"] == "4567"


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"nickname": "", "bank_name": "BB"},
        {"nickname": "x", "bank_name": ""},
        {"nickname": "x", "bank_name": "BB", "account_last4": "12345"},
        {"nickname": "x", "bank_name": "BB", "account_last4": "ab12"},
        {"nickname": "x", "bank_name": "BB", "purpose": "OTHER"},
        {"nickname": "x", "bank_name": "BB", "account_number": "123456789-0"},
    ],
)
def test_a_bad_account_is_a_422(
    apis: ApiFactory, school: PublicSchool, admin_engine: Engine, body: dict[str, Any]
) -> None:
    gestao = committed_manager(apis, admin_engine, school)

    assert gestao.post("/reconciliation/accounts", body).status_code == 422
    assert gestao.get("/reconciliation/accounts").json() == []


def test_two_accounts_cannot_share_a_nickname_and_one_can_be_switched_off(
    apis: ApiFactory, school: PublicSchool, admin_engine: Engine
) -> None:
    gestao = committed_manager(apis, admin_engine, school)
    first = _account(gestao)

    assert (
        gestao.post(
            "/reconciliation/accounts", {"nickname": "Conta principal", "bank_name": "X"}
        ).status_code
        == 409
    )
    off = gestao.patch(f"/reconciliation/accounts/{first}", {"is_active": False})
    assert off.status_code == 200 and off.json()["is_active"] is False
    assert gestao.patch(f"/reconciliation/accounts/{first}", {}).status_code == 422
    assert (
        gestao.patch(f"/reconciliation/accounts/{uuid.uuid4()}", {"nickname": "x"}).status_code
        == 404
    )


# --- importing and comparing ------------------------------------------------------------------------


def test_a_statement_is_compared_with_the_ledger_in_four_lists(
    apis: ApiFactory, school: PublicSchool, admin_engine: Engine
) -> None:
    gestao = committed_manager(apis, admin_engine, school)
    account = _account(gestao)
    paid_e2e, day = _paid(apis, school, admin_engine, 3000)  # matched by the id, at its net amount
    other_e2e, _ = _paid(
        apis, school, admin_engine, 2000
    )  # the bank has it with another amount: divergence
    _paid(apis, school, admin_engine, 4000)  # not in the bank at all
    data = sgml(
        [
            ("b1", day, "29.20", f"PIX RECEBIDO {paid_e2e} CPF 123.456.789-09"),
            ("b2", day, "1.00", f"PIX RECEBIDO {other_e2e}"),
            ("b3", day, "-0.80", "TARIFA PIX"),
            ("b4", day, "-150.00", "PAGAMENTO BOLETO MERCADO"),
        ],
        day, day,
    )  # fmt: skip

    imported = _upload(gestao, account, data)
    assert imported.status_code == 201, imported.text
    assert imported.json()["line_count"] == 4 and imported.json()["new_line_count"] == 4
    body = gestao.get(f"/reconciliation/imports/{imported.json()['id']}").json()

    assert [m["line"]["amount_cents"] for m in body["matched"]] == [2920]
    assert (
        body["matched"][0]["entry"]["amount_cents"] == 3000
        and body["matched"][0]["entry"]["net_cents"] == 2920
    )
    assert [d["reason"] for d in body["divergences"]] == ["amount_differs"]
    assert {ln["memo"] for ln in body["missing_in_system"]} == {
        "TARIFA PIX",
        "PAGAMENTO BOLETO MERCADO",
    }
    assert (
        next(ln for ln in body["missing_in_system"] if ln["memo"] == "TARIFA PIX")["looks_like_fee"]
        is True
    )
    assert [e["amount_cents"] for e in body["missing_in_bank"]] == [4000]


def test_the_comparison_is_read_only_and_the_text_is_stored_without_documents(
    apis: ApiFactory, school: PublicSchool, admin_engine: Engine
) -> None:
    gestao = committed_manager(apis, admin_engine, school)
    account = _account(gestao)
    day = date.today()
    with admin_engine.connect() as conn:
        before: int = conn.execute(
            text("SELECT count(*) FROM financial_transactions WHERE school_id = :s"),
            {"s": school.fresh.school},
        ).scalar_one()

    imported = _upload(
        gestao,
        account,
        sgml([("z1", day, "10.00", "TED DE 123.456.789-09 E 12.345.678/0001-95")], day, day),
    )
    gestao.get(f"/reconciliation/imports/{imported.json()['id']}")

    with admin_engine.connect() as conn:
        after: int = conn.execute(
            text("SELECT count(*) FROM financial_transactions WHERE school_id = :s"),
            {"s": school.fresh.school},
        ).scalar_one()
        memo: str = conn.execute(
            text("SELECT memo FROM bank_statement_lines WHERE school_id = :s"),
            {"s": school.fresh.school},
        ).scalar_one()
    assert before == after  # nothing entered the ledger
    assert memo == "TED DE *** E ***"


def test_the_same_file_twice_is_refused_and_an_overlapping_file_adds_only_what_is_new(
    apis: ApiFactory, school: PublicSchool, admin_engine: Engine
) -> None:
    gestao = committed_manager(apis, admin_engine, school)
    account = _account(gestao)
    day = date.today()
    first = sgml([("1", day, "10.00", "a"), ("2", day, "20.00", "b")], day, day)
    assert _upload(gestao, account, first).status_code == 201

    again = _upload(gestao, account, first)
    overlap = _upload(
        gestao, account, sgml([("2", day, "20.00", "b"), ("3", day, "30.00", "c")], day, day)
    )

    assert again.status_code == 409 and again.json()["code"] == "already_imported"
    assert (
        overlap.status_code == 201
        and overlap.json()["line_count"] == 2
        and overlap.json()["new_line_count"] == 1
    )
    with admin_engine.connect() as conn:
        assert (
            conn.execute(
                text("SELECT count(*) FROM bank_statement_lines WHERE school_id = :s"),
                {"s": school.fresh.school},
            ).scalar_one()
            == 3
        )


@pytest.mark.parametrize(
    ("data", "status", "code"),
    [(b"not a statement", 422, "csv_needs_mapping"), (b"<OFX></OFX>", 422, "ofx_without_lines")],
)
def test_a_bad_file_is_refused_with_a_code_and_stores_nothing(
    apis: ApiFactory,
    school: PublicSchool,
    admin_engine: Engine,
    data: bytes,
    status: int,
    code: str,
) -> None:
    gestao = committed_manager(apis, admin_engine, school)
    account = _account(gestao)

    answer = _upload(gestao, account, data)

    assert answer.status_code == status and answer.json()["code"] == code
    assert gestao.get("/reconciliation/imports").json()["items"] == []


def test_an_unknown_or_switched_off_account_and_a_missing_file_are_refused(
    apis: ApiFactory, school: PublicSchool, admin_engine: Engine
) -> None:
    gestao = committed_manager(apis, admin_engine, school)
    account = _account(gestao)
    day = date.today()
    data = sgml([("1", day, "10.00", "a")], day, day)
    gestao.patch(f"/reconciliation/accounts/{account}", {"is_active": False})

    assert _upload(gestao, account, data).status_code == 409
    assert _upload(gestao, str(uuid.uuid4()), data).status_code == 404
    assert (
        gestao.post("/reconciliation/imports", data={"bank_account_id": account}).status_code == 422
    )
    assert (
        gestao.post(
            "/reconciliation/imports",
            data={"bank_account_id": "x"},
            files={"file": ("a.ofx", data, "application/x-ofx")},
        ).status_code
        == 422
    )


# --- who can see it ---------------------------------------------------------------------------------


@pytest.mark.parametrize("role", ROLES)
def test_every_route_enforces_its_permission(scene: Scene, role: str) -> None:
    person = scene.person(role)
    routes = [
        ("GET", "/reconciliation/accounts"),
        ("GET", "/reconciliation/imports"),
        ("GET", f"/reconciliation/imports/{uuid.uuid4()}"),
    ]

    for method, tail in routes:
        answer = person.request(method, tail)
        if role in MANAGE:
            assert answer.status_code in (200, 404), (tail, answer.text)
        else:
            assert answer.status_code == 403 and answer.json()["code"] == "permission_denied", (
                tail,
                role,
            )
    assert person.post(
        "/reconciliation/accounts", {"nickname": f"conta-{uuid.uuid4().hex[:8]}", "bank_name": "b"}
    ).status_code == (201 if role in MANAGE else 403)


def test_another_school_sees_nothing_of_the_statement(
    apis: ApiFactory, school: PublicSchool, other_school: PublicSchool, admin_engine: Engine
) -> None:
    gestao = committed_manager(apis, admin_engine, school)
    account = _account(gestao)
    day = date.today()
    imported = _upload(gestao, account, sgml([("1", day, "10.00", "a")], day, day)).json()
    stranger = committed_manager(apis, admin_engine, other_school)

    assert stranger.get(f"/reconciliation/imports/{imported['id']}").status_code == 404
    assert stranger.get("/reconciliation/imports").json()["items"] == []
    assert stranger.get("/reconciliation/accounts").json() == []
    assert (
        _upload(stranger, account, sgml([("9", day, "9.00", "z")], day, day)).status_code == 404
    )  # an account of another school
    assert (
        stranger.get(
            f"/reconciliation/imports/{imported['id']}", school=school.fresh.school
        ).status_code
        == 404
    )


def test_the_same_file_in_two_schools_is_not_a_clash(
    apis: ApiFactory, school: PublicSchool, other_school: PublicSchool, admin_engine: Engine
) -> None:
    day = date.today()
    data = sgml([("1", day, "10.00", "a")], day, day)
    one, two = (
        committed_manager(apis, admin_engine, school),
        committed_manager(apis, admin_engine, other_school),
    )

    assert _upload(one, _account(one), data).status_code == 201
    assert (
        _upload(two, _account(two), data).status_code == 201
    )  # the answer for a school never tells about another


def test_e2e_helper_is_a_valid_id() -> None:
    assert len(e2e(1)) == 32
