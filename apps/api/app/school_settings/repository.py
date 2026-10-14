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
