# ruff: noqa: E501  (long assertions)
"""The official form of the FNDE (Demonstrativo): the data it asks for is kept (the entity, the carry-over,
the CNPJ or CPF of whoever was paid, the payment number, the yield and the return), and the form is
filled with sums of what was classified, listing what is missing instead of hiding it."""

import io
from datetime import date
from typing import Any

from sqlalchemy import Engine

from app.pdde import tax_id
from tests.authsupport import ApiFactory
from tests.campaigns.support import committed_manager
from tests.expenses.support import Client
from tests.pdde.test_pdde import _account, _doc, _key
from tests.public.conftest import PublicSchool
from tests.reconciliation.ofx_samples import sgml
from tests.statement.pdftext import text_of

CNPJ = "11222333000181"  # a number that passes the check digits (it is nobody's)
CPF = "11144477735"
ENTITY = {
    "legal_name": "ASSOCIACAO DE PAIS E MESTRES EXEMPLO",
    "cnpj": "11.222.333/0001-81",
    "address": "Rua das Flores, 100",
    "city": "Jundiaí",
    "state": "sp",
}

LINES = [
    ("F1", date(2025, 3, 10), "5000.00", "CREDITO REPASSE CUSTEIO"),
    ("F2", date(2025, 3, 10), "2000.00", "CREDITO REPASSE CAPITAL"),
    ("F3", date(2025, 3, 20), "-1500.00", "PAGAMENTO MATERIAL ESCOLAR"),
    ("F4", date(2025, 3, 31), "12.34", "RENDIMENTO APLICACAO"),
    ("F5", date(2025, 4, 2), "-100.00", "DEVOLUCAO AO FNDE"),
]


def test_a_cnpj_and_a_cpf_are_checked_by_their_digits() -> None:
    assert tax_id.is_valid_cnpj(CNPJ) and not tax_id.is_valid_cnpj("11222333000182")
    assert tax_id.is_valid_cpf(CPF) and not tax_id.is_valid_cpf("11144477736")
    assert not tax_id.is_valid_cnpj("00000000000000") and not tax_id.is_valid_cpf("11111111111")
    assert (
        tax_id.normalize("11.222.333/0001-81") == CNPJ and tax_id.mask(CNPJ) == "11.222.333/0001-81"
    )
    assert tax_id.mask(CPF) == "111.444.777-35" and tax_id.mask(None) == ""


def _setup(apis: ApiFactory, school: PublicSchool, engine: Engine) -> tuple[Client, dict[str, str]]:
    gestao = committed_manager(apis, engine, school)
    account = _account(gestao, "PDDE", "PDDE")
    sent = gestao.post(
        "/reconciliation/imports",
        data={"bank_account_id": account},
        files={
            "file": (
                "extrato.ofx",
                io.BytesIO(sgml(LINES, date(2025, 3, 1), date(2025, 4, 30), "5412.34")),
                "application/x-ofx",
            )
        },
    )
    assert sent.status_code == 201, sent.text
    by_memo = {
        ln["memo"]: ln["line_id"]
        for p in ("2025-03", "2025-04")
        for ln in gestao.get(f"/pdde/lines?period={p}").json()["lines"]
    }
    return gestao, by_memo


def _classify(gestao: Client, line: str, body: dict[str, Any]) -> Any:
    return gestao.post(f"/pdde/lines/{line}/classification", {"program": "BASICO", **body})


def _fill(gestao: Client, ids: dict[str, str]) -> None:
    assert (
        _classify(
            gestao,
            ids["CREDITO REPASSE CUSTEIO"],
            {"kind": "TRANSFER", "economic_category": "CUSTEIO"},
        ).status_code
        == 201
    )
    assert (
        _classify(
            gestao,
            ids["CREDITO REPASSE CAPITAL"],
            {"kind": "TRANSFER", "economic_category": "CAPITAL"},
        ).status_code
        == 201
    )
    assert (
        _classify(
            gestao,
            ids["PAGAMENTO MATERIAL ESCOLAR"],
            {
                "kind": "EXPENSE",
                "economic_category": "CAPITAL",
                "object": "Material permanente",
                "payment_number": "OB 123",
            },
        ).status_code
        == 201
    )
    assert (
        _classify(
            gestao, ids["RENDIMENTO APLICACAO"], {"kind": "YIELD", "economic_category": "CUSTEIO"}
        ).status_code
        == 201
    )
    assert (
        _classify(
            gestao,
            ids["DEVOLUCAO AO FNDE"],
            {"kind": "RETURN_TO_FNDE", "economic_category": "CUSTEIO"},
        ).status_code
        == 201
    )


def test_the_entity_is_checked_and_the_latest_one_counts(
    apis: ApiFactory, school: PublicSchool, admin_engine: Engine
) -> None:
    gestao = committed_manager(apis, admin_engine, school)
    assert gestao.get("/pdde/entity").json() is None

    bad_cnpj = gestao.post("/pdde/entity", {**ENTITY, "cnpj": "11222333000182"})
    bad_state = gestao.post("/pdde/entity", {**ENTITY, "state": "XX"})
    saved = gestao.post("/pdde/entity", ENTITY)
    corrected = gestao.post("/pdde/entity", {**ENTITY, "address": "Rua das Flores, 200"})

    assert bad_cnpj.status_code == bad_state.status_code == 422
    assert saved.status_code == corrected.status_code == 201
    assert gestao.get("/pdde/entity").json() == {
        "legal_name": ENTITY["legal_name"],
        "cnpj": CNPJ,
        "address": "Rua das Flores, 200",
        "city": "Jundiaí",
        "state": "SP",
    }


def test_the_carryover_needs_the_name_of_another_program_and_the_latest_counts(
    apis: ApiFactory, school: PublicSchool, admin_engine: Engine
) -> None:
    gestao = committed_manager(apis, admin_engine, school)
    base = {"year": 2025, "program": "BASICO", "custeio_cents": 100_000, "capital_cents": 50_000}

    assert gestao.post("/pdde/carryovers", {**base, "program": "OUTRO"}).status_code == 422
    assert (
        gestao.post("/pdde/carryovers", {**base, "program_label": "PDDE Mais"}).status_code == 422
    )
    assert gestao.post("/pdde/carryovers", {**base, "custeio_cents": -1}).status_code == 422
    assert gestao.post("/pdde/carryovers", base).status_code == 201
    assert gestao.post("/pdde/carryovers", {**base, "custeio_cents": 120_000}).status_code == 201

    assert gestao.get("/pdde/carryovers?year=2025").json() == [
        {
            "program": "BASICO",
            "program_label": None,
            "custeio_cents": 120_000,
            "capital_cents": 50_000,
        }
    ]
    assert gestao.get("/pdde/carryovers?year=2024").json() == []


def test_a_yield_is_money_in_and_a_return_is_money_out_and_both_need_custeio_or_capital(
    apis: ApiFactory, school: PublicSchool, admin_engine: Engine
) -> None:
    gestao, ids = _setup(apis, school, admin_engine)
    credit, debit = ids["RENDIMENTO APLICACAO"], ids["PAGAMENTO MATERIAL ESCOLAR"]

    assert _classify(gestao, credit, {"kind": "YIELD"}).status_code == 422  # no category
    assert (
        _classify(
            gestao, credit, {"kind": "YIELD", "economic_category": "CUSTEIO", "object": "x"}
        ).status_code
        == 422
    )
    assert (
        _classify(gestao, debit, {"kind": "YIELD", "economic_category": "CUSTEIO"}).status_code
        == 422
    )  # on a debit
    assert (
        _classify(
            gestao, credit, {"kind": "RETURN_TO_FNDE", "economic_category": "CUSTEIO"}
        ).status_code
        == 422
    )  # on a credit
    assert (
        _classify(gestao, credit, {"kind": "YIELD", "economic_category": "CUSTEIO"}).status_code
        == 201
    )
    done = next(
        ln
        for ln in gestao.get("/pdde/lines?period=2025-03").json()["lines"]
        if ln["line_id"] == credit
    )
    assert done["status"] == "DONE" and done["classification"]["kind"] == "YIELD"


def test_the_document_keeps_the_cnpj_or_cpf_of_who_was_paid_and_checks_it(
    apis: ApiFactory, school: PublicSchool, admin_engine: Engine
) -> None:
    gestao, ids = _setup(apis, school, admin_engine)
    debit = ids["PAGAMENTO MATERIAL ESCOLAR"]
    _classify(
        gestao,
        debit,
        {"kind": "EXPENSE", "economic_category": "CAPITAL", "object": "Material permanente"},
    )

    wrong = _doc(gestao, debit, 50_000, vendor_tax_id="11222333000182")
    punctuated = _doc(
        gestao,
        debit,
        50_000,
        vendor_tax_id="11.222.333/0001-81",
        quantity=2,
        specification="Ventilador de parede",
    )
    person = _doc(gestao, debit, 50_000, vendor_tax_id=CPF, doc_number="124")

    assert wrong.status_code == 422 and punctuated.status_code == 201 and person.status_code == 201
    line = next(
        ln
        for ln in gestao.get("/pdde/lines?period=2025-03").json()["lines"]
        if ln["line_id"] == debit
    )
    assert [(d["vendor_tax_id"], d["quantity"], d["specification"]) for d in line["documents"]] == [
        (CNPJ, 2, "Ventilador de parede"),
        (CPF, None, None),
    ]
    assert _doc(gestao, debit, 1, quantity=0).status_code == 422


def test_the_summary_counts_the_carryover_the_yield_and_the_return(
    apis: ApiFactory, school: PublicSchool, admin_engine: Engine
) -> None:
    gestao, ids = _setup(apis, school, admin_engine)
    _fill(gestao, ids)
    gestao.post(
        "/pdde/carryovers",
        {"year": 2025, "program": "BASICO", "custeio_cents": 30_000, "capital_cents": 0},
    )

    (basico,) = gestao.get("/pdde/summary?year=2025").json()["programs"]

    assert (
        basico["received_cents"] == 700_000
        and basico["yield_cents"] == 1234
        and basico["returned_cents"] == 10_000
    )
    assert basico["spent_capital_cents"] == 150_000
    assert basico["balance_cents"] == 30_000 + 700_000 + 1234 - 10_000 - 150_000


def test_the_demonstrativo_follows_the_form_with_its_numbered_fields(
    apis: ApiFactory, school: PublicSchool, admin_engine: Engine
) -> None:
    gestao, ids = _setup(apis, school, admin_engine)
    _fill(gestao, ids)
    gestao.post("/pdde/entity", ENTITY)
    _doc(
        gestao,
        ids["PAGAMENTO MATERIAL ESCOLAR"],
        150_000,
        doc_kind="NFE",
        access_key=_key(),
        vendor="Loja Eletro Exemplo",
        vendor_tax_id=CNPJ,
        doc_number="101",
        issued_on="2025-03-19",
    )

    response = gestao.get("/pdde/forms/demonstrativo.pdf?year=2025&program=BASICO")

    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == "application/pdf"
    assert (
        response.headers["content-disposition"]
        == 'attachment; filename="demonstrativo-basico-2025.pdf"'
    )
    text = text_of(response.content)
    for part in (
        "DEMONSTRATIVO DA EXECUÇÃO DA RECEITA E DA DESPESA E DE PAGAMENTOS EFETUADOS",
        "BLOCO 1",
        "BLOCO 2",
        "BLOCO 3",
        "BLOCO 4",
        "01 – Programa/Ação",
        "PDDE Básico",
        "02 – Exercício",
        "2025",
        "ASSOCIACAO DE PAIS E MESTRES EXEMPLO",
        "11.222.333/0001-81",
        "Rua das Flores, 100",
        "Jundiaí",
        "SP",
        "08 – Saldo reprogramado",
        "09 – Valor creditado pelo FNDE",
        "11 – Rendimento",
        "12 – Devolução",
        "13 – Valor total da receita",
        "14 – Valor da despesa realizada",
        "15 – Saldo a reprogramar",
        "17 – Período de execução",
        "18 – Nº de escolas",
        "Loja Eletro Exemplo",
        "11.222.333/0001-81",
        "Material permanente",
        "FNDE",
        "NF",
        "101",
        "OB 123",
        "28 – TOTAL",
    ):
        assert part in text, part
    # field 13 (receita) custeio = 5.000,00 + 12,34 - 100,00; capital = 2.000,00; field 14 capital = 1.500,00; field 15 capital = 500,00
    for amount in ("4.912,34", "2.000,00", "1.500,00", "500,00"):
        assert amount in text, amount
    assert "CONFERIR ANTES DE ASSINAR" in text  # the carry-over was not typed: the form says so
    assert "sem lançamentos de anos anteriores" in text


def test_what_the_data_cannot_fill_is_listed_and_never_hidden(
    apis: ApiFactory, school: PublicSchool, admin_engine: Engine
) -> None:
    gestao, ids = _setup(apis, school, admin_engine)
    _classify(gestao, ids["CREDITO REPASSE CUSTEIO"], {"kind": "TRANSFER"})  # no custeio or capital
    _classify(
        gestao,
        ids["PAGAMENTO MATERIAL ESCOLAR"],
        {"kind": "EXPENSE", "economic_category": "CAPITAL", "object": "Material permanente"},
    )
    _doc(gestao, ids["PAGAMENTO MATERIAL ESCOLAR"], 100_000, vendor="Loja Sem Cnpj")

    text = text_of(gestao.get("/pdde/forms/demonstrativo.pdf?year=2025&program=BASICO").content)

    for notice in (
        "Faltam os dados da entidade",
        "sem custeio ou capital",
        "sem classificação neste ano",
        "sem o CNPJ ou CPF do favorecido",
    ):
        assert notice in text, notice


def test_the_form_is_one_program_and_a_program_with_nothing_is_not_there(
    apis: ApiFactory, school: PublicSchool, admin_engine: Engine
) -> None:
    gestao, ids = _setup(apis, school, admin_engine)
    _fill(gestao, ids)

    assert gestao.get("/pdde/forms/demonstrativo.pdf?year=2025&program=EQUIDADE").status_code == 404
    assert gestao.get("/pdde/forms/demonstrativo.pdf?year=2024&program=BASICO").status_code == 404
    assert gestao.get("/pdde/forms/demonstrativo.pdf?year=2025&program=OUTRO").status_code == 422
    assert (
        gestao.get(
            "/pdde/forms/demonstrativo.pdf?year=2025&program=BASICO&program_label=x"
        ).status_code
        == 422
    )
    assert gestao.get("/pdde/forms/demonstrativo.pdf?year=2025&program=NOPE").status_code == 422


def test_the_balance_of_the_year_before_is_typed_or_calculated_and_the_form_says_which(
    apis: ApiFactory, school: PublicSchool, admin_engine: Engine
) -> None:
    gestao, ids = _setup(apis, school, admin_engine)
    _fill(gestao, ids)
    typed_none = text_of(
        gestao.get("/pdde/forms/demonstrativo.pdf?year=2025&program=BASICO").content
    )
    gestao.post(
        "/pdde/carryovers",
        {"year": 2025, "program": "BASICO", "custeio_cents": 30_000, "capital_cents": 0},
    )

    typed = text_of(gestao.get("/pdde/forms/demonstrativo.pdf?year=2025&program=BASICO").content)

    assert "sem lançamentos de anos anteriores" in typed_none
    assert "informado pela escola" in typed and "300,00" in typed
