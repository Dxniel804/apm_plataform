"""What the management follows in a campaign: the dashboard, the orders and their delivery (0014).

Everything here is READ from the ledger and from the copy each order kept (name, price and cost at
the purchase); nothing is computed in the browser. The cost is a management metric, not a ledger
entry: the real outflow is still the expense. A delivery can only be recorded for a PAID order of
this campaign (the database refuses anything else), the change is reversible, and every change is
audited.
"""

import unicodedata
import uuid
from collections import defaultdict
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from app.campaigns import repository
from app.campaigns.report import MAX_ORDERS_IN_PDF, render_campaign_report
from app.campaigns.schemas import (
    BuyerLine,
    BuyerList,
    BuyerOut,
    CampaignDashboard,
    DeliveryChange,
    DeliveryResult,
    OrderLine,
    OrderList,
    OrderOut,
    PaymentStatus,
    SoldItem,
)
from app.core.errors import ProblemError
from app.expenses.access import SchoolScope, not_found
from app.expenses.db_errors import database_rules
from app.reports.queries import names

MAX_PAGE = 100
MAX_SEARCH = 80


def _campaign(db: Session, scope: SchoolScope, campaign_id: uuid.UUID) -> Any:
    """The campaign of the school, or the one 404 (unknown, or of another school)."""
    rows = repository.search_campaigns(db, scope.school_id, campaign_id=campaign_id)
    if not rows:
        raise not_found()
    return rows[0]


def dashboard(db: Session, scope: SchoolScope, campaign_id: uuid.UUID) -> CampaignDashboard:
    campaign = _campaign(db, scope, campaign_id)
    by_payment = {
        row["payment_status"]: row
        for row in repository.orders_by_payment(db, scope.school_id, campaign_id)
    }

    def count(status: str) -> int:
        return int(by_payment[status]["orders"]) if status in by_payment else 0

    paid_count = count("PAID")
    collected = int(by_payment["PAID"]["cents"]) if "PAID" in by_payment else 0
    delivered = repository.delivered_orders(db, scope.school_id, campaign_id)

    items = [
        SoldItem(
            item_id=row["item_id"],
            name=row["name"],
            units_sold=int(row["units_sold"]),
            revenue_cents=int(row["revenue_cents"]),
            cost_cents=None if row["cost_cents"] is None else int(row["cost_cents"]),
            cost_known=bool(row["cost_known"]),
        )
        for row in repository.sold_items(db, scope.school_id, campaign_id)
    ]
    cost = sum(item.cost_cents or 0 for item in items)
    # The profit only exists when EVERY unit sold has a cost (otherwise it would be a lie).
    complete = all(item.cost_known for item in items if item.units_sold > 0)
    return CampaignDashboard(
        campaign_id=campaign["id"],
        title=campaign["title"],
        status=campaign["status"],
        paid_orders_count=paid_count,
        pending_orders_count=count("PENDING"),
        cancelled_orders_count=count("CANCELLED"),
        collected_cents=collected,
        units_sold=sum(item.units_sold for item in items),
        cost_cents=cost,
        cost_complete=complete,
        profit_cents=collected - cost if complete else None,
        delivered_orders_count=delivered,
        to_deliver_orders_count=paid_count - delivered,
        items=items,
    )


def list_orders(
    db: Session,
    scope: SchoolScope,
    campaign_id: uuid.UUID,
    *,
    payment: PaymentStatus | None,
    delivery: str | None,
    search: str | None,
    limit: int,
    offset: int,
) -> OrderList:
    _campaign(db, scope, campaign_id)
    return _page(
        db, scope, campaign_id,
        payment=payment, delivery=delivery, search=search,
        limit=max(1, min(limit, MAX_PAGE)), offset=max(0, offset),
    )  # fmt: skip


def _page(
    db: Session,
    scope: SchoolScope,
    campaign_id: uuid.UUID,
    *,
    payment: PaymentStatus | None,
    delivery: str | None,
    search: str | None,
    limit: int,
    offset: int,
) -> OrderList:
    text = search.strip()[:MAX_SEARCH] if search else None
    text = text or None
    total = repository.count_orders(
        db, scope.school_id, campaign_id, payment=payment, delivery=delivery, search=text
    )
    rows = repository.search_orders(
        db, scope.school_id, campaign_id,
        payment=payment, delivery=delivery, search=text, limit=limit, offset=offset,
    )  # fmt: skip
    lines: dict[uuid.UUID, list[OrderLine]] = defaultdict(list)
    if rows:
        for line in repository.order_lines(db, scope.school_id, [row["order_id"] for row in rows]):
            lines[line["transaction_id"]].append(
                OrderLine(
                    item_name=line["item_name"],
                    quantity=int(line["quantity"]),
                    unit_price_cents=int(line["unit_price_cents"]),
                )
            )
    return OrderList(
        items=[
            OrderOut(
                order_id=row["order_id"],
                reference_code=int(row["reference_code"]),
                created_at=row["created_at"],
                guardian_name=row["guardian_name"],
                student_name=row["student_name"],
                class_name=row["class_name"],
                amount_cents=int(row["amount_cents"]),
                payment_status=row["payment_status"],
                delivery_status=row["delivery_status"],
                delivery_changed_at=row["delivery_changed_at"],
                lines=lines[row["order_id"]],
            )
            for row in rows
        ],
        total=total,
        limit=limit,
        offset=offset,
    )


def _same(text: str | None) -> str:
    """A name to compare: lower case, no accents, single spaces ("Ana  SOUZA" is "ana souza")."""
    folded = unicodedata.normalize("NFKD", text or "")
    return " ".join("".join(c for c in folded if not unicodedata.combining(c)).casefold().split())


def group_buyers(paid: list[OrderOut]) -> list[BuyerOut]:
    """One row per guardian and student, with what they bought of each product. The paid orders are
    given newest first, so the name kept for a buyer is the latest way it was written."""
    groups: dict[tuple[str, str, str], dict[str, Any]] = {}
    for order in paid:
        key = (_same(order.guardian_name), _same(order.student_name), _same(order.class_name))
        group = groups.setdefault(
            key,
            {
                "guardian_name": order.guardian_name,
                "student_name": order.student_name,
                "class_name": order.class_name,
                "orders": 0,
                "amount_cents": 0,
                "quantities": defaultdict(int),
            },
        )
        group["orders"] += 1
        group["amount_cents"] += order.amount_cents
        for line in order.lines:
            group["quantities"][line.item_name] += line.quantity
    rows = [
        BuyerOut(
            guardian_name=g["guardian_name"],
            student_name=g["student_name"],
            class_name=g["class_name"],
            orders=g["orders"],
            units=sum(g["quantities"].values()),
            amount_cents=g["amount_cents"],
            lines=[BuyerLine(item_name=n, quantity=q) for n, q in sorted(g["quantities"].items())],
        )
        for g in groups.values()
    ]
    rows.sort(key=lambda r: (_same(r.guardian_name) or "\uffff", _same(r.student_name)))
    return rows


def buyers(db: Session, scope: SchoolScope, campaign_id: uuid.UUID) -> BuyerList:
    """Who bought what: the paid orders of the campaign grouped by guardian and student."""
    _campaign(db, scope, campaign_id)
    page = _page(
        db, scope, campaign_id,
        payment="PAID", delivery=None, search=None, limit=MAX_ORDERS_IN_PDF, offset=0,
    )  # fmt: skip
    return BuyerList(items=group_buyers(page.items), complete=page.total <= len(page.items))


def change_delivery(
    db: Session, scope: SchoolScope, campaign_id: uuid.UUID, body: DeliveryChange
) -> DeliveryResult:
    """Mark (or unmark) the delivery of up to 100 orders at once. An id that is not a PAID order of
    this campaign is skipped, never an error: the answer is the same for a stranger's id."""
    _campaign(db, scope, campaign_id)
    wanted = list(dict.fromkeys(body.order_ids))
    if len(wanted) != len(body.order_ids):
        raise ProblemError(
            422, "validation_error", "Invalid request",
            errors=[{"field": "order_ids", "code": "duplicate"}],
        )  # fmt: skip
    with database_rules(db):
        eligible = repository.paid_orders_of_campaign(db, scope.school_id, campaign_id, wanted)
        if body.delivered:
            changed = (
                repository.mark_delivered(
                    db,
                    organization_id=scope.organization_id,
                    school_id=scope.school_id,
                    user_id=scope.user_id,
                    order_ids=eligible,
                )
                if eligible
                else 0
            )
        else:
            changed = (
                repository.mark_pending(
                    db, school_id=scope.school_id, user_id=scope.user_id, order_ids=eligible
                )
                if eligible
                else 0
            )
        if changed:
            repository.audit_event(
                db,
                organization_id=scope.organization_id,
                school_id=scope.school_id,
                action="campaign.delivery_marked" if body.delivered else "campaign.delivery_undone",
                campaign_id=campaign_id,
                data={"orders": changed},
            )
        db.commit()
    return DeliveryResult(
        changed=changed, unchanged=len(eligible) - changed, skipped=len(wanted) - len(eligible)
    )


def report_pdf(db: Session, scope: SchoolScope, campaign_id: uuid.UUID) -> bytes:
    """The PDF of the campaign: the dashboard and every order (the most recent 5000)."""
    figures = dashboard(db, scope, campaign_id)
    everything = _page(
        db, scope, campaign_id,
        payment=None, delivery=None, search=None, limit=MAX_ORDERS_IN_PDF, offset=0,
    )  # fmt: skip
    organization_name, school_name = names(db, scope.school_id)
    who_bought = buyers(db, scope, campaign_id).items
    return render_campaign_report(
        organization_name=organization_name,
        school_name=school_name,
        timezone=repository.school_timezone(db, scope.school_id),
        generated_at=datetime.now(UTC),
        dashboard=figures,
        orders=everything.items,
        buyers=who_bought,
    )
