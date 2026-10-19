# ruff: noqa: E501  (SQL)
"""What the tax routes read and write (constants given to `text()`, values bound)."""

import datetime as dt
import uuid
from collections.abc import Sequence
from typing import Any

from sqlalchemy import RowMapping, text
from sqlalchemy.orm import Session

Row = RowMapping


def latest_rules(db: Session, school_id: uuid.UUID) -> Sequence[Row]:
    """The latest version of each rule (they are insert-only: a change is a new row of the same key)."""
    return (
        db.execute(
            text(
                "SELECT DISTINCT ON (rule_key) id, rule_key, label, tax_kind, applies_to, rate_bps, "
                "base_cap_cents, min_total_cents, darf_code, howto, due_day, due_roll, source_note, "
                "validated_at FROM tax_rules WHERE school_id = :school_id "
                "ORDER BY rule_key, created_at DESC, id DESC"
            ),
            {"school_id": school_id},
        )
        .mappings()
        .all()
    )


def rule_by_id(db: Session, school_id: uuid.UUID, rule_id: uuid.UUID) -> Row | None:
    return (
        db.execute(
            text(
                "SELECT id, rule_key, label, tax_kind, applies_to, rate_bps, base_cap_cents, "
                "min_total_cents, darf_code, howto, due_day, due_roll, source_note, validated_at "
                "FROM tax_rules WHERE id = :id AND school_id = :school_id"
            ),
            {"id": rule_id, "school_id": school_id},
        )
        .mappings()
        .first()
    )


def insert_rule(
    db: Session,
    *,
    organization_id: uuid.UUID,
    school_id: uuid.UUID,
    user_id: uuid.UUID,
    values: dict[str, Any],
    validated: bool,
) -> None:
    db.execute(
        text(
            "INSERT INTO tax_rules (organization_id, school_id, rule_key, label, tax_kind, applies_to, "
            "rate_bps, base_cap_cents, min_total_cents, darf_code, howto, due_day, due_roll, "
            "source_note, validated_at, validated_by_user_id, created_by_user_id) "
            "VALUES (:organization_id, :school_id, :rule_key, :label, :tax_kind, :applies_to, "
            ":rate_bps, :base_cap_cents, :min_total_cents, :darf_code, :howto, :due_day, :due_roll, "
            ":source_note, CASE WHEN :validated THEN now() END, CASE WHEN :validated THEN :user_id END, "
            ":user_id)"
        ),
        {
            "organization_id": organization_id,
            "school_id": school_id,
            "user_id": user_id,
            "validated": validated,
            **{
                k: values[k]
                for k in (
                    "rule_key", "label", "tax_kind", "applies_to", "rate_bps", "base_cap_cents",
                    "min_total_cents", "darf_code", "howto", "due_day", "due_roll", "source_note",
                )
            },
        },
    )  # fmt: skip


def insert_retention(
    db: Session,
    *,
    organization_id: uuid.UUID,
    school_id: uuid.UUID,
    user_id: uuid.UUID,
    rule_id: uuid.UUID,
    provider_kind: str,
    provider_name: str,
    competence: dt.date,
    gross_cents: int,
    base_cents: int,
    retained_cents: int,
    rate_bps: int,
    note: str | None,
) -> uuid.UUID:
    new_id: uuid.UUID = db.execute(
        text(
            "INSERT INTO tax_retentions (organization_id, school_id, rule_id, provider_kind, "
            "provider_name, competence, gross_cents, base_cents, retained_cents, rate_bps, note, "
            "created_by_user_id) VALUES (:organization_id, :school_id, :rule_id, :provider_kind, "
            ":provider_name, :competence, :gross_cents, :base_cents, :retained_cents, :rate_bps, "
            ":note, :user_id) RETURNING id"
        ),
        {
            "organization_id": organization_id,
            "school_id": school_id,
            "user_id": user_id,
            "rule_id": rule_id,
            "provider_kind": provider_kind,
            "provider_name": provider_name,
            "competence": competence,
            "gross_cents": gross_cents,
            "base_cents": base_cents,
            "retained_cents": retained_cents,
            "rate_bps": rate_bps,
            "note": note,
        },
    ).scalar_one()
    return new_id


def retentions(db: Session, school_id: uuid.UUID, competence: dt.date) -> Sequence[Row]:
    """The retentions of a competence month, with the exact rule version each one used."""
    return (
        db.execute(
            text(
                "SELECT r.id, r.rule_id, r.provider_kind, r.provider_name, r.competence, r.gross_cents, "
                "r.base_cents, r.retained_cents, r.rate_bps, r.note, r.voided_at IS NOT NULL AS voided, "
                "r.created_at, u.rule_key, u.label AS rule_label, u.tax_kind, u.darf_code, u.howto, "
                "u.due_day, u.due_roll, u.min_total_cents, u.validated_at IS NOT NULL AS validated "
                "FROM tax_retentions r JOIN tax_rules u ON u.id = r.rule_id AND u.school_id = r.school_id "
                "WHERE r.school_id = :school_id AND r.competence = :competence "
                "ORDER BY r.created_at, r.id"
            ),
            {"school_id": school_id, "competence": competence},
        )
        .mappings()
        .all()
    )


def void_retention(
    db: Session, school_id: uuid.UUID, retention_id: uuid.UUID, user_id: uuid.UUID
) -> bool:
    done = db.execute(
        text(
            "UPDATE tax_retentions SET voided_at = now(), voided_by_user_id = :user_id "
            "WHERE id = :id AND school_id = :school_id AND voided_at IS NULL RETURNING id"
        ),
        {"id": retention_id, "school_id": school_id, "user_id": user_id},
    ).first()
    return done is not None
