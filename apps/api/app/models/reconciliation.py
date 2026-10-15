"""Bank reconciliation (migration 0017): the accounts of a school, the statements imported and their
lines. The constraints mirror the migration and carry the same names; triggers, policies and grants
live only in the migration."""

import uuid
from datetime import date, datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKeyConstraint,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.financial_common import ScopeMixin, fin_pk, in_list, scope_constraints, user_fk


class BankAccount(ScopeMixin, Base):
    __tablename__ = "bank_accounts"
    __table_args__ = (
        *scope_constraints("bank_accounts"),
        user_fk("bank_accounts", "created_by_user_id"),
        UniqueConstraint(
            "id",
            "organization_id",
            "school_id",
            name="uq_bank_accounts_id_organization_id_school_id",
        ),
        UniqueConstraint("school_id", "nickname", name="uq_bank_accounts_school_id_nickname"),
        CheckConstraint("length(btrim(nickname)) BETWEEN 1 AND 60", name="nickname_length"),
        CheckConstraint("length(btrim(bank_name)) BETWEEN 1 AND 60", name="bank_name_length"),
        CheckConstraint(
            "account_last4 IS NULL OR account_last4 ~ '^[0-9]{1,4}$'", name="last4_format"
        ),
        CheckConstraint(in_list("purpose", ("GENERAL", "PDDE")), name="purpose_valid"),
        Index("ix_bank_accounts_school_id", "school_id"),
    )

    id: Mapped[uuid.UUID] = fin_pk()
    nickname: Mapped[str] = mapped_column(Text)
    bank_name: Mapped[str] = mapped_column(Text)
    account_last4: Mapped[str | None] = mapped_column(Text)
    purpose: Mapped[str] = mapped_column(Text, server_default=text("'GENERAL'"))
    is_active: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class BankStatementImport(ScopeMixin, Base):
    __tablename__ = "bank_statement_imports"
    __table_args__ = (
        *scope_constraints("bank_statement_imports"),
        ForeignKeyConstraint(
            ["bank_account_id", "organization_id", "school_id"],
            ["bank_accounts.id", "bank_accounts.organization_id", "bank_accounts.school_id"],
            name="fk_bank_statement_imports_bank_account_id_bank_accounts",
            ondelete="RESTRICT",
        ),
        user_fk("bank_statement_imports", "uploaded_by_user_id"),
        UniqueConstraint(
            "id",
            "organization_id",
            "school_id",
            name="uq_bank_statement_imports_id_organization_id_school_id",
        ),
        UniqueConstraint(
            "school_id", "file_sha256", name="uq_bank_statement_imports_school_id_file_sha256"
        ),
        CheckConstraint("file_sha256 ~ '^[0-9a-f]{64}$'", name="sha256_format"),
        CheckConstraint("period_start <= period_end", name="period_in_order"),
        CheckConstraint(
            "line_count BETWEEN 1 AND 5000 AND new_line_count BETWEEN 0 AND line_count",
            name="line_counts",
        ),
        Index("ix_bank_statement_imports_school_id", "school_id", text("created_at DESC")),
    )

    id: Mapped[uuid.UUID] = fin_pk()
    bank_account_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    file_sha256: Mapped[str] = mapped_column(Text)
    period_start: Mapped[date] = mapped_column(Date)
    period_end: Mapped[date] = mapped_column(Date)
    line_count: Mapped[int] = mapped_column(Integer)
    new_line_count: Mapped[int] = mapped_column(Integer)
    closing_balance_cents: Mapped[int | None] = mapped_column(BigInteger)
    uploaded_by_user_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class BankStatementLine(ScopeMixin, Base):
    __tablename__ = "bank_statement_lines"
    __table_args__ = (
        *scope_constraints("bank_statement_lines"),
        ForeignKeyConstraint(
            ["import_id", "organization_id", "school_id"],
            [
                "bank_statement_imports.id",
                "bank_statement_imports.organization_id",
                "bank_statement_imports.school_id",
            ],
            name="fk_bank_statement_lines_import_id_bank_statement_imports",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["bank_account_id", "organization_id", "school_id"],
            ["bank_accounts.id", "bank_accounts.organization_id", "bank_accounts.school_id"],
            name="fk_bank_statement_lines_bank_account_id_bank_accounts",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "school_id",
            "bank_account_id",
            "bank_ref",
            name="uq_bank_statement_lines_school_id_bank_account_id_bank_ref",
        ),
        CheckConstraint(
            "amount_cents <> 0 AND abs(amount_cents) <= 100000000000", name="amount_range"
        ),
        CheckConstraint("length(memo) <= 200", name="memo_length"),
        CheckConstraint("length(bank_ref) BETWEEN 1 AND 255", name="bank_ref_length"),
        CheckConstraint(
            "end_to_end_id IS NULL OR end_to_end_id ~ '^E[0-9A-Za-z]{31}$'", name="e2e_format"
        ),
        Index("ix_bank_statement_lines_import_id", "import_id"),
        Index("ix_bank_statement_lines_school_id_posted_on", "school_id", "posted_on"),
    )

    id: Mapped[uuid.UUID] = fin_pk()
    import_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    bank_account_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    posted_on: Mapped[date] = mapped_column(Date)
    amount_cents: Mapped[int] = mapped_column(BigInteger)
    memo: Mapped[str] = mapped_column(Text)
    bank_ref: Mapped[str] = mapped_column(Text)
    end_to_end_id: Mapped[str | None] = mapped_column(Text)
    looks_like_fee: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
