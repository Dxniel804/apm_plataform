# ruff: noqa: E501  (SQL text)
"""A sandbox school comes with made-up data (docs/adr-ambiente-sandbox.md, part 4).

When the first secretaria of a school in `sandbox` signs in, the school is empty: this fills it with
a month that is closed and a month that is running, so the whole product can be looked at: Pix of the
family page, Pix straight to the key, cash and a donation, expenses in every state of their life and a
reimbursement. Everything is invented (names, amounts, vendors) and the dates are relative to TODAY.

It runs with the permission of the application, inside the tenant of the school, like any request: the
same triggers and policies apply, nothing is bypassed, and the database marks every row `is_demo`
(0035) because the organization is a sandbox, so the rows disappear when it goes to production. The
person who signs in is the author of the records (the school has nobody else yet) and no user is made.

It does nothing when the school already has any movement (a real school sent to sandbox is never
touched) and takes a lock so two first sign-ins cannot fill it twice.
"""

import random
import uuid
from datetime import date, timedelta
from typing import Any

from sqlalchemy import TextClause, text
from sqlalchemy.orm import Session

AMOUNTS = [5000, 8000, 10000, 10000, 12000, 15000]
CLASSES = ["1A", "1B", "2A", "2B", "3A", "3B", "4A", "4B", "5A", "5B"]
FIRST = [
    "Ana", "Bruno", "Carla", "Diego", "Elisa", "Fabio", "Gabriela", "Hugo", "Isabela", "Joao",
    "Karina", "Luis", "Mariana", "Nelson", "Olivia", "Pedro", "Rafael", "Sandra", "Tiago", "Yara",
]  # fmt: skip
LAST = [
    "Almeida", "Barros", "Cardoso", "Dias", "Esteves", "Ferraz", "Gomes", "Lopes", "Moura",
    "Nunes", "Oliveira", "Pires", "Ramos", "Souza", "Teixeira", "Vieira",
]  # fmt: skip
# (category key, description, vendor, cents)
EXPENSES = [
    ("cleaning_supplies", "Sacos de lixo e desinfetante", "Distribuidora Limpa Bem", 19_480),
    ("teaching_material", "Kit de matemática (cubos)", "Livraria Saber", 38_400),
    ("stationery", "Cartolinas e EVA para o mural", "Papelaria Estrela", 9_760),
    ("office", "Toner da impressora", "Info Cartuchos", 21_900),
    ("maintenance_material", "Tintas e rolos para o muro", "Tintas Aurora", 34_500),
    ("services", "Jardinagem e poda das árvores", "Jardim Verde ME", 88_650),
    ("school_supplies", "Material para a feira de ciências", "Papelaria Estrela", 14_500),
    ("capital_equipment", "Ventilador de parede (2)", "Eletro Mais", 189_000),
]  # fmt: skip
_LOCK = 7002


def _first_of(day: date) -> date:
    return day.replace(day=1)


class _Filler:
    def __init__(self, db: Session, org: uuid.UUID, school: uuid.UUID, actor: uuid.UUID) -> None:
        self.db, self.org, self.school, self.actor = db, org, school, actor
        self.rng = random.Random(20261027)  # noqa: S311  (invented data, nothing secret)
        self.category: dict[str, Any] = {}
        self.account: Any = None
        today = date.today()
        self.today = today
        self.this_month = _first_of(today)
        self.last_month = _first_of(self.this_month - timedelta(days=1))
        self.used_e2e: set[str] = set()

    # --- helpers --------------------------------------------------------------------------------

    def one(self, statement: TextClause, **params: Any) -> Any:
        return self.db.execute(statement, params).scalar_one()

    def person(self) -> str:
        return f"{self.rng.choice(FIRST)} {self.rng.choice(LAST)}"

    def day_in(self, month: date, *, last: int = 28) -> date:
        """A day of that month, never in the future."""
        limit = last if month != self.this_month else min(last, max(1, self.today.day))
        return month.replace(day=self.rng.randint(1, limit))

    def e2e(self) -> str:
        while True:
            value = "E" + "".join(self.rng.choice("0123456789") for _ in range(31))
            if value not in self.used_e2e:
                self.used_e2e.add(value)
                return value

    def tx(
        self,
        *,
        kind: str,
        direction: str,
        amount: int,
        status: str,
        category: str,
        origin_type: str,
        day: date,
        origin_user: Any = None,
        settled: bool = False,
        parent: Any = None,
        parent_kind: str | None = None,
    ) -> Any:
        return self.one(
            text(
                "INSERT INTO financial_transactions (organization_id, school_id, kind, direction, "
            "amount_cents, status, category_id, origin_type, origin_user_id, occurred_at, settled_at, "
            "created_by_user_id, parent_transaction_id, parent_kind) VALUES (:o, :s, :kind, "
            ":direction, :amount, :status, :category, :origin_type, :origin_user, "
            "(CAST(:day AS date) + time '12:00') AT TIME ZONE 'America/Sao_Paulo', "
            "CASE WHEN :settled THEN (CAST(:day AS date) + time '12:00') "
            "AT TIME ZONE 'America/Sao_Paulo' END, :author, :parent, :parent_kind) RETURNING id"
            ),
            o=self.org, s=self.school, kind=kind, direction=direction, amount=amount,
            status=status, category=self.category[category], origin_type=origin_type,
            origin_user=origin_user, day=day, settled=settled, author=self.actor, parent=parent,
            parent_kind=parent_kind,
        )  # fmt: skip

    def settle(self, tx: Any, status: str, day: date) -> None:
        self.db.execute(
            text(
                "UPDATE financial_transactions SET status = :st, settled_at = (CAST(:day AS date) "
                "+ time '12:00') AT TIME ZONE 'America/Sao_Paulo' WHERE id = :t"
            ),
            {"st": status, "day": day, "t": tx},
        )

    def move(self, tx: Any, status: str) -> None:
        self.db.execute(
            text("UPDATE financial_transactions SET status = :st WHERE id = :t"),
            {"st": status, "t": tx},
        )

    # --- the movements --------------------------------------------------------------------------

    def contribution(self, amount: int, day: date, method: str, *, donation: bool = False) -> None:
        who = "Mercado Bom Preço (doação)" if donation else self.person()
        tx = self.tx(
            kind="CONTRIBUTION", direction="IN", amount=amount, status="PAID",
            category="donation" if donation else "parent_contribution",
            origin_type="OTHER" if donation else "GUARDIAN", day=day, settled=True,
        )  # fmt: skip
        self.db.execute(
            text(
                "INSERT INTO contributions (transaction_id, organization_id, school_id, method, "
                "external_reference, guardian_name, student_name, class_name, reference_month) "
                "VALUES (:t, :o, :s, :m, :e, :g, :st, :c, date_trunc('month', CAST(:day AS date))::date)"
            ),
            {
                "t": tx, "o": self.org, "s": self.school, "m": method,
                "e": self.e2e() if method == "PIX_DIRECT" else None, "g": who,
                "st": None if donation else self.person(),
                "c": None if donation else self.rng.choice(CLASSES), "day": day,
            },
        )  # fmt: skip

    def pix(self, amount: int, day: date, *, paid: bool) -> None:
        """A Pix of the family page (a charge of the platform, paid by the fake bank)."""
        tx = self.tx(
            kind="CONTRIBUTION", direction="IN", amount=amount, status="PENDING_PAYMENT",
            category="parent_contribution", origin_type="GUARDIAN", day=day,
        )  # fmt: skip
        self.db.execute(
            text(
                "INSERT INTO contributions (transaction_id, organization_id, school_id, method, "
                "guardian_name, student_name, class_name, reference_month, receipt_token_hash, "
                "receipt_expires_at) VALUES (:t, :o, :s, 'PIX', :g, :st, :c, "
                "date_trunc('month', CAST(:day AS date))::date, "
                "encode(sha256(gen_random_uuid()::text::bytea), 'hex'), now() + interval '30 days')"
            ),
            {
                "t": tx, "o": self.org, "s": self.school, "g": self.person(),
                "st": self.person(), "c": self.rng.choice(CLASSES), "day": day,
            },
        )  # fmt: skip
        charge = self.one(
            text(
                "INSERT INTO pix_charges (organization_id, school_id, transaction_id, payment_account_id, "
            "provider, txid, amount_cents, expires_at) VALUES (:o, :s, :t, :a, 'SANDBOX', "
            "replace(gen_random_uuid()::text, '-', ''), :amount, now() + interval '30 minutes') "
            "RETURNING id"
            ),
            o=self.org, s=self.school, t=tx, a=self.account, amount=amount,
        )  # fmt: skip
        if not paid:
            return
        self.db.execute(
            text(
                "UPDATE pix_charges SET status = 'PAID', paid_at = (CAST(:day AS date) + time '12:00') "
                "AT TIME ZONE 'America/Sao_Paulo', received_amount_cents = :r, end_to_end_id = :e "
                "WHERE id = :c"
            ),
            {"day": day, "r": amount, "e": self.e2e(), "c": charge},
        )
        self.settle(tx, "PAID", day)

    def expense(
        self, spec: tuple[str, str, str, int], day: date, status: str, *, paid_by: str = "APM"
    ) -> Any:
        """An expense of the APM in any state of its life."""
        key, description, vendor, amount = spec
        start = "DRAFT" if status == "DRAFT" else "SUBMITTED"
        tx = self.tx(
            kind="EXPENSE", direction="OUT", amount=amount, status=start, category=key,
            origin_type="TEACHER", origin_user=self.actor, day=day,
        )  # fmt: skip
        self.db.execute(
            text(
                "INSERT INTO expenses (transaction_id, organization_id, school_id, description, vendor, "
                "purchase_reason, payment_method, paid_by, submitted_by_user_id) VALUES (:t, :o, :s, "
                ":d, :v, 'uso da escola (demonstração)', 'PIX', :p, :u)"
            ),
            {
                "t": tx, "o": self.org, "s": self.school, "d": description, "v": vendor,
                "p": paid_by, "u": self.actor,
            },
        )  # fmt: skip
        if start != "DRAFT":
            self.db.execute(
                text(
                    "INSERT INTO expense_attachments (organization_id, school_id, transaction_id, kind, "
                    "storage_key, file_name, content_type, size_bytes, sha256, uploaded_by_user_id) "
                    "VALUES (:o, :s, :t, 'INVOICE', :k, 'nota-demonstracao.pdf', 'application/pdf', "
                    "2048, encode(sha256(gen_random_uuid()::text::bytea), 'hex'), :u)"
                ),
                {"o": self.org, "s": self.school, "t": tx, "k": f"demo/{tx}", "u": self.actor},
            )
        if status == "CORRECTION_REQUESTED":
            self.db.execute(
                text(
                    "UPDATE expenses SET correction_reason = 'anexe o comprovante do pagamento "
                    "(demonstração)' WHERE transaction_id = :t"
                ),
                {"t": tx},
            )
            self.move(tx, "CORRECTION_REQUESTED")
        elif status in ("APPROVED", "PAID"):
            self.db.execute(
                text(
                    "UPDATE expenses SET approved_by_user_id = :u, approved_amount_cents = :a "
                    "WHERE transaction_id = :t"
                ),
                {"u": self.actor, "a": amount, "t": tx},
            )
            self.move(tx, "APPROVED")
            if status == "PAID":
                self.settle(tx, "PAID", day)
        return tx

    def bank_fee(self, amount: int, day: date, description: str) -> None:
        """A bank fee: a category that needs no approval, so it has no decider."""
        tx = self.tx(
            kind="EXPENSE", direction="OUT", amount=amount, status="APPROVED",
            category="bank_fees", origin_type="BANK", day=day,
        )  # fmt: skip
        self.db.execute(
            text(
                "INSERT INTO expenses (transaction_id, organization_id, school_id, description, "
                "paid_by, submitted_by_user_id) VALUES (:t, :o, :s, :d, 'APM', :u)"
            ),
            {"t": tx, "o": self.org, "s": self.school, "d": description, "u": self.actor},
        )
        self.settle(tx, "PAID", day)

    def reimbursement(self, expense_id: Any, amount: int, day: date) -> None:
        tx = self.tx(
            kind="REIMBURSEMENT", direction="OUT", amount=amount, status="PENDING",
            category="teacher_reimbursement", origin_type="TEACHER", origin_user=self.actor,
            day=day, parent=expense_id, parent_kind="EXPENSE",
        )  # fmt: skip
        self.db.execute(
            text(
                "INSERT INTO reimbursements (transaction_id, organization_id, school_id, "
                "beneficiary_user_id) VALUES (:t, :o, :s, :b)"
            ),
            {"t": tx, "o": self.org, "s": self.school, "b": self.actor},
        )
        self.db.execute(
            text(
                "UPDATE reimbursements SET payment_reference = 'demonstracao-transferencia-001', "
                "paid_by_user_id = :u WHERE transaction_id = :t"
            ),
            {"u": self.actor, "t": tx},
        )
        self.settle(tx, "PAID", day)
        self.settle(expense_id, "PAID", day)

    # --- the dataset ----------------------------------------------------------------------------

    def run(self) -> None:
        """A closed month and a running one. The expenses that wait for a decision are there to be
        decided by the people of the school: nobody can decide an expense they submitted, and the
        school has one person at this point, so no expense is approved or paid here (only the bank
        fees, which need no approval)."""
        last, now = self.last_month, self.this_month
        for _ in range(14):
            self.pix(self.rng.choice(AMOUNTS), self.day_in(last), paid=True)
        for _ in range(6):
            self.contribution(self.rng.choice(AMOUNTS), self.day_in(last), "PIX_DIRECT")
        for _ in range(4):
            self.contribution(self.rng.choice(AMOUNTS[:3]), self.day_in(last), "CASH")
        self.contribution(30_000, self.day_in(last), "TRANSFER", donation=True)
        for _ in range(3):
            self.bank_fee(
                self.rng.choice([180, 250, 320]), self.day_in(last), "Tarifa de Pix enviado"
            )
        self.bank_fee(1_990, last.replace(day=5), "Tarifa de manutenção da conta")

        for _ in range(9):
            self.pix(self.rng.choice(AMOUNTS), self.day_in(now), paid=True)
        self.pix(self.rng.choice(AMOUNTS), self.today, paid=False)
        for _ in range(4):
            self.contribution(self.rng.choice(AMOUNTS), self.day_in(now), "PIX_DIRECT")
        for _ in range(3):
            self.contribution(self.rng.choice(AMOUNTS[:3]), self.day_in(now), "CASH")
        for _ in range(2):
            self.bank_fee(
                self.rng.choice([180, 250, 320]), self.day_in(now), "Tarifa de Pix enviado"
            )
        self.expense(EXPENSES[3], self.day_in(now), "SUBMITTED")
        self.expense(EXPENSES[1], self.day_in(now), "SUBMITTED")
        self.expense(EXPENSES[5], self.day_in(now), "CORRECTION_REQUESTED")
        self.expense(EXPENSES[7], self.day_in(now), "DRAFT")


def fill_demo_school(db: Session, *, org: uuid.UUID, school: uuid.UUID, actor: uuid.UUID) -> bool:
    """Fill the school of the bound tenant if it has no movement yet. True when it filled.

    The caller binds the tenant and commits (or rolls back)."""
    db.execute(
        text("SELECT pg_advisory_xact_lock(:k, hashtext(:s))"), {"k": _LOCK, "s": str(school)}
    )
    if db.execute(text("SELECT 1 FROM financial_transactions LIMIT 1")).first() is not None:
        return False
    filler = _Filler(db, org, school, actor)
    account = db.execute(
        text(
            "SELECT id FROM payment_accounts WHERE school_id = :s AND provider = 'SANDBOX' "
            "AND status = 'ACTIVE'"
        ),
        {"s": school},
    ).scalar_one_or_none()
    if account is None:
        return False
    filler.account = account
    for key, category in db.execute(
        text("SELECT key, id FROM categories WHERE school_id = :s"), {"s": school}
    ):
        filler.category[str(key)] = category
    filler.run()
    return True
