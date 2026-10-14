"""The settings of a school and its public link: what the management may change and what the
database then checks again (ranges, the suggested amounts inside the minimum and the maximum)."""

import uuid

from sqlalchemy.orm import Session

from app.core.config import ApiSettings
from app.core.errors import ProblemError
from app.expenses.access import SchoolScope, not_found
from app.expenses.db_errors import database_rules
from app.school_settings import repository
from app.school_settings.schemas import PublicLinkOut, SettingsOut, SettingsPatch


def _out(row: repository.Row) -> SettingsOut:
    return SettingsOut.model_validate(dict(row))


def get_settings(db: Session, scope: SchoolScope) -> SettingsOut:
    row = repository.read_settings(db, scope.school_id)
    if row is None:
        raise not_found()
    return _out(row)


def update_settings(db: Session, scope: SchoolScope, body: SettingsPatch) -> SettingsOut:
    sent = body.model_fields_set
    if not sent:
        raise ProblemError(
            422, "validation_error", "Invalid request", errors=[{"field": "body", "code": "empty"}]
        )
    for required in ("suggested_amounts_cents", "allow_custom_amount"):
        if required in sent and getattr(body, required) is None:
            raise ProblemError(
                422, "validation_error", "Invalid request",
                errors=[{"field": required, "code": "required"}],
            )  # fmt: skip
    with database_rules(db):
        current = repository.read_settings(db, scope.school_id)
        if current is None:
            raise not_found()
        changes = {name: getattr(body, name) for name in sent}
        amounts = changes.get("suggested_amounts_cents")
        if amounts is not None:
            low, high = current["min_contribution_cents"], current["max_contribution_cents"]
            if any(not low <= cents <= high for cents in amounts) or len(set(amounts)) != len(
                amounts
            ):
                raise ProblemError(
                    422, "validation_error", "Invalid request",
                    errors=[{"field": "suggested_amounts_cents", "code": "out_of_range"}],
                )  # fmt: skip
            changes["suggested_amounts_cents"] = sorted(amounts)
        repository.update_settings(db, scope.school_id, changes)
        db.commit()
    return get_settings(db, scope)


def public_link(db: Session, scope: SchoolScope, settings: ApiSettings) -> PublicLinkOut:
    """The address the families open. The slug of a school never changes by the application, so a
    printed QR code keeps working."""
    row = repository.school_identity(db, scope.school_id)
    if row is None:
        raise not_found()
    base = settings.public_base_url.rstrip("/")
    return PublicLinkOut(
        school_id=uuid.UUID(str(row["id"])),
        school_name=row["name"],
        slug=row["slug"],
        url=f"{base}/escola/{row['slug']}",
    )
