"""The SQL of the settings of a school: constant statements, values always bound."""

import uuid
from collections.abc import Mapping
from typing import Any

from sqlalchemy import RowMapping, text
from sqlalchemy.orm import Session

Row = RowMapping

SETTINGS_COLUMNS = frozenset(
    {
        "suggested_amounts_cents",
        "allow_custom_amount",
        "free_amount_text",
        "monthly_goal_cents",
        "expected_contributions",
    }
)


def read_settings(db: Session, school_id: uuid.UUID) -> Row | None:
    return (
        db.execute(
            text(
                "SELECT suggested_amounts_cents, allow_custom_amount, min_contribution_cents, "
                "max_contribution_cents, free_amount_text, monthly_goal_cents, "
                "expected_contributions FROM school_settings WHERE school_id = :school_id"
            ),
            {"school_id": school_id},
        )
        .mappings()
        .first()
    )


def update_settings(db: Session, school_id: uuid.UUID, changes: Mapping[str, Any]) -> None:
    """Only the columns named in `changes` are written; the statement is a constant, the choice
    is a bound flag per column."""
    unknown = set(changes) - SETTINGS_COLUMNS
    if unknown or not changes:
        raise ValueError("a settings update names only the editable columns")
    db.execute(
        text(
            "UPDATE school_settings SET "
            "suggested_amounts_cents = CASE WHEN :set_suggested_amounts_cents "
            "THEN CAST(:suggested_amounts_cents AS bigint[]) ELSE suggested_amounts_cents END, "
            "allow_custom_amount = CASE WHEN :set_allow_custom_amount "
            "THEN CAST(:allow_custom_amount AS boolean) ELSE allow_custom_amount END, "
            "free_amount_text = CASE WHEN :set_free_amount_text "
            "THEN CAST(:free_amount_text AS text) ELSE free_amount_text END, "
            "monthly_goal_cents = CASE WHEN :set_monthly_goal_cents "
            "THEN CAST(:monthly_goal_cents AS bigint) ELSE monthly_goal_cents END, "
            "expected_contributions = CASE WHEN :set_expected_contributions "
            "THEN CAST(:expected_contributions AS integer) ELSE expected_contributions END, "
            "updated_at = now() WHERE school_id = :school_id"
        ),
        {
            **{f"set_{column}": column in changes for column in sorted(SETTINGS_COLUMNS)},
            **{column: changes.get(column) for column in sorted(SETTINGS_COLUMNS)},
            "school_id": school_id,
        },
    )


def school_identity(db: Session, school_id: uuid.UUID) -> Row | None:
    return (
        db.execute(
            text("SELECT id, name, slug FROM schools WHERE id = :school_id"),
            {"school_id": school_id},
        )
        .mappings()
        .first()
    )


def identity_row(db: Session, school_id: uuid.UUID) -> Row | None:
    """The name and the address of the school, its counters, and whether it can receive payments."""
    return (
        db.execute(
            text(
                "SELECT s.id, s.name, s.slug, s.slug_changes, s.slug_changed_at, "
                "EXISTS (SELECT 1 FROM payment_accounts a WHERE a.school_id = s.id "
                "AND a.status = 'ACTIVE') AS link_active "
                "FROM schools s WHERE s.id = :school_id"
            ),
            {"school_id": school_id},
        )
        .mappings()
        .first()
    )


def previous_slugs(db: Session, school_id: uuid.UUID, current: str) -> list[str]:
    found = db.execute(
        text(
            "SELECT slug FROM school_slug_history "
            "WHERE school_id = :school_id AND slug <> :current ORDER BY created_at DESC"
        ),
        {"school_id": school_id, "current": current},
    )
    return [str(row[0]) for row in found.all()]


def update_identity(
    db: Session, school_id: uuid.UUID, *, name: str | None, slug: str | None
) -> None:
    db.execute(
        text(
            "UPDATE schools SET name = coalesce(:name, name), slug = coalesce(:slug, slug), "
            "updated_at = now() WHERE id = :school_id"
        ),
        {"school_id": school_id, "name": name, "slug": slug},
    )


def resolves_to(db: Session, slug: str) -> uuid.UUID | None:
    """The school the PUBLIC lookup (the one the families use) finds for an address."""
    found = db.execute(
        text("SELECT school_id FROM public.resolve_school_public(:slug)"), {"slug": slug}
    ).scalar_one_or_none()
    return None if found is None else uuid.UUID(str(found))
