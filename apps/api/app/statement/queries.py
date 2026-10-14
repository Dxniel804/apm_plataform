"""The statements the routes run. Each one is a constant given to `text()`; the values travel as
bound parameters. The database functions do all the arithmetic."""

from datetime import date
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session


def current_period(db: Session, school_id: UUID) -> str | None:
    """The month it is NOW in the time zone of the school (`YYYY-MM`)."""
    found = db.execute(
        text(
            "SELECT to_char(now() AT TIME ZONE st.timezone, 'YYYY-MM') "
            "FROM school_settings st WHERE st.school_id = :school_id"
        ),
        {"school_id": school_id},
    ).scalar_one_or_none()
    return None if found is None else str(found)


def reference_months(db: Session, school_id: UUID, ids: list[UUID]) -> dict[UUID, str]:
    """The month each contribution of the page is FOR (YYYY-MM). Read apart, on purpose: the
    statement function is the source of the closing hash and is not touched."""
    if not ids:
        return {}
    rows = db.execute(
        text(
            "SELECT transaction_id, to_char(reference_month, 'YYYY-MM') FROM contributions "
            "WHERE school_id = :school_id AND transaction_id = ANY(:ids) "
            "AND reference_month IS NOT NULL"
        ),
        {"school_id": school_id, "ids": ids},
    ).all()
    return {row[0]: row[1] for row in rows}


def fees_of(db: Session, school_id: UUID, ids: list[UUID]) -> dict[UUID, tuple[int, int]]:
    """For each contribution of the page that has one, (gateway fee, net) in cents."""
    if not ids:
        return {}
    rows = db.execute(
        text(
            "SELECT transaction_id, gateway_fee_cents, net_cents FROM contribution_fees "
            "WHERE school_id = :school_id AND transaction_id = ANY(:ids)"
        ),
        {"school_id": school_id, "ids": ids},
    ).all()
    return {row[0]: (int(row[1]), int(row[2])) for row in rows}


def fees_in_month(db: Session, school_id: UUID, start: date, end: date) -> int:
    """The fees of the contributions settled in the month (the same rows the statement lists)."""
    total: int = db.execute(
        text(
            "SELECT coalesce(sum(cf.gateway_fee_cents), 0) FROM contribution_fees cf "
            "JOIN financial_transactions f ON f.id = cf.transaction_id "
            "AND f.school_id = cf.school_id "
            "JOIN school_settings st ON st.school_id = cf.school_id "
            "WHERE cf.school_id = :school_id AND f.settled_at IS NOT NULL "
            "AND (f.settled_at AT TIME ZONE st.timezone)::date >= :start "
            "AND (f.settled_at AT TIME ZONE st.timezone)::date <= :end"
        ),
        {"school_id": school_id, "start": start, "end": end},
    ).scalar_one()
    return int(total)


def fetch_entries(
    db: Session,
    school_id: UUID,
    start: date,
    end: date,
    *,
    display_type: str | None,
    kind: str | None,
    category: UUID | None,
    status: str | None,
    person: UUID | None,
    after: dict[str, Any] | None,
    limit: int,
) -> list[dict[str, Any]]:
    """`limit` rows of the statement after the position `after` ((settled_at, reference_code) of
    the last row already sent). The window function of `statement_entries` has already computed
    the balances over every entry, so cutting the rows here does not change them."""
    rows = db.execute(
        text(
            "SELECT e.* FROM statement_entries("
            "CAST(:school_id AS uuid), CAST(:start AS date), CAST(:end AS date), "
            "CAST(:display_type AS text), CAST(:category AS uuid), CAST(:status AS text), "
            "CAST(:person AS uuid)) e "
            "WHERE (CAST(:kind AS text) IS NULL OR e.kind = CAST(:kind AS text)) "
            "AND (CAST(:after_at AS timestamptz) IS NULL OR (e.settled_at, e.reference_code) > "
            "(CAST(:after_at AS timestamptz), CAST(:after_ref AS bigint))) "
            "ORDER BY e.settled_at, e.reference_code LIMIT :limit"
        ),
        {
            "school_id": school_id,
            "start": start,
            "end": end,
            "display_type": display_type,
            "kind": kind,
            "category": category,
            "status": status,
            "person": person,
            "after_at": None if after is None else after["settled_at"],
            "after_ref": None if after is None else after["reference_code"],
            "limit": limit,
        },
    ).mappings()
    return [dict(row) for row in rows]


def fetch_summary(db: Session, school_id: UUID, start: date, end: date) -> dict[str, Any] | None:
    row = (
        db.execute(
            text("SELECT * FROM statement_summary(:school_id, :start, :end)"),
            {"school_id": school_id, "start": start, "end": end},
        )
        .mappings()
        .one_or_none()
    )
    return None if row is None else dict(row)


def count_paid_contributions(db: Session, school_id: UUID, start: date, end: date) -> int:
    """How many contributions of the guardians were settled in the month (the same rows the
    statement lists; campaign sales and other income are not contributions)."""
    count: int = db.execute(
        text(
            "SELECT count(*) FROM statement_entries(:school_id, :start, :end) e "
            "WHERE e.kind = 'CONTRIBUTION' AND e.report_group = 'CONTRIBUTIONS'"
        ),
        {"school_id": school_id, "start": start, "end": end},
    ).scalar_one()
    return int(count)


def school_goals(db: Session, school_id: UUID) -> tuple[int | None, int | None]:
    """The monthly goal and the number of contributions the school expects (null: not set)."""
    row = db.execute(
        text(
            "SELECT monthly_goal_cents, expected_contributions FROM school_settings "
            "WHERE school_id = :school_id"
        ),
        {"school_id": school_id},
    ).one_or_none()
    return (None, None) if row is None else (row[0], row[1])


def fetch_pending(
    db: Session,
    school_id: UUID,
    *,
    section: str | None,
    after: dict[str, Any] | None,
    limit: int,
) -> list[dict[str, Any]]:
    """`limit` rows of `statement_pending` after (occurred_at, reference_code)."""
    rows = db.execute(
        text(
            "SELECT p.* FROM statement_pending(CAST(:school_id AS uuid)) p "
            "WHERE (CAST(:section AS text) IS NULL OR p.section = CAST(:section AS text)) "
            "AND (CAST(:after_at AS timestamptz) IS NULL OR (p.occurred_at, p.reference_code) > "
            "(CAST(:after_at AS timestamptz), CAST(:after_ref AS bigint))) "
            "ORDER BY p.occurred_at, p.reference_code LIMIT :limit"
        ),
        {
            "school_id": school_id,
            "section": section,
            "after_at": None if after is None else after["occurred_at"],
            "after_ref": None if after is None else after["reference_code"],
            "limit": limit,
        },
    ).mappings()
    return [dict(row) for row in rows]
