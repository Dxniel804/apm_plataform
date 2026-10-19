# ruff: noqa: E501  (long lines)
"""PDDE (migration 0028): what the management decided about a line of the PDDE bank account, and
the documents that prove an expense. The constraints mirror the migration and carry the same names;
triggers, policies and grants live only in the migration."""

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
    SmallInteger,
    Text,
    Uuid,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.financial_common import ScopeMixin, fin_pk, in_list, scope_constraints, user_fk


def _line_fk(table: str) -> ForeignKeyConstraint:
    return ForeignKeyConstraint(
        ["line_id"],
        ["bank_statement_lines.id"],
        name=f"fk_{table}_line_id_bank_statement_lines",
        ondelete="RESTRICT",
    )


class PddeClassification(ScopeMixin, Base):
    __tablename__ = "pdde_classifications"
    __table_args__ = (
        *scope_constraints("pdde_classifications"),
        _line_fk("pdde_classifications"),
        user_fk("pdde_classifications", "created_by_user_id"),
        CheckConstraint(
            in_list(
                "kind",
                (
                    "TRANSFER",
                    "YIELD",
                    "EXPENSE",
                    "RETURN_TO_FNDE",
                    "TAX_TO_EEX",
                    "REFUND",
                    "INELIGIBLE",
                ),
            ),
            name="kind_valid",
        ),
        CheckConstraint(
            "program IS NULL OR "
            + in_list("program", ("BASICO", "EQUIDADE", "QUALIDADE", "CONECTADO", "OUTRO")),
            name="program_valid",
        ),
        CheckConstraint(
            "economic_category IS NULL OR " + in_list("economic_category", ("CUSTEIO", "CAPITAL")),
            name="category_valid",
        ),
        CheckConstraint(
            "(program IS NOT DISTINCT FROM 'OUTRO') = (program_label IS NOT NULL) "
            "AND (program_label IS NULL OR length(btrim(program_label)) BETWEEN 1 AND 60)",
            name="label_shape",
        ),
        CheckConstraint(
            "object IS NULL OR length(btrim(object)) BETWEEN 1 AND 120", name="object_length"
        ),
        CheckConstraint("note IS NULL OR length(note) <= 300", name="note_length"),
        CheckConstraint(
            "payment_number IS NULL OR length(btrim(payment_number)) BETWEEN 1 AND 40",
            name="payment_number_length",
        ),
        CheckConstraint(
            "(kind = 'TRANSFER' AND program IS NOT NULL AND object IS NULL) "
            "OR (kind IN ('YIELD', 'RETURN_TO_FNDE') AND program IS NOT NULL "
            "AND economic_category IS NOT NULL AND object IS NULL) "
            "OR (kind = 'EXPENSE' AND program IS NOT NULL AND economic_category IS NOT NULL "
            "AND object IS NOT NULL) "
            "OR kind IN ('TAX_TO_EEX', 'REFUND', 'INELIGIBLE')",
            name="shape",
        ),
        Index("ix_pdde_classifications_line_id", "line_id", text("created_at DESC")),
    )

    id: Mapped[uuid.UUID] = fin_pk()
    line_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    kind: Mapped[str] = mapped_column(Text)
    program: Mapped[str | None] = mapped_column(Text)
    program_label: Mapped[str | None] = mapped_column(Text)
    economic_category: Mapped[str | None] = mapped_column(Text)
    object: Mapped[str | None] = mapped_column(Text)
    note: Mapped[str | None] = mapped_column(Text)
    payment_number: Mapped[str | None] = mapped_column(Text)
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PddeDocument(ScopeMixin, Base):
    __tablename__ = "pdde_documents"
    __table_args__ = (
        *scope_constraints("pdde_documents"),
        _line_fk("pdde_documents"),
        user_fk("pdde_documents", "created_by_user_id"),
        user_fk("pdde_documents", "voided_by_user_id"),
        CheckConstraint(
            in_list("doc_kind", ("NFE", "INVOICE", "RECEIPT", "OTHER")), name="kind_valid"
        ),
        CheckConstraint(
            "(doc_kind = 'NFE' AND access_key ~ '^[0-9]{44}$') "
            "OR (doc_kind <> 'NFE' AND access_key IS NULL)",
            name="key_shape",
        ),
        CheckConstraint(
            "doc_number IS NULL OR length(btrim(doc_number)) BETWEEN 1 AND 40", name="number_length"
        ),
        CheckConstraint("length(btrim(vendor)) BETWEEN 1 AND 120", name="vendor_length"),
        CheckConstraint("amount_cents > 0 AND amount_cents <= 100000000000", name="amount_range"),
        CheckConstraint("(voided_at IS NULL) = (voided_by_user_id IS NULL)", name="void_pair"),
        CheckConstraint(
            "vendor_tax_id IS NULL OR vendor_tax_id ~ '^([0-9]{11}|[0-9]{14})$'",
            name="vendor_tax_id_format",
        ),
        CheckConstraint(
            "quantity IS NULL OR quantity BETWEEN 1 AND 1000000", name="quantity_range"
        ),
        CheckConstraint(
            "specification IS NULL OR length(btrim(specification)) BETWEEN 1 AND 200",
            name="specification_length",
        ),
        Index("ix_pdde_documents_line_id", "line_id"),
        Index(
            "uq_pdde_documents_school_id_access_key",
            "school_id",
            "access_key",
            unique=True,
            postgresql_where=text("access_key IS NOT NULL AND voided_at IS NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = fin_pk()
    line_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    doc_kind: Mapped[str] = mapped_column(Text)
    access_key: Mapped[str | None] = mapped_column(Text)
    doc_number: Mapped[str | None] = mapped_column(Text)
    issued_on: Mapped[date] = mapped_column(Date)
    vendor: Mapped[str] = mapped_column(Text)
    amount_cents: Mapped[int] = mapped_column(BigInteger)
    stamped: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    vendor_tax_id: Mapped[str | None] = mapped_column(Text)
    quantity: Mapped[int | None] = mapped_column(Integer)
    specification: Mapped[str | None] = mapped_column(Text)
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    voided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    voided_by_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)


class PddeEntity(ScopeMixin, Base):
    __tablename__ = "pdde_entities"
    __table_args__ = (
        *scope_constraints("pdde_entities"),
        user_fk("pdde_entities", "created_by_user_id"),
        CheckConstraint("length(btrim(legal_name)) BETWEEN 1 AND 120", name="legal_name_length"),
        CheckConstraint("cnpj ~ '^[0-9]{14}$'", name="cnpj_format"),
        CheckConstraint("length(btrim(address)) BETWEEN 1 AND 200", name="address_length"),
        CheckConstraint("length(btrim(city)) BETWEEN 1 AND 80", name="city_length"),
        CheckConstraint("state ~ '^[A-Z]{2}$'", name="state_format"),
        Index("ix_pdde_entities_school_id", "school_id", text("created_at DESC")),
    )

    id: Mapped[uuid.UUID] = fin_pk()
    legal_name: Mapped[str] = mapped_column(Text)
    cnpj: Mapped[str] = mapped_column(Text)
    address: Mapped[str] = mapped_column(Text)
    city: Mapped[str] = mapped_column(Text)
    state: Mapped[str] = mapped_column(Text)
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PddeCarryover(ScopeMixin, Base):
    __tablename__ = "pdde_carryovers"
    __table_args__ = (
        *scope_constraints("pdde_carryovers"),
        user_fk("pdde_carryovers", "created_by_user_id"),
        CheckConstraint("year BETWEEN 2000 AND 2100", name="year_range"),
        CheckConstraint(
            in_list("program", ("BASICO", "EQUIDADE", "QUALIDADE", "CONECTADO", "OUTRO")),
            name="program_valid",
        ),
        CheckConstraint(
            "(program = 'OUTRO') = (program_label IS NOT NULL) "
            "AND (program_label IS NULL OR length(btrim(program_label)) BETWEEN 1 AND 60)",
            name="label_shape",
        ),
        CheckConstraint(
            "custeio_cents BETWEEN 0 AND 100000000000 AND capital_cents BETWEEN 0 AND 100000000000",
            name="amounts",
        ),
        Index(
            "ix_pdde_carryovers_school_year",
            "school_id",
            "year",
            "program",
            text("created_at DESC"),
        ),
    )

    id: Mapped[uuid.UUID] = fin_pk()
    year: Mapped[int] = mapped_column(SmallInteger)
    program: Mapped[str] = mapped_column(Text)
    program_label: Mapped[str | None] = mapped_column(Text)
    custeio_cents: Mapped[int] = mapped_column(BigInteger)
    capital_cents: Mapped[int] = mapped_column(BigInteger)
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
