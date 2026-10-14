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

CAMPAIGN_COLUMNS = frozenset({"title", "description", "starts_on", "ends_on", "ask_student_class"})
ITEM_COLUMNS = frozenset(
    {
        "name", "description", "price_cents", "unit_cost_cents", "max_per_order", "position",
        "is_active",
    }
)  # fmt: skip


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
    ask_student_class: bool,
) -> uuid.UUID:
    created: uuid.UUID = db.execute(
        text(
            "INSERT INTO campaigns (organization_id, school_id, created_by_user_id, title, "
            "description, starts_on, ends_on, ask_student_class) VALUES (:organization_id, "
            ":school_id, :created_by_user_id, :title, :description, :starts_on, :ends_on, "
            ":ask_student_class) RETURNING id"
        ),
        {
            "organization_id": organization_id,
            "school_id": school_id,
            "created_by_user_id": created_by_user_id,
            "title": title,
            "description": description,
            "starts_on": starts_on,
            "ends_on": ends_on,
            "ask_student_class": ask_student_class,
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
                "c.updated_at, c.ask_student_class, "
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
            "ask_student_class = CASE WHEN :set_ask_student_class "
            "THEN CAST(:ask_student_class AS boolean) ELSE ask_student_class END, "
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
    unit_cost_cents: int | None,
    max_per_order: int | None,
    position: int,
) -> uuid.UUID:
    created: uuid.UUID = db.execute(
        text(
            "INSERT INTO campaign_items (organization_id, school_id, campaign_id, name, "
            "description, price_cents, unit_cost_cents, max_per_order, position) VALUES "
            "(:organization_id, :school_id, :campaign_id, :name, :description, :price_cents, "
            ":unit_cost_cents, :max_per_order, :position) RETURNING id"
        ),
        {
            "organization_id": organization_id,
            "school_id": school_id,
            "campaign_id": campaign_id,
            "name": name,
            "description": description,
            "price_cents": price_cents,
            "unit_cost_cents": unit_cost_cents,
            "max_per_order": max_per_order,
            "position": position,
        },
    ).scalar_one()
    return created


def items_of(db: Session, school_id: uuid.UUID, campaign_id: uuid.UUID) -> Sequence[Row]:
    return (
        db.execute(
            text(
                "SELECT id, name, description, price_cents, unit_cost_cents, max_per_order, "
                "position, is_active, image_storage_key IS NOT NULL AS has_image, image_version "
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
            "unit_cost_cents = CASE WHEN :set_unit_cost_cents "
            "THEN CAST(:unit_cost_cents AS bigint) ELSE unit_cost_cents END, "
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


# --- the dashboard, the orders and their delivery (0014) -------------------------------------
# Every statement is ONE constant string (docs/tenancy.md: nothing is built from pieces). The same
# fragments therefore repeat on purpose:
#   * the payment of an order as the panel shows it (PAID; PENDING when the Pix is open or in
#     review; CANCELLED when cancelled or expired) is the CASE on `f.status`;
#   * an order of the campaign joins its ledger row `f` and, when it was ever marked, its
#     delivery `d`.


def orders_by_payment(db: Session, school_id: uuid.UUID, campaign_id: uuid.UUID) -> Sequence[Row]:
    return (
        db.execute(
            text(
                "SELECT CASE f.status WHEN 'PAID' THEN 'PAID' "
                "WHEN 'PENDING_PAYMENT' THEN 'PENDING' "
                "WHEN 'REVIEW_REQUIRED' THEN 'PENDING' ELSE 'CANCELLED' END AS payment_status, "
                "count(*) AS orders, coalesce(sum(f.amount_cents), 0) AS cents "
                "FROM contributions o "
                "JOIN financial_transactions f ON f.id = o.transaction_id "
                "AND f.school_id = o.school_id "
                "WHERE o.campaign_id = :campaign_id AND o.school_id = :school_id GROUP BY 1"
            ),
            {"campaign_id": campaign_id, "school_id": school_id},
        )
        .mappings()
        .all()
    )


def delivered_orders(db: Session, school_id: uuid.UUID, campaign_id: uuid.UUID) -> int:
    return int(
        db.execute(
            text(
                "SELECT count(*) FROM contributions o "
                "JOIN financial_transactions f ON f.id = o.transaction_id "
                "AND f.school_id = o.school_id "
                "JOIN campaign_deliveries d ON d.transaction_id = o.transaction_id "
                "AND d.school_id = o.school_id "
                "WHERE o.campaign_id = :campaign_id AND o.school_id = :school_id "
                "AND f.status = 'PAID' AND d.status = 'DELIVERED'"
            ),
            {"campaign_id": campaign_id, "school_id": school_id},
        ).scalar_one()
    )


def sold_items(db: Session, school_id: uuid.UUID, campaign_id: uuid.UUID) -> Sequence[Row]:
    """Every product of the campaign (the ones that sold nothing too) with what its PAID orders
    took, read from the COPY the orders kept (name, price and cost at the purchase)."""
    return (
        db.execute(
            text(
                "SELECT ci.id AS item_id, ci.name, ci.position, "
                "coalesce(s.units, 0) AS units_sold, coalesce(s.revenue, 0) AS revenue_cents, "
                "s.cost AS cost_cents, coalesce(s.known, true) AS cost_known "
                "FROM campaign_items ci LEFT JOIN ("
                " SELECT i.campaign_item_id, sum(i.quantity) AS units, "
                "  sum(i.quantity * i.unit_price_cents) AS revenue, "
                "  sum(i.quantity * i.unit_cost_cents) AS cost, "
                "  bool_and(i.unit_cost_cents IS NOT NULL) AS known "
                " FROM contribution_items i "
                " JOIN contributions o ON o.transaction_id = i.transaction_id "
                "  AND o.school_id = i.school_id "
                " JOIN financial_transactions f ON f.id = o.transaction_id "
                "  AND f.school_id = o.school_id "
                " WHERE i.campaign_id = :campaign_id AND i.school_id = :school_id "
                "  AND f.status = 'PAID' GROUP BY i.campaign_item_id"
                ") s ON s.campaign_item_id = ci.id "
                "WHERE ci.campaign_id = :campaign_id AND ci.school_id = :school_id "
                "ORDER BY ci.position, ci.created_at, ci.id"
            ),
            {"campaign_id": campaign_id, "school_id": school_id},
        )
        .mappings()
        .all()
    )


def _like(search: str) -> str:
    """The text of a search as a LIKE pattern: the characters that mean something to LIKE are
    escaped (a person typing `%` looks for a percent sign)."""
    escaped = search.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def _order_params(
    school_id: uuid.UUID,
    campaign_id: uuid.UUID,
    payment: str | None,
    delivery: str | None,
    search: str | None,
) -> dict[str, Any]:
    digits = "".join(ch for ch in (search or "") if ch.isdigit()).lstrip("0")
    return {
        "school_id": school_id,
        "campaign_id": campaign_id,
        "payment": payment,
        "delivery": delivery,
        "search": search,
        "like": _like(search) if search else None,
        "digits": digits or None,
    }


def count_orders(
    db: Session,
    school_id: uuid.UUID,
    campaign_id: uuid.UUID,
    *,
    payment: str | None,
    delivery: str | None,
    search: str | None,
) -> int:
    return int(
        db.execute(
            text(
                "SELECT count(*) FROM contributions o "
                "JOIN financial_transactions f ON f.id = o.transaction_id "
                "AND f.school_id = o.school_id "
                "LEFT JOIN campaign_deliveries d ON d.transaction_id = o.transaction_id "
                "AND d.school_id = o.school_id "
                "WHERE o.campaign_id = :campaign_id AND o.school_id = :school_id "
                "AND (CAST(:payment AS text) IS NULL OR CASE f.status WHEN 'PAID' THEN 'PAID' "
                " WHEN 'PENDING_PAYMENT' THEN 'PENDING' WHEN 'REVIEW_REQUIRED' THEN 'PENDING' "
                " ELSE 'CANCELLED' END = :payment) "
                "AND (CAST(:delivery AS text) IS NULL OR "
                " (f.status = 'PAID' AND coalesce(d.status, 'PENDING') = :delivery)) "
                "AND (CAST(:search AS text) IS NULL "
                " OR o.guardian_name ILIKE :like ESCAPE '\\' "
                " OR o.student_name ILIKE :like ESCAPE '\\' "
                " OR o.class_name ILIKE :like ESCAPE '\\' "
                " OR CAST(f.reference_code AS text) = :digits)"
            ),
            _order_params(school_id, campaign_id, payment, delivery, search),
        ).scalar_one()
    )


def search_orders(
    db: Session,
    school_id: uuid.UUID,
    campaign_id: uuid.UUID,
    *,
    payment: str | None,
    delivery: str | None,
    search: str | None,
    limit: int,
    offset: int,
) -> Sequence[Row]:
    return (
        db.execute(
            text(
                "SELECT o.transaction_id AS order_id, f.reference_code, f.created_at, "
                "o.guardian_name, o.student_name, o.class_name, f.amount_cents, "
                "CASE f.status WHEN 'PAID' THEN 'PAID' WHEN 'PENDING_PAYMENT' THEN 'PENDING' "
                "WHEN 'REVIEW_REQUIRED' THEN 'PENDING' ELSE 'CANCELLED' END AS payment_status, "
                "CASE WHEN f.status = 'PAID' THEN coalesce(d.status, 'PENDING') END "
                "AS delivery_status, d.changed_at AS delivery_changed_at "
                "FROM contributions o "
                "JOIN financial_transactions f ON f.id = o.transaction_id "
                "AND f.school_id = o.school_id "
                "LEFT JOIN campaign_deliveries d ON d.transaction_id = o.transaction_id "
                "AND d.school_id = o.school_id "
                "WHERE o.campaign_id = :campaign_id AND o.school_id = :school_id "
                "AND (CAST(:payment AS text) IS NULL OR CASE f.status WHEN 'PAID' THEN 'PAID' "
                " WHEN 'PENDING_PAYMENT' THEN 'PENDING' WHEN 'REVIEW_REQUIRED' THEN 'PENDING' "
                " ELSE 'CANCELLED' END = :payment) "
                "AND (CAST(:delivery AS text) IS NULL OR "
                " (f.status = 'PAID' AND coalesce(d.status, 'PENDING') = :delivery)) "
                "AND (CAST(:search AS text) IS NULL "
                " OR o.guardian_name ILIKE :like ESCAPE '\\' "
                " OR o.student_name ILIKE :like ESCAPE '\\' "
                " OR o.class_name ILIKE :like ESCAPE '\\' "
                " OR CAST(f.reference_code AS text) = :digits) "
                "ORDER BY f.created_at DESC, o.transaction_id DESC LIMIT :limit OFFSET :offset"
            ),
            {
                **_order_params(school_id, campaign_id, payment, delivery, search),
                "limit": limit,
                "offset": offset,
            },
        )
        .mappings()
        .all()
    )


def order_lines(db: Session, school_id: uuid.UUID, order_ids: Sequence[uuid.UUID]) -> Sequence[Row]:
    return (
        db.execute(
            text(
                "SELECT transaction_id, item_name, quantity, unit_price_cents "
                "FROM contribution_items WHERE school_id = :school_id "
                "AND transaction_id = ANY(:ids) ORDER BY created_at, id"
            ),
            {"school_id": school_id, "ids": list(order_ids)},
        )
        .mappings()
        .all()
    )


def paid_orders_of_campaign(
    db: Session, school_id: uuid.UUID, campaign_id: uuid.UUID, order_ids: Sequence[uuid.UUID]
) -> list[uuid.UUID]:
    """Of the given ids, the ones that are orders of THIS campaign and PAID (the only ones a
    delivery can be recorded for)."""
    rows = db.execute(
        text(
            "SELECT o.transaction_id FROM contributions o "
            "JOIN financial_transactions f ON f.id = o.transaction_id "
            "AND f.school_id = o.school_id "
            "WHERE o.campaign_id = :campaign_id AND o.school_id = :school_id "
            "AND f.status = 'PAID' AND o.transaction_id = ANY(:ids)"
        ),
        {"campaign_id": campaign_id, "school_id": school_id, "ids": list(order_ids)},
    ).all()
    return [row[0] for row in rows]


def mark_delivered(
    db: Session,
    *,
    organization_id: uuid.UUID,
    school_id: uuid.UUID,
    user_id: uuid.UUID,
    order_ids: Sequence[uuid.UUID],
) -> int:
    """DELIVERED for each order (a row is created the first time); the ones that already were are
    left alone. Returns how many changed."""
    result = db.execute(
        text(
            "INSERT INTO campaign_deliveries (organization_id, school_id, transaction_id, "
            "status, changed_by_user_id) "
            "SELECT :organization_id, :school_id, t, 'DELIVERED', :user_id "
            "FROM unnest(CAST(:ids AS uuid[])) AS t "
            "ON CONFLICT (transaction_id, organization_id, school_id) DO UPDATE SET "
            "status = 'DELIVERED', changed_by_user_id = EXCLUDED.changed_by_user_id, "
            "changed_at = now() WHERE campaign_deliveries.status <> 'DELIVERED'"
        ),
        {
            "organization_id": organization_id,
            "school_id": school_id,
            "user_id": user_id,
            "ids": list(order_ids),
        },
    )
    return int(result.rowcount)  # type: ignore[attr-defined]


def mark_pending(
    db: Session,
    *,
    school_id: uuid.UUID,
    user_id: uuid.UUID,
    order_ids: Sequence[uuid.UUID],
) -> int:
    """Back to PENDING the orders that were DELIVERED. Returns how many changed."""
    result = db.execute(
        text(
            "UPDATE campaign_deliveries SET status = 'PENDING', changed_by_user_id = :user_id, "
            "changed_at = now() WHERE school_id = :school_id AND status = 'DELIVERED' "
            "AND transaction_id = ANY(:ids)"
        ),
        {"school_id": school_id, "user_id": user_id, "ids": list(order_ids)},
    )
    return int(result.rowcount)  # type: ignore[attr-defined]


def school_timezone(db: Session, school_id: uuid.UUID) -> str:
    zone: str = db.execute(
        text("SELECT timezone FROM school_settings WHERE school_id = :school_id"),
        {"school_id": school_id},
    ).scalar_one()
    return zone
