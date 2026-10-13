"""The SQL of the campaigns: constant statements, values always bound.

Every statement names the school (`school_id`) even though row level security already limits what
the session sees. Nothing here decides who may do what (the service does) or what the states allow
(the database does). The only text built from names is the SET list of an update, and its column
names come from a fixed list in this file, never from the caller.
"""

import datetime as dt
import json
import uuid
from collections.abc import Mapping, Sequence
from typing import Any

from sqlalchemy import RowMapping, text
from sqlalchemy.orm import Session

Row = RowMapping

CAMPAIGN_COLUMNS = frozenset({"title", "description", "starts_on", "ends_on"})
ITEM_COLUMNS = frozenset(
    {"name", "description", "price_cents", "max_per_order", "position", "is_active"}
)


def insert_campaign(
    db: Session,
    *,
    organization_id: uuid.UUID,
    school_id: uuid.UUID,
    created_by_user_id: uuid.UUID,
    title: str,
    description: str | None,
    starts_on: dt.date | None,
    ends_on: dt.date | None,
) -> uuid.UUID:
    created: uuid.UUID = db.execute(
        text(
            "INSERT INTO campaigns (organization_id, school_id, created_by_user_id, title, "
            "description, starts_on, ends_on) VALUES (:organization_id, :school_id, "
            ":created_by_user_id, :title, :description, :starts_on, :ends_on) RETURNING id"
        ),
        {
            "organization_id": organization_id,
            "school_id": school_id,
            "created_by_user_id": created_by_user_id,
            "title": title,
            "description": description,
            "starts_on": starts_on,
            "ends_on": ends_on,
        },
    ).scalar_one()
    return created


def search_campaigns(
    db: Session,
    school_id: uuid.UUID,
    *,
    campaign_id: uuid.UUID | None = None,
    status: str | None = None,
) -> Sequence[Row]:
    """The campaigns of the school with their counts, the ones on sale first. One statement serves
    the list and the detail: a filter that is NULL does not apply."""
    return (
        db.execute(
            text(
                "SELECT c.id, c.title, c.description, c.status, c.starts_on, c.ends_on, "
                "c.cover_storage_key IS NOT NULL AS has_cover, c.cover_version, c.created_at, "
                "c.updated_at, "
                "(SELECT count(*) FROM campaign_items i "
                " WHERE i.campaign_id = c.id AND i.school_id = c.school_id) AS items_count, "
                "(SELECT count(*) FROM campaign_items i "
                " WHERE i.campaign_id = c.id AND i.school_id = c.school_id AND i.is_active) "
                "AS active_items_count, "
                "(SELECT count(*) FROM contributions o "
                " JOIN financial_transactions f ON f.id = o.transaction_id "
                " AND f.school_id = o.school_id "
                " WHERE o.campaign_id = c.id AND o.school_id = c.school_id AND f.status = 'PAID') "
                "AS paid_orders_count, "
                "(SELECT coalesce(sum(f.amount_cents), 0) FROM contributions o "
                " JOIN financial_transactions f ON f.id = o.transaction_id "
                " AND f.school_id = o.school_id "
                " WHERE o.campaign_id = c.id AND o.school_id = c.school_id AND f.status = 'PAID') "
                "AS paid_cents "
                "FROM campaigns c WHERE c.school_id = :school_id "
                "AND (CAST(:campaign_id AS uuid) IS NULL OR c.id = :campaign_id) "
                "AND (CAST(:status AS text) IS NULL OR c.status = :status) "
                "ORDER BY CASE c.status WHEN 'ACTIVE' THEN 0 WHEN 'DRAFT' THEN 1 ELSE 2 END, "
                "c.created_at DESC, c.id DESC LIMIT 100"
            ),
            {"school_id": school_id, "campaign_id": campaign_id, "status": status},
        )
        .mappings()
        .all()
    )


def lock_campaign(db: Session, school_id: uuid.UUID, campaign_id: uuid.UUID) -> bool:
    """Hold the row of the campaign until the end of the transaction (False: there is none)."""
    return (
        db.execute(
            text("SELECT id FROM campaigns WHERE id = :id AND school_id = :school_id FOR UPDATE"),
            {"id": campaign_id, "school_id": school_id},
        ).first()
        is not None
    )


def campaign_image(db: Session, school_id: uuid.UUID, campaign_id: uuid.UUID) -> Row | None:
    return (
        db.execute(
            text(
                "SELECT cover_storage_key AS storage_key, cover_content_type AS content_type, "
                "cover_size_bytes AS size_bytes, cover_sha256 AS sha256 FROM campaigns "
                "WHERE id = :id AND school_id = :school_id AND cover_storage_key IS NOT NULL"
            ),
            {"id": campaign_id, "school_id": school_id},
        )
        .mappings()
        .first()
    )


def update_campaign(
    db: Session, school_id: uuid.UUID, campaign_id: uuid.UUID, changes: Mapping[str, Any]
) -> None:
    """Only the columns named in `changes` are written (the others keep their value); the statement
    is a constant, the choice is a bound flag per column."""
    unknown = set(changes) - CAMPAIGN_COLUMNS
    if unknown or not changes:
        raise ValueError("a campaign update names only the editable columns")
    db.execute(
        text(
            "UPDATE campaigns SET "
            "title = CASE WHEN :set_title THEN CAST(:title AS text) ELSE title END, "
            "description = CASE WHEN :set_description THEN CAST(:description AS text) "
            "ELSE description END, "
            "starts_on = CASE WHEN :set_starts_on THEN CAST(:starts_on AS date) "
            "ELSE starts_on END, "
            "ends_on = CASE WHEN :set_ends_on THEN CAST(:ends_on AS date) ELSE ends_on END, "
            "updated_at = now() WHERE id = :id AND school_id = :school_id"
        ),
        {
            **{f"set_{column}": column in changes for column in sorted(CAMPAIGN_COLUMNS)},
            **{column: changes.get(column) for column in sorted(CAMPAIGN_COLUMNS)},
            "id": campaign_id,
            "school_id": school_id,
        },
    )


def set_status(
    db: Session, school_id: uuid.UUID, campaign_id: uuid.UUID, status: str, expected: str
) -> bool:
    """Move the campaign to `status` only if it is still in the `expected` one."""
    result = db.execute(
        text(
            "UPDATE campaigns SET status = :status, updated_at = now(), "
            "ended_at = CASE WHEN :status = 'ENDED' THEN now() ELSE ended_at END "
            "WHERE id = :id AND school_id = :school_id AND status = :expected"
        ),
        {"status": status, "id": campaign_id, "school_id": school_id, "expected": expected},
    )
    return bool(result.rowcount == 1)  # type: ignore[attr-defined]


def set_cover(
    db: Session,
    school_id: uuid.UUID,
    campaign_id: uuid.UUID,
    *,
    storage_key: str | None,
    content_type: str | None,
    size_bytes: int | None,
    sha256: str | None,
) -> None:
    db.execute(
        text(
            "UPDATE campaigns SET cover_storage_key = :key, cover_content_type = :content_type, "
            "cover_size_bytes = :size_bytes, cover_sha256 = :sha256, "
            "cover_version = cover_version + 1, updated_at = now() "
            "WHERE id = :id AND school_id = :school_id"
        ),
        {
            "key": storage_key,
            "content_type": content_type,
            "size_bytes": size_bytes,
            "sha256": sha256,
            "id": campaign_id,
            "school_id": school_id,
        },
    )


def today_in_school(db: Session, school_id: uuid.UUID) -> dt.date:
    today: dt.date = db.execute(
        text(
            "SELECT (now() AT TIME ZONE timezone)::date FROM school_settings "
            "WHERE school_id = :school_id"
        ),
        {"school_id": school_id},
    ).scalar_one()
    return today


# --- products -------------------------------------------------------------------------------------


def insert_item(
    db: Session,
    *,
    organization_id: uuid.UUID,
    school_id: uuid.UUID,
    campaign_id: uuid.UUID,
    name: str,
    description: str | None,
    price_cents: int,
    max_per_order: int | None,
    position: int,
) -> uuid.UUID:
    created: uuid.UUID = db.execute(
        text(
            "INSERT INTO campaign_items (organization_id, school_id, campaign_id, name, "
            "description, price_cents, max_per_order, position) VALUES (:organization_id, "
            ":school_id, :campaign_id, :name, :description, :price_cents, :max_per_order, "
            ":position) RETURNING id"
        ),
        {
            "organization_id": organization_id,
            "school_id": school_id,
            "campaign_id": campaign_id,
            "name": name,
            "description": description,
            "price_cents": price_cents,
            "max_per_order": max_per_order,
            "position": position,
        },
    ).scalar_one()
    return created


def items_of(db: Session, school_id: uuid.UUID, campaign_id: uuid.UUID) -> Sequence[Row]:
    return (
        db.execute(
            text(
                "SELECT id, name, description, price_cents, max_per_order, position, is_active, "
                "image_storage_key IS NOT NULL AS has_image, image_version "
                "FROM campaign_items WHERE campaign_id = :campaign_id AND school_id = :school_id "
                "ORDER BY position, created_at, id"
            ),
            {"campaign_id": campaign_id, "school_id": school_id},
        )
        .mappings()
        .all()
    )


def count_items(db: Session, school_id: uuid.UUID, campaign_id: uuid.UUID) -> int:
    return int(
        db.execute(
            text(
                "SELECT count(*) FROM campaign_items "
                "WHERE campaign_id = :campaign_id AND school_id = :school_id"
            ),
            {"campaign_id": campaign_id, "school_id": school_id},
        ).scalar_one()
    )


def count_active_items(db: Session, school_id: uuid.UUID, campaign_id: uuid.UUID) -> int:
    return int(
        db.execute(
            text(
                "SELECT count(*) FROM campaign_items WHERE campaign_id = :campaign_id "
                "AND school_id = :school_id AND is_active"
            ),
            {"campaign_id": campaign_id, "school_id": school_id},
        ).scalar_one()
    )


def lock_item(
    db: Session, school_id: uuid.UUID, campaign_id: uuid.UUID, item_id: uuid.UUID
) -> Row | None:
    return (
        db.execute(
            text(
                "SELECT id, image_storage_key FROM campaign_items WHERE id = :id "
                "AND campaign_id = :campaign_id AND school_id = :school_id FOR UPDATE"
            ),
            {"id": item_id, "campaign_id": campaign_id, "school_id": school_id},
        )
        .mappings()
        .first()
    )


def update_item(
    db: Session,
    school_id: uuid.UUID,
    campaign_id: uuid.UUID,
    item_id: uuid.UUID,
    changes: Mapping[str, Any],
) -> None:
    unknown = set(changes) - ITEM_COLUMNS
    if unknown or not changes:
        raise ValueError("a product update names only the editable columns")
    db.execute(
        text(
            "UPDATE campaign_items SET "
            "name = CASE WHEN :set_name THEN CAST(:name AS text) ELSE name END, "
            "description = CASE WHEN :set_description THEN CAST(:description AS text) "
            "ELSE description END, "
            "price_cents = CASE WHEN :set_price_cents THEN CAST(:price_cents AS bigint) "
            "ELSE price_cents END, "
            "max_per_order = CASE WHEN :set_max_per_order THEN CAST(:max_per_order AS integer) "
            "ELSE max_per_order END, "
            "position = CASE WHEN :set_position THEN CAST(:position AS integer) ELSE position END, "
            "is_active = CASE WHEN :set_is_active THEN CAST(:is_active AS boolean) "
            "ELSE is_active END, "
            "updated_at = now() "
            "WHERE id = :id AND campaign_id = :campaign_id AND school_id = :school_id"
        ),
        {
            **{f"set_{column}": column in changes for column in sorted(ITEM_COLUMNS)},
            **{column: changes.get(column) for column in sorted(ITEM_COLUMNS)},
            "id": item_id,
            "campaign_id": campaign_id,
            "school_id": school_id,
        },
    )


def item_image(
    db: Session, school_id: uuid.UUID, campaign_id: uuid.UUID, item_id: uuid.UUID
) -> Row | None:
    return (
        db.execute(
            text(
                "SELECT image_storage_key AS storage_key, image_content_type AS content_type, "
                "image_size_bytes AS size_bytes, image_sha256 AS sha256 FROM campaign_items "
                "WHERE id = :id AND campaign_id = :campaign_id AND school_id = :school_id "
                "AND image_storage_key IS NOT NULL"
            ),
            {"id": item_id, "campaign_id": campaign_id, "school_id": school_id},
        )
        .mappings()
        .first()
    )


def set_item_image(
    db: Session,
    school_id: uuid.UUID,
    campaign_id: uuid.UUID,
    item_id: uuid.UUID,
    *,
    storage_key: str | None,
    content_type: str | None,
    size_bytes: int | None,
    sha256: str | None,
) -> None:
    db.execute(
        text(
            "UPDATE campaign_items SET image_storage_key = :key, image_content_type = "
            ":content_type, image_size_bytes = :size_bytes, image_sha256 = :sha256, "
            "image_version = image_version + 1, updated_at = now() "
            "WHERE id = :id AND campaign_id = :campaign_id AND school_id = :school_id"
        ),
        {
            "key": storage_key,
            "content_type": content_type,
            "size_bytes": size_bytes,
            "sha256": sha256,
            "id": item_id,
            "campaign_id": campaign_id,
            "school_id": school_id,
        },
    )


def audit_event(
    db: Session,
    *,
    organization_id: uuid.UUID,
    school_id: uuid.UUID,
    action: str,
    campaign_id: uuid.UUID,
    data: Mapping[str, Any],
) -> None:
    """A high-level event (`campaign.activated`) next to the row changes the triggers record. The
    actor is NOT passed: the database takes it from the settings of the transaction. `data` holds
    ids, states and numbers only, never free text."""
    db.execute(
        text(
            "INSERT INTO audit_logs (organization_id, school_id, action, entity_type, entity_id, "
            "after_data) VALUES (:organization_id, :school_id, :action, 'campaigns', "
            ":entity_id, CAST(:data AS jsonb))"
        ),
        {
            "organization_id": organization_id,
            "school_id": school_id,
            "action": action,
            "entity_id": campaign_id,
            "data": json.dumps(data),
        },
    )
