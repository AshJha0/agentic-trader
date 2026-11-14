"""NYSE trading calendar, standard library only (no pandas, no dateutil).

Kept free of third-party imports so the paper workflow's freshness job can load this file
with a bare Python (``importlib`` on the path, no package import) and the OMS and the paper
script can share it. Covers the standing holiday rules, the one-off full-day closures since
2000 (``NYSE_SPECIAL_CLOSURES``) and the 13:00 early closes (``nyse_early_closes``).
Closures before 2000 and future one-off closures are not modelled; add them to the table
(or to the OMS ``extra_equity_holidays`` config) when the NYSE announces one.
"""

from __future__ import annotations

from datetime import date, time, timedelta
from functools import lru_cache

EQUITY_CLOSE_NY = time(16, 0)
EQUITY_EARLY_CLOSE_NY = time(13, 0)

# One-off full-day NYSE closures since 2000 (NYSE closure notices; national days of mourning
# and emergencies). The standing rules in nyse_holidays cannot produce these.
NYSE_SPECIAL_CLOSURES: dict[date, str] = {
    date(2001, 9, 11): "September 11 attacks",
    date(2001, 9, 12): "September 11 attacks",
    date(2001, 9, 13): "September 11 attacks",
    date(2001, 9, 14): "September 11 attacks",
    date(2004, 6, 11): "national day of mourning, President Reagan",
    date(2007, 1, 2): "national day of mourning, President Ford",
    date(2012, 10, 29): "Hurricane Sandy",
    date(2012, 10, 30): "Hurricane Sandy",
    date(2018, 12, 5): "national day of mourning, President G. H. W. Bush",
    date(2025, 1, 9): "national day of mourning, President Carter",
}


def easter(year: int) -> date:
    """Gregorian Easter Sunday (anonymous Gregorian algorithm, same as dateutil's default)."""
    a, b, c = year % 19, year // 100, year % 100
    d, e = b // 4, b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    el = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * el) // 451
    n = h + el - 7 * m + 114
    return date(year, n // 31, n % 31 + 1)


def _observed(d: date) -> date:
    """NYSE observance: Saturday -> Friday, Sunday -> Monday."""
    if d.weekday() == 5:
        return d - timedelta(days=1)
    if d.weekday() == 6:
        return d + timedelta(days=1)
    return d


def _nth_weekday(year: int, month: int, weekday: int, n: int) -> date:
    d = date(year, month, 1)
    d += timedelta(days=(weekday - d.weekday()) % 7)
    return d + timedelta(weeks=n - 1)


def _last_weekday(year: int, month: int, weekday: int) -> date:
    d = date(year + (month == 12), month % 12 + 1, 1) - timedelta(days=1)
    return d - timedelta(days=(d.weekday() - weekday) % 7)


@lru_cache(maxsize=None)
def nyse_holidays(year: int) -> frozenset[date]:
    """Full-day NYSE closures: the standing rules plus ``NYSE_SPECIAL_CLOSURES``.

    New Year (a Saturday 1 January is not observed on the Friday before), Martin Luther King
    Jr. Day (from 1998), Washington's Birthday, Good Friday, Memorial Day, Juneteenth (from
    2022), Independence Day, Labor Day, Thanksgiving, Christmas."""
    days: set[date] = {d for d in NYSE_SPECIAL_CLOSURES if d.year == year}
    ny = date(year, 1, 1)
    if ny.weekday() != 5:
        days.add(_observed(ny))
    if year >= 1998:
        days.add(_nth_weekday(year, 1, 0, 3))
    days.add(_nth_weekday(year, 2, 0, 3))
    days.add(easter(year) - timedelta(days=2))
    days.add(_last_weekday(year, 5, 0))
    if year >= 2022:
        days.add(_observed(date(year, 6, 19)))
    days.add(_observed(date(year, 7, 4)))
    days.add(_nth_weekday(year, 9, 0, 1))
    days.add(_nth_weekday(year, 11, 3, 4))
    days.add(_observed(date(year, 12, 25)))
    return frozenset(days)


@lru_cache(maxsize=None)
def nyse_early_closes(year: int) -> frozenset[date]:
    """NYSE sessions that close at 13:00 New York (rules as applied since 2000).

    * The day before Independence Day when it is a Monday, Tuesday or Thursday (4 July on a
      Tuesday, Wednesday or Friday), and from 2013 also a Wednesday (4 July on a Thursday).
      In 2002 (4 July on a Thursday) the early close was Friday 5 July instead.
    * The day after Thanksgiving.
    * 24 December when it is Monday to Thursday (a Friday 24 December is the observed
      Christmas holiday)."""
    days: set[date] = set()
    july3 = date(year, 7, 3)
    if july3.weekday() in (0, 1, 3) or (july3.weekday() == 2 and year >= 2013):
        days.add(july3)
    if year == 2002:
        days.add(date(2002, 7, 5))
    days.add(_nth_weekday(year, 11, 3, 4) + timedelta(days=1))
    eve = date(year, 12, 24)
    if eve.weekday() <= 3:
        days.add(eve)
    return frozenset(d for d in days if d not in NYSE_SPECIAL_CLOSURES)


def nyse_close_time(d: date) -> time:
    """The NYSE closing time (New York) on session ``d``: 13:00 on early-close days, else 16:00."""
    return EQUITY_EARLY_CLOSE_NY if d in nyse_early_closes(d.year) else EQUITY_CLOSE_NY


def is_session(d: date) -> bool:
    """True when ``d`` is an NYSE trading session (a weekday that is not a closure)."""
    return d.weekday() < 5 and d not in nyse_holidays(d.year)


def last_session_on_or_before(d: date) -> date:
    """The latest NYSE session on or before ``d`` (a Monday run's 'yesterday' is Friday)."""
    while not is_session(d):
        d -= timedelta(days=1)
    return d


def sessions_after(last: date, today: date) -> int:
    """NYSE sessions strictly after ``last`` up to and including ``today``."""
    n, d = 0, last + timedelta(days=1)
    while d <= today:
        n += is_session(d)
        d += timedelta(days=1)
    return n
