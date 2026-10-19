# ruff: noqa: E501  (long assertions)
"""The PDDE accountability layer: the lines of the PDDE bank account are classified (program, custeio
or capital, object) and the expenses are proved by documents. Only a PDDE account's lines count, the
documents never add up to more than the line, a wrong document is voided (never deleted), and the
balance of a program and the alerts are computed on every read."""

import io
import uuid
from datetime import date
from typing import Any

import pytest
from sqlalchemy import Engine

from app.auth.permissions import ROLE_PERMISSIONS, Permission
from app.pdde import nfe
from tests.authsupport import ApiFactory
from tests.campaigns.support import committed_manager
from tests.expenses.support import Client, Scene
from tests.public.conftest import PublicSchool
from tests.reconciliation.ofx_samples import sgml
from tests.statement.pdftext import text_of

ROLES = ["secretaria", "staff"]
MANAGE = {r for r in ROLES if Permission.RECONCILIATION_MANAGE in ROLE_PERMISSIONS[r]}


def _key(prefix: str = "35250312345678000190550010000001231000001234"[:43]) -> str:
    """A valid 44-digit NF-e key: the 43 digits and their check digit."""
    return prefix + str(nfe.check_digit(prefix))


def _account(gestao: Client, nickname: str, purpose: str) -> str:
    made = gestao.post(
        "/reconciliation/accounts",
        {"nickname": nickname, "bank_name": "Banco do Brasil", "purpose": purpose},
    )
    assert made.status_code == 201, made.text
    return str(made.json()["id"])


def _import(gestao: Client, account: str, data: bytes) -> None:
    sent = gestao.post(
        "/reconciliation/imports",
        data={"bank_account_id": account},
        files={"file": ("extrato.ofx", io.BytesIO(data), "application/x-ofx")},
    )
    assert sent.status_code == 201, sent.text


MARCH = [
    ("F1", date(2025, 3, 10), "10000.00", "CREDITO REPASSE FNDE"),
    ("F2", date(2025, 3, 20), "-1500.00", "PAGAMENTO MATERIAL ESCOLAR"),
    ("F3", date(2025, 3, 25), "-12.00", "TARIFA PACOTE DE SERVICOS"),
]


def _setup(apis: ApiFactory, school: PublicSchool, engine: Engine) -> tuple[Client, dict[str, str]]:
    """A PDDE account with the lines of March 2025, and a general account that must stay out of it."""
    gestao = committed_manager(apis, engine, school)
    pdde = _account(gestao, "PDDE", "PDDE")
    general = _account(gestao, "Geral", "GENERAL")
    _import(gestao, pdde, sgml(MARCH, date(2025, 3, 1), date(2025, 3, 31), "8488.00"))
    _import(
        gestao,
        general,
        sgml(
            [("G1", date(2025, 3, 12), "-50.00", "COMPRA GERAL")],
            date(2025, 3, 1),
            date(2025, 3, 31),
        ),
    )
    listed = gestao.get("/pdde/lines?period=2025-03").json()
    ids = {ln["memo"]: ln["line_id"] for ln in listed["lines"]}
    return gestao, ids


def _transfer(gestao: Client, line: str, **extra: Any) -> Any:
    return gestao.post(
        f"/pdde/lines/{line}/classification", {"kind": "TRANSFER", "program": "BASICO", **extra}
    )


def _expense(gestao: Client, line: str, category: str = "CAPITAL", **extra: Any) -> Any:
    return gestao.post(
        f"/pdde/lines/{line}/classification",
        {
            "kind": "EXPENSE",
            "program": "BASICO",
            "economic_category": category,
            "object": "Material permanente",
            **extra,
        },
    )


def _doc(gestao: Client, line: str, cents: int, **extra: Any) -> Any:
    body = {
        "doc_kind": "RECEIPT",
        "doc_number": "123",
        "issued_on": "2025-03-19",
        "vendor": "Papelaria Exemplo",
        "amount_cents": cents,
        "stamped": True,
    }
    return gestao.post(f"/pdde/lines/{line}/documents", {**body, **extra})


def _line(gestao: Client, ids: dict[str, str], word: str) -> dict[str, Any]:
    listed = gestao.get("/pdde/lines?period=2025-03").json()["lines"]
    return next(ln for ln in listed if word in ln["memo"])


def test_only_the_lines_of_the_pdde_account_are_listed_and_all_start_pending(
    apis: ApiFactory, school: PublicSchool, admin_engine: Engine
) -> None:
    gestao, _ = _setup(apis, school, admin_engine)

    month = gestao.get("/pdde/lines?period=2025-03").json()

    assert [a["nickname"] for a in month["accounts"]] == ["PDDE"]
    assert len(month["lines"]) == 3 and all(
        ln["account_nickname"] == "PDDE" for ln in month["lines"]
    )
    assert all(ln["status"] == "PENDING" and ln["classification"] is None for ln in month["lines"])
    assert month["pending_count"] == 3


def test_a_line_of_another_account_or_school_is_not_there(
    apis: ApiFactory, school: PublicSchool, admin_engine: Engine
) -> None:
    gestao, _ = _setup(apis, school, admin_engine)
    with admin_engine.connect() as conn:
        from sqlalchemy import text

        general: Any = conn.execute(
            text(
                "SELECT id FROM bank_statement_lines WHERE memo LIKE 'COMPRA GERAL%' AND school_id = :s"
            ),
            {"s": school.fresh.school},
        ).scalar_one()

    assert _transfer(gestao, str(general)).status_code == 404
    assert _transfer(gestao, str(uuid.uuid4())).status_code == 404


def test_a_repasse_and_an_expense_are_classified_and_the_latest_decision_counts(
    apis: ApiFactory, school: PublicSchool, admin_engine: Engine
) -> None:
    gestao, ids = _setup(apis, school, admin_engine)
    credit, debit = ids["CREDITO REPASSE FNDE"], ids["PAGAMENTO MATERIAL ESCOLAR"]

    assert _transfer(gestao, credit).status_code == 201
    assert _expense(gestao, debit, "CUSTEIO").status_code == 201
    assert _expense(gestao, debit, "CAPITAL").status_code == 201  # a correction: the latest counts

    credit_line, debit_line = _line(gestao, ids, "REPASSE"), _line(gestao, ids, "MATERIAL")
    assert credit_line["classification"]["kind"] == "TRANSFER" and credit_line["status"] == "DONE"
    assert debit_line["classification"]["economic_category"] == "CAPITAL"
    assert debit_line["status"] == "PENDING"  # an expense needs its documents


def test_the_shape_of_a_classification_is_checked_by_the_site_and_by_the_database(
    apis: ApiFactory, school: PublicSchool, admin_engine: Engine
) -> None:
    gestao, ids = _setup(apis, school, admin_engine)
    credit, debit = ids["CREDITO REPASSE FNDE"], ids["PAGAMENTO MATERIAL ESCOLAR"]
    path = "/pdde/lines/{}/classification"

    no_program = gestao.post(path.format(credit), {"kind": "TRANSFER"})
    expense_without_object = gestao.post(
        path.format(debit), {"kind": "EXPENSE", "program": "BASICO", "economic_category": "CAPITAL"}
    )
    other_without_name = gestao.post(path.format(credit), {"kind": "TRANSFER", "program": "OUTRO"})
    transfer_on_a_debit = _transfer(gestao, debit)  # money in on a line that is money out
    expense_on_a_credit = _expense(gestao, credit)

    assert (
        no_program.status_code
        == expense_without_object.status_code
        == other_without_name.status_code
        == 422
    )
    assert transfer_on_a_debit.status_code == expense_on_a_credit.status_code == 422
    assert (
        gestao.post(
            path.format(credit),
            {"kind": "TRANSFER", "program": "OUTRO", "program_label": "PDDE Mais"},
        ).status_code
        == 201
    )


def test_documents_prove_the_expense_in_parts_and_never_beyond_the_line(
    apis: ApiFactory, school: PublicSchool, admin_engine: Engine
) -> None:
    gestao, ids = _setup(apis, school, admin_engine)
    debit = ids["PAGAMENTO MATERIAL ESCOLAR"]
    assert _expense(gestao, debit).status_code == 201

    first = _doc(gestao, debit, 100_000)
    over = _doc(gestao, debit, 60_000)  # 1.000 + 600 > 1.500
    assert first.status_code == 201 and over.status_code == 422
    assert _line(gestao, ids, "MATERIAL")["status"] == "PARTIAL"

    second = _doc(gestao, debit, 50_000, doc_number="124")
    assert second.status_code == 201
    done = _line(gestao, ids, "MATERIAL")
    assert (
        done["status"] == "DONE"
        and done["documented_cents"] == 150_000
        and len(done["documents"]) == 2
    )


def test_a_wrong_document_is_voided_never_deleted_and_frees_its_value(
    apis: ApiFactory, school: PublicSchool, admin_engine: Engine
) -> None:
    gestao, ids = _setup(apis, school, admin_engine)
    debit = ids["PAGAMENTO MATERIAL ESCOLAR"]
    _expense(gestao, debit)
    wrong = _doc(gestao, debit, 150_000).json()["id"]

    voided = gestao.post(f"/pdde/documents/{wrong}/void", {})
    again = gestao.post(f"/pdde/documents/{wrong}/void", {})
    line = _line(gestao, ids, "MATERIAL")

    assert voided.status_code == 200 and again.status_code == 404
    assert line["documented_cents"] == 0 and line["status"] == "PENDING"
    assert [d["voided"] for d in line["documents"]] == [True]  # still there, marked
    assert _doc(gestao, debit, 150_000, doc_number="125").status_code == 201


def test_the_access_key_of_a_nfe_is_checked_and_one_nfe_proves_one_line(
    apis: ApiFactory, school: PublicSchool, admin_engine: Engine
) -> None:
    gestao, ids = _setup(apis, school, admin_engine)
    debit, fee = ids["PAGAMENTO MATERIAL ESCOLAR"], ids["TARIFA PACOTE DE SERVICOS"]
    key = _key()
    typo = key[:-1] + str((int(key[-1]) + 1) % 10)

    bad = _doc(gestao, debit, 50_000, doc_kind="NFE", access_key=typo)
    spaced = " ".join(key[i : i + 4] for i in range(0, 44, 4))
    good = _doc(gestao, debit, 50_000, doc_kind="NFE", access_key=spaced)
    key_on_a_receipt = _doc(gestao, debit, 10_000, doc_kind="RECEIPT", access_key=key)
    reused = _doc(gestao, fee, 1_000, doc_kind="NFE", access_key=key)

    assert bad.status_code == 422 and key_on_a_receipt.status_code == 422
    assert good.status_code == 201
    assert (
        _line(gestao, ids, "MATERIAL")["documents"][0]["access_key"] == key
    )  # kept without the spaces
    assert reused.status_code == 409 and reused.json()["code"] == "document_key_used"


def test_a_document_belongs_to_money_that_left_the_account(
    apis: ApiFactory, school: PublicSchool, admin_engine: Engine
) -> None:
    gestao, ids = _setup(apis, school, admin_engine)

    on_a_credit = _doc(gestao, ids["CREDITO REPASSE FNDE"], 1_000)

    assert on_a_credit.status_code == 422 and on_a_credit.json()["code"] == "line_is_not_an_expense"


def test_the_summary_gives_each_program_its_balance_and_warns_about_what_needs_attention(
    apis: ApiFactory, school: PublicSchool, admin_engine: Engine
) -> None:
    gestao, ids = _setup(apis, school, admin_engine)
    assert (
        _transfer(gestao, ids["CREDITO REPASSE FNDE"], economic_category="CAPITAL").status_code
        == 201
    )
    assert _expense(gestao, ids["PAGAMENTO MATERIAL ESCOLAR"], "CAPITAL").status_code == 201

    summary = gestao.get("/pdde/summary?year=2025").json()

    (basico,) = summary["programs"]
    assert basico["program"] == "BASICO" and basico["received_cents"] == 1_000_000
    assert basico["spent_capital_cents"] == 150_000 and basico["spent_custeio_cents"] == 0
    assert basico["balance_cents"] == 850_000
    codes = {a["code"] for a in summary["alerts"]}
    # the bank fee in the PDDE account, the lines still pending, December without its balance
    assert {"fee_on_pdde_account", "pending_lines", "year_end_reconciliation"} <= codes
    fee = next(a for a in summary["alerts"] if a["code"] == "fee_on_pdde_account")
    assert fee["count"] == 1 and fee["cents"] == 1200
    after = "deadline" if date.today() <= date(2026, 4, 30) else "deadline_passed"
    assert after in codes


def test_spending_more_than_came_in_a_category_is_flagged_and_a_december_statement_gives_the_balance(
    apis: ApiFactory, school: PublicSchool, admin_engine: Engine
) -> None:
    gestao, ids = _setup(apis, school, admin_engine)
    assert (
        _transfer(gestao, ids["CREDITO REPASSE FNDE"], economic_category="CUSTEIO").status_code
        == 201
    )
    assert _expense(gestao, ids["PAGAMENTO MATERIAL ESCOLAR"], "CUSTEIO").status_code == 201
    pdde = gestao.get("/reconciliation/accounts").json()
    account = next(a["id"] for a in pdde if a["purpose"] == "PDDE")
    _import(
        gestao,
        account,
        sgml(
            [("D1", date(2025, 12, 30), "-200.00", "PAGAMENTO DEZEMBRO")],
            date(2025, 12, 1),
            date(2025, 12, 31),
            "8288.00",
        ),
    )
    december = next(ln for ln in gestao.get("/pdde/lines?period=2025-12").json()["lines"])
    assert _transfer(gestao, december["line_id"]) is not None
    assert (
        _expense(gestao, december["line_id"], "CUSTEIO", object="Material de consumo").status_code
        == 201
    )

    summary = gestao.get("/pdde/summary?year=2025").json()

    assert summary["year_end"][0]["balance_cents"] == 828_800
    assert "year_end_reconciliation" not in {a["code"] for a in summary["alerts"]}
    # 10.000 came as custeio; 1.500 + 200 went out as custeio: no excess, so no warning
    assert "spent_over_received" not in {a["code"] for a in summary["alerts"]}
    assert (
        gestao.post(
            f"/pdde/lines/{december['line_id']}/classification",
            {"kind": "TRANSFER", "program": "BASICO", "economic_category": "CAPITAL"},
        ).status_code
        == 422
    )  # money out is not a repasse


def test_a_year_report_is_a_spreadsheet_and_a_pdf_in_the_order_of_the_bank(
    apis: ApiFactory, school: PublicSchool, admin_engine: Engine
) -> None:
    gestao, ids = _setup(apis, school, admin_engine)
    _transfer(gestao, ids["CREDITO REPASSE FNDE"])
    _expense(gestao, ids["PAGAMENTO MATERIAL ESCOLAR"])
    _doc(
        gestao,
        ids["PAGAMENTO MATERIAL ESCOLAR"],
        150_000,
        vendor='=HYPERLINK("x")',
        doc_number=None,
        stamped=False,
    )

    csv_response = gestao.get("/pdde/report.csv?year=2025")
    pdf_response = gestao.get("/pdde/report.pdf?year=2025")

    assert csv_response.status_code == 200 and csv_response.headers["content-type"].startswith(
        "text/csv"
    )
    text = csv_response.content.decode("utf-8-sig")
    assert (
        text.splitlines()[0]
        == "Data;Valor;Conta;Tipo;Programa;Custeio/Capital;Objeto;Documentos;Situação"
    )
    assert "10/03/2025;10000,00;PDDE;Repasse;PDDE Básico" in text
    assert "20/03/2025;-1500,00;PDDE;Despesa" in text  # a number is never prefixed
    assert "'=HYPERLINK" in text and "sem carimbo" in text  # shown, never run
    assert pdf_response.status_code == 200 and pdf_response.content.startswith(b"%PDF-")
    pdf_text = text_of(pdf_response.content)
    assert "PDDE: prestação de contas de 2025" in pdf_text and "Confere com o original" in pdf_text
    assert "PDDE Básico" in pdf_text


@pytest.mark.parametrize("role", ROLES)
def test_every_route_enforces_its_permission(scene: Scene, role: str) -> None:
    person = scene.person(role)
    line = uuid.uuid4()
    routes = [
        ("GET", "/pdde/lines?period=2025-03", None),
        ("GET", "/pdde/summary?year=2025", None),
        ("GET", "/pdde/report.csv?year=2025", None),
        ("GET", "/pdde/report.pdf?year=2025", None),
        ("POST", f"/pdde/lines/{line}/classification", {"kind": "INELIGIBLE"}),
        ("POST", f"/pdde/documents/{line}/void", {}),
    ]

    for method, tail, body in routes:
        answer = person.request(method, tail, json=body)
        if role in MANAGE:
            assert answer.status_code in (200, 404), (tail, answer.text)
        else:
            assert answer.status_code == 403 and answer.json()["code"] == "permission_denied", (
                tail,
                role,
            )


def test_another_school_sees_nothing_of_the_pdde(
    apis: ApiFactory, school: PublicSchool, other_school: PublicSchool, admin_engine: Engine
) -> None:
    gestao, ids = _setup(apis, school, admin_engine)
    stranger = committed_manager(apis, admin_engine, other_school)
    stranger_line = ids["CREDITO REPASSE FNDE"]

    month = stranger.get("/pdde/lines?period=2025-03").json()
    classify = stranger.post(f"/pdde/lines/{stranger_line}/classification", {"kind": "INELIGIBLE"})

    assert month["lines"] == [] and month["accounts"] == []
    assert classify.status_code == 404
