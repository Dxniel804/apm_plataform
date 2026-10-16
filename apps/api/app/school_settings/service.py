"""The settings of a school and its public link: what the management may change and what the
database then checks again (ranges, the suggested amounts inside the minimum and the maximum)."""

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from app.core.config import ApiSettings
from app.core.errors import ProblemError
from app.expenses.access import SchoolScope, not_found
from app.expenses.db_errors import database_rules
from app.school_settings import repository
from app.school_settings.schemas import (
    IdentityOut,
    IdentityPatch,
    PublicLinkOut,
    SettingsOut,
    SettingsPatch,
)


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
    """The address the families open. The school may change it (docs/adr-school-identity.md), but an
    old address keeps opening the school, so a printed QR code keeps working."""
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


FREE_SLUG_CHANGES = 2
SLUG_COOLDOWN = timedelta(days=15)


def _locked_until(changes: int, changed_at: datetime | None) -> datetime | None:
    """When the address may be changed again, or None if it may be changed now."""
    if changes < FREE_SLUG_CHANGES or changed_at is None:
        return None
    until = changed_at + SLUG_COOLDOWN
    return until if until > datetime.now(UTC) else None


def _identity_out(db: Session, row: repository.Row, settings: ApiSettings) -> IdentityOut:
    base = settings.public_base_url.rstrip("/")
    changes = int(row["slug_changes"])
    school_id = uuid.UUID(str(row["id"]))
    return IdentityOut(
        school_id=school_id,
        name=row["name"],
        slug=row["slug"],
        url=f"{base}/escola/{row['slug']}",
        slug_changes=changes,
        free_changes_left=max(0, FREE_SLUG_CHANGES - changes),
        slug_locked_until=_locked_until(changes, row["slug_changed_at"]),
        link_active=bool(row["link_active"]),
        previous_slugs=repository.previous_slugs(db, school_id, row["slug"]),
    )


def get_identity(db: Session, scope: SchoolScope, settings: ApiSettings) -> IdentityOut:
    row = repository.identity_row(db, scope.school_id)
    if row is None:
        raise not_found()
    return _identity_out(db, row, settings)


def update_identity(
    db: Session, scope: SchoolScope, body: IdentityPatch, settings: ApiSettings
) -> IdentityOut:
    """Change the name and/or the address. The database decides (reserved words, the 15 days, an
    address that is or was anybody else's); this checks first only to give a precise answer."""
    if not body.model_fields_set:
        raise ProblemError(
            422, "validation_error", "Invalid request", errors=[{"field": "body", "code": "empty"}]
        )
    with database_rules(db):
        row = repository.identity_row(db, scope.school_id)
        if row is None:
            raise not_found()
        changing_slug = body.slug is not None and body.slug != row["slug"]
        if changing_slug:
            until = _locked_until(int(row["slug_changes"]), row["slug_changed_at"])
            if until is not None:
                raise ProblemError(
                    409, "slug_change_locked", "The address was changed too recently",
                    errors=[{"field": "slug", "code": "locked_until", "until": until.isoformat()}],
                )  # fmt: skip
        repository.update_identity(
            db,
            scope.school_id,
            name=body.name,
            slug=body.slug if changing_slug else None,
        )
        # The families pay through this address: before keeping the change, the PUBLIC lookup must
        # open this very school by the new address and by the old one.
        if (
            changing_slug
            and row["link_active"]
            and (
                repository.resolves_to(db, str(body.slug)) != scope.school_id
                or repository.resolves_to(db, str(row["slug"])) != scope.school_id
            )
        ):
            db.rollback()
            raise ProblemError(500, "link_check_failed", "The new address could not be confirmed")
        db.commit()
    return get_identity(db, scope, settings)
