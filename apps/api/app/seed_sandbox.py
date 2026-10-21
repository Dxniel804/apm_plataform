# ruff: noqa: E501  (SQL text)
"""The SANDBOX: a made-up school that bought APM Digital in September 2026 and already has September
(closed) and October (open, until the 18th) filled in, so the whole product can be looked at with real-looking
data: contributions by Pix, cash and direct Pix, expenses in every state, the bank statements of two
accounts (the APM's and the PDDE's), the PDDE classified, the tax retentions and the balancete.

    docker compose run --rm tools python -m app.seed_sandbox

FAKE data only (every name, amount and document is invented); refuses to run with ENV=production. It
creates ONE school and is a no-op when that school already exists; to start over, drop the sandbox
database volume (`docker compose down -v`) and run it again. Same rules as app/seed.py: it connects with
the admin URL of development, so it bypasses row level security by design.

The logins are printed ONCE, with a password that is generated (or SEED_PASSWORD).
"""

import hashlib
import os
import random
import secrets
import sys
from datetime import date
from typing import Any

from sqlalchemy import Connection, create_engine, text

from app.auth.passwords import MIN_LENGTH, hash_password
from app.pdde import nfe
from app.tax import calc

PRODUCTION_REFUSAL = "refusing to seed: ENV=production. The sandbox is for development only."
SLUG = "sandbox-sol-nascente"
ORG_SLUG = "sandbox-sol-nascente-conta"
SECRETARIA = ("sandbox.secretaria@example.test", "Marina Souza (sandbox)")
FUNCIONARIA = ("sandbox.funcionaria@example.test", "Paula Lima (sandbox)")
TZ = "America/Sao_Paulo"

FIRST = [
    "Ana",
    "Bruno",
    "Carla",
    "Diego",
    "Elisa",
    "Fabio",
    "Gabriela",
    "Hugo",
    "Isabela",
    "Joao",
    "Karina",
    "Luis",
    "Mariana",
    "Nelson",
    "Olivia",
    "Pedro",
    "Quiteria",
    "Rafael",
    "Sandra",
    "Tiago",
    "Ursula",
    "Vitor",
    "Wanda",
    "Yara",
]
LAST = [
    "Almeida",
    "Barros",
    "Cardoso",
    "Dias",
    "Esteves",
    "Ferraz",
    "Gomes",
    "Hernandes",
    "Ibrahim",
    "Jesus",
    "Klein",
    "Lopes",
    "Moura",
    "Nunes",
    "Oliveira",
    "Pires",
    "Queiroz",
    "Ramos",
    "Silva",
    "Teixeira",
]
# What a family gives in a month (in cents): from R$ 50 to R$ 150, the way a real APM receives it.
AMOUNTS = [5000, 8000, 10000, 10000, 12000, 15000]
CLASSES = ["1A", "1B", "2A", "2B", "3A", "3B", "4A", "4B", "5A", "5B"]

# (key of the category, description, vendor, cents, day, kind of payment): what the APM bought.
SEPT_EXPENSES = [
    (
        "cleaning_supplies",
        "Produtos de limpeza do mês",
        "Distribuidora Limpa Bem",
        28_990,
        date(2026, 9, 3),
    ),
    ("stationery", "Resmas de papel e canetas", "Papelaria Estrela", 17_620, date(2026, 9, 8)),
    (
        "teaching_material",
        "Jogos pedagógicos da sala 3",
        "Livraria Saber",
        52_700,
        date(2026, 9, 10),
    ),
    (
        "equipment_maintenance",
        "Conserto do bebedouro",
        "Refrigeração Gelo Bom",
        11_800,
        date(2026, 9, 15),
    ),
    (
        "animals",
        "Ração para os animais da horta",
        "Casa Rural Campo Belo",
        15_990,
        date(2026, 9, 17),
    ),
    ("capital_equipment", "Ventilador de parede (2)", "Eletro Mais", 189_000, date(2026, 9, 22)),
    (
        "maintenance_material",
        "Tintas e rolos para o muro",
        "Tintas Aurora",
        34_500,
        date(2026, 9, 24),
    ),
    ("office", "Toner da impressora", "Info Cartuchos", 21_900, date(2026, 9, 29)),
]
OCT_EXPENSES = [
    (
        "cleaning_supplies",
        "Sacos de lixo e desinfetante",
        "Distribuidora Limpa Bem",
        19_480,
        date(2026, 10, 2),
    ),
    ("teaching_material", "Kit de matemática (cubos)", "Livraria Saber", 38_400, date(2026, 10, 6)),
    ("stationery", "Cartolinas e EVA para o mural", "Papelaria Estrela", 9_760, date(2026, 10, 9)),
    (
        "capital_furniture",
        "Armário de aço para a secretaria",
        "Móveis Lar & Cia",
        129_900,
        date(2026, 10, 13),
    ),
]


class Sandbox:
    def __init__(self, connection: Connection, password: str) -> None:
        self.c = connection
        self.password = password
        self.rng = random.Random(20260901)  # noqa: S311  (invented data, nothing secret)
        self.e2e_used: set[str] = set()
        self.bank: dict[str, list[dict[str, Any]]] = {"general": [], "pdde": []}
        self.cash_in: dict[str, int] = {"2026-09": 0, "2026-10": 0}
        self.org: Any = None
        self.school: Any = None
        self.treasurer: Any = None
        self.submitter: Any = None
        self.category: dict[str, Any] = {}
        self.account: Any = None
        self.counter = 0

    # --- small helpers -------------------------------------------------------------------------

    def one(self, sql: Any, **params: Any) -> Any:
        return self.c.execute(sql, params).scalar_one()

    def e2e(self) -> str:
        while True:
            value = "E" + "".join(self.rng.choice("0123456789") for _ in range(31))
            if value not in self.e2e_used:
                self.e2e_used.add(value)
                return value

    def person(self) -> str:
        return f"{self.rng.choice(FIRST)} {self.rng.choice(LAST)}"

    # --- the school and its people -----------------------------------------------------------------

    def use_school(self, slug: str) -> None:
        """Fill a school that already exists (the one the Central created for an organization): the same
        data, no new organization. The two people are created with no password (they enter through the
        Central, which links them by e-mail on the first sign-in)."""
        found = self.c.execute(
            text("SELECT s.id, s.organization_id FROM schools s WHERE s.slug = :s"), {"s": slug}
        ).first()
        if found is None:
            raise SystemExit(f"no school with the slug '{slug}'")
        self.school, self.org = found[0], found[1]
        people = {
            "secretaria": (
                os.environ.get("SANDBOX_SECRETARIA_EMAIL", SECRETARIA[0]),
                SECRETARIA[1],
            ),
            "staff": (os.environ.get("SANDBOX_FUNCIONARIA_EMAIL", FUNCIONARIA[0]), FUNCIONARIA[1]),
        }
        ids: dict[str, Any] = {}
        for role, (email, name) in people.items():
            row = self.c.execute(
                text("SELECT id FROM users WHERE lower(email) = lower(:e)"), {"e": email}
            ).first()
            ids[role] = (
                row[0]
                if row is not None
                else self.one(
                    text(
                        "INSERT INTO users (email, full_name, password_hash) VALUES (:e, :n, :h) RETURNING id"
                    ),
                    e=email,
                    n=name,
                    h=hash_password(secrets.token_urlsafe(24)),
                )
            )
            if (
                self.c.execute(
                    text("SELECT 1 FROM memberships WHERE user_id = :u AND school_id = :s"),
                    {"u": ids[role], "s": self.school},
                ).first()
                is None
            ):
                self.c.execute(
                    text(
                        "INSERT INTO memberships (user_id, organization_id, school_id, role, status) VALUES (:u, :o, :s, :r, 'active')"
                    ),
                    {"u": ids[role], "o": self.org, "s": self.school, "r": role},
                )
        self.treasurer, self.submitter = ids["secretaria"], ids["staff"]
        self.finish_school()

    def create_school(self) -> None:
        self.org = self.one(
            text(
                "INSERT INTO organizations (name, slug) VALUES ('APM da EMEB Sol Nascente (sandbox)', :s) RETURNING id"
            ),
            s=ORG_SLUG,
        )
        self.school = self.one(
            text(
                "INSERT INTO schools (organization_id, name, slug) VALUES (:o, 'EMEB Sol Nascente (sandbox)', :s) RETURNING id"
            ),
            o=self.org,
            s=SLUG,
        )
        users: dict[str, Any] = {}
        for email, name in (SECRETARIA, FUNCIONARIA):
            users[email] = self.one(
                text(
                    "INSERT INTO users (email, full_name, password_hash) VALUES (:e, :n, :h) RETURNING id"
                ),
                e=email,
                n=name,
                h=hash_password(self.password),
            )
        for email, role in ((SECRETARIA[0], "secretaria"), (FUNCIONARIA[0], "staff")):
            self.c.execute(
                text(
                    "INSERT INTO memberships (user_id, organization_id, school_id, role, status) VALUES (:u, :o, :s, :r, 'active')"
                ),
                {"u": users[email], "o": self.org, "s": self.school, "r": role},
            )
        self.treasurer, self.submitter = users[SECRETARIA[0]], users[FUNCIONARIA[0]]
        self.finish_school()

    def finish_school(self) -> None:
        # The categories and the settings come from the trigger of the school; the goals are the school's own.
        self.c.execute(
            text(
                "UPDATE school_settings SET monthly_goal_cents = 1000000, expected_contributions = 90 WHERE school_id = :s"
            ),
            {"s": self.school},
        )
        for row in self.c.execute(
            text("SELECT key, id FROM categories WHERE school_id = :s"), {"s": self.school}
        ):
            self.category[str(row[0])] = row[1]
        self.account = self.one(
            text(
                "INSERT INTO payment_accounts (organization_id, school_id, provider, external_account_id, status, secret_ref, webhook_secret_hash) "
                "VALUES (:o, :s, 'SANDBOX', 'sandbox-sol-nascente', 'ACTIVE', 'env:APM_DEMO_PIX_SECRET', encode(sha256(gen_random_uuid()::text::bytea), 'hex')) RETURNING id"
            ),
            o=self.org,
            s=self.school,
        )

    # --- the ledger -----------------------------------------------------------------------------

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
        author: Any = None,
        origin_user: Any = None,
        settled: bool = False,
        parent: Any = None,
        parent_kind: str | None = None,
    ) -> Any:
        return self.one(
            text(
                "INSERT INTO financial_transactions (organization_id, school_id, kind, direction, amount_cents, status, category_id, origin_type, origin_user_id, "
                "occurred_at, settled_at, created_by_user_id, parent_transaction_id, parent_kind) "
                "VALUES (:o, :s, :kind, :direction, :amount, :status, :category, :origin_type, :origin_user, "
                "(CAST(:day AS date) + time '12:00') AT TIME ZONE 'America/Sao_Paulo', "
                "CASE WHEN :settled THEN (CAST(:day AS date) + time '12:00') AT TIME ZONE 'America/Sao_Paulo' END, "
                ":author, :parent, :parent_kind) RETURNING id"
            ),
            o=self.org, s=self.school, kind=kind, direction=direction, amount=amount, status=status,
            category=self.category[category], origin_type=origin_type, origin_user=origin_user, day=day,
            settled=settled, author=author, parent=parent, parent_kind=parent_kind,
        )  # fmt: skip

    def settle(self, tx: Any, status: str, day: date) -> None:
        self.c.execute(
            text(
                "UPDATE financial_transactions SET status = :st, settled_at = (CAST(:day AS date) + time '12:00') AT TIME ZONE 'America/Sao_Paulo' WHERE id = :t"
            ),
            {"st": status, "day": day, "t": tx},
        )

    def move(self, tx: Any, status: str) -> None:
        self.c.execute(
            text("UPDATE financial_transactions SET status = :st WHERE id = :t"),
            {"st": status, "t": tx},
        )

    def bank_row(
        self,
        account: str,
        day: date,
        amount: int,
        memo: str,
        *,
        e2e: str | None = None,
        fee: bool = False,
    ) -> None:
        self.bank[account].append(
            {"day": day, "amount": amount, "memo": memo, "e2e": e2e, "fee": fee}
        )

    def contribution(
        self,
        amount: int,
        day: date,
        method: str,
        *,
        name: str | None = None,
        donation: bool = False,
    ) -> None:
        """A contribution already paid: cash, a transfer, or a Pix straight to the key of the APM."""
        who = name or self.person()
        tx = self.tx(
            kind="CONTRIBUTION", direction="IN", amount=amount, status="PAID",
            category="donation" if donation else "parent_contribution",
            origin_type="OTHER" if donation else "GUARDIAN", day=day, author=self.treasurer, settled=True,
        )  # fmt: skip
        e2e = self.e2e() if method == "PIX_DIRECT" else None
        self.c.execute(
            text(
                "INSERT INTO contributions (transaction_id, organization_id, school_id, method, external_reference, guardian_name, student_name, class_name, reference_month) "
                "VALUES (:t, :o, :s, :m, :e, :g, :st, :c, date_trunc('month', CAST(:day AS date))::date)"
            ),
            {
                "t": tx,
                "o": self.org,
                "s": self.school,
                "m": method,
                "e": e2e,
                "g": who,
                "st": None if donation else self.person(),
                "c": None if donation else self.rng.choice(CLASSES),
                "day": day,
            },
        )
        if method == "CASH":
            self.cash_in[f"{day.year}-{day.month:02d}"] += amount
        else:
            self.bank_row(
                "general",
                day,
                amount,
                f"PIX RECEBIDO {who.upper()}"
                if method == "PIX_DIRECT"
                else f"TRANSFERENCIA RECEBIDA {who.upper()}",
                e2e=e2e,
            )

    def pix(self, amount: int, day: date, outcome: str) -> None:
        """A Pix made through the family's page (the charge of the platform): paid, waiting, or with another amount."""
        who = self.person()
        tx = self.tx(
            kind="CONTRIBUTION",
            direction="IN",
            amount=amount,
            status="PENDING_PAYMENT",
            category="parent_contribution",
            origin_type="GUARDIAN",
            day=day,
        )
        self.c.execute(
            text(
                "INSERT INTO contributions (transaction_id, organization_id, school_id, method, guardian_name, student_name, class_name, reference_month, receipt_token_hash, receipt_expires_at) "
                "VALUES (:t, :o, :s, 'PIX', :g, :st, :c, date_trunc('month', CAST(:day AS date))::date, encode(sha256(gen_random_uuid()::text::bytea), 'hex'), now() + interval '30 days')"
            ),
            {
                "t": tx,
                "o": self.org,
                "s": self.school,
                "g": who,
                "st": self.person(),
                "c": self.rng.choice(CLASSES),
                "day": day,
            },
        )
        charge = self.one(
            text(
                "INSERT INTO pix_charges (organization_id, school_id, transaction_id, payment_account_id, provider, txid, amount_cents, expires_at) "
                "VALUES (:o, :s, :t, :a, 'SANDBOX', replace(gen_random_uuid()::text, '-', ''), :amount, now() + interval '30 minutes') RETURNING id"
            ),
            o=self.org, s=self.school, t=tx, a=self.account, amount=amount,
        )  # fmt: skip
        if outcome == "pending":
            return
        e2e = self.e2e()
        received = amount if outcome == "paid" else amount + 500
        self.c.execute(
            text(
                "UPDATE pix_charges SET status = :st, paid_at = (CAST(:day AS date) + time '12:00') AT TIME ZONE 'America/Sao_Paulo', received_amount_cents = :r, divergence_reason = :why, end_to_end_id = :e WHERE id = :c"
            ),
            {
                "st": "PAID" if outcome == "paid" else "REVIEW_REQUIRED",
                "day": day,
                "r": received,
                "why": None
                if outcome == "paid"
                else "valor recebido diferente do esperado (sandbox)",
                "e": e2e,
                "c": charge,
            },
        )
        if outcome == "paid":
            self.settle(tx, "PAID", day)
            self.bank_row("general", day, amount, f"PIX RECEBIDO {who.upper()}", e2e=e2e)
        else:
            self.move(tx, "REVIEW_REQUIRED")
            self.bank_row("general", day, received, f"PIX RECEBIDO {who.upper()}", e2e=e2e)

    def bank_fee(self, amount: int, day: date, description: str) -> None:
        tx = self.tx(
            kind="EXPENSE",
            direction="OUT",
            amount=amount,
            status="APPROVED",
            category="bank_fees",
            origin_type="BANK",
            day=day,
            author=self.treasurer,
        )
        self.c.execute(
            text(
                "INSERT INTO expenses (transaction_id, organization_id, school_id, description, paid_by, submitted_by_user_id) VALUES (:t, :o, :s, :d, 'APM', :u)"
            ),
            {"t": tx, "o": self.org, "s": self.school, "d": description, "u": self.treasurer},
        )
        self.settle(tx, "PAID", day)
        self.bank_row("general", day, -amount, "TARIFA PIX ENVIADO", fee=True)

    def expense(
        self,
        key: str,
        description: str,
        vendor: str,
        amount: int,
        day: date,
        status: str,
        *,
        paid_by: str = "APM",
        approved: int | None = None,
        pay_by_pix: bool = True,
    ) -> Any:
        """An expense of the APM in any state of its life (the staff submits, the secretaria decides)."""
        start = "DRAFT" if status == "DRAFT" else "SUBMITTED"
        tx = self.tx(
            kind="EXPENSE",
            direction="OUT",
            amount=amount,
            status=start,
            category=key,
            origin_type="TEACHER",
            origin_user=self.submitter,
            day=day,
            author=self.submitter,
        )
        self.c.execute(
            text(
                "INSERT INTO expenses (transaction_id, organization_id, school_id, description, vendor, purchase_reason, payment_method, paid_by, submitted_by_user_id) "
                "VALUES (:t, :o, :s, :d, :v, 'uso da escola (sandbox)', 'PIX', :p, :u)"
            ),
            {
                "t": tx,
                "o": self.org,
                "s": self.school,
                "d": description,
                "v": vendor,
                "p": paid_by,
                "u": self.submitter,
            },
        )
        if start != "DRAFT":
            self.c.execute(
                text(
                    "INSERT INTO expense_attachments (organization_id, school_id, transaction_id, kind, storage_key, file_name, content_type, size_bytes, sha256, uploaded_by_user_id) "
                    "VALUES (:o, :s, :t, 'INVOICE', :k, 'nota-sandbox.pdf', 'application/pdf', 2048, encode(sha256(gen_random_uuid()::text::bytea), 'hex'), :u)"
                ),
                {
                    "o": self.org,
                    "s": self.school,
                    "t": tx,
                    "k": f"sandbox/{tx}",
                    "u": self.submitter,
                },
            )
        if status == "CORRECTION_REQUESTED":
            self.c.execute(
                text(
                    "UPDATE expenses SET correction_reason = 'anexe o comprovante do pagamento (sandbox)' WHERE transaction_id = :t"
                ),
                {"t": tx},
            )
            self.move(tx, "CORRECTION_REQUESTED")
        elif status in ("APPROVED", "PAID"):
            self.c.execute(
                text(
                    "UPDATE expenses SET approved_by_user_id = :u, approved_amount_cents = :a WHERE transaction_id = :t"
                ),
                {"u": self.treasurer, "a": approved or amount, "t": tx},
            )
            self.move(tx, "APPROVED")
            if status == "PAID":
                self.settle(tx, "PAID", day)
                if paid_by == "APM" and pay_by_pix:
                    self.bank_row("general", day, -amount, f"PIX ENVIADO {vendor.upper()}")
        return tx

    def reimbursement(self, expense_id: Any, amount: int, day: date, *, paid: bool) -> None:
        tx = self.tx(
            kind="REIMBURSEMENT", direction="OUT", amount=amount, status="PENDING", category="teacher_reimbursement",
            origin_type="TEACHER", origin_user=self.submitter, day=day, author=self.treasurer, parent=expense_id, parent_kind="EXPENSE",
        )  # fmt: skip
        self.c.execute(
            text(
                "INSERT INTO reimbursements (transaction_id, organization_id, school_id, beneficiary_user_id) VALUES (:t, :o, :s, :b)"
            ),
            {"t": tx, "o": self.org, "s": self.school, "b": self.submitter},
        )
        if paid:
            self.c.execute(
                text(
                    "UPDATE reimbursements SET payment_reference = 'sandbox-transferencia-001', paid_by_user_id = :u WHERE transaction_id = :t"
                ),
                {"u": self.treasurer, "t": tx},
            )
            self.settle(tx, "PAID", day)
            self.settle(expense_id, "PAID", day)
            self.bank_row("general", day, -amount, "TRANSFERENCIA ENVIADA PAULA LIMA")

    def give_back(self, amount: int, day: date, parent: Any) -> None:
        tx = self.tx(
            kind="REFUND", direction="IN", amount=amount, status="REQUESTED", category="refund", origin_type="TEACHER",
            origin_user=self.submitter, day=day, author=self.treasurer, parent=parent, parent_kind="EXPENSE",
        )  # fmt: skip
        self.c.execute(
            text(
                "INSERT INTO refunds (transaction_id, organization_id, school_id, reason) VALUES (:t, :o, :s, 'Troco da compra devolvido (sandbox)')"
            ),
            {"t": tx, "o": self.org, "s": self.school},
        )
        self.move(tx, "AWAITING_CONFIRMATION")
        self.c.execute(
            text("UPDATE refunds SET confirmed_by_user_id = :u WHERE transaction_id = :t"),
            {"u": self.treasurer, "t": tx},
        )
        self.settle(tx, "CONFIRMED", day)
        self.bank_row("general", day, amount, "PIX RECEBIDO PAULA LIMA", e2e=self.e2e())

    def ledger(self) -> None:
        """September in full and October until the 18th."""
        # September: 24 Pix of the page, 8 direct Pix, 6 in cash, one donation, one Pix with another amount.
        for _ in range(50):
            self.pix(self.rng.choice(AMOUNTS), date(2026, 9, self.rng.randint(1, 29)), "paid")
        for _ in range(12):
            self.contribution(
                self.rng.choice(AMOUNTS), date(2026, 9, self.rng.randint(1, 29)), "PIX_DIRECT"
            )
        for _ in range(8):
            self.contribution(
                self.rng.choice(AMOUNTS[:3]), date(2026, 9, self.rng.randint(1, 29)), "CASH"
            )
        self.contribution(
            30_000, date(2026, 9, 12), "TRANSFER", name="Mercado Bom Preço (doação)", donation=True
        )
        self.pix(3000, date(2026, 9, 26), "review")
        for key, description, vendor, cents, day in SEPT_EXPENSES:
            self.expense(key, description, vendor, cents, day, "PAID")
        # The services that held back a tax: the ledger has what LEFT the account (the net).
        self.expense(
            "services",
            "Pintura do muro da quadra",
            "Pintura Cores do Sul Ltda",
            118_200,
            date(2026, 9, 18),
            "PAID",
        )
        self.expense(
            "services",
            "Jardinagem e poda das árvores",
            "Jardim Verde ME",
            88_650,
            date(2026, 9, 25),
            "PAID",
        )
        paid_by_staff = self.expense(
            "school_supplies",
            "Material para a feira de ciências",
            "Papelaria Estrela",
            14_500,
            date(2026, 9, 14),
            "APPROVED",
            paid_by="COLLABORATOR",
        )
        self.reimbursement(paid_by_staff, 14_500, date(2026, 9, 16), paid=True)
        partial = self.expense(
            "school_supplies",
            "Lanche da reunião de pais",
            "Padaria Pão Quente",
            9_000,
            date(2026, 9, 5),
            "PAID",
        )
        self.give_back(1_500, date(2026, 9, 6), partial)
        self.bank_fee(1_890, date(2026, 9, 30), "Tarifa de pacote de serviços (setembro)")
        # October, until the 18th.
        for _ in range(30):
            self.pix(self.rng.choice(AMOUNTS), date(2026, 10, self.rng.randint(1, 18)), "paid")
        for _ in range(8):
            self.contribution(
                self.rng.choice(AMOUNTS), date(2026, 10, self.rng.randint(1, 18)), "PIX_DIRECT"
            )
        for _ in range(5):
            self.contribution(
                self.rng.choice(AMOUNTS[:3]), date(2026, 10, self.rng.randint(1, 18)), "CASH"
            )
        self.pix(3000, date(2026, 10, 17), "review")
        self.pix(2000, date(2026, 10, 18), "pending")
        for key, description, vendor, cents, day in OCT_EXPENSES:
            self.expense(key, description, vendor, cents, day, "PAID")
        self.expense(
            "services",
            "Troca de fiação da sala 2",
            "Carlos Eletricista",
            44_500,
            date(2026, 10, 8),
            "PAID",
        )
        self.expense(
            "services",
            "Troca de fechaduras",
            "Chaveiro Pronto Socorro Ltda",
            39_400,
            date(2026, 10, 15),
            "PAID",
        )
        self.expense(
            "other_authorized",
            "Reparo do portão (aguardando aprovação)",
            "Serralheria Ferro Forte",
            26_000,
            date(2026, 10, 16),
            "SUBMITTED",
        )
        self.expense(
            "office",
            "Cartuchos de tinta (aguardando aprovação)",
            "Info Cartuchos",
            12_300,
            date(2026, 10, 17),
            "SUBMITTED",
        )
        self.expense(
            "teaching_material",
            "Livros de leitura da biblioteca",
            "Livraria Saber",
            31_900,
            date(2026, 10, 14),
            "CORRECTION_REQUESTED",
        )
        self.expense(
            "cleaning_supplies",
            "Rascunho: material de limpeza",
            "Distribuidora Limpa Bem",
            7_800,
            date(2026, 10, 18),
            "DRAFT",
        )
        self.expense(
            "stationery",
            "Carimbos e almofadas (aprovada, falta pagar)",
            "Papelaria Estrela",
            6_400,
            date(2026, 10, 16),
            "APPROVED",
        )
        pending_reimbursement = self.expense(
            "school_supplies",
            "Água e copos para o evento",
            "Mercadinho do Zé",
            8_200,
            date(2026, 10, 11),
            "APPROVED",
            paid_by="COLLABORATOR",
        )
        self.reimbursement(pending_reimbursement, 8_200, date(2026, 10, 12), paid=False)
        self.bank_fee(1_890, date(2026, 10, 15), "Tarifa de pacote de serviços (outubro)")

    # --- the banks -------------------------------------------------------------------------------

    def bank_account(self, nickname: str, purpose: str, last4: str) -> Any:
        return self.one(
            text("INSERT INTO bank_accounts (organization_id, school_id, nickname, bank_name, account_last4, purpose, created_by_user_id) VALUES (:o, :s, :n, 'Banco do Brasil', :l, :p, :u) RETURNING id"),
            o=self.org, s=self.school, n=nickname, l=last4, p=purpose, u=self.treasurer,
        )  # fmt: skip

    def statements(
        self, account: Any, rows: list[dict[str, Any]], opening: int, label: str
    ) -> dict[str, Any]:
        """One import for September and one for October (up to the 18th), with the balance of the bank at the end of each."""
        lines: dict[str, Any] = {}
        balance = opening
        for period, (start, end) in {
            "2026-09": (date(2026, 9, 1), date(2026, 9, 30)),
            "2026-10": (date(2026, 10, 1), date(2026, 10, 18)),
        }.items():
            chosen = sorted(
                (r for r in rows if start <= r["day"] <= end), key=lambda r: (r["day"], r["memo"])
            )
            if not chosen:
                continue
            balance += sum(r["amount"] for r in chosen)
            digest = hashlib.sha256(f"{label}-{period}".encode()).hexdigest()
            import_id = self.one(
                text(
                    "INSERT INTO bank_statement_imports (organization_id, school_id, bank_account_id, file_sha256, period_start, period_end, line_count, new_line_count, closing_balance_cents, uploaded_by_user_id, source) "
                    "VALUES (:o, :s, :a, :h, :ps, :pe, :n, :n, :b, :u, 'OFX') RETURNING id"
                ),
                o=self.org, s=self.school, a=account, h=digest, ps=start, pe=end, n=len(chosen), b=balance, u=self.treasurer,
            )  # fmt: skip
            for index, r in enumerate(chosen):
                self.counter += 1
                lines[f"{label}:{period}:{index}"] = self.one(
                    text(
                        "INSERT INTO bank_statement_lines (organization_id, school_id, import_id, bank_account_id, posted_on, amount_cents, memo, bank_ref, end_to_end_id, looks_like_fee) "
                        "VALUES (:o, :s, :i, :a, :d, :amt, :m, :ref, :e, :f) RETURNING id"
                    ),
                    o=self.org, s=self.school, i=import_id, a=account, d=r["day"], amt=r["amount"], m=r["memo"][:120],
                    ref=f"sandbox-{label}-{self.counter:05d}", e=r["e2e"], f=r["fee"],
                )  # fmt: skip
                r["line_id"] = lines[f"{label}:{period}:{index}"]
            lines[f"{label}:{period}:balance"] = balance
        return lines

    def banks(self) -> None:
        # In the bank but not in the ledger (a Pix nobody registered, a fee the ledger does not have): the comparison shows them.
        self.bank_row(
            "general", date(2026, 10, 7), 4_500, "PIX RECEBIDO FAMILIA SEM CADASTRO", e2e=self.e2e()
        )
        self.bank_row("general", date(2026, 9, 29), -1_250, "TARIFA TED", fee=True)
        general = self.bank_account("Conta da APM (BB)", "GENERAL", "4521")
        self.statements(general, self.bank["general"], 1_840_000, "geral")
        pdde = self.bank_account("Conta PDDE (BB)", "PDDE", "9087")
        self.pdde_account = pdde
        self.pdde_lines()
        self.statements(pdde, self.bank["pdde"], 0, "pdde")
        self.pdde_decisions()

    # --- the PDDE --------------------------------------------------------------------------------

    def pdde_lines(self) -> None:
        rows = [
            (date(2026, 9, 3), 240_000, "CREDITO FNDE PDDE BASICO CUSTEIO"),
            (date(2026, 9, 3), 360_000, "CREDITO FNDE PDDE BASICO CAPITAL"),
            (date(2026, 9, 12), -115_040, "PAGAMENTO PAPELARIA MODELO LTDA"),
            (date(2026, 9, 18), -298_000, "PAGAMENTO LOJA ELETRO EXEMPLO"),
            (date(2026, 9, 25), -1_490, "TARIFA PACOTE DE SERVICOS"),
            (date(2026, 10, 6), 350_000, "CREDITO FNDE EDUCACAO CONECTADA"),
            (date(2026, 10, 9), -48_000, "PAGAMENTO TELECOM EXEMPLO"),
            (date(2026, 10, 14), -125_000, "PAGAMENTO SERVICOS REPARO PREDIAL"),
            (date(2026, 9, 30), 1_832, "RENDIMENTO APLICACAO FINANCEIRA"),
            (date(2026, 10, 16), -10_000, "DEVOLUCAO SALDO AO FNDE"),
        ]
        for day, amount, memo in rows:
            self.bank_row("pdde", day, amount, memo, fee="TARIFA" in memo)

    def pdde_decisions(self) -> None:
        line = {r["memo"]: r["line_id"] for r in self.bank["pdde"]}

        def classify(
            memo: str,
            kind: str,
            program: str | None,
            category: str | None,
            obj: str | None,
            pay: str | None = None,
        ) -> None:
            self.c.execute(
                text(
                    "INSERT INTO pdde_classifications (organization_id, school_id, line_id, kind, program, economic_category, object, payment_number, created_by_user_id) VALUES (:o, :s, :l, :k, :p, :c, :ob, :pay, :u)"
                ),
                {
                    "o": self.org,
                    "s": self.school,
                    "l": line[memo],
                    "k": kind,
                    "p": program,
                    "c": category,
                    "ob": obj,
                    "pay": pay,
                    "u": self.treasurer,
                },
            )

        def document(
            memo: str,
            kind: str,
            number: str,
            day: date,
            vendor: str,
            cents: int,
            stamped: bool,
            tax: str | None = None,
            qty: int | None = None,
            spec: str | None = None,
        ) -> None:
            key = None
            if kind == "NFE":
                body = f"3526091234567800019055001{int(number):09d}1000000{int(number):02d}"[
                    :43
                ].ljust(43, "0")
                key = body + str(nfe.check_digit(body))
            self.c.execute(
                text(
                    "INSERT INTO pdde_documents (organization_id, school_id, line_id, doc_kind, access_key, doc_number, issued_on, vendor, amount_cents, stamped, vendor_tax_id, quantity, specification, created_by_user_id) VALUES (:o, :s, :l, :k, :a, :n, :d, :v, :c, :st, :t, :q, :sp, :u)"
                ),
                {
                    "o": self.org,
                    "s": self.school,
                    "l": line[memo],
                    "k": kind,
                    "a": key,
                    "n": number,
                    "d": day,
                    "v": vendor,
                    "c": cents,
                    "st": stamped,
                    "t": tax,
                    "q": qty,
                    "sp": spec,
                    "u": self.treasurer,
                },
            )

        classify("CREDITO FNDE PDDE BASICO CUSTEIO", "TRANSFER", "BASICO", "CUSTEIO", None)
        classify("CREDITO FNDE PDDE BASICO CAPITAL", "TRANSFER", "BASICO", "CAPITAL", None)
        classify(
            "PAGAMENTO PAPELARIA MODELO LTDA",
            "EXPENSE",
            "BASICO",
            "CUSTEIO",
            "Material de consumo",
            "OB 2026091201",
        )
        document(
            "PAGAMENTO PAPELARIA MODELO LTDA",
            "NFE",
            "101",
            date(2026, 9, 11),
            "Papelaria Modelo Ltda",
            115_040,
            True,
            "11444777000161",
        )
        classify(
            "PAGAMENTO LOJA ELETRO EXEMPLO",
            "EXPENSE",
            "BASICO",
            "CAPITAL",
            "Material permanente",
            "OB 2026091801",
        )
        document(
            "PAGAMENTO LOJA ELETRO EXEMPLO",
            "RECEIPT",
            "55",
            date(2026, 9, 17),
            "Loja Eletro Exemplo",
            200_000,
            True,
            "12345678000195",
            4,
            "Ventilador de parede 60 cm",
        )  # only part of it is proved
        classify("RENDIMENTO APLICACAO FINANCEIRA", "YIELD", "BASICO", "CUSTEIO", None)
        classify(
            "DEVOLUCAO SALDO AO FNDE", "RETURN_TO_FNDE", "BASICO", "CUSTEIO", None, "OB 2026101601"
        )
        classify("CREDITO FNDE EDUCACAO CONECTADA", "TRANSFER", "CONECTADO", None, None)
        # A repair paid with PDDE and classified as capital by mistake: it makes the "spent more than came in capital" warning appear.
        classify(
            "PAGAMENTO SERVICOS REPARO PREDIAL", "EXPENSE", "BASICO", "CAPITAL", "Pequenos reparos"
        )
        # "PAGAMENTO TELECOM EXEMPLO" and the fee of September are left for the person to classify.
        # What the official form asks for and the school typed once (all invented): the entity and the
        # balance that came from the year before.
        self.c.execute(
            text(
                "INSERT INTO pdde_entities (organization_id, school_id, legal_name, cnpj, address, city, state, created_by_user_id) VALUES (:o, :s, 'ASSOCIACAO DE PAIS E MESTRES DA EMEB SOL NASCENTE (SANDBOX)', '11222333000181', 'Rua das Flores, 100', 'Jundiaí', 'SP', :u)"
            ),
            {"o": self.org, "s": self.school, "u": self.treasurer},
        )
        self.c.execute(
            text(
                "INSERT INTO pdde_carryovers (organization_id, school_id, year, program, program_label, custeio_cents, capital_cents, created_by_user_id) VALUES (:o, :s, 2026, 'BASICO', NULL, 120000, 0, :u)"
            ),
            {"o": self.org, "s": self.school, "u": self.treasurer},
        )

    # --- taxes -----------------------------------------------------------------------------------

    def taxes(self) -> None:
        def rule(
            key: str,
            label: str,
            kind: str,
            applies: str,
            bps: int,
            cap: int | None,
            code: str | None,
            howto: str | None,
            source: str | None,
            checked: bool,
        ) -> Any:
            return self.one(
                text(
                    "INSERT INTO tax_rules (organization_id, school_id, rule_key, label, tax_kind, applies_to, rate_bps, base_cap_cents, min_total_cents, darf_code, howto, due_day, due_roll, source_note, validated_at, validated_by_user_id, created_by_user_id) "
                    "VALUES (:o, :s, :k, :l, :t, :a, :r, :cap, 1000, :code, :how, 20, 'PREVIOUS', :src, CASE WHEN :ok THEN now() END, CASE WHEN :ok THEN :u END, :u) RETURNING id"
                ),
                o=self.org, s=self.school, k=key, l=label, t=kind, a=applies, r=bps, cap=cap, code=code, how=howto, src=source, ok=checked, u=self.treasurer,
            )  # fmt: skip

        irrf = rule(
            "irrf-servicos-pj",
            "IRRF sobre serviço de empresa (exemplo)",
            "IRRF",
            "PJ",
            150,
            None,
            "1708",
            None,
            None,
            False,
        )
        inss = rule(
            "inss-autonomo",
            "INSS retido de autônomo (exemplo)",
            "INSS",
            "PF",
            1100,
            847_555,
            None,
            "Veja no site da Receita como recolher o INSS retido (eSocial/DCTFWeb).",
            None,
            False,
        )
        rule(
            "iss-municipal",
            "ISS retido (exemplo conferido)",
            "ISS",
            "BOTH",
            300,
            None,
            None,
            "Guia no site da prefeitura.",
            "SANDBOX: exemplo inventado, não é fonte oficial",
            True,
        )

        def retention(
            rule_id: Any,
            kind: str,
            name: str,
            competence: date,
            gross: int,
            bps: int,
            cap: int | None,
        ) -> None:
            base, retained = calc.retention(gross, bps, cap)
            self.c.execute(
                text(
                    "INSERT INTO tax_retentions (organization_id, school_id, rule_id, provider_kind, provider_name, competence, gross_cents, base_cents, retained_cents, rate_bps, created_by_user_id) "
                    "VALUES (:o, :s, :r, :k, :n, :c, :g, :b, :t, :bps, :u)"
                ),
                {
                    "o": self.org,
                    "s": self.school,
                    "r": rule_id,
                    "k": kind,
                    "n": name,
                    "c": competence,
                    "g": gross,
                    "b": base,
                    "t": retained,
                    "bps": bps,
                    "u": self.treasurer,
                },
            )

        retention(irrf, "PJ", "Pintura Cores do Sul Ltda", date(2026, 9, 1), 120_000, 150, None)
        retention(irrf, "PJ", "Jardim Verde ME", date(2026, 9, 1), 90_000, 150, None)
        retention(inss, "PF", "Carlos Eletricista", date(2026, 10, 1), 50_000, 1100, 847_555)
        retention(irrf, "PJ", "Chaveiro Pronto Socorro Ltda", date(2026, 10, 1), 40_000, 150, None)

    # --- balancete and closing -------------------------------------------------------------------

    def balancete(self) -> None:
        self.c.execute(
            text(
                "INSERT INTO balancete_balances (organization_id, school_id, kind, period_start, bank_cents, cash_cents, investment_cents, created_by_user_id) VALUES (:o, :s, 'OPENING', NULL, 1840000, 65000, 200000, :u)"
            ),
            {"o": self.org, "s": self.school, "u": self.treasurer},
        )
        # At the end of September: the cash the school had at the start plus the cash contributions of the month, and the money invested.
        self.c.execute(
            text(
                "INSERT INTO balancete_balances (organization_id, school_id, kind, period_start, bank_cents, cash_cents, investment_cents, created_by_user_id) VALUES (:o, :s, 'MONTH', '2026-09-01', NULL, :cash, 200000, :u)"
            ),
            {
                "o": self.org,
                "s": self.school,
                "cash": 65_000 + self.cash_in["2026-09"],
                "u": self.treasurer,
            },
        )

    def close_september(self, bank_balance: int) -> None:
        self.c.execute(
            text(
                "INSERT INTO monthly_closings (organization_id, school_id, period_start, closed_by_user_id, bank_balance_reported_cents) VALUES (:o, :s, '2026-09-01', :u, :b)"
            ),
            {"o": self.org, "s": self.school, "u": self.treasurer, "b": bank_balance},
        )


def build(connection: Connection, password: str) -> str:
    connection.execute(text("SELECT set_config('app.actor_type', 'SYSTEM', true)"))
    # SANDBOX_FILL_SCHOOL: fill the school the Central created, instead of making a new one.
    fill = os.environ.get("SANDBOX_FILL_SCHOOL")
    target = fill or SLUG
    exists = connection.execute(
        text("SELECT 1 FROM schools WHERE slug = :s"), {"s": target}
    ).first()
    if fill is None and exists is not None:
        return "the sandbox school already exists: nothing to do (to start over: docker compose down -v)"
    if fill is not None:
        if exists is None:
            return f"no school with the slug '{fill}': nothing to fill"
        filled = connection.execute(
            text(
                "SELECT 1 FROM financial_transactions t JOIN schools s ON s.id = t.school_id WHERE s.slug = :s LIMIT 1"
            ),
            {"s": fill},
        ).first()
        if filled is not None:
            return f"the school '{fill}' already has data: nothing to do"
    box = Sandbox(connection, password)
    if fill is None:
        box.create_school()
    else:
        box.use_school(fill)
    box.ledger()
    box.banks()
    box.taxes()
    box.balancete()
    sept_bank: Any = connection.execute(
        text(
            "SELECT i.closing_balance_cents FROM bank_statement_imports i JOIN bank_accounts a ON a.id = i.bank_account_id WHERE a.school_id = :s AND a.purpose = 'GENERAL' AND i.period_end = '2026-09-30'"
        ),
        {"s": box.school},
    ).scalar_one()
    box.close_september(int(sept_bank))
    return f"created the sandbox school '{target}' (September closed, October open until the 18th)"


def main() -> int:
    if os.environ.get("ENV", "").strip().lower() == "production":
        print(PRODUCTION_REFUSAL, file=sys.stderr)
        return 1
    from app.core.config import get_admin_settings

    settings = get_admin_settings()
    if settings.is_production:
        print(PRODUCTION_REFUSAL, file=sys.stderr)
        return 1
    chosen = os.environ.get("SEED_PASSWORD")
    if chosen is not None and len(chosen) < MIN_LENGTH:
        print(
            f"refusing to seed: SEED_PASSWORD must have at least {MIN_LENGTH} characters",
            file=sys.stderr,
        )
        return 1
    password = chosen if chosen is not None else secrets.token_urlsafe(18)
    engine = create_engine(settings.database_admin_url.get_secret_value())
    try:
        with engine.begin() as connection:
            bypasses_rls: Any = connection.execute(
                text("SELECT rolsuper OR rolbypassrls FROM pg_roles WHERE rolname = current_user")
            ).scalar_one()
            if not bypasses_rls:
                print(
                    "refusing to seed: the admin role must be able to bypass row level security (a development superuser).",
                    file=sys.stderr,
                )
                return 1
            message = build(connection, password)
    finally:
        engine.dispose()
    print(message)
    if message.startswith("created") and os.environ.get("SANDBOX_FILL_SCHOOL") is None:
        print(f"login: {SECRETARIA[0]} (secretaria) and {FUNCIONARIA[0]} (funcionária)")
        print(f"SANDBOX_PASSWORD={password}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
