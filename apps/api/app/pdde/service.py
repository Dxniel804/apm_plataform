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
from app.pdde import forms, forms_more, repository
from app.pdde.schemas import (
    AccountOut,
    AlertOut,
    BankBalance,
    CarryoverIn,
    CarryoverOut,
    ClassificationIn,
    ClassificationOut,
    DocumentIn,
    DocumentOut,
    EntityIn,
    EntityOut,
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
                vendor_tax_id=d["vendor_tax_id"],
                quantity=d["quantity"],
                specification=d["specification"],
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
                payment_number=r["payment_number"],
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
        bank_balances=[
            BankBalance(
                account_id=b["id"],
                account_nickname=b["nickname"],
                balance_cents=b["closing_balance_cents"],
                as_of=b["period_end"],
            )
            for b in repository.bank_balances(db, scope.school_id, end)
        ],
        lines=lines,
        pending_count=sum(1 for ln in lines if ln.status != "DONE"),
        alerts=_line_alerts(lines),
    )


def year_lines(db: Session, school_id: uuid.UUID, year: int) -> list[LineOut]:
    return _lines_out(
        db, school_id, repository.lines(db, school_id, dt.date(year, 1, 1), dt.date(year, 12, 31))
    )


Key = tuple[str, str | None]


def balances(
    lines: list[LineOut], carry: dict[Key, tuple[int, int]] | None = None
) -> tuple[list[ProgramBalance], list[AlertOut]]:
    """The balance of each program: the balance that came from the year before, plus what came in (the
    repasses and the yield of the investment), minus what was returned to the FNDE and what was spent.
    When the money says which category it is, spending more than came in that category is the use of
    custeio in capital or the opposite, which makes a prestação 'aprovada com ressalva' (Res. 15/2021,
    art. 33)."""
    carry = carry or {}
    received: dict[Key, int] = {}
    yielded: dict[Key, int] = {}
    returned: dict[Key, int] = {}
    came: dict[tuple[str, str], int] = {}
    spent: dict[Key, dict[str, int]] = {}
    for key, (custeio, capital) in carry.items():
        came[(key[0], "CUSTEIO")] = came.get((key[0], "CUSTEIO"), 0) + custeio
        came[(key[0], "CAPITAL")] = came.get((key[0], "CAPITAL"), 0) + capital
    for ln in lines:
        c = ln.classification
        if c is None or c.program is None:
            continue
        key = (c.program, c.program_label)
        if c.kind == "TRANSFER" and ln.amount_cents > 0:
            received[key] = received.get(key, 0) + ln.amount_cents
        elif c.kind == "YIELD" and ln.amount_cents > 0:
            yielded[key] = yielded.get(key, 0) + ln.amount_cents
        elif c.kind == "RETURN_TO_FNDE" and ln.amount_cents < 0:
            returned[key] = returned.get(key, 0) - ln.amount_cents
        elif c.kind == "EXPENSE" and ln.amount_cents < 0 and c.economic_category is not None:
            bucket = spent.setdefault(key, {"CUSTEIO": 0, "CAPITAL": 0})
            bucket[c.economic_category] += -ln.amount_cents
        if (
            c.kind in ("TRANSFER", "YIELD")
            and ln.amount_cents > 0
            and c.economic_category is not None
        ):
            came[(c.program, c.economic_category)] = (
                came.get((c.program, c.economic_category), 0) + ln.amount_cents
            )
    out: list[ProgramBalance] = []
    alerts: list[AlertOut] = []
    keys = (
        set(received)
        | set(spent)
        | set(yielded)
        | set(returned)
        | {k for k, v in carry.items() if any(v)}
    )
    for pkey in sorted(keys, key=lambda k: (k[0], k[1] or "")):
        program, label = pkey
        bucket = spent.get(pkey, {"CUSTEIO": 0, "CAPITAL": 0})
        got = received.get(pkey, 0)
        before = sum(carry.get(pkey, (0, 0)))
        out.append(
            ProgramBalance(
                program=cast(Program, program),
                program_label=label,
                received_cents=got,
                yield_cents=yielded.get(pkey, 0),
                returned_cents=returned.get(pkey, 0),
                spent_custeio_cents=bucket["CUSTEIO"],
                spent_capital_cents=bucket["CAPITAL"],
                balance_cents=before
                + got
                + yielded.get(pkey, 0)
                - returned.get(pkey, 0)
                - bucket["CUSTEIO"]
                - bucket["CAPITAL"],
            )
        )
        for category in ("CUSTEIO", "CAPITAL"):
            total_in = came.get((program, category), 0)
            if total_in > 0 and bucket[category] > total_in:
                alerts.append(
                    AlertOut(
                        code="spent_over_received",
                        program=cast(Program, program),
                        economic_category=category,
                        cents=bucket[category] - total_in,
                    )
                )
    return out, alerts


def prior_balances(
    db: Session, scope: SchoolScope, year: int
) -> tuple[dict[Key, tuple[int, int]], str]:
    """The balance that came from the year before (field 08 of the form), by program: what the school
    typed for the year, else what the lines of the earlier years leave, else nothing. The second
    element says which one it was, because the form must not pass a guess as a fact."""
    typed = {
        (str(r["program"]), r["program_label"]): (int(r["custeio_cents"]), int(r["capital_cents"]))
        for r in repository.carryovers(db, scope.school_id, year)
    }
    if typed:
        return typed, "typed"
    earlier = _lines_out(
        db,
        scope.school_id,
        repository.lines(db, scope.school_id, dt.date(2000, 1, 1), dt.date(year - 1, 12, 31)),
    )
    computed: dict[Key, list[int]] = {}
    for ln in earlier:
        c = ln.classification
        # A repasse of an earlier year with no custeio or capital cannot be split, so it is left out
        # (the form says the balance is a calculation and the school can type the right one).
        if c is None or c.program is None or c.economic_category is None:
            continue
        sign = (
            1
            if c.kind in ("TRANSFER", "YIELD")
            else -1
            if c.kind in ("EXPENSE", "RETURN_TO_FNDE")
            else 0
        )
        if sign == 0:
            continue
        slot = computed.setdefault((c.program, c.program_label), [0, 0])
        slot[0 if c.economic_category == "CUSTEIO" else 1] += sign * abs(ln.amount_cents)
    if computed:
        return {k: (v[0], v[1]) for k, v in computed.items()}, "computed"
    return {}, "none"


def year_view(db: Session, scope: SchoolScope, year: int) -> YearOut:
    lines = year_lines(db, scope.school_id, year)
    carry, _ = prior_balances(db, scope, year)
    programs, over = balances(lines, carry)
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


# --- the official forms ----------------------------------------------------------------------------


def get_entity(db: Session, scope: SchoolScope) -> EntityOut | None:
    row = repository.latest_entity(db, scope.school_id)
    return None if row is None else EntityOut.model_validate(dict(row))


def save_entity(db: Session, scope: SchoolScope, body: EntityIn) -> None:
    with database_rules(db):
        repository.insert_entity(
            db, organization_id=scope.organization_id, school_id=scope.school_id,
            user_id=scope.user_id, values=body.model_dump(),
        )  # fmt: skip
        db.commit()


def list_carryovers(db: Session, scope: SchoolScope, year: int) -> list[CarryoverOut]:
    return [
        CarryoverOut.model_validate(dict(r))
        for r in repository.carryovers(db, scope.school_id, year)
    ]


def save_carryover(db: Session, scope: SchoolScope, body: CarryoverIn) -> None:
    with database_rules(db):
        repository.insert_carryover(
            db, organization_id=scope.organization_id, school_id=scope.school_id,
            user_id=scope.user_id, values=body.model_dump(),
        )  # fmt: skip
        db.commit()


def demonstrativo_pdf(
    db: Session,
    scope: SchoolScope,
    year: int,
    program: str,
    label: str | None,
    generated_at: dt.datetime,
) -> bytes:
    """One form per program and year. A program that has nothing in the year is a 404 (there is nothing to account)."""
    lines = year_lines(db, scope.school_id, year)
    carry, source = prior_balances(db, scope, year)
    if not any(forms._same(ln, program, label) for ln in lines) and (program, label) not in carry:
        raise not_found()
    entity = repository.latest_entity(db, scope.school_id)
    apm, _ = repository.school_name(db, scope.school_id)
    form = forms.build_demonstrativo(
        lines=lines, program=program, label=label, year=year, carry=carry, carry_source=source,
        entity=None if entity is None else {k: str(v) for k, v in entity.items()}, fallback_name=apm,
    )  # fmt: skip
    return forms.render_pdf(form, generated_at=generated_at, place=entity["city"] if entity else "")


def _entity_dict(db: Session, scope: SchoolScope) -> dict[str, str] | None:
    entity = repository.latest_entity(db, scope.school_id)
    return None if entity is None else {k: str(v) for k, v in entity.items()}


def goods_pdf(
    db: Session,
    scope: SchoolScope,
    year: int,
    program: str,
    label: str | None,
    generated_at: dt.datetime,
) -> bytes:
    """The list of goods of a program and year. A program with nothing in the year is a 404."""
    lines = year_lines(db, scope.school_id, year)
    carry, _ = prior_balances(db, scope, year)
    if not any(forms._same(ln, program, label) for ln in lines) and (program, label) not in carry:
        raise not_found()
    entity = _entity_dict(db, scope)
    apm, _school = repository.school_name(db, scope.school_id)
    goods = forms_more.build_goods(
        lines=lines, program=program, label=label, year=year, entity=entity, fallback_name=apm
    )
    return forms_more.render_goods(
        goods, generated_at=generated_at, place=entity["city"] if entity else ""
    )


def reconciliation_pdf(
    db: Session, scope: SchoolScope, year: int, account_id: uuid.UUID, generated_at: dt.datetime
) -> bytes:
    """The bank reconciliation of one PDDE account (a 404 for any other account)."""
    account = repository.account_with_statement(db, scope.school_id, account_id, year)
    if account is None:
        raise not_found()
    lines = year_lines(db, scope.school_id, year)
    carry, _ = prior_balances(db, scope, year)
    programs, _alerts = balances(lines, carry)
    # The balance carried from the year before is by program, not by account: the conference is made only when
    # the school has one PDDE account.
    one_account = len(repository.accounts(db, scope.school_id)) == 1
    entity = _entity_dict(db, scope)
    apm, _school = repository.school_name(db, scope.school_id)
    reconciliation = forms_more.build_reconciliation(
        lines=lines, account_id=account_id, year=year, bank_name=account["bank_name"],
        account_last4=account["account_last4"], statement_date=account["period_end"],
        statement_cents=None if account["closing_balance_cents"] is None else int(account["closing_balance_cents"]),
        program_balance_sum=sum(p.balance_cents for p in programs) if one_account else None,
        entity=entity, fallback_name=apm,
    )  # fmt: skip
    return forms_more.render_reconciliation(
        reconciliation, generated_at=generated_at, place=entity["city"] if entity else ""
    )
