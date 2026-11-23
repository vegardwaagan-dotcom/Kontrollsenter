"""Norske røde dager (offentlige høytidsdager) og merkedager – regnes ut for hvilket år som helst (påsken med
Gauss/Meeus-formelen), så kalenderen virker like langt fram i tid som du vil.

Røde dager: nyttårsdag, skjærtorsdag, langfredag, 1. og 2. påskedag, 1. mai, 17. mai, Kristi himmelfartsdag,
1. og 2. pinsedag, 1. og 2. juledag – pluss alle søndager.
"""
import datetime as dt
from functools import lru_cache


def easter(year):
    """1. påskedag (gregoriansk kalender)."""
    a = year % 19
    b, c = divmod(year, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    l_ = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l_) // 451
    month = (h + l_ - 7 * m + 114) // 31
    day = (h + l_ - 7 * m + 114) % 31 + 1
    return dt.date(year, month, day)


@lru_cache(maxsize=256)
def red_days(year):
    """{dato: navn} for alle røde dager i året (ikke vanlige søndager)."""
    e = easter(year)
    d = {
        dt.date(year, 1, 1): "Nyttårsdag",
        e - dt.timedelta(days=3): "Skjærtorsdag",
        e - dt.timedelta(days=2): "Langfredag",
        e: "1. påskedag",
        e + dt.timedelta(days=1): "2. påskedag",
        dt.date(year, 5, 1): "Arbeidernes dag",
        dt.date(year, 5, 17): "Grunnlovsdagen",
        e + dt.timedelta(days=39): "Kristi himmelfartsdag",
        e + dt.timedelta(days=49): "1. pinsedag",
        e + dt.timedelta(days=50): "2. pinsedag",
        dt.date(year, 12, 25): "1. juledag",
        dt.date(year, 12, 26): "2. juledag",
    }
    return dict(sorted(d.items()))


def _nth_sunday(year, month, n):
    first = dt.date(year, month, 1)
    return first + dt.timedelta(days=(6 - first.weekday()) % 7 + 7 * (n - 1))


@lru_cache(maxsize=256)
def special_days(year):
    """Merkedager som ikke er fridager (vises med en liten prikk): julaften, nyttårsaften, morsdag, farsdag …"""
    e = easter(year)
    d = {
        dt.date(year, 2, 14): "Valentinsdagen",
        _nth_sunday(year, 2, 2): "Morsdag",
        e - dt.timedelta(days=7): "Palmesøndag",
        dt.date(year, 6, 23): "Sankthansaften",
        _nth_sunday(year, 11, 2): "Farsdag",
        dt.date(year, 12, 24): "Julaften",
        dt.date(year, 12, 31): "Nyttårsaften",
        e - dt.timedelta(days=49): "Fastelavnssøndag",
    }
    return dict(sorted(d.items()))


def is_red(day):
    return day.weekday() == 6 or day in red_days(day.year)


def name(day):
    return red_days(day.year).get(day) or special_days(day.year).get(day) or ""


def upcoming(n=10, start=None):
    """De neste n røde dagene (ikke vanlige søndager): [(dato, navn, dager til)]."""
    start = start or dt.date.today()
    out, y = [], start.year
    while len(out) < n and y < start.year + 5:
        out += [(d, nm, (d - start).days) for d, nm in red_days(y).items() if d >= start]
        y += 1
    return out[:n]


def long_weekends(year):
    """Røde dager som gir langhelg (fredag eller mandag) – fint for planlegging."""
    return [(d, nm) for d, nm in red_days(year).items() if d.weekday() in (0, 4)]


def month_json(year, month):
    """For mobilappen: alle dager i måneden med rød/merkedag."""
    import calendar
    days = []
    for d in calendar.Calendar(firstweekday=0).itermonthdates(year, month):
        days.append({"d": d.isoformat(), "day": d.day, "in": d.month == month, "red": is_red(d),
                     "name": name(d), "today": d == dt.date.today(), "week": d.isocalendar()[1]})
    return {"year": year, "month": month, "days": days,
            "upcoming": [{"d": d.isoformat(), "name": nm, "in": n} for d, nm, n in upcoming(8)],
            "year_list": [{"d": d.isoformat(), "name": nm} for d, nm in red_days(year).items()]}
