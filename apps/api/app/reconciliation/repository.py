# ruff: noqa: E501  (SQL)
"""The SQL of the bank reconciliation: constant statements, values always bound."""

import datetime as dt
import uuid
from collections.abc import Mapping, Sequence
from typing import Any

from sqlalchemy import RowMapping, text
from sqlalchemy.orm import Session

Row = RowMapping

ACCOUNT_COLUMNS = frozenset({"nickname", "bank_name", "account_last4", "purpose", "is_active"})


def insert_account(
    db: Session, *, organization_id: uuid.UUID, school_id: uuid.UUID, user_id: uuid.UUID,
    nickname: str, bank_name: str, account_last4: str | None, purpose: str,
) -> uuid.UUID:  # fmt: skip
    created: uuid.UUID = db.execute(
        text(
            "INSERT INTO bank_accounts (organization_id, school_id, nickname, bank_name, "
            "account_last4, purpose, created_by_user_id) VALUES (:org, :school, :nickname, "
            ":bank, :last4, :purpose, :user) RETURNING id"
        ),
        {
            "org": organization_id, "school": school_id, "nickname": nickname, "bank": bank_name,
            "last4": account_last4, "purpose": purpose, "user": user_id,
        },
    ).scalar_one()  # fmt: skip
    return created


def accounts(
    db: Session, school_id: uuid.UUID, account_id: uuid.UUID | None = None
) -> Sequence[Row]:
    return (
        db.execute(
            text(
                "SELECT id, nickname, bank_name, account_last4, purpose, is_active FROM bank_accounts "
                "WHERE school_id = :school_id AND (CAST(:id AS uuid) IS NULL OR id = :id) "
                "ORDER BY is_active DESC, nickname"
            ),
            {"school_id": school_id, "id": account_id},
        )
        .mappings()
        .all()
    )


def update_account(
    db: Session, school_id: uuid.UUID, account_id: uuid.UUID, changes: Mapping[str, Any]
) -> None:
    unknown = set(changes) - ACCOUNT_COLUMNS
    if unknown or not changes:
        raise ValueError("an account update names only the editable columns")
    db.execute(
        text(
            "UPDATE bank_accounts SET "
            "nickname = CASE WHEN :set_nickname THEN CAST(:nickname AS text) ELSE nickname END, "
            "bank_name = CASE WHEN :set_bank_name THEN CAST(:bank_name AS text) ELSE bank_name END, "
            "account_last4 = CASE WHEN :set_account_last4 THEN CAST(:account_last4 AS text) "
            "ELSE account_last4 END, "
            "purpose = CASE WHEN :set_purpose THEN CAST(:purpose AS text) ELSE purpose END, "
            "is_active = CASE WHEN :set_is_active THEN CAST(:is_active AS boolean) ELSE is_active END, "
            "updated_at = now() WHERE id = :id AND school_id = :school_id"
        ),
        {
            **{f"set_{c}": c in changes for c in sorted(ACCOUNT_COLUMNS)},
            **{c: changes.get(c) for c in sorted(ACCOUNT_COLUMNS)},
            "id": account_id,
            "school_id": school_id,
        },
    )


def insert_import(
    db: Session, *, organization_id: uuid.UUID, school_id: uuid.UUID, user_id: uuid.UUID,
    account_id: uuid.UUID, sha256: str, start: dt.date, end: dt.date, line_count: int,
    new_line_count: int, closing_balance_cents: int | None,
) -> uuid.UUID:  # fmt: skip
    created: uuid.UUID = db.execute(
        text(
            "INSERT INTO bank_statement_imports (organization_id, school_id, bank_account_id, "
            "file_sha256, period_start, period_end, line_count, new_line_count, "
            "closing_balance_cents, uploaded_by_user_id) VALUES (:org, :school, :account, :sha, "
            ":start, :end, :count, :new, :closing, :user) RETURNING id"
        ),
        {
            "org": organization_id, "school": school_id, "account": account_id, "sha": sha256,
            "start": start, "end": end, "count": line_count, "new": new_line_count,
            "closing": closing_balance_cents,
            "user": user_id,
        },
    ).scalar_one()  # fmt: skip
    return created


def insert_line(
    db: Session, *, organization_id: uuid.UUID, school_id: uuid.UUID, import_id: uuid.UUID,
    account_id: uuid.UUID, posted_on: dt.date, amount_cents: int, memo: str, bank_ref: str,
    end_to_end_id: str | None, looks_like_fee: bool,
) -> bool:  # fmt: skip
    """True when the line is new (a line the bank already sent in an earlier file is skipped)."""
    result = db.execute(
        text(
            "INSERT INTO bank_statement_lines (organization_id, school_id, import_id, "
            "bank_account_id, posted_on, amount_cents, memo, bank_ref, end_to_end_id, looks_like_fee) "
            "VALUES (:org, :school, :import, :account, :day, :amount, :memo, :ref, :e2e, :fee) "
            "ON CONFLICT (school_id, bank_account_id, bank_ref) DO NOTHING"
        ),
        {
            "org": organization_id, "school": school_id, "import": import_id, "account": account_id,
            "day": posted_on, "amount": amount_cents, "memo": memo, "ref": bank_ref,
            "e2e": end_to_end_id, "fee": looks_like_fee,
        },
    )  # fmt: skip
    return bool(result.rowcount == 1)  # type: ignore[attr-defined]


def import_exists(db: Session, school_id: uuid.UUID, sha256: str) -> bool:
    return (
        db.execute(
            text(
                "SELECT 1 FROM bank_statement_imports WHERE school_id = :school_id AND file_sha256 = :sha"
            ),
            {"school_id": school_id, "sha": sha256},
        ).first()
        is not None
    )


def existing_refs(
    db: Session, school_id: uuid.UUID, account_id: uuid.UUID, refs: Sequence[str]
) -> set[str]:
    """The ids the bank gave to lines that are already stored (an overlapping file sends them again)."""
    rows = db.execute(
        text(
            "SELECT bank_ref FROM bank_statement_lines WHERE school_id = :school_id "
            "AND bank_account_id = :account AND bank_ref = ANY(:refs)"
        ),
        {"school_id": school_id, "account": account_id, "refs": list(refs)},
    ).all()
    return {str(row[0]) for row in rows}


def imports(
    db: Session, school_id: uuid.UUID, import_id: uuid.UUID | None = None, limit: int = 50
) -> Sequence[Row]:
    return (
        db.execute(
            text(
                "SELECT id, bank_account_id, period_start, period_end, line_count, new_line_count, "
                "closing_balance_cents, created_at FROM bank_statement_imports "
                "WHERE school_id = :school_id AND (CAST(:id AS uuid) IS NULL OR id = :id) "
                "ORDER BY created_at DESC, id DESC LIMIT :limit"
            ),
            {"school_id": school_id, "id": import_id, "limit": limit},
        )
        .mappings()
        .all()
    )


def bank_lines(
    db: Session, school_id: uuid.UUID, account_id: uuid.UUID, start: dt.date, end: dt.date
) -> Sequence[Row]:
    return (
        db.execute(
            text(
                "SELECT id AS line_id, posted_on, amount_cents, memo, end_to_end_id, looks_like_fee "
                "FROM bank_statement_lines WHERE school_id = :school_id AND bank_account_id = :account "
                "AND posted_on BETWEEN :start AND :end ORDER BY posted_on, id"
            ),
            {"school_id": school_id, "account": account_id, "start": start, "end": end},
        )
        .mappings()
        .all()
    )


def ledger_items(db: Session, school_id: uuid.UUID, start: dt.date, end: dt.date) -> Sequence[Row]:
    """What the ledger booked as cash in the period and that passes through a bank: not cash in hand
    and not an expense somebody paid from their own pocket (it never touched the account)."""
    return (
        db.execute(
            text(
                "SELECT f.id AS transaction_id, f.reference_code, f.kind, f.direction, f.amount_cents, "
                "(f.settled_at AT TIME ZONE st.timezone)::date AS day, "
                "coalesce(pc.end_to_end_id, c.external_reference) AS end_to_end_id, cf.net_cents "
                "FROM financial_transactions f "
                "JOIN school_settings st ON st.school_id = f.school_id "
                "LEFT JOIN contributions c ON c.transaction_id = f.id AND c.school_id = f.school_id "
                "LEFT JOIN pix_charges pc ON pc.transaction_id = f.id AND pc.school_id = f.school_id "
                "AND pc.status = 'PAID' "
                "LEFT JOIN contribution_fees cf ON cf.transaction_id = f.id AND cf.school_id = f.school_id "
                "LEFT JOIN expenses e ON e.transaction_id = f.id AND e.school_id = f.school_id "
                "WHERE f.school_id = :school_id AND f.settled_at IS NOT NULL "
                "AND (f.settled_at AT TIME ZONE st.timezone)::date BETWEEN :start AND :end "
                "AND (f.kind <> 'EXPENSE' OR e.paid_by = 'APM') "
                "AND (c.method IS NULL OR c.method <> 'CASH') "
                "ORDER BY f.settled_at, f.reference_code"
            ),
            {"school_id": school_id, "start": start, "end": end},
        )
        .mappings()
        .all()
    )
