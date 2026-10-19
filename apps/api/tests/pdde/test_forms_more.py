# ruff: noqa: E501  (long assertions)
"""The other two official forms: the list of goods (only capital, one row per document) and the bank
reconciliation (one PDDE account), with the conference of the system outside the form."""

import uuid

import pytest
from sqlalchemy import Engine

from app.auth.permissions import ROLE_PERMISSIONS, Permission
from tests.authsupport import ApiFactory
from tests.campaigns.support import committed_manager
from tests.expenses.support import Scene
from tests.pdde.test_forms import CNPJ, ENTITY, _classify, _fill, _setup
from tests.pdde.test_pdde import _account, _doc
from tests.public.conftest import PublicSchool
from tests.statement.pdftext import text_of

ROLES = ["secretaria", "staff"]
MANAGE = {r for r in ROLES if Permission.RECONCILIATION_MANAGE in ROLE_PERMISSIONS[r]}


def _pdde_account(gestao: object) -> str:
    accounts = gestao.get("/reconciliation/accounts").json()  # type: ignore[attr-defined]
    return str(next(a["id"] for a in accounts if a["purpose"] == "PDDE"))


def test_the_list_of_goods_has_one_row_per_document_of_capital_with_the_unit_value(
    apis: ApiFactory, school: PublicSchool, admin_engine: Engine
) -> None:
    gestao, ids = _setup(apis, school, admin_engine)
    _fill(gestao, ids)
    gestao.post("/pdde/entity", ENTITY)
    material = ids["PAGAMENTO MATERIAL ESCOLAR"]
    assert (
        _doc(
            gestao,
            material,
            100_000,
            vendor_tax_id=CNPJ,
            quantity=2,
            specification="Ventilador de parede 60 cm",
            doc_number="55",
            issued_on="2025-03-19",
        ).status_code
        == 201
    )
    assert (
        _doc(gestao, material, 50_000, doc_number="56", issued_on="2025-03-20").status_code == 201
    )

    response = gestao.get("/pdde/forms/bens.pdf?year=2025&program=BASICO")

    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == "application/pdf"
    assert (
        response.headers["content-disposition"]
        == 'attachment; filename="relacao-de-bens-basico-2025.pdf"'
    )
    text = text_of(response.content)
    for part in (
        "RELAÇÃO DE BENS ADQUIRIDOS OU PRODUZIDOS",
        "BLOCO 1",
        "BLOCO 2",
        "BLOCO 3",
        "08 – Documento",
        "09 – Especificação dos bens",
        "Quantidade",
        "Unitário",
        "ASSOCIACAO DE PAIS E MESTRES EXEMPLO",
        "Ventilador de parede 60 cm",
        "R$ 500,00",
        "R$ 1.000,00",
        "Material permanente",
        "12 – TOTAL",
        "R$ 1.500,00",
    ):
        assert part in text, part
    assert (
        "1 documento(s) sem quantidade" in text
    )  # the second document: the form says so, it does not guess


def test_a_program_without_capital_gets_an_empty_list_that_says_so_and_a_program_with_nothing_is_not_there(
    apis: ApiFactory, school: PublicSchool, admin_engine: Engine
) -> None:
    gestao, ids = _setup(apis, school, admin_engine)
    _classify(
        gestao, ids["CREDITO REPASSE CUSTEIO"], {"kind": "TRANSFER", "economic_category": "CUSTEIO"}
    )
    _classify(
        gestao,
        ids["PAGAMENTO MATERIAL ESCOLAR"],
        {"kind": "EXPENSE", "economic_category": "CUSTEIO", "object": "Material de consumo"},
    )

    empty = gestao.get("/pdde/forms/bens.pdf?year=2025&program=BASICO")

    assert empty.status_code == 200
    assert "Nenhuma despesa de capital classificada" in text_of(empty.content)
    assert gestao.get("/pdde/forms/bens.pdf?year=2025&program=EQUIDADE").status_code == 404
    assert gestao.get("/pdde/forms/bens.pdf?year=2025&program=OUTRO").status_code == 422


def test_the_reconciliation_carries_the_statement_balance_and_the_conference_says_when_it_matches(
    apis: ApiFactory, school: PublicSchool, admin_engine: Engine
) -> None:
    gestao, ids = _setup(apis, school, admin_engine)
    _fill(
        gestao, ids
    )  # 7.000,00 + 12,34 in, 100,00 returned, 1.500,00 spent: 5.412,34 = the balance of the statement
    gestao.post("/pdde/entity", ENTITY)
    account = _pdde_account(gestao)

    response = gestao.get(f"/pdde/forms/conciliacao.pdf?year=2025&account_id={account}")

    assert response.status_code == 200, response.text
    assert (
        response.headers["content-disposition"]
        == 'attachment; filename="conciliacao-bancaria-pdde-2025.pdf"'
    )
    text = text_of(response.content)
    for part in (
        "CONCILIAÇÃO BANCÁRIA",
        "BLOCO 1",
        "BLOCO 2",
        "BLOCO 3",
        "BLOCO 4",
        "08 – Banco",
        "Banco do Brasil",
        "09 – Cód. da agência",
        "10 – Nº da conta corrente",
        "11 – Saldo do extrato bancário",
        "30/04/2025",
        "R$ 5.412,34",
        "12 – Créditos não demonstrados",
        "13 – Débitos não demonstrados",
        "14 – Restos a pagar processados",
        "15 – Saldo contábil",
        "16 – Total",
        "CONFERÊNCIA DO SISTEMA",
        "Bate.",
    ):
        assert part in text, part
    assert "vai só até 30/04/2025" in text  # the December statement was not imported


def test_the_conference_says_when_it_does_not_match(
    apis: ApiFactory, school: PublicSchool, admin_engine: Engine
) -> None:
    gestao, ids = _setup(apis, school, admin_engine)
    _fill(gestao, ids)
    gestao.post(
        "/pdde/carryovers",
        {"year": 2025, "program": "BASICO", "custeio_cents": 30_000, "capital_cents": 0},
    )  # a balance the statement does not have
    account = _pdde_account(gestao)

    text = text_of(
        gestao.get(f"/pdde/forms/conciliacao.pdf?year=2025&account_id={account}").content
    )

    assert "Não bate" in text and "-R$ 300,00" in text
    assert "Faltam os dados da entidade" in text


def test_only_a_pdde_account_of_the_school_has_a_reconciliation(
    apis: ApiFactory, school: PublicSchool, other_school: PublicSchool, admin_engine: Engine
) -> None:
    gestao, _ = _setup(apis, school, admin_engine)
    general = _account(gestao, "Geral", "GENERAL")
    stranger = committed_manager(apis, admin_engine, other_school)
    pdde = _pdde_account(gestao)

    assert (
        gestao.get(f"/pdde/forms/conciliacao.pdf?year=2025&account_id={general}").status_code == 404
    )
    assert (
        gestao.get(f"/pdde/forms/conciliacao.pdf?year=2025&account_id={uuid.uuid4()}").status_code
        == 404
    )
    assert (
        stranger.get(f"/pdde/forms/conciliacao.pdf?year=2025&account_id={pdde}").status_code == 404
    )
    assert stranger.get("/pdde/forms/bens.pdf?year=2025&program=BASICO").status_code == 404


@pytest.mark.parametrize("role", ROLES)
def test_every_new_route_enforces_its_permission(scene: Scene, role: str) -> None:
    person = scene.person(role)
    some = uuid.uuid4()
    routes = [
        "/pdde/forms/bens.pdf?year=2025&program=BASICO",
        f"/pdde/forms/conciliacao.pdf?year=2025&account_id={some}",
        "/pdde/forms/demonstrativo.pdf?year=2025&program=BASICO",
    ]

    for tail in routes:
        answer = person.request("GET", tail)
        if role in MANAGE:
            assert answer.status_code in (200, 404), (tail, answer.text)
        else:
            assert answer.status_code == 403 and answer.json()["code"] == "permission_denied", (
                tail,
                role,
            )
