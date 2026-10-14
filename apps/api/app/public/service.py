"""The public contribution flow, step by step (ADR-010, ADR-011, ADR-018).

Nobody is logged in here, so the tenant is found in two moves: a narrow SECURITY DEFINER function
turns a slug (or a receipt token) into the school, and then the session is bound to that school and
everything else runs as `apm_app` under row level security with the actor PUBLIC. Nothing that
answers "does this exist?" differs between an unknown, an expired and a foreign value.
"""

import hashlib
import math
import re
import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any, NoReturn

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth.ratelimit import AttemptKeys, attempt_keys, blocked_for, record_attempt
from app.auth.tokens import b64url, keyed_digest, looks_like_a_token
from app.contributions.expiry import expire_charges, expire_contribution
from app.core.config import ApiSettings
from app.core.errors import ProblemError
from app.pix.provider import ChargeTarget, get_provider
from app.public.schemas import ContributionIn, Identification

FIELD_NAMES = (
    "guardian_name",
    "student_name",
    "class_name",
    "contributor_email",
    "contributor_phone",
)
RECEIPT_DAYS = 30
CREATIONS_PER_WINDOW = 30  # new contributions per client address
CREATION_WINDOW_SECONDS = 15 * 60

_SLUG = re.compile(r"[a-z0-9][a-z0-9-]{0,79}")
_EMAIL = re.compile(r"[^@\s]+@[^@\s]+")
_PHONE = re.compile(r"[0-9 ()+.-]{1,30}")


def not_found() -> ProblemError:
    """The one answer for an unknown, expired, foreign or malformed school, token or receipt."""
    return ProblemError(404, "not_found", "Not found")


@dataclass(frozen=True)
class PublicSchool:
    organization_id: uuid.UUID
    school_id: uuid.UUID
    slug: str
    name: str
    accent_color: str
    accent_contrast_color: str
    suggested_amounts_cents: list[int]
    allow_custom_amount: bool
    min_amount_cents: int
    max_amount_cents: int
    required_fields: list[str]
    optional_fields: list[str]

    def identification(self) -> dict[str, str]:
        return {
            name: "REQUIRED"
            if name in self.required_fields
            else "OPTIONAL"
            if name in self.optional_fields
            else "HIDDEN"
            for name in FIELD_NAMES
        }


@dataclass(frozen=True)
class ContributionRef:
    organization_id: uuid.UUID
    school_id: uuid.UUID
    transaction_id: uuid.UUID


@dataclass(frozen=True)
class ChargeState:
    status: str
    amount_cents: int
    emv_payload: str | None
    expires_at: datetime


@dataclass(frozen=True)
class ContributionState:
    status: str
    amount_cents: int
    charge: ChargeState | None


# --- the two lookups without a tenant ------------------------------------------------------------


def resolve_school(db: Session, slug: str) -> PublicSchool | None:
    if not _SLUG.fullmatch(slug):
        return None
    row = db.execute(
        text("SELECT * FROM public.resolve_school_public(:slug)"), {"slug": slug}
    ).one_or_none()
    return None if row is None else PublicSchool(**row._mapping)


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def resolve_contribution(db: Session, token: str) -> ContributionRef | None:
    if not looks_like_a_token(token):
        return None
    row = db.execute(
        text("SELECT * FROM public.resolve_receipt(:hash)"), {"hash": token_hash(token)}
    ).one_or_none()
    return None if row is None else ContributionRef(**row._mapping)


def receipt_token(settings: ApiSettings, school_id: uuid.UUID, key: uuid.UUID) -> str:
    """The token of a contribution is derived from the Idempotency-Key, so replaying the same POST
    answers with the same token without the server ever storing it (only its hash is stored)."""
    return b64url(keyed_digest(settings.auth_secret, "receipt-token", f"{school_id}|{key}"))


# --- limits ---------------------------------------------------------------------------------------


def _too_many(wait: int) -> ProblemError:
    return ProblemError(
        429,
        "rate_limited",
        "Too many attempts, try again later",
        headers={"Retry-After": str(max(1, wait))},
    )


def guard_creation(db: Session, settings: ApiSettings, ip: str) -> None:
    """At most CREATIONS_PER_WINDOW new contributions per client address in the window."""
    keys = attempt_keys(settings.auth_secret, ip, ip)
    # One request of this address at a time, so the count and the insert cannot interleave.
    db.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 1))"),
        {"key": "public_contribution" + keys.ip.hex()},
    )
    row = db.execute(
        text(
            "SELECT count(*), extract(epoch FROM now() - min(attempted_at)) FROM login_attempts "
            "WHERE kind = 'public_contribution' AND ip_hmac = :ip "
            "AND attempted_at > now() - make_interval(secs => :window)"
        ),
        {"ip": keys.ip, "window": CREATION_WINDOW_SECONDS},
    ).one()
    if row[0] >= CREATIONS_PER_WINDOW:
        raise _too_many(math.ceil(CREATION_WINDOW_SECONDS - float(row[1] or 0)))
    record_attempt(db, "public_contribution", keys, succeeded=False)
    # Committed on its own: a later 422 or 409 must not take the attempt back.
    db.commit()


def guard_token_guessing(db: Session, settings: ApiSettings, ip: str) -> AttemptKeys:
    """Unknown tokens count against the client address (the token is a 256-bit secret, but nobody
    should be able to try them for free)."""
    keys = attempt_keys(settings.auth_secret, ip, ip)
    wait = blocked_for(db, "public_token", keys)
    if wait:
        db.commit()
        raise _too_many(wait)
    return keys


def fail_lookup(db: Session, keys: AttemptKeys) -> NoReturn:
    record_attempt(db, "public_token", keys, succeeded=False)
    db.commit()
    raise not_found()


# --- validating what the family sent --------------------------------------------------------------


def field_problem(name: str, value: str) -> str | None:
    if name == "contributor_email":
        return None if _EMAIL.fullmatch(value) else "invalid"
    if name == "contributor_phone":
        return None if _PHONE.fullmatch(value) else "invalid"
    return None if 1 <= len(value) <= 120 else "invalid"


def identification_values(
    school: PublicSchool, data: Identification, errors: list[dict[str, str]]
) -> dict[str, str]:
    """The identification to store: only what the school asks for, trimmed, and valid. A required
    field that is missing, or one that is malformed, is added to `errors` (a code per field)."""
    allowed = set(school.required_fields) | set(school.optional_fields)
    values: dict[str, str] = {}
    for name in FIELD_NAMES:
        if name not in allowed:
            continue  # the school does not ask for it: it is never stored
        raw: str | None = getattr(data, name)
        value = raw.strip() if raw else ""
        if not value:
            if name in school.required_fields:
                errors.append({"field": name, "code": "required"})
            continue
        problem = field_problem(name, value)
        if problem is not None:
            errors.append({"field": name, "code": problem})
            continue
        values[name] = value
    return values


def refuse(errors: list[dict[str, str]]) -> None:
    """Answer the 422 with a code per field, when there is any error."""
    if errors:
        raise ProblemError(422, "validation_error", "Invalid request", errors=errors)


def school_today(db: Session, school: PublicSchool) -> date:
    """Today in the time zone of the school (the month of a contribution is the school's month)."""
    today: date = db.execute(
        text(
            "SELECT (now() AT TIME ZONE timezone)::date FROM school_settings WHERE school_id = :s"
        ),
        {"s": school.school_id},
    ).scalar_one()
    return today


def free_amount_text(db: Session, school: PublicSchool) -> str | None:
    """The sentence the school wrote for the family next to the free amount (the settings table is
    read inside the school: the narrow function that finds the school does not carry it)."""
    text_value: str | None = db.execute(
        text("SELECT free_amount_text FROM school_settings WHERE school_id = :s"),
        {"s": school.school_id},
    ).scalar_one_or_none()
    return text_value


def offered_months(today: date) -> list[date]:
    """The months a contribution can be for: the current one and the eleven before it, oldest first
    (the first day of each)."""
    months: list[date] = []
    year, month = today.year, today.month
    for _ in range(12):
        months.append(date(year, month, 1))
        year, month = (year, month - 1) if month > 1 else (year - 1, 12)
    return list(reversed(months))


def reference_month_value(
    db: Session, school: PublicSchool, raw: str | None, errors: list[dict[str, str]]
) -> date | None:
    """The first day of the month the family chose, or None when it chose none. A month the server
    does not offer is an error: a contribution is never "for" a year ago or for next year."""
    if raw is None:
        return None
    chosen = date(int(raw[:4]), int(raw[5:7]), 1)
    if chosen not in offered_months(school_today(db, school)):
        errors.append({"field": "reference_month", "code": "out_of_range"})
        return None
    return chosen


def clean_input(school: PublicSchool, data: ContributionIn) -> dict[str, str]:
    """The identification to store: only what the school asks for, trimmed, and valid. Raises the
    422 with a code per field when the amount or a required field is wrong."""
    errors: list[dict[str, str]] = []
    if not school.min_amount_cents <= data.amount_cents <= school.max_amount_cents:
        errors.append({"field": "amount_cents", "code": "out_of_range"})
    elif not school.allow_custom_amount and data.amount_cents not in school.suggested_amounts_cents:
        errors.append({"field": "amount_cents", "code": "not_suggested"})
    values = identification_values(school, data, errors)
    refuse(errors)
    return values


# --- reading and writing as apm_app, inside the school -------------------------------------------


def read_state(db: Session, transaction_id: uuid.UUID) -> ContributionState:
    expire_charges(db, transaction_id=transaction_id)
    expire_contribution(db, transaction_id)
    contribution = db.execute(
        text("SELECT status, amount_cents FROM financial_transactions WHERE id = :tx"),
        {"tx": transaction_id},
    ).one()
    charge = db.execute(
        text(
            "SELECT status, amount_cents, emv_payload, expires_at FROM pix_charges "
            "WHERE transaction_id = :tx ORDER BY created_at DESC, id DESC LIMIT 1"
        ),
        {"tx": transaction_id},
    ).one_or_none()
    return ContributionState(
        contribution[0],
        contribution[1],
        None if charge is None else ChargeState(*charge),
    )


def open_charge(
    db: Session,
    settings: ApiSettings,
    school: PublicSchool,
    transaction_id: uuid.UUID,
    amount_cents: int,
) -> None:
    """Ask the provider for a dynamic charge on the ACTIVE account of the school and record it."""
    account = db.execute(
        text(
            "SELECT id, provider FROM payment_accounts WHERE school_id = :s AND status = 'ACTIVE'"
        ),
        {"s": school.school_id},
    ).one_or_none()
    if account is None:
        raise ProblemError(409, "payment_unavailable", "This school cannot receive Pix right now")
    txid = uuid.uuid4().hex
    created = get_provider(account[1], settings.env).create_charge(
        ChargeTarget(school.organization_id, school.school_id, account[0]),
        txid=txid,
        amount_cents=amount_cents,
        expires_at=_expiry(db, school),
    )
    db.execute(
        text(
            "INSERT INTO pix_charges (transaction_id, organization_id, school_id, "
            "payment_account_id, provider, txid, status, amount_cents, expires_at, emv_payload) "
            "VALUES (:tx, :org, :school, :account, :provider, :txid, 'PENDING', :amount, "
            ":expires, :emv)"
        ),
        {
            "tx": transaction_id,
            "org": school.organization_id,
            "school": school.school_id,
            "account": account[0],
            "provider": account[1],
            "txid": created.txid,
            "amount": amount_cents,
            "expires": created.expires_at,
            "emv": created.emv_payload,
        },
    )


def _expiry(db: Session, school: PublicSchool) -> datetime:
    minutes: Any = db.execute(
        text("SELECT pix_expiration_minutes FROM school_settings WHERE school_id = :s"),
        {"s": school.school_id},
    ).scalar_one()
    return datetime.now(UTC) + timedelta(minutes=int(minutes))


def create_contribution(
    db: Session,
    settings: ApiSettings,
    school: PublicSchool,
    key: uuid.UUID,
    data: ContributionIn,
) -> tuple[str, ContributionState]:
    """The contribution (PENDING_PAYMENT) and its first charge. The same Idempotency-Key answers
    with the same contribution; the same key with another amount is a conflict."""
    token = receipt_token(settings, school.school_id, key)
    existing = existing_contribution(db, school, key)
    if existing is None:
        values = clean_input(school, data)
        month_errors: list[dict[str, str]] = []
        reference_month = reference_month_value(db, school, data.reference_month, month_errors)
        refuse(month_errors)
        try:
            transaction_id = insert_contribution(
                db, school, key, token, data.amount_cents, values, reference_month=reference_month
            )
        except IntegrityError:
            db.rollback()  # lost a race with the same key: answer with the winner
            existing = existing_contribution(db, school, key)
            if existing is None:
                raise
        else:
            open_charge(db, settings, school, transaction_id, data.amount_cents)
            return token, read_state(db, transaction_id)
    state = read_state(db, existing)
    if state.amount_cents != data.amount_cents:
        raise ProblemError(
            409, "idempotency_key_reused", "That Idempotency-Key was used for another amount"
        )
    return token, state


def existing_contribution(db: Session, school: PublicSchool, key: uuid.UUID) -> uuid.UUID | None:
    found = db.execute(
        text(
            "SELECT transaction_id FROM contributions WHERE school_id = :s AND idempotency_key = :k"
        ),
        {"s": school.school_id, "k": key},
    ).scalar_one_or_none()
    return None if found is None else uuid.UUID(str(found))


def insert_contribution(
    db: Session,
    school: PublicSchool,
    key: uuid.UUID,
    token: str,
    amount_cents: int,
    values: dict[str, str],
    *,
    category_key: str = "parent_contribution",
    campaign_id: uuid.UUID | None = None,
    reference_month: date | None = None,
) -> uuid.UUID:
    """The ledger row and the detail of a PENDING_PAYMENT Pix contribution. The order of a
    campaign is the same thing filed under its own category and tied to its campaign."""
    category = db.execute(
        text("SELECT id FROM categories WHERE school_id = :s AND key = :key"),
        {"s": school.school_id, "key": category_key},
    ).scalar_one_or_none()
    if category is None:
        raise ProblemError(409, "payment_unavailable", "This school cannot receive contributions")
    transaction_id = db.execute(
        text(
            "INSERT INTO financial_transactions (organization_id, school_id, kind, direction, "
            "amount_cents, status, category_id, origin_type, occurred_at) "
            "VALUES (:org, :school, 'CONTRIBUTION', 'IN', :amount, 'PENDING_PAYMENT', :category, "
            "'GUARDIAN', now()) RETURNING id"
        ),
        {
            "org": school.organization_id,
            "school": school.school_id,
            "amount": amount_cents,
            "category": category,
        },
    ).scalar_one()
    params: dict[str, Any] = {name: values.get(name) for name in FIELD_NAMES}
    db.execute(
        text(
            "INSERT INTO contributions (transaction_id, organization_id, school_id, method, "
            "guardian_name, student_name, class_name, contributor_email, contributor_phone, "
            "receipt_token_hash, receipt_expires_at, idempotency_key, campaign_id, "
            "reference_month) "
            "VALUES (:tx, :org, :school, 'PIX', :guardian_name, :student_name, :class_name, "
            ":contributor_email, :contributor_phone, :hash, "
            "now() + make_interval(days => :days), :key, :campaign, :reference_month)"
        ),
        {
            **params,
            "tx": transaction_id,
            "org": school.organization_id,
            "school": school.school_id,
            "hash": token_hash(token),
            "days": RECEIPT_DAYS,
            "key": key,
            "campaign": campaign_id,
            "reference_month": reference_month,
        },
    )
    return uuid.UUID(str(transaction_id))


def renew_charge(
    db: Session, settings: ApiSettings, school: PublicSchool, ref: ContributionRef
) -> ContributionState:
    """A new charge when the previous one expired and the family still wants to pay. While a
    charge is PENDING there is only that one (no duplicated request)."""
    # Two requests renewing at once would each ask the provider for a charge and only one row fits:
    # the loser would leave a payable charge nobody recorded. The lock makes the second one wait
    # and find the charge of the first.
    db.execute(
        text("SELECT id FROM financial_transactions WHERE id = :tx FOR UPDATE"),
        {"tx": ref.transaction_id},
    )
    state = read_state(db, ref.transaction_id)
    if state.status != "PENDING_PAYMENT":
        raise ProblemError(409, "contribution_closed", "This contribution is no longer waiting")
    if state.charge is not None and state.charge.status == "PENDING":
        return state
    try:
        open_charge(db, settings, school, ref.transaction_id, state.amount_cents)
    except IntegrityError:
        db.rollback()  # another request opened it first
    return read_state(db, ref.transaction_id)


def read_receipt(db: Session, school: PublicSchool, ref: ContributionRef) -> dict[str, Any]:
    row = db.execute(
        text(
            "SELECT f.status, f.amount_cents, f.settled_at, f.reference_code, c.method, "
            "c.reference_month "
            "FROM financial_transactions f JOIN contributions c ON c.transaction_id = f.id "
            "WHERE f.id = :tx"
        ),
        {"tx": ref.transaction_id},
    ).one()
    if row[0] != "PAID" or row[2] is None:
        raise ProblemError(409, "payment_not_confirmed", "The payment is not confirmed yet")
    campaign_title = db.execute(
        text(
            "SELECT c.title FROM contributions o JOIN campaigns c ON c.id = o.campaign_id "
            "AND c.school_id = o.school_id WHERE o.transaction_id = :tx AND o.school_id = :s"
        ),
        {"tx": ref.transaction_id, "s": school.school_id},
    ).scalar_one_or_none()
    lines = db.execute(
        text(
            "SELECT i.item_name, i.unit_price_cents, i.quantity FROM contribution_items i "
            "JOIN campaign_items p ON p.id = i.campaign_item_id AND p.school_id = i.school_id "
            "WHERE i.transaction_id = :tx AND i.school_id = :s "
            "ORDER BY p.position, p.created_at, i.id"
        ),
        {"tx": ref.transaction_id, "s": school.school_id},
    ).all()
    return {
        "status": "PAID",
        "reference_code": f"APM-{int(row[3]):06d}",
        "amount_cents": row[1],
        "paid_at": row[2],
        "school_name": school.name,
        "method": row[4],
        "reference_month": None if row[5] is None else row[5].strftime("%Y-%m"),
        "campaign_title": campaign_title,
        "items": [
            {"name": line[0], "unit_price_cents": line[1], "quantity": line[2]} for line in lines
        ],
    }
