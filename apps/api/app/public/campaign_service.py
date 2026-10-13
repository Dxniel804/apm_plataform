"""The campaigns on sale, and the order of a family (migration 0013).

Same two moves as the rest of the public flow: the school comes from the slug through the narrow
function of 0008, the session is then bound to that school and everything runs as `apm_app` under
row level security with the actor PUBLIC. No new SECURITY DEFINER function is needed.

The family sends WHICH products and HOW MANY; it never sends a price or a total. The server reads
the current prices, adds them up, and the database refuses a copy that is not the current name and
price of a product on sale, and a contribution whose amount is not the sum of its items (0013).
"""

import uuid
from collections.abc import Sequence
from typing import Any

from sqlalchemy import RowMapping, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import ApiSettings
from app.core.errors import ProblemError
from app.public import service
from app.public.schemas import OrderIn
from app.public.service import ContributionState, PublicSchool

CATEGORY_KEY = "campaign_sales"
# The most one order may add up to (R$ 50.000,00): beyond it somebody is testing, not buying.
MAX_ORDER_CENTS = 5_000_000
MIN_ORDER_CENTS = 100

# "On sale today" is: ACTIVE, and today (in the time zone of the school) inside its dates. The same
# predicate the database applies before it accepts a copy of a product (0013), written out in
# `_LIST_OPEN` because a statement is always a constant (nothing is interpolated into SQL).
_LIST_OPEN = text(
    "SELECT c.id, c.title, c.description, c.ends_on, "
    "c.cover_storage_key IS NOT NULL AS has_cover, c.cover_version, "
    "(SELECT count(*) FROM campaign_items i WHERE i.campaign_id = c.id "
    " AND i.school_id = c.school_id AND i.is_active) AS items_count "
    "FROM campaigns c WHERE c.school_id = :school AND ("
    "c.status = 'ACTIVE' "
    "AND (c.starts_on IS NULL OR c.starts_on <= (now() AT TIME ZONE coalesce("
    "(SELECT ss.timezone FROM school_settings ss WHERE ss.school_id = c.school_id), "
    "'America/Sao_Paulo'))::date) "
    "AND (c.ends_on IS NULL OR c.ends_on >= (now() AT TIME ZONE coalesce("
    "(SELECT ss.timezone FROM school_settings ss WHERE ss.school_id = c.school_id), "
    "'America/Sao_Paulo'))::date)) "
    "AND EXISTS (SELECT 1 FROM campaign_items i WHERE i.campaign_id = c.id "
    " AND i.school_id = c.school_id AND i.is_active) "
    "ORDER BY c.created_at DESC, c.id DESC LIMIT 20"
)

Row = RowMapping


def list_open(db: Session, school: PublicSchool) -> Sequence[Row]:
    return db.execute(_LIST_OPEN, {"school": school.school_id}).mappings().all()


def open_campaign(db: Session, school: PublicSchool, campaign_id: uuid.UUID) -> Row | None:
    """A campaign on sale at the school, or None (unknown, a draft, ended, not yet or no longer
    in its dates, or of another school: all the same)."""
    rows = [row for row in list_open(db, school) if row["id"] == campaign_id]
    return rows[0] if rows else None


def open_items(db: Session, school: PublicSchool, campaign_id: uuid.UUID) -> Sequence[Row]:
    return (
        db.execute(
            text(
                "SELECT id, name, description, price_cents, max_per_order, "
                "image_storage_key IS NOT NULL AS has_image, image_version "
                "FROM campaign_items WHERE campaign_id = :campaign AND school_id = :school "
                "AND is_active ORDER BY position, created_at, id"
            ),
            {"campaign": campaign_id, "school": school.school_id},
        )
        .mappings()
        .all()
    )


def cover_image(db: Session, school: PublicSchool, campaign_id: uuid.UUID) -> Row | None:
    if open_campaign(db, school, campaign_id) is None:
        return None
    return (
        db.execute(
            text(
                "SELECT cover_storage_key AS storage_key, cover_content_type AS content_type, "
                "cover_size_bytes AS size_bytes, cover_sha256 AS sha256 FROM campaigns "
                "WHERE id = :campaign AND school_id = :school AND cover_storage_key IS NOT NULL"
            ),
            {"campaign": campaign_id, "school": school.school_id},
        )
        .mappings()
        .first()
    )


def item_image(
    db: Session, school: PublicSchool, campaign_id: uuid.UUID, item_id: uuid.UUID
) -> Row | None:
    if open_campaign(db, school, campaign_id) is None:
        return None
    return (
        db.execute(
            text(
                "SELECT image_storage_key AS storage_key, image_content_type AS content_type, "
                "image_size_bytes AS size_bytes, image_sha256 AS sha256 FROM campaign_items "
                "WHERE id = :item AND campaign_id = :campaign AND school_id = :school "
                "AND is_active AND image_storage_key IS NOT NULL"
            ),
            {"item": item_id, "campaign": campaign_id, "school": school.school_id},
        )
        .mappings()
        .first()
    )


# --- the order ------------------------------------------------------------------------------------


def _wanted(order: OrderIn, errors: list[dict[str, str]]) -> dict[uuid.UUID, int]:
    """item -> quantity; a product listed twice is an error (the quantity says how many)."""
    wanted: dict[uuid.UUID, int] = {}
    for index, line in enumerate(order.lines):
        if line.item_id in wanted:
            errors.append({"field": f"lines[{index}].item_id", "code": "duplicate"})
        else:
            wanted[line.item_id] = line.quantity
    return wanted


def _order_lines(
    db: Session,
    school: PublicSchool,
    campaign_id: uuid.UUID,
    order: OrderIn,
    errors: list[dict[str, str]],
) -> list[dict[str, Any]]:
    """The lines to buy with the CURRENT name and price of each product, or the errors (a product
    that is not on sale, a quantity over the limit of the product)."""
    wanted = _wanted(order, errors)
    rows = {
        row["id"]: row
        for row in db.execute(
            text(
                "SELECT id, name, price_cents, max_per_order FROM campaign_items "
                "WHERE campaign_id = :campaign AND school_id = :school AND is_active "
                "AND id = ANY(:ids)"
            ),
            {"campaign": campaign_id, "school": school.school_id, "ids": list(wanted)},
        )
        .mappings()
        .all()
    }
    lines: list[dict[str, Any]] = []
    for index, line in enumerate(order.lines):
        row = rows.get(line.item_id)
        if row is None:
            errors.append({"field": f"lines[{index}].item_id", "code": "unavailable"})
        elif row["max_per_order"] is not None and line.quantity > row["max_per_order"]:
            errors.append({"field": f"lines[{index}].quantity", "code": "over_limit"})
        elif line.item_id in wanted:
            lines.append(
                {
                    "item_id": line.item_id,
                    "name": row["name"],
                    "unit_price_cents": int(row["price_cents"]),
                    "quantity": line.quantity,
                }
            )
    return lines


def create_order(
    db: Session,
    settings: ApiSettings,
    school: PublicSchool,
    campaign_id: uuid.UUID,
    key: uuid.UUID,
    order: OrderIn,
) -> tuple[str, ContributionState]:
    """The order (a PENDING_PAYMENT contribution of the campaign) and its first Pix charge. The
    same Idempotency-Key answers with the same order; the same key with another cart is a
    conflict. The total is the sum of the prices the SERVER read."""
    token = service.receipt_token(settings, school.school_id, key)
    existing = service.existing_contribution(db, school, key)
    if existing is None:
        campaign = open_campaign(db, school, campaign_id)
        if campaign is None:
            raise service.not_found()
        errors: list[dict[str, str]] = []
        values = service.identification_values(school, order, errors)
        lines = _order_lines(db, school, campaign_id, order, errors)
        total = sum(line["unit_price_cents"] * line["quantity"] for line in lines)
        if not errors and not MIN_ORDER_CENTS <= total <= MAX_ORDER_CENTS:
            errors.append({"field": "lines", "code": "total_out_of_range"})
        service.refuse(errors)
        try:
            transaction_id = service.insert_contribution(
                db,
                school,
                key,
                token,
                total,
                values,
                category_key=CATEGORY_KEY,
                campaign_id=campaign_id,
            )
        except IntegrityError:
            db.rollback()  # lost a race with the same key: answer with the winner
            existing = service.existing_contribution(db, school, key)
            if existing is None:
                raise
        else:
            _insert_items(db, school, campaign_id, transaction_id, lines)
            service.open_charge(db, settings, school, transaction_id, total)
            return token, service.read_state(db, transaction_id)
    _same_order(db, school, existing, campaign_id, order)
    return token, service.read_state(db, existing)


def _insert_items(
    db: Session,
    school: PublicSchool,
    campaign_id: uuid.UUID,
    transaction_id: uuid.UUID,
    lines: list[dict[str, Any]],
) -> None:
    try:
        for line in lines:
            db.execute(
                text(
                    "INSERT INTO contribution_items (organization_id, school_id, transaction_id, "
                    "campaign_id, campaign_item_id, item_name, unit_price_cents, quantity) "
                    "VALUES (:org, :school, :tx, :campaign, :item, :name, :price, :quantity)"
                ),
                {
                    "org": school.organization_id,
                    "school": school.school_id,
                    "tx": transaction_id,
                    "campaign": campaign_id,
                    "item": line["item_id"],
                    "name": line["name"],
                    "price": line["unit_price_cents"],
                    "quantity": line["quantity"],
                },
            )
    except IntegrityError:
        # The database refused a copy that is not the current name and price of a product on sale:
        # somebody changed the product between our reading and our writing. Nothing was kept.
        db.rollback()
        raise ProblemError(
            409, "campaign_changed", "The campaign changed while you were ordering: review the cart"
        ) from None


def _same_order(
    db: Session,
    school: PublicSchool,
    transaction_id: uuid.UUID,
    campaign_id: uuid.UUID,
    order: OrderIn,
) -> None:
    """A repeated POST with the same key must be the SAME cart: the same campaign, the same
    products, the same quantities. Anything else is a reused key."""
    row = db.execute(
        text("SELECT campaign_id FROM contributions WHERE transaction_id = :tx AND school_id = :s"),
        {"tx": transaction_id, "s": school.school_id},
    ).one()
    bought: dict[uuid.UUID, int] = {
        found[0]: int(found[1])
        for found in db.execute(
            text(
                "SELECT campaign_item_id, quantity FROM contribution_items "
                "WHERE transaction_id = :tx AND school_id = :s"
            ),
            {"tx": transaction_id, "s": school.school_id},
        ).all()
    }
    wanted: dict[uuid.UUID, int] = {}
    for line in order.lines:
        wanted[line.item_id] = wanted.get(line.item_id, 0) + line.quantity
    if row[0] != campaign_id or bought != wanted:
        raise ProblemError(
            409, "idempotency_key_reused", "That Idempotency-Key was used for another order"
        )
