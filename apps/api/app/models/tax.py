"""Tax guides (migration 0029): the rules a school writes down and the retentions on the services it
pays. The constraints mirror the migration and carry the same names; triggers, policies and grants
live only in the migration."""

import uuid
from datetime import date, datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKeyConstraint,
    Index,
    Integer,
    SmallInteger,
    Text,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.financial_common import ScopeMixin, fin_pk, in_list, scope_constraints, user_fk


class TaxRule(ScopeMixin, Base):
    __tablename__ = "tax_rules"
    __table_args__ = (
        *scope_constraints("tax_rules"),
        user_fk("tax_rules", "created_by_user_id"),
        user_fk("tax_rules", "validated_by_user_id"),
        UniqueConstraint("id", "school_id", name="uq_tax_rules_id_school_id"),
        CheckConstraint("rule_key ~ '^[a-z0-9][a-z0-9-]{2,39}$'", name="key_format"),
        CheckConstraint("length(btrim(label)) BETWEEN 1 AND 80", name="label_length"),
        CheckConstraint(in_list("tax_kind", ("IRRF", "INSS", "ISS", "OTHER")), name="kind_valid"),
        CheckConstraint(in_list("applies_to", ("PF", "PJ", "BOTH")), name="applies_valid"),
        CheckConstraint("rate_bps BETWEEN 1 AND 10000", name="rate_range"),
        CheckConstraint(
            "base_cap_cents IS NULL OR base_cap_cents BETWEEN 1 AND 100000000000", name="cap_range"
        ),
        CheckConstraint("min_total_cents BETWEEN 0 AND 100000000", name="min_range"),
        CheckConstraint("darf_code IS NULL OR darf_code ~ '^[0-9]{4}$'", name="code_format"),
        CheckConstraint(
            "howto IS NULL OR length(btrim(howto)) BETWEEN 1 AND 300", name="howto_length"
        ),
        CheckConstraint("darf_code IS NOT NULL OR howto IS NOT NULL", name="where_to_pay"),
        CheckConstraint("due_day BETWEEN 1 AND 31", name="due_day_range"),
        CheckConstraint(in_list("due_roll", ("PREVIOUS", "NEXT")), name="due_roll_valid"),
        CheckConstraint(
            "source_note IS NULL OR length(btrim(source_note)) BETWEEN 1 AND 200",
            name="source_length",
        ),
        CheckConstraint(
            "(validated_at IS NULL) = (validated_by_user_id IS NULL)", name="validated_pair"
        ),
        Index("ix_tax_rules_school_key", "school_id", "rule_key", text("created_at DESC")),
    )

    id: Mapped[uuid.UUID] = fin_pk()
    rule_key: Mapped[str] = mapped_column(Text)
    label: Mapped[str] = mapped_column(Text)
    tax_kind: Mapped[str] = mapped_column(Text)
    applies_to: Mapped[str] = mapped_column(Text)
    rate_bps: Mapped[int] = mapped_column(Integer)
    base_cap_cents: Mapped[int | None] = mapped_column(BigInteger)
    min_total_cents: Mapped[int] = mapped_column(BigInteger, server_default=text("1000"))
    darf_code: Mapped[str | None] = mapped_column(Text)
    howto: Mapped[str | None] = mapped_column(Text)
    due_day: Mapped[int] = mapped_column(SmallInteger)
    due_roll: Mapped[str] = mapped_column(Text)
    source_note: Mapped[str | None] = mapped_column(Text)
    validated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    validated_by_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class TaxRetention(ScopeMixin, Base):
    __tablename__ = "tax_retentions"
    __table_args__ = (
        *scope_constraints("tax_retentions"),
        ForeignKeyConstraint(
            ["rule_id", "school_id"],
            ["tax_rules.id", "tax_rules.school_id"],
            name="fk_tax_retentions_rule_id_tax_rules",
            ondelete="RESTRICT",
        ),
        user_fk("tax_retentions", "created_by_user_id"),
        user_fk("tax_retentions", "voided_by_user_id"),
        CheckConstraint(in_list("provider_kind", ("PF", "PJ")), name="kind_valid"),
        CheckConstraint("length(btrim(provider_name)) BETWEEN 1 AND 120", name="name_length"),
        CheckConstraint("extract(day FROM competence) = 1", name="competence_first_day"),
        CheckConstraint(
            "gross_cents BETWEEN 1 AND 100000000000 AND base_cents BETWEEN 1 AND gross_cents "
            "AND retained_cents BETWEEN 0 AND base_cents",
            name="amounts",
        ),
        CheckConstraint("rate_bps BETWEEN 1 AND 10000", name="rate_range"),
        CheckConstraint("note IS NULL OR length(note) <= 300", name="note_length"),
        CheckConstraint("(voided_at IS NULL) = (voided_by_user_id IS NULL)", name="void_pair"),
        Index("ix_tax_retentions_school_competence", "school_id", "competence"),
    )

    id: Mapped[uuid.UUID] = fin_pk()
    rule_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    provider_kind: Mapped[str] = mapped_column(Text)
    provider_name: Mapped[str] = mapped_column(Text)
    competence: Mapped[date] = mapped_column(Date)
    gross_cents: Mapped[int] = mapped_column(BigInteger)
    base_cents: Mapped[int] = mapped_column(BigInteger)
    retained_cents: Mapped[int] = mapped_column(BigInteger)
    rate_bps: Mapped[int] = mapped_column(Integer)
    note: Mapped[str | None] = mapped_column(Text)
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    voided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    voided_by_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
