# ruff: noqa: E501  (long lines)
"""The PDDE accountability layer: classify the lines of the PDDE bank account and prove the expenses.

Nothing here writes to the ledger. The lines are the bank's word; this adds what the management says
about each one (the program, custeio or capital, the object) and the documents that prove it. The
status of a line and the balance of a program are computed on every read from those rows (never
stored), so there is nothing to keep in step."""

import datetime as dt
import uuid
from collections.abc import Sequence
from typing import cast

from sqlalchemy import RowMapping
from sqlalchemy.orm import Session

from app.core.errors import ProblemError
from app.expenses.access import SchoolScope, not_found
from app.expenses.db_errors import database_rules
from app.pdde import repository
from app.pdde.schemas import (
    AccountOut,
    AlertOut,
    ClassificationIn,
    ClassificationOut,
    DocumentIn,
    DocumentOut,
    LineOut,
    MonthOut,
    Program,
    ProgramBalance,
    YearEndBalance,
    YearOut,
)
from app.statement.periods import month_bounds

Row = RowMapping
DEADLINE_MONTH, DEADLINE_DAY = (
    4,
    30,
)  # the prefeitura sends the year's accounts by 30/04 (Res. 15/2021, art. 32)


def _status(line: Row, classification: ClassificationOut | None, documented: int) -> str:
    """PENDING until it is classified (an expense also needs its documents), PARTIAL while the documents
    are worth less than the line, DONE when the line is proved."""
    if classification is None:
        return "PENDING"
    if classification.kind != "EXPENSE":
        return "DONE"
    if documented <= 0:
        return "PENDING"
    return "DONE" if documented >= -int(line["amount_cents"]) else "PARTIAL"


def _lines_out(db: Session, school_id: uuid.UUID, rows: Sequence[Row]) -> list[LineOut]:
    by_line: dict[uuid.UUID, list[DocumentOut]] = {}
    for d in repository.documents(db, school_id, [r["line_id"] for r in rows]):
        by_line.setdefault(d["line_id"], []).append(
            DocumentOut(
                id=d["id"],
                doc_kind=d["doc_kind"],
                access_key=d["access_key"],
                doc_number=d["doc_number"],
                issued_on=d["issued_on"],
                vendor=d["vendor"],
                amount_cents=int(d["amount_cents"]),
                stamped=bool(d["stamped"]),
                voided=bool(d["voided"]),
            )  # fmt: skip
        )
    out: list[LineOut] = []
    for r in rows:
        documents = by_line.get(r["line_id"], [])
        classification = (
            None
            if r["kind"] is None
            else ClassificationOut(
                kind=r["kind"],
                program=r["program"],
                program_label=r["program_label"],
                economic_category=r["economic_category"],
                object=r["object"],
                note=r["note"],
            )  # fmt: skip
        )
        documented = sum(d.amount_cents for d in documents if not d.voided)
        out.append(
            LineOut(
                line_id=r["line_id"],
                account_id=r["account_id"],
                account_nickname=r["account_nickname"],
                posted_on=r["posted_on"],
                amount_cents=int(r["amount_cents"]),
                memo=r["memo"],
                looks_like_fee=bool(r["looks_like_fee"]),
                classification=classification,
                documents=documents,
                documented_cents=documented,
                status=_status(r, classification, documented),  # type: ignore[arg-type]
            )  # fmt: skip
        )
    return out


def _accounts(db: Session, school_id: uuid.UUID) -> list[AccountOut]:
    return [
        AccountOut(id=a["id"], nickname=a["nickname"], bank_name=a["bank_name"], account_last4=a["account_last4"])
        for a in repository.accounts(db, school_id)
    ]  # fmt: skip


def _line_alerts(lines: list[LineOut]) -> list[AlertOut]:
    alerts: list[AlertOut] = []
    fees = [ln for ln in lines if ln.looks_like_fee and ln.amount_cents < 0]
    if fees:
        # The PDDE account is exempt from bank fees and the money cannot pay them (Res. 15/2021, art. 4, 2, IV).
        alerts.append(
            AlertOut(
                code="fee_on_pdde_account",
                count=len(fees),
                cents=-sum(ln.amount_cents for ln in fees),
            )
        )
    pending = [ln for ln in lines if ln.status != "DONE"]
    if pending:
        alerts.append(AlertOut(code="pending_lines", count=len(pending)))
    return alerts


def month_view(db: Session, scope: SchoolScope, period: str) -> MonthOut:
    start, end = month_bounds(period)
    lines = _lines_out(db, scope.school_id, repository.lines(db, scope.school_id, start, end))
    return MonthOut(
        period=period,
        accounts=_accounts(db, scope.school_id),
        lines=lines,
        pending_count=sum(1 for ln in lines if ln.status != "DONE"),
        alerts=_line_alerts(lines),
    )


def year_lines(db: Session, school_id: uuid.UUID, year: int) -> list[LineOut]:
    return _lines_out(
        db, school_id, repository.lines(db, school_id, dt.date(year, 1, 1), dt.date(year, 12, 31))
    )


def balances(lines: list[LineOut]) -> tuple[list[ProgramBalance], list[AlertOut]]:
    """The balance of each program: what came in (the repasses) minus what was spent. When the repasses
    say which category they are, spending more than came in that category is the use of custeio in
    capital or the opposite, which makes a prestação 'aprovada com ressalva' (Res. 15/2021, art. 33)."""
    received: dict[tuple[str, str | None], int] = {}
    received_by_category: dict[tuple[str, str], int] = {}
    spent: dict[tuple[str, str | None], dict[str, int]] = {}
    for ln in lines:
        c = ln.classification
        if c is None or c.program is None:
            continue
        key = (c.program, c.program_label)
        if c.kind == "TRANSFER" and ln.amount_cents > 0:
            received[key] = received.get(key, 0) + ln.amount_cents
            if c.economic_category is not None:
                received_by_category[(c.program, c.economic_category)] = (
                    received_by_category.get((c.program, c.economic_category), 0) + ln.amount_cents
                )
        elif c.kind == "EXPENSE" and ln.amount_cents < 0 and c.economic_category is not None:
            bucket = spent.setdefault(key, {"CUSTEIO": 0, "CAPITAL": 0})
            bucket[c.economic_category] += -ln.amount_cents
    out: list[ProgramBalance] = []
    alerts: list[AlertOut] = []
    for pkey in sorted(set(received) | set(spent), key=lambda k: (k[0], k[1] or "")):
        program, label = pkey
        bucket = spent.get(pkey, {"CUSTEIO": 0, "CAPITAL": 0})
        got = received.get(pkey, 0)
        out.append(
            ProgramBalance(
                program=cast(Program, program),
                program_label=label,
                received_cents=got,
                spent_custeio_cents=bucket["CUSTEIO"],
                spent_capital_cents=bucket["CAPITAL"],
                balance_cents=got - bucket["CUSTEIO"] - bucket["CAPITAL"],
            )
        )
        for category in ("CUSTEIO", "CAPITAL"):
            came = received_by_category.get((program, category), 0)
            if came > 0 and bucket[category] > came:
                alerts.append(
                    AlertOut(
                        code="spent_over_received",
                        program=cast(Program, program),
                        economic_category=category,
                        cents=bucket[category] - came,
                    )
                )
    return out, alerts


def year_view(db: Session, scope: SchoolScope, year: int) -> YearOut:
    lines = year_lines(db, scope.school_id, year)
    programs, over = balances(lines)
    today = repository.today(db, scope.school_id)
    year_end = [
        YearEndBalance(
            account_id=b["account_id"],
            account_nickname=b["account_nickname"],
            balance_cents=None if b["balance_cents"] is None else int(b["balance_cents"]),
        )  # fmt: skip
        for b in repository.december_balances(db, scope.school_id, year)
    ]
    alerts = _line_alerts(lines) + over
    # The conciliação bancária of 31/12 (Res. 15/2021, art. 33, V): asked from December on.
    if today >= dt.date(year, 12, 1):
        missing = [b for b in year_end if b.balance_cents is None]
        if missing:
            alerts.append(AlertOut(code="year_end_reconciliation", count=len(missing)))
    pending = sum(1 for ln in lines if ln.status != "DONE")
    deadline = dt.date(year + 1, DEADLINE_MONTH, DEADLINE_DAY)
    if pending and today > dt.date(year, 12, 31):
        alerts.append(
            AlertOut(
                code="deadline" if today <= deadline else "deadline_passed",
                count=pending,
                date=deadline,
            )
        )
    return YearOut(
        year=year, accounts=_accounts(db, scope.school_id), programs=programs,
        pending_count=pending, year_end=year_end, alerts=alerts,
    )  # fmt: skip


# --- writes ---------------------------------------------------------------------------------------


def classify(db: Session, scope: SchoolScope, line_id: uuid.UUID, body: ClassificationIn) -> None:
    """A new row: the latest classification of a line counts, and the earlier ones stay in the audit."""
    with database_rules(db):
        if repository.line_of_pdde_account(db, scope.school_id, line_id) is None:
            raise not_found()
        repository.insert_classification(
            db, organization_id=scope.organization_id, school_id=scope.school_id,
            line_id=line_id, user_id=scope.user_id, values=body.model_dump(),
        )  # fmt: skip
        db.commit()


def add_document(
    db: Session, scope: SchoolScope, line_id: uuid.UUID, body: DocumentIn
) -> uuid.UUID:
    with database_rules(db):
        line = repository.line_of_pdde_account(db, scope.school_id, line_id)
        if line is None:
            raise not_found()
        if int(line["amount_cents"]) >= 0:
            raise ProblemError(
                422, "line_is_not_an_expense", "A document proves money that left the account"
            )
        new_id = repository.insert_document(
            db, organization_id=scope.organization_id, school_id=scope.school_id,
            line_id=line_id, user_id=scope.user_id, values=body.model_dump(exclude={"stamped"}) | {"stamped": body.stamped},
        )  # fmt: skip
        db.commit()
        return new_id


def void_document(db: Session, scope: SchoolScope, document_id: uuid.UUID) -> None:
    with database_rules(db):
        if not repository.void_document(db, scope.school_id, document_id, scope.user_id):
            raise not_found()
        db.commit()


def report_rows(db: Session, scope: SchoolScope, year: int) -> list[LineOut]:
    """Every line of the year, in the order of the bank's screen (the date)."""
    return year_lines(db, scope.school_id, year)
