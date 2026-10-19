"""The arithmetic of a retention and of the due date: no database and no opinion about the law.

The rate, the cap and the due day are DATA the school writes (usually with its accountant): this
module only applies them. Money is integer cents; a rate is in basis points (1,5% is 150)."""

import calendar
from datetime import date, timedelta


def retention(gross_cents: int, rate_bps: int, cap_cents: int | None) -> tuple[int, int]:
    """(base, retained): the base is the gross amount up to the cap, and the retained amount is
    base x rate rounded to the cent, half up (never a float)."""
    base = gross_cents if cap_cents is None else min(gross_cents, cap_cents)
    retained = (base * rate_bps + 5000) // 10000
    return base, retained


def due_date(competence: date, due_day: int, roll: str) -> date:
    """The day of the month AFTER the competence, moved off a weekend to the business day before
    (`PREVIOUS`) or after (`NEXT`). A day the month does not have (31 in a short month) is the last
    day of it. Holidays are NOT known: the screen says so."""
    year = competence.year + (1 if competence.month == 12 else 0)
    month = 1 if competence.month == 12 else competence.month + 1
    day = min(due_day, calendar.monthrange(year, month)[1])
    result = date(year, month, day)
    step = timedelta(days=-1 if roll == "PREVIOUS" else 1)
    while result.weekday() >= 5:
        result += step
    return result
