"""The pairing of the lines of a bank statement with the entries of the ledger: a PURE function.

The same input always gives the same answer, and the rule is cautious: a line is paired only when
the pairing is certain. First by the end-to-end id of the Pix (the bank and the ledger both know
it); then by amount and date, one to one, inside a few days. When two things could be paired with
the same line, or with different amounts, nothing is guessed: it goes to "divergences", for a
person to decide.
"""

import uuid
from dataclasses import dataclass, field
from datetime import date

WINDOW_DAYS = 3


@dataclass(frozen=True)
class BankLine:
    line_id: uuid.UUID
    posted_on: date
    amount_cents: int  # signed, as the bank writes it
    end_to_end_id: str | None


@dataclass(frozen=True)
class LedgerItem:
    transaction_id: uuid.UUID
    reference_code: int
    kind: str
    day: date
    # Signed like the bank: in is positive. `gross` is what the ledger holds; `net` is what the bank
    # receives when a gateway fee was kept (None: the same as gross).
    gross_cents: int
    net_cents: int | None
    end_to_end_id: str | None

    def amounts(self) -> set[int]:
        return {self.gross_cents} | ({self.net_cents} if self.net_cents is not None else set())


@dataclass(frozen=True)
class Divergence:
    line: BankLine
    candidates: list[LedgerItem]
    reason: str  # "ambiguous" or "amount_differs"


@dataclass
class Pairing:
    matched: list[tuple[BankLine, LedgerItem]] = field(default_factory=list)
    missing_in_system: list[BankLine] = field(
        default_factory=list
    )  # in the bank, not in the ledger
    missing_in_bank: list[LedgerItem] = field(
        default_factory=list
    )  # in the ledger, not in the bank
    divergences: list[Divergence] = field(default_factory=list)


def pair(lines: list[BankLine], items: list[LedgerItem]) -> Pairing:
    result = Pairing()
    used_items: set[uuid.UUID] = set()
    settled_lines: set[uuid.UUID] = set()
    by_e2e: dict[str, list[LedgerItem]] = {}
    for item in items:
        if item.end_to_end_id:
            by_e2e.setdefault(item.end_to_end_id, []).append(item)

    # 1. the end-to-end id: the strongest proof.
    for line in sorted(lines, key=lambda x: (x.posted_on, str(x.line_id))):
        if not line.end_to_end_id or line.end_to_end_id not in by_e2e:
            continue
        found = [i for i in by_e2e[line.end_to_end_id] if i.transaction_id not in used_items]
        if len(found) == 1 and line.amount_cents in found[0].amounts():
            result.matched.append((line, found[0]))
            used_items.add(found[0].transaction_id)
        else:
            reason = "ambiguous" if len(found) != 1 else "amount_differs"
            result.divergences.append(Divergence(line, found, reason))
            used_items.update(i.transaction_id for i in found)
        settled_lines.add(line.line_id)

    # 2. amount and date, one to one. Every line and every item looks at its neighbours BEFORE
    # anything is decided, so the answer never depends on the order they come in.
    rest_lines = sorted(
        (ln for ln in lines if ln.line_id not in settled_lines),
        key=lambda x: (x.posted_on, str(x.line_id)),
    )
    rest_items = [i for i in items if i.transaction_id not in used_items]

    def near(line: BankLine, item: LedgerItem) -> bool:
        return (
            line.amount_cents in item.amounts()
            and abs((line.posted_on - item.day).days) <= WINDOW_DAYS
        )

    candidates = {ln.line_id: [i for i in rest_items if near(ln, i)] for ln in rest_lines}
    rivals = {i.transaction_id: [ln for ln in rest_lines if near(ln, i)] for i in rest_items}
    for line in rest_lines:
        found = candidates[line.line_id]
        if not found:
            result.missing_in_system.append(line)
        elif len(found) == 1 and len(rivals[found[0].transaction_id]) == 1:
            result.matched.append((line, found[0]))
            used_items.add(found[0].transaction_id)
        else:
            result.divergences.append(Divergence(line, found, "ambiguous"))
            used_items.update(i.transaction_id for i in found)

    result.missing_in_bank = [i for i in items if i.transaction_id not in used_items]
    return result
