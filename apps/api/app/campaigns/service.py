"""The rules of the campaigns the management writes: who may do what, in which state.

The database enforces the states (the edges, the final state, what never changes), the prices and
what an order may copy; this layer decides what the database cannot know (a campaign goes on sale
with a product, a date is not in the past) and answers with a stable `code`. `database_rules` is the
net under it, for a race or a rule nobody foresaw.

Every function takes the `SchoolScope` of the request (organization, school and user come from the
session) and commits its own transaction.
"""

import hashlib
import uuid
from typing import Any, BinaryIO

from sqlalchemy.orm import Session

from app.campaigns import repository
from app.campaigns.schemas import (
    CampaignCreate,
    CampaignDetail,
    CampaignList,
    CampaignPatch,
    CampaignSummary,
    ItemCreate,
    ItemOut,
    ItemPatch,
)
from app.core.errors import ProblemError
from app.expenses.access import SchoolScope, not_found
from app.expenses.attachment_types import HEAD_BYTES, sniff
from app.expenses.db_errors import database_rules
from app.storage import AttachmentStore
from app.storage.base import CHUNK_SIZE
from app.storage.image_clean import ImageRejected, clean_image
from app.storage.uploads import discard

Row = repository.Row

IMAGE_TYPES = ("image/png", "image/jpeg", "image/webp")
MAX_IMAGE_BYTES = 5 * 1024 * 1024  # the database refuses more (`size_range`)
MAX_ITEMS_PER_CAMPAIGN = 50


def invalid_field(field: str, code: str) -> ProblemError:
    """A 422 shaped like the validation errors of the framework: the field and a fixed code."""
    return ProblemError(
        422, "validation_error", "Invalid request", errors=[{"field": field, "code": code}]
    )


def _invalid_state(status: str) -> ProblemError:
    return ProblemError(
        409,
        "invalid_state",
        "The campaign is in a state that does not allow this",
        detail=f"The campaign is {status}.",
    )


# --- reading --------------------------------------------------------------------------------------


def _summary(row: Row) -> CampaignSummary:
    return CampaignSummary.model_validate(dict(row))


def _detail(db: Session, scope: SchoolScope, row: Row) -> CampaignDetail:
    items = [
        ItemOut.model_validate(dict(item))
        for item in repository.items_of(db, scope.school_id, row["id"])
    ]
    return CampaignDetail.model_validate({**dict(row), "items": items})


def _fetch(db: Session, scope: SchoolScope, campaign_id: uuid.UUID) -> Row:
    """The campaign of the school, or the one 404 (unknown, or of another school)."""
    rows = repository.search_campaigns(db, scope.school_id, campaign_id=campaign_id)
    if not rows:
        raise not_found()
    return rows[0]


def _load_for_update(db: Session, scope: SchoolScope, campaign_id: uuid.UUID) -> Row:
    """The same, but holding the lock of the row, and read again after waiting for it."""
    _fetch(db, scope, campaign_id)
    if not repository.lock_campaign(db, scope.school_id, campaign_id):
        raise not_found()
    return _fetch(db, scope, campaign_id)


def get_campaign(db: Session, scope: SchoolScope, campaign_id: uuid.UUID) -> CampaignDetail:
    return _detail(db, scope, _fetch(db, scope, campaign_id))


def list_campaigns(db: Session, scope: SchoolScope, *, status: str | None) -> CampaignList:
    rows = repository.search_campaigns(db, scope.school_id, status=status)
    return CampaignList(items=[_summary(row) for row in rows])


# --- writing --------------------------------------------------------------------------------------


def _audit(
    db: Session, scope: SchoolScope, campaign_id: uuid.UUID, action: str, **data: Any
) -> None:
    repository.audit_event(
        db,
        organization_id=scope.organization_id,
        school_id=scope.school_id,
        action=action,
        campaign_id=campaign_id,
        data=data,
    )


def _check_dates(starts_on: Any, ends_on: Any) -> None:
    if starts_on is not None and ends_on is not None and starts_on > ends_on:
        raise invalid_field("ends_on", "before_start")


def create_campaign(db: Session, scope: SchoolScope, body: CampaignCreate) -> CampaignDetail:
    """Always a DRAFT: nothing is on sale until the management says so."""
    _check_dates(body.starts_on, body.ends_on)
    with database_rules(db):
        campaign_id = repository.insert_campaign(
            db,
            organization_id=scope.organization_id,
            school_id=scope.school_id,
            created_by_user_id=scope.user_id,
            title=body.title,
            description=body.description,
            starts_on=body.starts_on,
            ends_on=body.ends_on,
        )
        _audit(db, scope, campaign_id, "campaign.created", status="DRAFT")
        db.commit()
    return get_campaign(db, scope, campaign_id)


def update_campaign(
    db: Session, scope: SchoolScope, campaign_id: uuid.UUID, body: CampaignPatch
) -> CampaignDetail:
    sent = body.model_fields_set
    if not sent:
        raise invalid_field("body", "empty")
    if "title" in sent and body.title is None:
        raise invalid_field("title", "required")
    with database_rules(db):
        row = _load_for_update(db, scope, campaign_id)
        if row["status"] == "ENDED":
            raise _invalid_state(row["status"])
        changes = {name: getattr(body, name) for name in sent}
        _check_dates(
            changes.get("starts_on", row["starts_on"]), changes.get("ends_on", row["ends_on"])
        )
        repository.update_campaign(db, scope.school_id, campaign_id, changes)
        _audit(db, scope, campaign_id, "campaign.updated", fields=sorted(changes))
        db.commit()
    return get_campaign(db, scope, campaign_id)


def activate(db: Session, scope: SchoolScope, campaign_id: uuid.UUID) -> CampaignDetail:
    """DRAFT to ACTIVE: needs a product that is switched on, and an end date that is not past."""
    with database_rules(db):
        row = _load_for_update(db, scope, campaign_id)
        if row["status"] != "DRAFT":
            raise _invalid_state(row["status"])
        if repository.count_active_items(db, scope.school_id, campaign_id) == 0:
            raise ProblemError(
                409, "campaign_needs_a_product", "Add a product before putting it on sale"
            )
        if row["ends_on"] is not None and row["ends_on"] < repository.today_in_school(
            db, scope.school_id
        ):
            raise invalid_field("ends_on", "in_the_past")
        if not repository.set_status(db, scope.school_id, campaign_id, "ACTIVE", "DRAFT"):
            raise _invalid_state(row["status"])
        _audit(db, scope, campaign_id, "campaign.activated", status="ACTIVE")
        db.commit()
    return get_campaign(db, scope, campaign_id)


def end(db: Session, scope: SchoolScope, campaign_id: uuid.UUID) -> CampaignDetail:
    """DRAFT or ACTIVE to ENDED: final. Orders already made are untouched."""
    with database_rules(db):
        row = _load_for_update(db, scope, campaign_id)
        if row["status"] == "ENDED":
            raise _invalid_state(row["status"])
        if not repository.set_status(db, scope.school_id, campaign_id, "ENDED", row["status"]):
            raise _invalid_state(row["status"])
        _audit(db, scope, campaign_id, "campaign.ended", status="ENDED")
        db.commit()
    return get_campaign(db, scope, campaign_id)


# --- products -------------------------------------------------------------------------------------


def add_item(
    db: Session, scope: SchoolScope, campaign_id: uuid.UUID, body: ItemCreate
) -> CampaignDetail:
    with database_rules(db):
        row = _load_for_update(db, scope, campaign_id)
        if row["status"] == "ENDED":
            raise _invalid_state(row["status"])
        if repository.count_items(db, scope.school_id, campaign_id) >= MAX_ITEMS_PER_CAMPAIGN:
            raise ProblemError(409, "item_limit", "The campaign has too many products")
        item_id = repository.insert_item(
            db,
            organization_id=scope.organization_id,
            school_id=scope.school_id,
            campaign_id=campaign_id,
            name=body.name,
            description=body.description,
            price_cents=body.price_cents,
            max_per_order=body.max_per_order,
            position=body.position,
        )
        _audit(db, scope, campaign_id, "campaign.item_added", item_id=str(item_id))
        db.commit()
    return get_campaign(db, scope, campaign_id)


def update_item(
    db: Session, scope: SchoolScope, campaign_id: uuid.UUID, item_id: uuid.UUID, body: ItemPatch
) -> CampaignDetail:
    """A price or a name changed here never touches an order already made (it holds a copy)."""
    sent = body.model_fields_set
    if not sent:
        raise invalid_field("body", "empty")
    for required in ("name", "price_cents", "position", "is_active"):
        if required in sent and getattr(body, required) is None:
            raise invalid_field(required, "required")
    with database_rules(db):
        row = _load_for_update(db, scope, campaign_id)
        if row["status"] == "ENDED":
            raise _invalid_state(row["status"])
        if repository.lock_item(db, scope.school_id, campaign_id, item_id) is None:
            raise not_found()
        changes = {name: getattr(body, name) for name in sent}
        repository.update_item(db, scope.school_id, campaign_id, item_id, changes)
        _audit(
            db, scope, campaign_id, "campaign.item_updated", item_id=str(item_id),
            fields=sorted(changes),
        )  # fmt: skip
        db.commit()
    return get_campaign(db, scope, campaign_id)


# --- pictures -------------------------------------------------------------------------------------


def _read_image(stream: BinaryIO, max_bytes: int) -> tuple[str, bytes]:
    """The type (from the bytes) and the whole file, bounded: a picture is at most a few MiB."""
    head = stream.read(max(CHUNK_SIZE, HEAD_BYTES))
    if not head:
        raise invalid_field("file", "empty")
    kind = sniff(head)
    if kind is None or kind.content_type not in IMAGE_TYPES:
        raise ProblemError(
            415, "attachment_type_not_allowed", "Only pictures (PNG, JPEG, WebP) are accepted"
        )
    data = head + stream.read(max_bytes + 1 - len(head))
    if len(data) > max_bytes:
        raise ProblemError(413, "payload_too_large", "The file is larger than the limit")
    return kind.content_type, data


def set_image(
    db: Session,
    scope: SchoolScope,
    store: AttachmentStore,
    campaign_id: uuid.UUID,
    item_id: uuid.UUID | None,
    *,
    stream: BinaryIO,
    max_bytes: int,
) -> CampaignDetail:
    """The cover (`item_id` None) or the picture of a product. The metadata of the photo is
    removed BEFORE it is stored (it will be public); a file that is not a well formed picture is
    refused. The file is written first and the row after: if the row fails the file is removed;
    the old picture is removed after the commit."""
    content_type, raw = _read_image(stream, min(max_bytes, MAX_IMAGE_BYTES))
    try:
        cleaned = clean_image(content_type, raw)
    except ImageRejected as error:
        raise invalid_field("file", str(error)) from None
    key = f"{scope.organization_id}/{scope.school_id}/campaigns/{campaign_id}/{uuid.uuid4().hex}"
    sha256 = hashlib.sha256(cleaned).hexdigest()
    old_key: str | None = None
    with database_rules(db):
        row = _load_for_update(db, scope, campaign_id)
        if row["status"] == "ENDED":
            raise _invalid_state(row["status"])
        if item_id is None:
            current = repository.campaign_image(db, scope.school_id, campaign_id)
        else:
            if repository.lock_item(db, scope.school_id, campaign_id, item_id) is None:
                raise not_found()
            current = repository.item_image(db, scope.school_id, campaign_id, item_id)
        old_key = None if current is None else current["storage_key"]
        store.put(key, [cleaned])
        try:
            if item_id is None:
                repository.set_cover(
                    db, scope.school_id, campaign_id, storage_key=key,
                    content_type=content_type, size_bytes=len(cleaned), sha256=sha256,
                )  # fmt: skip
            else:
                repository.set_item_image(
                    db, scope.school_id, campaign_id, item_id, storage_key=key,
                    content_type=content_type, size_bytes=len(cleaned), sha256=sha256,
                )  # fmt: skip
            _audit(
                db, scope, campaign_id, "campaign.image_set",
                item_id=None if item_id is None else str(item_id), size_bytes=len(cleaned),
            )  # fmt: skip
        except BaseException:
            discard(store, key)
            raise
        db.commit()  # a failure HERE keeps the new file (a file without a row is the lesser evil)
    if old_key is not None:
        discard(store, old_key)
    return get_campaign(db, scope, campaign_id)


def clear_image(
    db: Session,
    scope: SchoolScope,
    store: AttachmentStore,
    campaign_id: uuid.UUID,
    item_id: uuid.UUID | None,
) -> CampaignDetail:
    old_key: str | None = None
    with database_rules(db):
        row = _load_for_update(db, scope, campaign_id)
        if row["status"] == "ENDED":
            raise _invalid_state(row["status"])
        if item_id is None:
            current = repository.campaign_image(db, scope.school_id, campaign_id)
        else:
            if repository.lock_item(db, scope.school_id, campaign_id, item_id) is None:
                raise not_found()
            current = repository.item_image(db, scope.school_id, campaign_id, item_id)
        if current is not None:
            old_key = current["storage_key"]
            if item_id is None:
                repository.set_cover(
                    db, scope.school_id, campaign_id, storage_key=None,
                    content_type=None, size_bytes=None, sha256=None,
                )  # fmt: skip
            else:
                repository.set_item_image(
                    db, scope.school_id, campaign_id, item_id, storage_key=None,
                    content_type=None, size_bytes=None, sha256=None,
                )  # fmt: skip
            _audit(
                db, scope, campaign_id, "campaign.image_cleared",
                item_id=None if item_id is None else str(item_id),
            )  # fmt: skip
        db.commit()
    if old_key is not None:
        discard(store, old_key)
    return get_campaign(db, scope, campaign_id)


def image_for_download(
    db: Session, scope: SchoolScope, campaign_id: uuid.UUID, item_id: uuid.UUID | None
) -> Row:
    """The picture, for the management (to see a draft too); the 404 when there is none."""
    _fetch(db, scope, campaign_id)
    image = (
        repository.campaign_image(db, scope.school_id, campaign_id)
        if item_id is None
        else repository.item_image(db, scope.school_id, campaign_id, item_id)
    )
    if image is None:
        raise not_found()
    return image
