"""Which money pays an expense: the category suggests it, the secretaria decides."""

from typing import Any

from tests.expenses.support import Scene


def _submitted(scene: Scene, key: str) -> tuple[Any, Any, dict[str, Any]]:
    teacher = scene.person("staff", label="teacher")
    treasurer = scene.person("secretaria", label="secretaria")
    expense = scene.submitted(teacher, category_id=scene.category(teacher.school, key))
    return teacher, treasurer, expense


def test_the_category_suggests_the_money_and_the_expense_has_none_until_it_is_decided(
    scene: Scene,
) -> None:
    _, _, usual = _submitted(scene, "cleaning_supplies")
    assert usual["fund"] is None
    assert usual["suggested_fund"] == "PDDE" and usual["economic_nature"] == "CUSTEIO"
    assert usual["pdde_rule"] == "SUGGESTED"

    _, _, generic = _submitted(scene, "other_authorized")
    assert generic["suggested_fund"] == "APM" and generic["pdde_rule"] == "ALLOWED"


def test_approving_without_a_choice_takes_what_the_category_suggests(scene: Scene) -> None:
    _, treasurer, expense = _submitted(scene, "capital_equipment")

    approved = treasurer.post(f"/expenses/{expense['id']}/approve", {})

    assert approved.status_code == 200, approved.text
    assert approved.json()["fund"] == "PDDE" and approved.json()["economic_nature"] == "CAPITAL"


def test_the_secretaria_can_change_the_money_of_an_expense(scene: Scene) -> None:
    _, treasurer, expense = _submitted(scene, "capital_equipment")

    approved = treasurer.post(f"/expenses/{expense['id']}/approve", {"fund": "APM"})

    assert approved.status_code == 200, approved.text
    assert approved.json()["fund"] == "APM"
    assert approved.json()["suggested_fund"] == "PDDE"


def test_what_the_resolution_forbids_cannot_be_paid_with_the_pdde(scene: Scene) -> None:
    _, treasurer, expense = _submitted(scene, "tax_payments")

    refused = treasurer.post(f"/expenses/{expense['id']}/approve", {"fund": "PDDE"})

    assert refused.status_code == 422, refused.text
    assert refused.json()["code"] == "pdde_not_allowed"
    # Nothing was decided: the expense is still waiting, and approving it as the APM works.
    assert treasurer.get(f"/expenses/{expense['id']}").json()["status"] == "SUBMITTED"
    assert treasurer.post(f"/expenses/{expense['id']}/approve", {}).json()["fund"] == "APM"


def test_a_rejected_expense_has_no_money(scene: Scene) -> None:
    _, treasurer, expense = _submitted(scene, "capital_equipment")

    rejected = treasurer.post(f"/expenses/{expense['id']}/reject", {"reason": "sem orçamento"})

    assert rejected.status_code == 200, rejected.text
    assert rejected.json()["fund"] is None


def test_the_fund_is_written_once(scene: Scene) -> None:
    teacher, treasurer, expense = _submitted(scene, "capital_equipment")
    treasurer.post(f"/expenses/{expense['id']}/approve", {"fund": "PDDE"})

    again = treasurer.post(f"/expenses/{expense['id']}/approve", {"fund": "APM"})

    assert again.status_code == 409, again.text
    assert treasurer.get(f"/expenses/{expense['id']}").json()["fund"] == "PDDE"


def _paid(scene: Scene, key: str, fund: str, paid_by: str, cents: int) -> None:
    teacher = scene.person("staff", label="teacher")
    treasurer = scene.person("secretaria", label="secretaria")
    expense = scene.submitted(
        teacher,
        category_id=scene.category(teacher.school, key),
        paid_by=paid_by,
        amount_cents=cents,
    )
    assert treasurer.post(f"/expenses/{expense['id']}/approve", {"fund": fund}).status_code == 200
    if paid_by == "APM":
        assert treasurer.post(f"/expenses/{expense['id']}/pay").status_code == 200
    else:
        reimbursed = treasurer.post(
            f"/expenses/{expense['id']}/reimburse", {"payment_reference": "PIX-1"}
        )
        assert reimbursed.status_code == 200, reimbursed.text


def _cash(scene: Scene) -> tuple[int, int]:
    treasurer = scene.person("secretaria", label="secretaria")
    summary = treasurer.get("/statement/summary").json()
    return summary["total_out_cents"], summary["closing_balance_cents"]


def test_what_the_pdde_pays_does_not_leave_the_cash_of_the_apm(scene: Scene) -> None:
    out, balance = _cash(scene)

    _paid(scene, "capital_equipment", "PDDE", "APM", 4_000)
    assert _cash(scene) == (out, balance)  # paid with the PDDE: the APM cash did not move

    _paid(scene, "capital_equipment", "APM", "APM", 1_500)
    assert _cash(scene) == (out + 1_500, balance - 1_500)  # the same expense with the APM money


def test_the_reimbursement_of_a_pdde_expense_is_not_the_apms_cash_either(scene: Scene) -> None:
    out, balance = _cash(scene)

    _paid(scene, "capital_furniture", "PDDE", "COLLABORATOR", 2_000)
    assert _cash(scene) == (out, balance)

    _paid(scene, "capital_furniture", "APM", "COLLABORATOR", 700)
    assert _cash(scene) == (out + 700, balance - 700)
