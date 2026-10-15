# ruff: noqa: E501  (SQL and long assertions)
"""What the management does with a line that is in the bank and not in the ledger (0018): register
the money or ignore the line, once, and the next comparison pairs what was registered."""

from datetime import date, timedelta
from typing import Any

from sqlalchemy import Engine, text

from tests.authsupport import ApiFactory
from tests.campaigns.support import committed_manager
from tests.expenses.support import Client
from tests.public.conftest import PublicSchool
from tests.reconciliation.ofx_samples import e2e, sgml


def _imported(gestao: Client, lines: list[tuple[str, date, str, str]], day: date) -> str:
    account = gestao.post(
        "/reconciliation/accounts", {"nickname": "Conta principal", "bank_name": "Banco do Brasil"}
    ).json()["id"]
    sent = gestao.post(
        "/reconciliation/imports",
        data={"bank_account_id": account},
        files={"file": ("extrato.ofx", sgml(lines, day, day), "application/x-ofx")},
    )
    assert sent.status_code == 201, sent.text
    return str(sent.json()["id"])


def _missing(gestao: Client, import_id: str) -> Any:
    return gestao.get(f"/reconciliation/imports/{import_id}").json()


def _line(body: Any, memo: str) -> str:
    return str(next(ln for ln in body["missing_in_system"] if ln["memo"] == memo)["line_id"])


def test_a_pix_straight_to_the_key_is_registered_once_and_then_matches(
    apis: ApiFactory, school: PublicSchool, admin_engine: Engine
) -> None:
    gestao = committed_manager(apis, admin_engine, school)
    day = date.today() - timedelta(days=2)
    import_id = _imported(gestao, [("p1", day, "12.34", f"PIX RECEBIDO {e2e(901)} MARIA")], day)
    line = _line(_missing(gestao, import_id), f"PIX RECEBIDO {e2e(901)} MARIA")

    done = gestao.post(f"/reconciliation/lines/{line}/actions", {"action": "REGISTER_INCOME"})
    again = gestao.post(f"/reconciliation/lines/{line}/actions", {"action": "REGISTER_INCOME"})
    body = _missing(gestao, import_id)

    assert done.status_code == 201 and done.json()["action"] == "REGISTERED", done.text
    assert again.status_code == 409 and again.json()["code"] == "already_resolved"
    assert body["missing_in_system"] == [] and body["divergences"] == []
    assert [m["entry"]["amount_cents"] for m in body["matched"]] == [1234]
    with admin_engine.connect() as conn:
        count, method, ref, settled = conn.execute(
            text(
                "SELECT count(*) OVER (), c.method, c.external_reference, (f.settled_at AT TIME ZONE st.timezone)::date "
                "FROM contributions c JOIN financial_transactions f ON f.id = c.transaction_id "
                "JOIN school_settings st ON st.school_id = f.school_id WHERE c.school_id = :s"
            ),
            {"s": school.fresh.school},
        ).one()
    assert (count, method, ref, settled) == (1, "PIX_DIRECT", e2e(901), day)


def test_a_transfer_without_an_id_is_a_transfer_and_a_pix_needs_the_id(
    apis: ApiFactory, school: PublicSchool, admin_engine: Engine
) -> None:
    gestao = committed_manager(apis, admin_engine, school)
    day = date.today() - timedelta(days=2)
    import_id = _imported(gestao, [("t1", day, "50.00", "TED RECEBIDA ASSOCIADO")], day)
    line = _line(_missing(gestao, import_id), "TED RECEBIDA ASSOCIADO")

    pix = gestao.post(
        f"/reconciliation/lines/{line}/actions",
        {"action": "REGISTER_INCOME", "method": "PIX_DIRECT"},
    )
    ted = gestao.post(
        f"/reconciliation/lines/{line}/actions",
        {"action": "REGISTER_INCOME", "category_key": "donation", "guardian_name": "Associado"},
    )

    assert pix.status_code == 422
    assert ted.status_code == 201, ted.text
    assert [m["entry"]["amount_cents"] for m in _missing(gestao, import_id)["matched"]] == [5000]


def test_a_bank_fee_becomes_a_paid_expense_in_the_fee_category(
    apis: ApiFactory, school: PublicSchool, admin_engine: Engine
) -> None:
    gestao = committed_manager(apis, admin_engine, school)
    day = date.today() - timedelta(days=2)
    import_id = _imported(
        gestao, [("f1", day, "-0.80", "TARIFA PIX"), ("i1", day, "10.00", "DEPOSITO")], day
    )
    body = _missing(gestao, import_id)

    wrong = gestao.post(
        f"/reconciliation/lines/{_line(body, 'DEPOSITO')}/actions", {"action": "REGISTER_FEE"}
    )
    done = gestao.post(
        f"/reconciliation/lines/{_line(body, 'TARIFA PIX')}/actions", {"action": "REGISTER_FEE"}
    )

    assert wrong.status_code == 422
    assert done.status_code == 201, done.text
    after = _missing(gestao, import_id)
    assert [(m["entry"]["kind"], m["entry"]["amount_cents"]) for m in after["matched"]] == [
        ("EXPENSE", -80)
    ]
    with admin_engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT f.status, f.origin_type, c.key, e.paid_by FROM financial_transactions f "
                "JOIN categories c ON c.id = f.category_id JOIN expenses e ON e.transaction_id = f.id "
                "WHERE f.school_id = :s AND f.kind = 'EXPENSE'"
            ),
            {"s": school.fresh.school},
        ).one()
    assert tuple(row) == ("PAID", "BANK", "bank_fees", "APM")


def test_ignoring_a_line_needs_a_reason_and_keeps_it(
    apis: ApiFactory, school: PublicSchool, admin_engine: Engine
) -> None:
    gestao = committed_manager(apis, admin_engine, school)
    day = date.today() - timedelta(days=2)
    import_id = _imported(gestao, [("g1", day, "-150.00", "PAGAMENTO BOLETO")], day)
    line = _line(_missing(gestao, import_id), "PAGAMENTO BOLETO")

    without = gestao.post(f"/reconciliation/lines/{line}/actions", {"action": "IGNORE"})
    short = gestao.post(
        f"/reconciliation/lines/{line}/actions", {"action": "IGNORE", "reason": "x"}
    )
    done = gestao.post(
        f"/reconciliation/lines/{line}/actions",
        {"action": "IGNORE", "reason": "Pago pela prefeitura, não é da APM"},
    )
    body = _missing(gestao, import_id)

    assert without.status_code == 422 and short.status_code == 422
    assert done.status_code == 201 and done.json()["transaction_id"] is None
    assert body["missing_in_system"] == []
    assert [i["reason"] for i in body["ignored"]] == ["Pago pela prefeitura, não é da APM"]


def test_another_school_cannot_act_on_the_line(
    apis: ApiFactory, school: PublicSchool, other_school: PublicSchool, admin_engine: Engine
) -> None:
    gestao = committed_manager(apis, admin_engine, school)
    stranger = committed_manager(apis, admin_engine, other_school)
    day = date.today() - timedelta(days=2)
    import_id = _imported(gestao, [("x1", day, "-3.00", "TARIFA")], day)
    line = _line(_missing(gestao, import_id), "TARIFA")

    answer = stranger.post(f"/reconciliation/lines/{line}/actions", {"action": "REGISTER_FEE"})

    assert answer.status_code == 404
