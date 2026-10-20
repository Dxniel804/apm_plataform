# ruff: noqa: E501  (long assertions)
"""The comparison knows the wallet of an account: a PDDE account is compared with what was paid with the
PDDE money, any other with the APM's, and a line that left the wrong account is told apart."""

import io
import uuid
from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo

from tests.expenses.support import Client, Scene
from tests.reconciliation.ofx_samples import sgml


def _today() -> date:
    return datetime.now(ZoneInfo("America/Sao_Paulo")).date()


def _account(gestao: Client, nickname: str, purpose: str) -> str:
    made = gestao.post(
        "/reconciliation/accounts",
        {
            "nickname": f"{nickname} {uuid.uuid4().hex[:6]}",
            "bank_name": "Banco do Brasil",
            "purpose": purpose,
        },
    )
    assert made.status_code == 201, made.text
    return str(made.json()["id"])


def _import(gestao: Client, account: str, amount: str, memo: str = "PAGAMENTO FORNECEDOR") -> str:
    day = _today()
    first = day.replace(day=1)
    sent = gestao.post(
        "/reconciliation/imports",
        data={"bank_account_id": account},
        files={
            "file": (
                "extrato.ofx",
                io.BytesIO(
                    sgml([(f"F{uuid.uuid4().hex[:12]}", day, amount, memo)], first, day, "1000.00")
                ),
                "application/x-ofx",
            )
        },
    )
    assert sent.status_code == 201, sent.text
    return str(sent.json()["id"])


def _paid(scene: Scene, key: str, fund: str, cents: int) -> dict[str, Any]:
    teacher = scene.person("staff", label="teacher")
    treasurer = scene.person("secretaria", label="secretaria")
    expense = scene.submitted(
        teacher, category_id=scene.category(teacher.school, key), paid_by="APM", amount_cents=cents
    )
    assert treasurer.post(f"/expenses/{expense['id']}/approve", {"fund": fund}).status_code == 200
    assert treasurer.post(f"/expenses/{expense['id']}/pay").status_code == 200
    return dict(expense)


def test_each_account_is_compared_with_the_money_of_its_wallet(scene: Scene) -> None:
    treasurer = scene.person("secretaria", label="secretaria")
    _paid(scene, "capital_equipment", "PDDE", 4_555)
    _paid(scene, "cleaning_supplies", "APM", 1_666)
    general = _account(treasurer, "Conta da APM", "GENERAL")
    pdde = _account(treasurer, "Conta do PDDE", "PDDE")

    apm_view = treasurer.get(
        f"/reconciliation/imports/{_import(treasurer, general, '-16.66')}"
    ).json()
    pdde_view = treasurer.get(
        f"/reconciliation/imports/{_import(treasurer, pdde, '-45.55')}"
    ).json()

    # The APM extract pairs with the APM expense only: the PDDE one is not "missing in the bank" here.
    assert (
        len(apm_view["matched"]) == 1 and apm_view["matched"][0]["entry"]["amount_cents"] == -1_666
    )
    assert apm_view["missing_in_bank"] == [] and apm_view["wrong_account"] == []
    # And the PDDE extract pairs with the PDDE expense only.
    assert (
        len(pdde_view["matched"]) == 1
        and pdde_view["matched"][0]["entry"]["amount_cents"] == -4_555
    )
    assert pdde_view["missing_in_bank"] == [] and pdde_view["wrong_account"] == []


def test_a_pdde_expense_that_left_the_apm_account_is_told(scene: Scene) -> None:
    treasurer = scene.person("secretaria", label="secretaria")
    _paid(scene, "capital_equipment", "PDDE", 4_111)
    general = _account(treasurer, "Conta da APM", "GENERAL")

    view = treasurer.get(f"/reconciliation/imports/{_import(treasurer, general, '-41.11')}").json()

    assert view["matched"] == [] and view["missing_in_system"] == []
    [wrong] = view["wrong_account"]
    assert wrong["belongs_to"] == "PDDE" and wrong["line"]["amount_cents"] == -4_111
    assert wrong["entry"]["amount_cents"] == -4_111


def test_an_apm_expense_that_left_the_pdde_account_is_told(scene: Scene) -> None:
    treasurer = scene.person("secretaria", label="secretaria")
    _paid(scene, "cleaning_supplies", "APM", 1_222)
    pdde = _account(treasurer, "Conta do PDDE", "PDDE")

    view = treasurer.get(f"/reconciliation/imports/{_import(treasurer, pdde, '-12.22')}").json()

    [wrong] = view["wrong_account"]
    assert wrong["belongs_to"] == "APM" and view["missing_in_system"] == []


def test_a_line_of_a_pdde_account_cannot_be_booked_in_the_apm_cash(scene: Scene) -> None:
    treasurer = scene.person("secretaria", label="secretaria")
    pdde = _account(treasurer, "Conta do PDDE", "PDDE")
    view = treasurer.get(
        f"/reconciliation/imports/{_import(treasurer, pdde, '-12.34', 'TARIFA')}"
    ).json()
    line = view["missing_in_system"][0]["line_id"]

    refused = treasurer.post(f"/reconciliation/lines/{line}/actions", {"action": "REGISTER_FEE"})

    assert refused.status_code == 422, refused.text
    assert any(e["code"] == "pdde_account_line" for e in refused.json()["errors"])
    ignored = treasurer.post(
        f"/reconciliation/lines/{line}/actions", {"action": "IGNORE", "reason": "ver no PDDE"}
    )
    assert ignored.status_code == 201, ignored.text


def test_the_pdde_line_says_which_expense_it_pays(scene: Scene) -> None:
    treasurer = scene.person("secretaria", label="secretaria")
    expense = _paid(scene, "capital_equipment", "PDDE", 4_333)
    pdde = _account(treasurer, "Conta do PDDE", "PDDE")
    _import(treasurer, pdde, "-43.33")

    month = treasurer.get(f"/pdde/lines?period={_today():%Y-%m}").json()

    line = next(ln for ln in month["lines"] if ln["amount_cents"] == -4_333)
    link = line["expense"]
    assert (
        link["expense_id"] == expense["id"] and link["reference_code"] == expense["reference_code"]
    )
    assert link["category_key"] == "capital_equipment" and link["economic_nature"] == "CAPITAL"
    assert link["description"] == expense["description"]


def test_a_pdde_line_with_no_matching_expense_has_no_link(scene: Scene) -> None:
    treasurer = scene.person("secretaria", label="secretaria")
    _paid(scene, "capital_equipment", "PDDE", 4_444)
    pdde = _account(treasurer, "Conta do PDDE", "PDDE")
    _import(treasurer, pdde, "-99.99")

    month = treasurer.get(f"/pdde/lines?period={_today():%Y-%m}").json()

    assert next(ln for ln in month["lines"] if ln["amount_cents"] == -9_999)["expense"] is None
