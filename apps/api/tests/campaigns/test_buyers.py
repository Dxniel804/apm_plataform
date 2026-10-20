"""Who bought what in a campaign: the paid orders grouped by guardian and student."""

import uuid

from sqlalchemy import Engine

from tests.authsupport import ApiFactory
from tests.campaigns.support import committed_manager, seed_campaign
from tests.campaigns.test_public import _pay, order
from tests.public.conftest import PublicSchool
from tests.public.support import txid_of
from tests.statement.pdftext import text_of


def _paid_order(
    apis: ApiFactory,
    school: PublicSchool,
    campaign: uuid.UUID,
    lines: list[tuple[uuid.UUID, int]],
    **who: str,
) -> None:
    api = apis.make()
    created = order(api, school.slug, campaign, lines, **who)
    assert created.status_code == 201, created.text
    assert _pay(api, txid_of(created)).status_code == 200


def test_the_buyers_add_up_what_each_guardian_bought_for_each_student(
    apis: ApiFactory, school: PublicSchool, admin_engine: Engine
) -> None:
    seeded = seed_campaign(admin_engine, school.fresh, ask_student_class=True)
    gestao = committed_manager(apis, admin_engine, school)
    a, b = seeded.items
    maria = {"guardian_name": "Maria Souza", "student_name": "Ana", "class_name": "3º ano A"}
    _paid_order(apis, school, seeded.campaign, [(a, 2), (b, 1)], **maria)
    # The same person, written another way: the same buyer.
    again = {"guardian_name": "  MARIA  souza ", "student_name": "ana", "class_name": "3º ano A"}
    _paid_order(apis, school, seeded.campaign, [(a, 1)], **again)
    other = {"guardian_name": "João Lima", "student_name": "Beto", "class_name": "5º ano B"}
    _paid_order(apis, school, seeded.campaign, [(b, 3)], **other)
    # An order not paid yet is not a sale.
    waiting = {"guardian_name": "Rita", "student_name": "Caio", "class_name": "1º ano C"}
    assert order(apis.make(), school.slug, seeded.campaign, [(a, 1)], **waiting).status_code == 201

    body = gestao.get(f"/campaigns/{seeded.campaign}/buyers").json()

    assert body["complete"] is True
    joao, maria_row = body["items"]  # in the order of the guardian's name
    assert joao["guardian_name"] == "João Lima" and joao["units"] == 3 and joao["orders"] == 1
    assert joao["lines"] == [{"item_name": "Pamonha", "quantity": 3}]
    assert maria_row["orders"] == 2 and maria_row["units"] == 4
    assert maria_row["lines"] == [
        {"item_name": "Cachorro-quente", "quantity": 3},
        {"item_name": "Pamonha", "quantity": 1},
    ]
    assert maria_row["amount_cents"] == 2250 + 800


def test_a_guardian_with_two_students_has_two_rows(
    apis: ApiFactory, school: PublicSchool, admin_engine: Engine
) -> None:
    seeded = seed_campaign(admin_engine, school.fresh, ask_student_class=True)
    gestao = committed_manager(apis, admin_engine, school)
    a, _ = seeded.items
    for student in ("Ana", "Bia"):
        who = {"guardian_name": "Maria Souza", "student_name": student, "class_name": "3º ano A"}
        _paid_order(apis, school, seeded.campaign, [(a, 1)], **who)

    rows = gestao.get(f"/campaigns/{seeded.campaign}/buyers").json()["items"]

    assert sorted(row["student_name"] for row in rows) == ["Ana", "Bia"]
    assert {row["guardian_name"] for row in rows} == {"Maria Souza"}


def test_a_campaign_with_no_paid_order_has_no_buyers(
    apis: ApiFactory, school: PublicSchool, admin_engine: Engine
) -> None:
    seeded = seed_campaign(admin_engine, school.fresh)
    gestao = committed_manager(apis, admin_engine, school)

    assert gestao.get(f"/campaigns/{seeded.campaign}/buyers").json() == {
        "items": [],
        "complete": True,
    }


def test_the_pdf_of_the_campaign_has_who_bought(
    apis: ApiFactory, school: PublicSchool, admin_engine: Engine
) -> None:
    seeded = seed_campaign(admin_engine, school.fresh, ask_student_class=True)
    gestao = committed_manager(apis, admin_engine, school)
    who = {"guardian_name": "Maria Souza", "student_name": "Ana", "class_name": "3º ano A"}
    _paid_order(apis, school, seeded.campaign, [(seeded.items[0], 2)], **who)

    pdf = gestao.get(f"/campaigns/{seeded.campaign}/report.pdf")

    assert pdf.status_code == 200
    text = text_of(pdf.content)
    assert "Quem comprou (1)" in text and "Maria Souza" in text and "2 × Cachorro-quente" in text
