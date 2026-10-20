"""The bank reconciliation: accounts, the import of an OFX file, and the comparison with the ledger.

Nothing here writes to the ledger. An import stores what the bank says (the lines, with the personal
data masked) and the comparison is computed each time it is read, by a pure function, from the lines
and from the ledger as it is now."""

import datetime as dt
import hashlib
import json
import uuid
from typing import BinaryIO, Literal

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import ProblemError
from app.expenses.access import SchoolScope, not_found
from app.expenses.db_errors import database_rules
from app.reconciliation import repository
from app.reconciliation.csv_statement import (
    CsvError,
    CsvProfile,
    detect,
    parse_csv,
    profile_from_dict,
)
from app.reconciliation.matcher import BankLine, Divergence, LedgerItem, pair
from app.reconciliation.ofx import MAX_BYTES, OfxError, parse_ofx
from app.reconciliation.pdf_statement import PdfError, parse_pdf
from app.reconciliation.schemas import (
    AccountCreate,
    AccountOut,
    AccountPatch,
    BankLineOut,
    ClosingBalanceItem,
    ClosingBalanceOut,
    CsvPreviewOut,
    DivergenceOut,
    ImportList,
    ImportOut,
    LedgerEntryOut,
    LineAction,
    LineActionOut,
    MatchedOut,
    ReconciliationOut,
    ResolvedOut,
    WrongAccountOut,
)

UPLOAD_MAX_BYTES = 5 * 1024 * 1024  # a PDF may be larger; OFX and CSV stay at MAX_BYTES
READ_PROBLEMS = {
    "file_too_large": (413, "payload_too_large"),
    "not_ofx": (422, "not_an_ofx_file"),
    "not_csv": (422, "not_a_csv_file"),
    "not_pdf": (422, "not_a_pdf_file"),
    "bad_line": (422, "ofx_line_unreadable"),
    "bad_profile": (422, "csv_profile_invalid"),
    "too_many_lines": (422, "ofx_too_many_lines"),
    "no_lines": (422, "ofx_without_lines"),
    "pdf_without_text": (422, "pdf_without_text"),
    "pdf_encrypted": (422, "pdf_encrypted"),
    "pdf_too_many_pages": (422, "pdf_too_many_pages"),
    "pdf_year_unknown": (422, "pdf_year_unknown"),
}


def _invalid(field: str, code: str) -> ProblemError:
    return ProblemError(
        422, "validation_error", "Invalid request", errors=[{"field": field, "code": code}]
    )


# --- accounts -------------------------------------------------------------------------------------


def list_accounts(db: Session, scope: SchoolScope) -> list[AccountOut]:
    return [AccountOut.model_validate(dict(r)) for r in repository.accounts(db, scope.school_id)]


def _account(db: Session, scope: SchoolScope, account_id: uuid.UUID) -> AccountOut:
    rows = repository.accounts(db, scope.school_id, account_id)
    if not rows:
        raise not_found()
    return AccountOut.model_validate(dict(rows[0]))


def create_account(db: Session, scope: SchoolScope, body: AccountCreate) -> AccountOut:
    with database_rules(db):
        created = repository.insert_account(
            db, organization_id=scope.organization_id, school_id=scope.school_id,
            user_id=scope.user_id, nickname=body.nickname, bank_name=body.bank_name,
            account_last4=body.account_last4, purpose=body.purpose,
        )  # fmt: skip
        db.commit()
    return _account(db, scope, created)


def update_account(
    db: Session, scope: SchoolScope, account_id: uuid.UUID, body: AccountPatch
) -> AccountOut:
    sent = body.model_fields_set
    if not sent:
        raise _invalid("body", "empty")
    for required in ("nickname", "bank_name", "purpose", "is_active"):
        if required in sent and getattr(body, required) is None:
            raise _invalid(required, "required")
    _account(db, scope, account_id)
    with database_rules(db):
        repository.update_account(
            db, scope.school_id, account_id, {n: getattr(body, n) for n in sent}
        )
        db.commit()
    return _account(db, scope, account_id)


# --- importing ------------------------------------------------------------------------------------


def _import_out(row: repository.Row) -> ImportOut:
    return ImportOut.model_validate(dict(row))


def _kind_of(data: bytes) -> Literal["OFX", "CSV", "PDF"]:
    """What the bytes are, whatever the name says: a PDF, an OFX or (anything else) a CSV."""
    if data.lstrip()[:5] == b"%PDF-":
        return "PDF"
    head = data[:4096].upper()
    if b"OFXHEADER" in head or b"<OFX" in head:
        return "OFX"
    return "CSV"


def _problem(error: OfxError | CsvError | PdfError) -> ProblemError:
    status, code = READ_PROBLEMS.get(error.code, (422, "statement_unreadable"))
    return ProblemError(status, code, "The file could not be read")


def _profile_from(raw: str | None) -> CsvProfile | None:
    if raw is None or not raw.strip():
        return None
    try:
        return profile_from_dict(json.loads(raw))
    except (json.JSONDecodeError, CsvError):
        raise ProblemError(422, "csv_profile_invalid", "The column map is not valid") from None


def _read_upload(stream: BinaryIO) -> bytes:
    data = stream.read(UPLOAD_MAX_BYTES + 1)
    if len(data) > UPLOAD_MAX_BYTES:
        raise ProblemError(413, "payload_too_large", "The file is too large")
    return data


def preview(
    db: Session, scope: SchoolScope, account_id: uuid.UUID, stream: BinaryIO
) -> CsvPreviewOut:
    """For a CSV: its first rows and the columns it looks like (nothing is stored)."""
    account = _account(db, scope, account_id)
    data = _read_upload(stream)
    kind = _kind_of(data)
    if kind != "CSV":
        return CsvPreviewOut(kind=kind, header=None, sample=[], suggested_profile=None,
                             saved_profile=None)  # fmt: skip
    if len(data) > MAX_BYTES:
        raise ProblemError(413, "payload_too_large", "The file is too large")
    try:
        header, sample, profile = detect(data)
    except CsvError as error:
        raise _problem(error) from None
    return CsvPreviewOut(
        kind="CSV", header=header, sample=sample,
        suggested_profile=None if profile is None else profile.as_dict(),
        saved_profile=account.csv_profile,
    )  # fmt: skip


def import_file(
    db: Session,
    scope: SchoolScope,
    account_id: uuid.UUID,
    stream: BinaryIO,
    profile_raw: str | None = None,
) -> ImportOut:
    """Read the file (bounded; OFX, CSV or PDF, told apart by what is inside it), refuse the same
    file twice, store the lines the bank had not sent yet. The file itself is not kept. A line from
    a PDF is stored marked for review."""
    account = _account(db, scope, account_id)
    if not account.is_active:
        raise ProblemError(409, "account_inactive", "This bank account is switched off")
    data = _read_upload(stream)
    kind = _kind_of(data)
    if kind != "PDF" and len(data) > MAX_BYTES:
        raise ProblemError(413, "payload_too_large", "The file is too large")
    explicit = _profile_from(profile_raw) if kind == "CSV" else None
    try:
        if kind == "OFX":
            statement = parse_ofx(data)
        elif kind == "PDF":
            statement = parse_pdf(data)
        else:
            profile = explicit
            if profile is None and account.csv_profile is not None:
                profile = profile_from_dict(account.csv_profile)
            if profile is None:
                profile = detect(data)[2]
            if profile is None:
                raise ProblemError(
                    422,
                    "csv_needs_mapping",
                    "Tell which column is the date, the text and the amount",
                )
            statement = parse_csv(data, profile)
    except (OfxError, CsvError, PdfError) as error:
        raise _problem(error) from None
    sha256 = hashlib.sha256(data).hexdigest()
    if repository.import_exists(db, scope.school_id, sha256):
        raise ProblemError(409, "already_imported", "This file was already imported")
    refs = list(dict.fromkeys(line.bank_ref for line in statement.lines))
    new = len(refs) - len(repository.existing_refs(db, scope.school_id, account_id, refs))
    review = kind == "PDF"
    with database_rules(db):
        import_id = repository.insert_import(
            db, organization_id=scope.organization_id, school_id=scope.school_id,
            user_id=scope.user_id, account_id=account_id, sha256=sha256,
            start=statement.period_start, end=statement.period_end, line_count=len(statement.lines),
            new_line_count=new, closing_balance_cents=statement.closing_balance_cents,
            source=kind,
        )  # fmt: skip
        for line in statement.lines:
            repository.insert_line(
                db, organization_id=scope.organization_id, school_id=scope.school_id,
                import_id=import_id, account_id=account_id, posted_on=line.posted_on,
                amount_cents=line.amount_cents, memo=line.memo, bank_ref=line.bank_ref,
                end_to_end_id=line.end_to_end_id, looks_like_fee=line.looks_like_fee,
                needs_review=review,
            )  # fmt: skip
        if explicit is not None:
            repository.set_csv_profile(
                db, scope.school_id, account_id, json.dumps(explicit.as_dict())
            )
        db.commit()
    return _import_out(repository.imports(db, scope.school_id, import_id)[0])


def list_imports(db: Session, scope: SchoolScope) -> ImportList:
    return ImportList(items=[_import_out(r) for r in repository.imports(db, scope.school_id)])


# --- comparing ------------------------------------------------------------------------------------


def _line_out(line: BankLine, memos: dict[uuid.UUID, tuple[str, bool, bool]]) -> BankLineOut:
    memo, fee, review = memos[line.line_id]
    return BankLineOut(
        line_id=line.line_id, posted_on=line.posted_on, amount_cents=line.amount_cents, memo=memo,
        end_to_end_id=line.end_to_end_id, looks_like_fee=fee, needs_review=review,
    )  # fmt: skip


def _entry_out(item: LedgerItem) -> LedgerEntryOut:
    return LedgerEntryOut(
        transaction_id=item.transaction_id, reference_code=item.reference_code, kind=item.kind,
        day=item.day, amount_cents=item.gross_cents, net_cents=item.net_cents,
    )  # fmt: skip


def _ledger(
    db: Session, scope: SchoolScope, statement: repository.Row, wallet: Literal["APM", "PDDE"]
) -> list[LedgerItem]:
    return [
        LedgerItem(
            transaction_id=r["transaction_id"],
            reference_code=int(r["reference_code"]),
            kind=r["kind"],
            day=r["day"],
            gross_cents=int(r["amount_cents"])
            if r["direction"] == "IN"
            else -int(r["amount_cents"]),
            net_cents=None if r["net_cents"] is None else int(r["net_cents"]),
            end_to_end_id=r["end_to_end_id"],
        )  # fmt: skip
        for r in repository.ledger_items(
            db, scope.school_id, statement["period_start"], statement["period_end"], wallet
        )
    ]


def compare(db: Session, scope: SchoolScope, import_id: uuid.UUID) -> ReconciliationOut:
    found = repository.imports(db, scope.school_id, import_id)
    if not found:
        raise not_found()
    statement = found[0]
    rows = repository.bank_lines(
        db,
        scope.school_id,
        statement["bank_account_id"],
        statement["period_start"],
        statement["period_end"],
    )
    memos = {
        r["line_id"]: (r["memo"], bool(r["looks_like_fee"]), bool(r["needs_review"])) for r in rows
    }
    lines = [
        BankLine(r["line_id"], r["posted_on"], int(r["amount_cents"]), r["end_to_end_id"])
        for r in rows
    ]
    # The ledger items of the wallet the account belongs to (a PDDE account: what was paid with the
    # PDDE money; any other: the APM's). The other wallet's outflows are kept apart to find the line
    # that left the wrong account.
    wallet: Literal["APM", "PDDE"] = (
        "PDDE" if _account(db, scope, statement["bank_account_id"]).purpose == "PDDE" else "APM"
    )
    other: Literal["APM", "PDDE"] = "APM" if wallet == "PDDE" else "PDDE"
    items = _ledger(db, scope, statement, wallet)
    foreign = [i for i in _ledger(db, scope, statement, other) if i.gross_cents < 0]
    result = pair(lines, items)
    decided = {
        r["line_id"]: r
        for r in repository.resolutions(db, scope.school_id, [ln.line_id for ln in lines])
    }
    left = [ln for ln in result.missing_in_system if ln.line_id not in decided]
    wrong = pair(left, foreign).matched if foreign else []
    wrong_ids = {ln.line_id for ln, _ in wrong}

    def divergence(d: Divergence) -> DivergenceOut:
        return DivergenceOut(
            line=_line_out(d.line, memos), candidates=[_entry_out(c) for c in d.candidates],
            reason=d.reason,  # type: ignore[arg-type]
        )  # fmt: skip

    return ReconciliationOut(
        statement=_import_out(statement),
        matched=[
            MatchedOut(line=_line_out(ln, memos), entry=_entry_out(it)) for ln, it in result.matched
        ],
        missing_in_system=[_line_out(ln, memos) for ln in left if ln.line_id not in wrong_ids],
        wrong_account=[
            WrongAccountOut(line=_line_out(ln, memos), entry=_entry_out(it), belongs_to=other)
            for ln, it in wrong
        ],
        missing_in_bank=[_entry_out(i) for i in result.missing_in_bank],
        divergences=[divergence(d) for d in result.divergences],
        ignored=[
            ResolvedOut(line=_line_out(ln, memos), reason=str(decided[ln.line_id]["reason"]))
            for ln in result.missing_in_system
            if ln.line_id in decided and decided[ln.line_id]["action"] == "IGNORED"
        ],
    )


# --- acting on a line -----------------------------------------------------------------------------


def act_on_line(
    db: Session, scope: SchoolScope, line_id: uuid.UUID, body: LineAction
) -> LineActionOut:
    """The management decides about a line that is in the bank and not in the ledger: register the
    money (a Pix straight to the key, a transfer, a bank fee) or ignore it, with a reason.

    Everything happens in ONE transaction and a line is resolved once (a unique key in the
    database), so a double click or two people at once never book the money twice. What is
    registered is dated on the day of the bank; the next comparison pairs it with its line."""
    try:
        return _act_on_line(db, scope, line_id, body)
    except IntegrityError:  # the same line resolved at the same moment by someone else
        db.rollback()
        raise ProblemError(409, "already_resolved", "This line was already resolved") from None


def _act_on_line(
    db: Session, scope: SchoolScope, line_id: uuid.UUID, body: LineAction
) -> LineActionOut:
    with database_rules(db):
        line = repository.line_by_id(db, scope.school_id, line_id)
        if line is None:
            raise not_found()
        if line["resolution"] is not None:
            raise ProblemError(409, "already_resolved", "This line was already resolved")
        if line["purpose"] == "PDDE" and body.action != "IGNORE":
            # The PDDE money is not the APM's cash: its lines are handled in the PDDE screen.
            raise _invalid("action", "pdde_account_line")
        amount = int(line["amount_cents"])
        if body.action != "IGNORE" and line["needs_review"] and not body.reviewed:
            raise _invalid("reviewed", "review_required")
        transaction_id: uuid.UUID | None = None
        reference_code: int | None = None
        kind: str | None = None
        reason: str | None = None
        if body.action == "IGNORE":
            if body.reason is None:
                raise _invalid("reason", "required")
            reason = body.reason
        elif body.action == "REGISTER_INCOME":
            if amount <= 0:
                raise _invalid("action", "line_is_not_an_income")
            e2e = line["end_to_end_id"]
            method = body.method or ("PIX_DIRECT" if e2e else "TRANSFER")
            if method == "PIX_DIRECT" and e2e is None:
                raise _invalid("method", "needs_an_end_to_end_id")
            category = repository.income_category(db, scope.school_id, body.category_key)
            if category is None:
                raise _invalid("category_key", "unknown")
            moment = repository.bank_moment(db, scope.school_id, line["posted_on"])
            transaction_id, reference_code = repository.insert_income(
                db, organization_id=scope.organization_id, school_id=scope.school_id,
                user_id=scope.user_id, category_id=category, amount_cents=amount, moment=moment,
                method=method, external_reference=e2e if method == "PIX_DIRECT" else None,
                guardian_name=body.guardian_name,
            )  # fmt: skip
            kind = "CONTRIBUTION"
        else:  # REGISTER_FEE
            if amount >= 0:
                raise _invalid("action", "line_is_not_a_charge")
            category = repository.bank_fees_category(db, scope.school_id)
            if category is None:
                raise _invalid("category_key", "unknown")
            moment = repository.bank_moment(db, scope.school_id, line["posted_on"])
            transaction_id, reference_code = repository.insert_fee_expense(
                db, organization_id=scope.organization_id, school_id=scope.school_id,
                user_id=scope.user_id, category_id=category, amount_cents=-amount, moment=moment,
                description=(str(line["memo"]).strip() or "Tarifa bancária")[:120],
            )  # fmt: skip
            kind = "EXPENSE"
        repository.insert_resolution(
            db, organization_id=scope.organization_id, school_id=scope.school_id,
            user_id=scope.user_id, line_id=line_id,
            action="IGNORED" if body.action == "IGNORE" else "REGISTERED", reason=reason,
            transaction_id=transaction_id, transaction_kind=kind,
        )  # fmt: skip
        db.commit()
    return LineActionOut(
        line_id=line_id,
        action="IGNORED" if body.action == "IGNORE" else "REGISTERED",
        transaction_id=transaction_id,
        reference_code=None if reference_code is None else f"APM-{reference_code:06d}",
    )


# --- the balance for the closing ------------------------------------------------------------------


def closing_balance(db: Session, scope: SchoolScope, period: str) -> ClosingBalanceOut:
    """The balance of the last statement of each general account up to the end of the month."""
    try:
        year, month = (int(part) for part in period.split("-"))
        first = dt.date(year, month, 1)
    except ValueError:
        raise _invalid("period", "invalid") from None
    month_end = (first.replace(day=28) + dt.timedelta(days=4)).replace(day=1) - dt.timedelta(days=1)
    items = [
        ClosingBalanceItem(
            bank_account_id=r["bank_account_id"],
            nickname=r["nickname"],
            closing_balance_cents=int(r["closing_balance_cents"]),
            as_of=r["as_of"],
        )
        for r in repository.closing_balances(db, scope.school_id, month_end)
    ]
    return ClosingBalanceOut(
        items=items,
        total_cents=sum(i.closing_balance_cents for i in items) if items else None,
    )
