"""The bank reconciliation: accounts, the import of an OFX file, and the comparison with the ledger.

Nothing here writes to the ledger. An import stores what the bank says (the lines, with the personal
data masked) and the comparison is computed each time it is read, by a pure function, from the lines
and from the ledger as it is now."""

import hashlib
import uuid
from typing import BinaryIO

from sqlalchemy.orm import Session

from app.core.errors import ProblemError
from app.expenses.access import SchoolScope, not_found
from app.expenses.db_errors import database_rules
from app.reconciliation import repository
from app.reconciliation.matcher import BankLine, Divergence, LedgerItem, pair
from app.reconciliation.ofx import MAX_BYTES, OfxError, parse_ofx
from app.reconciliation.schemas import (
    AccountCreate,
    AccountOut,
    AccountPatch,
    BankLineOut,
    DivergenceOut,
    ImportList,
    ImportOut,
    LedgerEntryOut,
    MatchedOut,
    ReconciliationOut,
)

OFX_PROBLEMS = {
    "file_too_large": (413, "payload_too_large"),
    "not_ofx": (422, "not_an_ofx_file"),
    "bad_line": (422, "ofx_line_unreadable"),
    "too_many_lines": (422, "ofx_too_many_lines"),
    "no_lines": (422, "ofx_without_lines"),
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


def import_ofx(
    db: Session, scope: SchoolScope, account_id: uuid.UUID, stream: BinaryIO
) -> ImportOut:
    """Read the file (bounded), refuse the same file twice, store the lines the bank had not sent
    yet. The file itself is not kept."""
    account = _account(db, scope, account_id)
    if not account.is_active:
        raise ProblemError(409, "account_inactive", "This bank account is switched off")
    data = stream.read(MAX_BYTES + 1)
    try:
        statement = parse_ofx(data)
    except OfxError as error:
        status, code = OFX_PROBLEMS.get(error.code, (422, "ofx_unreadable"))
        raise ProblemError(status, code, "The file could not be read") from None
    sha256 = hashlib.sha256(data).hexdigest()
    if repository.import_exists(db, scope.school_id, sha256):
        raise ProblemError(409, "already_imported", "This file was already imported")
    refs = list(dict.fromkeys(line.bank_ref for line in statement.lines))
    new = len(refs) - len(repository.existing_refs(db, scope.school_id, account_id, refs))
    with database_rules(db):
        import_id = repository.insert_import(
            db, organization_id=scope.organization_id, school_id=scope.school_id,
            user_id=scope.user_id, account_id=account_id, sha256=sha256,
            start=statement.period_start, end=statement.period_end, line_count=len(statement.lines),
            new_line_count=new, closing_balance_cents=statement.closing_balance_cents,
        )  # fmt: skip
        for line in statement.lines:
            repository.insert_line(
                db, organization_id=scope.organization_id, school_id=scope.school_id,
                import_id=import_id, account_id=account_id, posted_on=line.posted_on,
                amount_cents=line.amount_cents, memo=line.memo, bank_ref=line.bank_ref,
                end_to_end_id=line.end_to_end_id, looks_like_fee=line.looks_like_fee,
            )  # fmt: skip
        db.commit()
    return _import_out(repository.imports(db, scope.school_id, import_id)[0])


def list_imports(db: Session, scope: SchoolScope) -> ImportList:
    return ImportList(items=[_import_out(r) for r in repository.imports(db, scope.school_id)])


# --- comparing ------------------------------------------------------------------------------------


def _line_out(line: BankLine, memos: dict[uuid.UUID, tuple[str, bool]]) -> BankLineOut:
    memo, fee = memos[line.line_id]
    return BankLineOut(
        line_id=line.line_id, posted_on=line.posted_on, amount_cents=line.amount_cents, memo=memo,
        end_to_end_id=line.end_to_end_id, looks_like_fee=fee,
    )  # fmt: skip


def _entry_out(item: LedgerItem) -> LedgerEntryOut:
    return LedgerEntryOut(
        transaction_id=item.transaction_id, reference_code=item.reference_code, kind=item.kind,
        day=item.day, amount_cents=item.gross_cents, net_cents=item.net_cents,
    )  # fmt: skip


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
    memos = {r["line_id"]: (r["memo"], bool(r["looks_like_fee"])) for r in rows}
    lines = [
        BankLine(r["line_id"], r["posted_on"], int(r["amount_cents"]), r["end_to_end_id"])
        for r in rows
    ]
    items = [
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
            db, scope.school_id, statement["period_start"], statement["period_end"]
        )
    ]
    result = pair(lines, items)

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
        missing_in_system=[_line_out(ln, memos) for ln in result.missing_in_system],
        missing_in_bank=[_entry_out(i) for i in result.missing_in_bank],
        divergences=[divergence(d) for d in result.divergences],
    )
