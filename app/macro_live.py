"""
macro_live.py — in-memory cache for the 6-pillar FRED macro engine.

Refresh policy (V5.6):
  • Every 4 hours (default)
  • Every 1 hour when a HIGH-impact USD event is within 24h
  • On cold start
"""

from __future__ import annotations

import asyncio
import os
from datetime import datetime, timezone
from typing import Any

from backtester.macro_pillars import build_macro_strength, pillars_for

try:
    from app.macro_calendar import calendar_status
except ImportError:
    calendar_status = None

_cache: dict[str, Any] = {
    "oecd": None,
    "ism": None,
    "fetched_at": None,
    "refresh_lock": asyncio.Lock(),
}

REFRESH_SECONDS = int(os.getenv("MACRO_REFRESH_SECONDS", str(4 * 3600)))
EVENT_PROXIMITY_REFRESH = int(os.getenv("MACRO_EVENT_REFRESH_SECONDS", str(3600)))

NARRATIVE = {
    "fomc": {
        "HAWKISH": "• <b>FOMC:</b> Hawkish Hold (+3) | <i>Rates elevated. Capital inflow to USD yield.</i>",
        "DOVISH":  "• <b>FOMC:</b> Dovish Pivot (-3) | <i>Rate cuts incoming. Capital fleeing USD for risk assets.</i>",
    },
    "cpi": {
        "HOT":  "• <b>CPI:</b> Hot (+2) | <i>Inflation sticky. Forces Fed to maintain high terminal rates.</i>",
        "COLD": "• <b>CPI:</b> Cold (-2) | <i>Disinflation path opens room for easing.</i>",
    },
    "yields": {
        "RISING":  "• <b>10Y Yield:</b> Rising (+2) | <i>Bond market pricing 'Higher for Longer'.</i>",
        "FALLING": "• <b>10Y Yield:</b> Falling (-2) | <i>Yield compression supports risk assets.</i>",
    },
    "nfp": {
        "STRONG": "• <b>Labor:</b> Strong (+2) | <i>Resilient jobs give Fed room to hold rates.</i>",
        "WEAK":   "• <b>Labor:</b> Weak (-2) | <i>Softening labor increases cut probability.</i>",
    },
    "pmi": {
        "EXPANSION":   "• <b>PMI:</b> Expansion (+2) | <i>Manufacturing/services momentum supports USD.</i>",
        "CONTRACTION": "• <b>PMI:</b> Contraction (-2) | <i>Activity slowdown weighs on USD.</i>",
    },
    "retail_sales": {
        "STRONG": "• <b>Retail Sales:</b> Strong (+1) | <i>Consumer spending resilient.</i>",
        "WEAK":   "• <b>Retail Sales:</b> Weak (-1) | <i>Consumer pullback signals slowdown.</i>",
    },
}

STATE_SUMMARY = {
    "Wrecking Ball":     "\n🔥 <b>MARKET STATE: Wrecking Ball</b>\n<i>USD universally dominant. Risk assets face sustained downward pressure.</i>",
    "USD Collapse":      "\n🩸 <b>MARKET STATE: USD Collapse</b>\n<i>USD in freefall. Liquidity rotating into high-beta risk assets.</i>",
    "Choppy / Neutral":  "\n⚖️ <b>MARKET STATE: Choppy / Neutral</b>\n<i>Conflicting macro. Prices driven by local technicals and order flow.</i>",
    "Trending Bias":     "\n📉 <b>MARKET STATE: Trending Bias</b>\n<i>Moderate, structured directional bias established.</i>",
}


def _event_within_24h(now: datetime) -> bool:
    if calendar_status is None:
        return False
    try:
        st = calendar_status(now)
        nh = st.get("next_high_impact")
        if nh and (nh.time_utc - now).total_seconds() <= 24 * 3600:
            return True
        if st.get("in_blackout"):
            return True
    except Exception:
        pass
    return False


def _needs_refresh(now: datetime | None = None) -> bool:
    now = now or datetime.now(timezone.utc)
    fetched = _cache["fetched_at"]
    if fetched is None:
        return True
    age = (now - fetched).total_seconds()
    if age >= REFRESH_SECONDS:
        return True
    if _event_within_24h(now) and age >= EVENT_PROXIMITY_REFRESH:
        return True
    return False


def _fetch_all_sync() -> None:
    """Blocking FRED pull — run in executor thread."""
    _cache["oecd"] = build_macro_strength(pmi_source="oecd")
    _cache["ism"] = build_macro_strength(pmi_source="ism")
    _cache["fetched_at"] = datetime.now(timezone.utc)
    print(f"[macro_live] Refreshed FRED pillars at {_cache['fetched_at'].isoformat()}")


async def ensure_macro_fresh() -> None:
    """Refresh cache if stale."""
    if not _needs_refresh():
        return
    async with _cache["refresh_lock"]:
        if not _needs_refresh():
            return
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, _fetch_all_sync)


async def warm_macro_cache() -> None:
    """Startup hook — populate cache before first webhook."""
    await ensure_macro_fresh()


def get_macro_frame(pmi_source: str = "oecd"):
    """Return cached macro DataFrame (sync — call ensure_macro_fresh first)."""
    key = pmi_source if pmi_source in ("oecd", "ism") else "oecd"
    frame = _cache.get(key)
    if frame is None:
        raise RuntimeError("Macro cache empty — call ensure_macro_fresh() first.")
    return frame


def cache_status() -> dict:
    fetched = _cache["fetched_at"]
    now = datetime.now(timezone.utc)
    age_min = None
    if fetched:
        age_min = round((now - fetched).total_seconds() / 60, 1)
    return {
        "fetched_at": fetched.isoformat() if fetched else None,
        "age_minutes": age_min,
        "refresh_interval_hours": REFRESH_SECONDS / 3600,
        "oecd_rows": len(_cache["oecd"]) if _cache["oecd"] is not None else 0,
        "ism_rows": len(_cache["ism"]) if _cache["ism"] is not None else 0,
    }


def calculate_usd_macro_bias(pmi_source: str = "oecd") -> tuple[int, list[str]]:
    """
    Live replacement for the old MACRO_CACHE calculator.
    Reads the latest lag-adjusted pillar row from the in-memory FRED cache.
    """
    macro = get_macro_frame(pmi_source)
    latest = macro.dropna(subset=["usd_strength"]).iloc[-1]
    usd_strength = int(latest["usd_strength"])
    reasons: list[str] = []

    for p in pillars_for(pmi_source):
        status = str(latest.get(f"{p.name}_status", "NEUTRAL"))
        if status != "NEUTRAL" and p.name in NARRATIVE and status in NARRATIVE[p.name]:
            reasons.append(NARRATIVE[p.name][status])

    state = str(latest.get("market_state", "Trending Bias"))
    reasons.append(STATE_SUMMARY.get(state, STATE_SUMMARY["Trending Bias"]))
    return usd_strength, reasons


def live_pillar_summary(pmi_source: str = "oecd") -> str:
    """One-line FRED pillar score breakdown for Telegram verification."""
    macro = get_macro_frame(pmi_source)
    latest = macro.dropna(subset=["usd_strength"]).iloc[-1]
    parts = []
    for p in pillars_for(pmi_source):
        sc = latest.get(f"{p.name}_score", 0)
        st = latest.get(f"{p.name}_status", "NEUTRAL")
        parts.append(f"{p.name.upper()}:{st}({int(sc):+d})")
    return f"PMI={pmi_source} | " + " ".join(parts) + f" | TOTAL={int(latest['usd_strength']):+d}"
