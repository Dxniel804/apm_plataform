"""The balances the treasurer types for the balancete (migration 0027): what the school had when it
started to use the system, and the cash and the invested money at the end of a month. The
constraints mirror the migration and carry the same names; triggers, policies and grants live only
in the migration."""

import uuid
from datetime import date, datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    Index,
    Text,
    Uuid,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.financial_common import ScopeMixin, fin_pk, in_list, scope_constraints, user_fk
from app.models.mixins import DemoMixin


class BalanceteBalance(DemoMixin, ScopeMixin, Base):
    __tablename__ = "balancete_balances"
    __table_args__ = (
        *scope_constraints("balancete_balances"),
        user_fk("balancete_balances", "created_by_user_id"),
        CheckConstraint(in_list("kind", ("OPENING", "MONTH")), name="kind_valid"),
        CheckConstraint(
            "(kind = 'OPENING' AND period_start IS NULL AND bank_cents IS NOT NULL) "
            "OR (kind = 'MONTH' AND period_start IS NOT NULL AND bank_cents IS NULL "
            "AND extract(day FROM period_start) = 1)",
            name="shape",
        ),
        CheckConstraint(
            "cash_cents BETWEEN 0 AND 100000000000 "
            "AND investment_cents BETWEEN 0 AND 100000000000 "
            "AND (bank_cents IS NULL OR bank_cents BETWEEN -100000000000 AND 100000000000)",
            name="amounts",
        ),
        Index(
            "ix_balancete_balances_school_kind_period",
            "school_id",
            "kind",
            "period_start",
            text("created_at DESC"),
        ),
    )

    id: Mapped[uuid.UUID] = fin_pk()
    kind: Mapped[str] = mapped_column(Text)
    period_start: Mapped[date | None] = mapped_column(Date)
    bank_cents: Mapped[int | None] = mapped_column(BigInteger)
    cash_cents: Mapped[int] = mapped_column(BigInteger)
    investment_cents: Mapped[int] = mapped_column(BigInteger)
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
