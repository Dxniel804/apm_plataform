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
                "SELECT id, nickname, bank_name, account_last4, purpose, is_active, csv_profile FROM bank_accounts "
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
    new_line_count: int, closing_balance_cents: int | None, source: str = "OFX",
) -> uuid.UUID:  # fmt: skip
    created: uuid.UUID = db.execute(
        text(
            "INSERT INTO bank_statement_imports (organization_id, school_id, bank_account_id, "
            "file_sha256, period_start, period_end, line_count, new_line_count, "
            "closing_balance_cents, uploaded_by_user_id, source) VALUES (:org, :school, :account, "
            ":sha, :start, :end, :count, :new, :closing, :user, :source) RETURNING id"
        ),
        {
            "org": organization_id, "school": school_id, "account": account_id, "sha": sha256,
            "start": start, "end": end, "count": line_count, "new": new_line_count,
            "closing": closing_balance_cents,
            "user": user_id, "source": source,
        },
    ).scalar_one()  # fmt: skip
    return created


def insert_line(
    db: Session, *, organization_id: uuid.UUID, school_id: uuid.UUID, import_id: uuid.UUID,
    account_id: uuid.UUID, posted_on: dt.date, amount_cents: int, memo: str, bank_ref: str,
    end_to_end_id: str | None, looks_like_fee: bool, needs_review: bool = False,
) -> bool:  # fmt: skip
    """True when the line is new (a line the bank already sent in an earlier file is skipped)."""
    result = db.execute(
        text(
            "INSERT INTO bank_statement_lines (organization_id, school_id, import_id, "
            "bank_account_id, posted_on, amount_cents, memo, bank_ref, end_to_end_id, looks_like_fee, "
            "needs_review) VALUES (:org, :school, :import, :account, :day, :amount, :memo, :ref, "
            ":e2e, :fee, :review) "
            "ON CONFLICT (school_id, bank_account_id, bank_ref) DO NOTHING"
        ),
        {
            "org": organization_id, "school": school_id, "import": import_id, "account": account_id,
            "day": posted_on, "amount": amount_cents, "memo": memo, "ref": bank_ref,
            "e2e": end_to_end_id, "fee": looks_like_fee, "review": needs_review,
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
                "closing_balance_cents, created_at, source FROM bank_statement_imports "
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
                "SELECT id AS line_id, posted_on, amount_cents, memo, end_to_end_id, looks_like_fee, needs_review "
                "FROM bank_statement_lines WHERE school_id = :school_id AND bank_account_id = :account "
                "AND posted_on BETWEEN :start AND :end ORDER BY posted_on, id"
            ),
            {"school_id": school_id, "account": account_id, "start": start, "end": end},
        )
        .mappings()
        .all()
    )


def ledger_items(
    db: Session, school_id: uuid.UUID, start: dt.date, end: dt.date, wallet: str = "APM"
) -> Sequence[Row]:
    """What the ledger booked as cash in the period and that passes through a bank: not cash in hand
    and not an expense somebody paid from their own pocket (it never touched the account). Only the
    items of the wallet (`APM` or `PDDE`): an expense decided as PDDE, and the reimbursement of it, is
    paid from the PDDE account; everything else is the APM's."""
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
                "LEFT JOIN expenses pe ON pe.transaction_id = f.parent_transaction_id "
                "AND pe.school_id = f.school_id "
                "WHERE f.school_id = :school_id AND f.settled_at IS NOT NULL "
                "AND (f.settled_at AT TIME ZONE st.timezone)::date BETWEEN :start AND :end "
                "AND (f.kind <> 'EXPENSE' OR e.paid_by = 'APM') "
                "AND (c.method IS NULL OR c.method <> 'CASH') "
                "AND (CASE WHEN f.kind = 'EXPENSE' THEN coalesce(e.fund, 'APM') "
                "WHEN f.kind = 'REIMBURSEMENT' THEN coalesce(pe.fund, 'APM') ELSE 'APM' END) = :wallet "
                "ORDER BY f.settled_at, f.reference_code"
            ),
            {"school_id": school_id, "start": start, "end": end, "wallet": wallet},
        )
        .mappings()
        .all()
    )


# --- what the management decides about a line (0018) -------------------------------------------


def line_by_id(db: Session, school_id: uuid.UUID, line_id: uuid.UUID) -> Row | None:
    """The line with the resolution it already has (if any). Two people acting at once are told
    apart by the unique key of the resolution, not by a lock."""
    return (
        db.execute(
            text(
                "SELECT l.id, l.posted_on, l.amount_cents, l.memo, l.end_to_end_id, l.needs_review, "
                "(SELECT a.purpose FROM bank_accounts a WHERE a.id = l.bank_account_id "
                "AND a.school_id = l.school_id) AS purpose, "
                "(SELECT r.action FROM bank_line_resolutions r WHERE r.school_id = l.school_id "
                "AND r.line_id = l.id) AS resolution "
                "FROM bank_statement_lines l WHERE l.id = :id AND l.school_id = :school_id"
            ),
            {"id": line_id, "school_id": school_id},
        )
        .mappings()
        .first()
    )


def resolutions(db: Session, school_id: uuid.UUID, line_ids: Sequence[uuid.UUID]) -> Sequence[Row]:
    return (
        db.execute(
            text(
                "SELECT line_id, action, reason, created_at FROM bank_line_resolutions "
                "WHERE school_id = :school_id AND line_id = ANY(:ids)"
            ),
            {"school_id": school_id, "ids": list(line_ids)},
        )
        .mappings()
        .all()
    )


def income_category(db: Session, school_id: uuid.UUID, key: str) -> uuid.UUID | None:
    found: uuid.UUID | None = db.execute(
        text(
            "SELECT id FROM categories WHERE school_id = :school AND key = :key "
            "AND applies_to = 'IN' AND is_active"
        ),
        {"school": school_id, "key": key},
    ).scalar_one_or_none()
    return found


def bank_fees_category(db: Session, school_id: uuid.UUID) -> uuid.UUID | None:
    found: uuid.UUID | None = db.execute(
        text(
            "SELECT id FROM categories WHERE school_id = :school AND key = 'bank_fees' "
            "AND applies_to = 'OUT' AND is_active"
        ),
        {"school": school_id},
    ).scalar_one_or_none()
    return found


def bank_moment(db: Session, school_id: uuid.UUID, day: dt.date) -> dt.datetime:
    """The moment a line counts in the ledger: noon of the day the bank says, in the school's time
    zone (never in the future). The statement has a day, not a time."""
    moment: dt.datetime = db.execute(
        text(
            "SELECT least((CAST(:day AS date) + time '12:00') AT TIME ZONE st.timezone, "
            "clock_timestamp()) FROM school_settings st WHERE st.school_id = :school"
        ),
        {"day": day, "school": school_id},
    ).scalar_one()
    return moment


def insert_income(
    db: Session, *, organization_id: uuid.UUID, school_id: uuid.UUID, user_id: uuid.UUID,
    category_id: uuid.UUID, amount_cents: int, moment: dt.datetime, method: str,
    external_reference: str | None, guardian_name: str | None,
) -> tuple[uuid.UUID, int]:  # fmt: skip
    """A contribution the bank shows and the ledger did not know: PAID, on the day of the bank."""
    row = db.execute(
        text(
            "INSERT INTO financial_transactions (organization_id, school_id, kind, direction, "
            "amount_cents, status, category_id, origin_type, created_by_user_id, occurred_at, "
            "settled_at) VALUES (:org, :school, 'CONTRIBUTION', 'IN', :amount, 'PAID', :category, "
            "'GUARDIAN', :user, :moment, :moment) RETURNING id, reference_code"
        ),
        {
            "org": organization_id, "school": school_id, "amount": amount_cents,
            "category": category_id, "user": user_id, "moment": moment,
        },
    ).one()  # fmt: skip
    db.execute(
        text(
            "INSERT INTO contributions (transaction_id, organization_id, school_id, method, "
            "external_reference, guardian_name) VALUES (:tx, :org, :school, :method, :ref, :guardian)"
        ),
        {
            "tx": row[0], "org": organization_id, "school": school_id, "method": method,
            "ref": external_reference, "guardian": guardian_name,
        },
    )  # fmt: skip
    return row[0], int(row[1])


def insert_fee_expense(
    db: Session, *, organization_id: uuid.UUID, school_id: uuid.UUID, user_id: uuid.UUID,
    category_id: uuid.UUID, amount_cents: int, moment: dt.datetime, description: str,
) -> tuple[uuid.UUID, int]:  # fmt: skip
    """A bank fee the ledger did not know: an expense of the APM in the category without approval,
    born APPROVED (the bank already took the money) and settled on the day of the bank."""
    row = db.execute(
        text(
            "INSERT INTO financial_transactions (organization_id, school_id, kind, direction, "
            "amount_cents, status, category_id, origin_type, origin_name, created_by_user_id, "
            "occurred_at) VALUES (:org, :school, 'EXPENSE', 'OUT', :amount, 'APPROVED', :category, "
            "'BANK', 'Banco', :user, :moment) RETURNING id, reference_code"
        ),
        {
            "org": organization_id, "school": school_id, "amount": amount_cents,
            "category": category_id, "user": user_id, "moment": moment,
        },
    ).one()  # fmt: skip
    db.execute(
        text(
            "INSERT INTO expenses (transaction_id, organization_id, school_id, description, "
            "paid_by, submitted_by_user_id) VALUES (:tx, :org, :school, :description, 'APM', :user)"
        ),
        {
            "tx": row[0], "org": organization_id, "school": school_id,
            "description": description, "user": user_id,
        },
    )  # fmt: skip
    db.execute(
        text(
            "UPDATE financial_transactions SET status = 'PAID', settled_at = :moment, "
            "updated_at = now() WHERE id = :id AND school_id = :school AND status = 'APPROVED'"
        ),
        {"id": row[0], "school": school_id, "moment": moment},
    )
    return row[0], int(row[1])


def insert_resolution(
    db: Session, *, organization_id: uuid.UUID, school_id: uuid.UUID, user_id: uuid.UUID,
    line_id: uuid.UUID, action: str, reason: str | None, transaction_id: uuid.UUID | None,
    transaction_kind: str | None,
) -> None:  # fmt: skip
    db.execute(
        text(
            "INSERT INTO bank_line_resolutions (organization_id, school_id, line_id, action, "
            "reason, transaction_id, transaction_kind, resolved_by_user_id) "
            "VALUES (:org, :school, :line, :action, :reason, :tx, :kind, :user)"
        ),
        {
            "org": organization_id, "school": school_id, "line": line_id, "action": action,
            "reason": reason, "tx": transaction_id, "kind": transaction_kind, "user": user_id,
        },
    )  # fmt: skip


def closing_balances(db: Session, school_id: uuid.UUID, month_end: dt.date) -> Sequence[Row]:
    """For each active general account, the balance the bank gave in the last statement that ends
    on or before the end of the month."""
    return (
        db.execute(
            text(
                "SELECT DISTINCT ON (a.id) a.id AS bank_account_id, a.nickname, "
                "i.closing_balance_cents, i.period_end AS as_of "
                "FROM bank_accounts a JOIN bank_statement_imports i ON i.bank_account_id = a.id "
                "AND i.school_id = a.school_id "
                "WHERE a.school_id = :school_id AND a.is_active AND a.purpose = 'GENERAL' "
                "AND i.period_end <= :month_end AND i.closing_balance_cents IS NOT NULL "
                "ORDER BY a.id, i.period_end DESC, i.created_at DESC"
            ),
            {"school_id": school_id, "month_end": month_end},
        )
        .mappings()
        .all()
    )


def set_csv_profile(
    db: Session, school_id: uuid.UUID, account_id: uuid.UUID, profile_json: str
) -> None:
    """Keep how this bank's CSV is read, so the next file of the account needs no mapping."""
    db.execute(
        text(
            "UPDATE bank_accounts SET csv_profile = CAST(:profile AS jsonb), updated_at = now() "
            "WHERE id = :id AND school_id = :school_id"
        ),
        {"profile": profile_json, "id": account_id, "school_id": school_id},
    )
