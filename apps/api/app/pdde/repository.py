# ruff: noqa: E501  (SQL)
"""What the PDDE routes read and write (constants given to `text()`, values bound)."""

import datetime as dt
import uuid
from collections.abc import Sequence
from typing import Any

from sqlalchemy import RowMapping, text
from sqlalchemy.orm import Session

Row = RowMapping


def accounts(db: Session, school_id: uuid.UUID) -> Sequence[Row]:
    """The active bank accounts whose purpose is PDDE: the only ones whose lines are classified."""
    return (
        db.execute(
            text(
                "SELECT id, nickname, bank_name, account_last4 FROM bank_accounts "
                "WHERE school_id = :school_id AND purpose = 'PDDE' AND is_active "
                "ORDER BY nickname"
            ),
            {"school_id": school_id},
        )
        .mappings()
        .all()
    )


def lines(db: Session, school_id: uuid.UUID, start: dt.date, end: dt.date) -> Sequence[Row]:
    """The lines of the PDDE accounts in the window, each with the latest classification."""
    return (
        db.execute(
            text(
                "SELECT l.id AS line_id, l.posted_on, l.amount_cents, l.memo, l.looks_like_fee, "
                "a.id AS account_id, a.nickname AS account_nickname, "
                "c.kind, c.program, c.program_label, c.economic_category, c.object, c.note, "
                "c.payment_number "
                "FROM bank_statement_lines l "
                "JOIN bank_accounts a ON a.id = l.bank_account_id AND a.school_id = l.school_id "
                "LEFT JOIN LATERAL (SELECT x.kind, x.program, x.program_label, x.economic_category, "
                "  x.object, x.note, x.payment_number FROM pdde_classifications x "
                "  WHERE x.line_id = l.id ORDER BY x.created_at DESC, x.id DESC LIMIT 1) c ON true "
                "WHERE l.school_id = :school_id AND a.purpose = 'PDDE' "
                "AND l.posted_on BETWEEN :start AND :end ORDER BY l.posted_on, l.id"
            ),
            {"school_id": school_id, "start": start, "end": end},
        )
        .mappings()
        .all()
    )


def documents(db: Session, school_id: uuid.UUID, line_ids: Sequence[uuid.UUID]) -> Sequence[Row]:
    if not line_ids:
        return []
    return (
        db.execute(
            text(
                "SELECT id, line_id, doc_kind, access_key, doc_number, issued_on, vendor, "
                "amount_cents, stamped, voided_at IS NOT NULL AS voided, vendor_tax_id, quantity, "
                "specification "
                "FROM pdde_documents WHERE school_id = :school_id AND line_id = ANY(:ids) "
                "ORDER BY created_at, id"
            ),
            {"school_id": school_id, "ids": list(line_ids)},
        )
        .mappings()
        .all()
    )


def line_of_pdde_account(db: Session, school_id: uuid.UUID, line_id: uuid.UUID) -> Row | None:
    """A line of the school, with whether it is in a PDDE account (anything else is not there)."""
    return (
        db.execute(
            text(
                "SELECT l.id, l.amount_cents FROM bank_statement_lines l "
                "JOIN bank_accounts a ON a.id = l.bank_account_id AND a.school_id = l.school_id "
                "WHERE l.id = :id AND l.school_id = :school_id AND a.purpose = 'PDDE'"
            ),
            {"id": line_id, "school_id": school_id},
        )
        .mappings()
        .first()
    )


def insert_classification(
    db: Session,
    *,
    organization_id: uuid.UUID,
    school_id: uuid.UUID,
    line_id: uuid.UUID,
    user_id: uuid.UUID,
    values: dict[str, Any],
) -> None:
    db.execute(
        text(
            "INSERT INTO pdde_classifications (organization_id, school_id, line_id, kind, program, "
            "program_label, economic_category, object, note, payment_number, created_by_user_id) "
            "VALUES (:organization_id, :school_id, :line_id, :kind, :program, :program_label, "
            ":economic_category, :object, :note, :payment_number, :user_id)"
        ),
        {
            "organization_id": organization_id,
            "school_id": school_id,
            "line_id": line_id,
            "user_id": user_id,
            "kind": values["kind"],
            "program": values.get("program"),
            "program_label": values.get("program_label"),
            "economic_category": values.get("economic_category"),
            "object": values.get("object"),
            "note": values.get("note"),
            "payment_number": values.get("payment_number"),
        },
    )


def insert_document(
    db: Session,
    *,
    organization_id: uuid.UUID,
    school_id: uuid.UUID,
    line_id: uuid.UUID,
    user_id: uuid.UUID,
    values: dict[str, Any],
) -> uuid.UUID:
    new_id: uuid.UUID = db.execute(
        text(
            "INSERT INTO pdde_documents (organization_id, school_id, line_id, doc_kind, access_key, "
            "doc_number, issued_on, vendor, amount_cents, stamped, vendor_tax_id, quantity, specification, "
            "created_by_user_id) "
            "VALUES (:organization_id, :school_id, :line_id, :doc_kind, :access_key, :doc_number, "
            ":issued_on, :vendor, :amount_cents, :stamped, :vendor_tax_id, :quantity, :specification, "
            ":user_id) RETURNING id"
        ),
        {
            "organization_id": organization_id,
            "school_id": school_id,
            "line_id": line_id,
            "user_id": user_id,
            **values,
        },
    ).scalar_one()
    return new_id


def void_document(
    db: Session, school_id: uuid.UUID, document_id: uuid.UUID, user_id: uuid.UUID
) -> bool:
    """True when a document of the school was voided now (False: not there, or already voided)."""
    done = db.execute(
        text(
            "UPDATE pdde_documents SET voided_at = now(), voided_by_user_id = :user_id "
            "WHERE id = :id AND school_id = :school_id AND voided_at IS NULL RETURNING id"
        ),
        {"id": document_id, "school_id": school_id, "user_id": user_id},
    ).first()
    return done is not None


def today(db: Session, school_id: uuid.UUID) -> dt.date:
    """Today in the time zone of the school."""
    found = db.execute(
        text(
            "SELECT (now() AT TIME ZONE st.timezone)::date FROM school_settings st "
            "WHERE st.school_id = :school_id"
        ),
        {"school_id": school_id},
    ).scalar_one_or_none()
    return found if isinstance(found, dt.date) else dt.date.today()


def december_balances(db: Session, school_id: uuid.UUID, year: int) -> Sequence[Row]:
    """For each PDDE account, the closing balance of a statement that ends on 31/12 (if any)."""
    return (
        db.execute(
            text(
                "SELECT a.id AS account_id, a.nickname AS account_nickname, "
                "(SELECT i.closing_balance_cents FROM bank_statement_imports i "
                " WHERE i.bank_account_id = a.id AND i.school_id = a.school_id "
                " AND i.period_end = make_date(:year, 12, 31) AND i.closing_balance_cents IS NOT NULL "
                " ORDER BY i.created_at DESC LIMIT 1) AS balance_cents "
                "FROM bank_accounts a WHERE a.school_id = :school_id AND a.purpose = 'PDDE' "
                "AND a.is_active ORDER BY a.nickname"
            ),
            {"school_id": school_id, "year": year},
        )
        .mappings()
        .all()
    )


# --- what the official forms print ---------------------------------------------------------------


def latest_entity(db: Session, school_id: uuid.UUID) -> Row | None:
    """The identification of the entity (CNPJ, address, city, state): the latest row counts."""
    return (
        db.execute(
            text(
                "SELECT legal_name, cnpj, address, city, state FROM pdde_entities WHERE school_id = :school_id "
                "ORDER BY created_at DESC, id DESC LIMIT 1"
            ),
            {"school_id": school_id},
        )
        .mappings()
        .first()
    )


def insert_entity(
    db: Session,
    *,
    organization_id: uuid.UUID,
    school_id: uuid.UUID,
    user_id: uuid.UUID,
    values: dict[str, Any],
) -> None:
    db.execute(
        text(
            "INSERT INTO pdde_entities (organization_id, school_id, legal_name, cnpj, address, city, "
            "state, created_by_user_id) VALUES (:organization_id, :school_id, :legal_name, :cnpj, :address, :city, "
            ":state, :user_id)"
        ),
        {"organization_id": organization_id, "school_id": school_id, "user_id": user_id, **values},
    )


def carryovers(db: Session, school_id: uuid.UUID, year: int) -> Sequence[Row]:
    """The latest carry-over of each program for the year."""
    return (
        db.execute(
            text(
                "SELECT DISTINCT ON (program, coalesce(program_label, '')) program, program_label, "
                "custeio_cents, capital_cents FROM pdde_carryovers "
                "WHERE school_id = :school_id AND year = :year "
                "ORDER BY program, coalesce(program_label, ''), created_at DESC, id DESC"
            ),
            {"school_id": school_id, "year": year},
        )
        .mappings()
        .all()
    )


def insert_carryover(
    db: Session,
    *,
    organization_id: uuid.UUID,
    school_id: uuid.UUID,
    user_id: uuid.UUID,
    values: dict[str, Any],
) -> None:
    db.execute(
        text(
            "INSERT INTO pdde_carryovers (organization_id, school_id, year, program, program_label, "
            "custeio_cents, capital_cents, created_by_user_id) VALUES (:organization_id, :school_id, "
            ":year, :program, :program_label, :custeio_cents, :capital_cents, :user_id)"
        ),
        {"organization_id": organization_id, "school_id": school_id, "user_id": user_id, **values},
    )


def school_name(db: Session, school_id: uuid.UUID) -> tuple[str, str]:
    """(the APM, the school): the name of the entity printed on the form when no other was given."""
    row = db.execute(
        text(
            "SELECT o.name, s.name FROM schools s JOIN organizations o ON o.id = s.organization_id "
            "WHERE s.id = :school_id"
        ),
        {"school_id": school_id},
    ).one()
    return str(row[0]), str(row[1])
