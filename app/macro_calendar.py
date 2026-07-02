"""
macro_calendar.py — live USD economic calendar + news blackout windows.

Sources:
  • ForexFactory public JSON (this week): nfs.faireconomy.media/ff_calendar_thisweek.json
  • Embedded FOMC statement dates (Fed schedule) for events beyond the weekly feed

Blackout policy (configurable via env):
  HIGH impact   → ABORT trades from 2h before until 1h after release
  MEDIUM impact → warning in Telegram from 4h before (no hard abort by default)
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo

import requests

ET = ZoneInfo("America/New_York")
FF_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"

# FOMC statement days (2:00 PM ET) — 2025–2027
FOMC_STATEMENTS_UTC: list[tuple[str, datetime]] = []


def _fomc_dt(y: int, m: int, d: int) -> datetime:
    return datetime(y, m, d, 14, 0, tzinfo=ET).astimezone(timezone.utc)


for _y, _days in (
    (2025, [(1, 29), (3, 19), (5, 7), (6, 18), (7, 30), (9, 17), (10, 29), (12, 10)]),
    (2026, [(1, 28), (3, 18), (4, 29), (6, 17), (7, 30), (9, 16), (11, 4), (12, 16)]),
    (2027, [(1, 27), (3, 17), (4, 28), (6, 16), (7, 28), (9, 15), (11, 3), (12, 15)]),
):
    for mo, da in _days:
        FOMC_STATEMENTS_UTC.append((f"FOMC Rate Decision", _fomc_dt(_y, mo, da)))

HIGH_KEYWORDS = re.compile(
    r"(non-farm|nfp|cpi|core cpi|fomc|fed interest rate|interest rate decision|"
    r"gdp|pce|retail sales|ism manufacturing|ism services|pmi)",
    re.I,
)

_cache: dict = {
    "events": [],
    "fetched_at": None,
}

BLACKOUT_HOURS_BEFORE_HIGH = float(os.getenv("MACRO_BLACKOUT_HOURS_BEFORE", "2"))
BLACKOUT_HOURS_AFTER_HIGH = float(os.getenv("MACRO_BLACKOUT_HOURS_AFTER", "1"))
WARN_HOURS_BEFORE_MEDIUM = float(os.getenv("MACRO_WARN_HOURS_BEFORE", "4"))


@dataclass
class MacroEvent:
    title: str
    time_utc: datetime
    impact: str  # High, Medium, Low

    @property
    def is_high(self) -> bool:
        if self.impact.lower() == "high":
            return True
        return bool(HIGH_KEYWORDS.search(self.title))

    @property
    def is_medium_up(self) -> bool:
        return self.impact.lower() in ("high", "medium") or self.is_high


def _parse_ff_date(raw: str) -> datetime:
    return datetime.fromisoformat(raw).astimezone(timezone.utc)


def _first_friday(year: int, month: int) -> datetime:
    from datetime import date
    d = date(year, month, 1)
    while d.weekday() != 4:
        d = d.replace(day=d.day + 1)
    return datetime(d.year, d.month, d.day, 8, 30, tzinfo=ET).astimezone(timezone.utc)


def _nth_business_day(year: int, month: int, n: int) -> datetime:
    from datetime import date, timedelta
    d = date(year, month, 1)
    count = 0
    while True:
        if d.weekday() < 5:
            count += 1
            if count == n:
                return datetime(d.year, d.month, d.day, 10, 0, tzinfo=ET).astimezone(timezone.utc)
        d += timedelta(days=1)


def _computed_high_impact(now: datetime) -> list[MacroEvent]:
    """Fallback schedule when FF feed is down — NFP, ISM, CPI estimates."""
    out: list[MacroEvent] = []
    y, m = now.year, now.month
    for mo_offset in (0, 1):
        mm = m + mo_offset
        yy = y
        if mm > 12:
            mm -= 12
            yy += 1
        try:
            out.append(MacroEvent("Non-Farm Employment Change", _first_friday(yy, mm), "High"))
            out.append(MacroEvent("ISM Manufacturing PMI", _nth_business_day(yy, mm, 1), "High"))
            out.append(MacroEvent("ISM Services PMI", _nth_business_day(yy, mm, 3), "High"))
            # CPI ~12th of month 8:30 ET
            from datetime import date
            cpi_day = min(12, 28)
            cpi_d = date(yy, mm, cpi_day)
            while cpi_d.weekday() >= 5:
                cpi_d = cpi_d.replace(day=cpi_d.day + 1)
            out.append(MacroEvent(
                "CPI m/m",
                datetime(cpi_d.year, cpi_d.month, cpi_d.day, 8, 30, tzinfo=ET).astimezone(timezone.utc),
                "High",
            ))
        except Exception:
            pass
    return out


def _fetch_ff_events() -> list[MacroEvent]:
    events: list[MacroEvent] = []
    ff_ok = False
    try:
        resp = requests.get(FF_URL, timeout=15.0)
        resp.raise_for_status()
        rows = resp.json()
        ff_ok = True
        for row in rows:
            if row.get("country") != "USD":
                continue
            impact = row.get("impact") or "Low"
            if impact.lower() in ("holiday", "low") and not HIGH_KEYWORDS.search(row.get("title", "")):
                continue
            try:
                t = _parse_ff_date(row["date"])
            except (KeyError, ValueError):
                continue
            events.append(MacroEvent(title=row.get("title", "USD Event"), time_utc=t, impact=impact))
    except Exception as exc:
        print(f"[macro_calendar] FF fetch failed: {exc}")

    if not ff_ok:
        events.extend(_computed_high_impact(datetime.now(timezone.utc)))
        if _cache.get("events"):
            # merge stale FF cache with computed
            events.extend(_cache["events"])

    for title, t in FOMC_STATEMENTS_UTC:
        if t > datetime.now(timezone.utc) - timedelta(days=1):
            events.append(MacroEvent(title=title, time_utc=t, impact="High"))

    events.sort(key=lambda e: e.time_utc)
    # dedupe by time+title
    seen = set()
    out = []
    for e in events:
        k = (e.title, int(e.time_utc.timestamp()))
        if k in seen:
            continue
        seen.add(k)
        out.append(e)
    return out


def _needs_calendar_refresh(now: datetime) -> bool:
    fetched = _cache.get("fetched_at")
    if fetched is None:
        return True
    age = (now - fetched).total_seconds()
    return age >= 6 * 3600  # refresh calendar every 6h


def ensure_calendar_fresh(now: datetime | None = None) -> None:
    now = now or datetime.now(timezone.utc)
    if not _needs_calendar_refresh(now):
        return
    events = _fetch_ff_events()
    if events:
        _cache["events"] = events
    _cache["fetched_at"] = now
    print(f"[macro_calendar] Loaded {len(_cache['events'])} USD events at {now.isoformat()}")


def upcoming_usd_events(within_hours: float = 168, now: datetime | None = None) -> list[MacroEvent]:
    now = now or datetime.now(timezone.utc)
    ensure_calendar_fresh(now)
    horizon = now + timedelta(hours=within_hours)
    return [e for e in _cache["events"] if now - timedelta(hours=1) <= e.time_utc <= horizon]


def _fmt_countdown(delta: timedelta) -> str:
    if delta.total_seconds() < 0:
        return "NOW / just released"
    secs = int(delta.total_seconds())
    h, rem = divmod(secs, 3600)
    m, s = divmod(rem, 60)
    if h >= 48:
        d, h = divmod(h, 24)
        return f"{d}d {h}h"
    if h > 0:
        return f"{h}h {m}m"
    return f"{m}m {s}s"


def calendar_status(now: datetime | None = None) -> dict:
    """
    Returns blackout state + next events for Telegram / gating.
    """
    now = now or datetime.now(timezone.utc)
    ensure_calendar_fresh(now)
    events = upcoming_usd_events(168, now)

    in_blackout = False
    blackout_reason = ""
    active_event: MacroEvent | None = None

    for ev in events:
        if not ev.is_high:
            continue
        start = ev.time_utc - timedelta(hours=BLACKOUT_HOURS_BEFORE_HIGH)
        end = ev.time_utc + timedelta(hours=BLACKOUT_HOURS_AFTER_HIGH)
        if start <= now <= end:
            in_blackout = True
            active_event = ev
            if now < ev.time_utc:
                blackout_reason = (
                    f"HIGH impact in {_fmt_countdown(ev.time_utc - now)}: "
                    f"{ev.title} @ {ev.time_utc.astimezone(ET).strftime('%Y-%m-%d %H:%M ET')}"
                )
            else:
                blackout_reason = (
                    f"Post-release window ({_fmt_countdown(end - now)} left): {ev.title}"
                )
            break

    warnings: list[str] = []
    if not in_blackout:
        for ev in events:
            if not ev.is_medium_up:
                continue
            warn_start = ev.time_utc - timedelta(hours=WARN_HOURS_BEFORE_MEDIUM)
            if warn_start <= now < ev.time_utc:
                warnings.append(
                    f"⚠️ {ev.impact.upper()}: {ev.title} in {_fmt_countdown(ev.time_utc - now)} "
                    f"({ev.time_utc.astimezone(ET).strftime('%H:%M ET')})"
                )

    future = [e for e in events if e.time_utc > now]
    next_ev = future[0] if future else None
    next_high = next((e for e in future if e.is_high), None)

    countdown_line = "No USD events in next 7d"
    if next_ev:
        tag = "🔴" if next_ev.is_high else "🟡"
        countdown_line = (
            f"{tag} Next: {next_ev.title} in {_fmt_countdown(next_ev.time_utc - now)} "
            f"({next_ev.time_utc.astimezone(ET).strftime('%a %b %d %H:%M ET')})"
        )

    return {
        "in_blackout": in_blackout,
        "blackout_reason": blackout_reason,
        "active_event": active_event,
        "warnings": warnings,
        "next_event": next_ev,
        "next_high_impact": next_high,
        "countdown_line": countdown_line,
        "calendar_fetched_at": _cache.get("fetched_at"),
        "event_count": len(events),
    }


def format_calendar_block(status: dict) -> str:
    lines = [f"📅 <b>Macro Calendar</b>", f"• {status['countdown_line']}"]
    if status["in_blackout"]:
        lines.append(f"• 🚫 <b>BLACKOUT ACTIVE</b> — {status['blackout_reason']}")
    for w in status.get("warnings", [])[:3]:
        lines.append(f"• {w}")
    if status.get("next_high_impact") and not status["in_blackout"]:
        nh = status["next_high_impact"]
        lines.append(
            f"• 🔴 Next HIGH: {nh.title} — "
            f"{_fmt_countdown(nh.time_utc - datetime.now(timezone.utc))}"
        )
    return "\n".join(lines) + "\n"
