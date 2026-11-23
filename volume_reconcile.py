"""Reconcile event volumes against Kalshi's public event API.

Market volume_fp is cumulative contract quantity. Summing markets is
app-derived and may not match Kalshi.com's event-level volume.
"""
from __future__ import annotations
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from urllib.parse import quote
import requests
from scanner import BASE


def get_event_snapshot(event_ticker, session=None, timeout=12):
    if not event_ticker:
        raise ValueError("Missing event ticker")
    client = session or requests
    response = client.get(
        BASE + "/events/" + quote(str(event_ticker), safe=""),
        params={"with_nested_markets": "true"}, timeout=timeout,
    )
    response.raise_for_status()
    payload = response.json()
    event = payload.get("event") or {}
    markets = event.get("markets") or payload.get("markets") or []
    if not isinstance(markets, list):
        raise ValueError("Unexpected response from Kalshi event API")
    return {"event": event, "markets": markets,
            "retrieved_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}


def _quantity(value):
    if value in (None, ""):
        return None
    try:
        n = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
    return n if n.is_finite() and n >= 0 else None


def reconciliation_report(snapshot, website_volume=None):
    """Report both API numbers and the reference; do not invent a matching rule."""
    contracts = []
    seen = set()
    for market in snapshot.get("markets") or []:
        ticker = market.get("ticker")
        if not ticker or ticker in seen:
            continue
        seen.add(ticker)
        total = _quantity(market.get("volume_fp"))
        daily = _quantity(market.get("volume_24h_fp"))
        contracts.append({
            "Outcome": market.get("yes_sub_title") or market.get("title") or "YES",
            "Ticker": ticker,
            "Status": market.get("status") or "unknown",
            "Cumulative contracts": float(total) if total is not None else None,
            "24h contracts": float(daily) if daily is not None else None,
        })
    numbers = [item["Cumulative contracts"] for item in contracts]
    complete = bool(numbers) and all(v is not None for v in numbers)
    summed = sum(numbers) if complete else None
    largest = max(numbers) if complete else None
    reference = _quantity(website_volume)
    reference_float = float(reference) if reference is not None else None
    delta = summed - reference_float if summed is not None and reference_float is not None else None
    event = snapshot.get("event") or {}
    published = _quantity(event.get("volume_fp"))
    return {
        "event_ticker": event.get("event_ticker"),
        "retrieved_at": snapshot.get("retrieved_at"),
        "contracts": contracts,
        "count": len(contracts),
        "sum": summed,
        "largest": largest,
        "published_event_volume": float(published) if published is not None else None,
        "reference": reference_float,
        "difference": delta,
        "matches_sum": abs(delta) < 0.5 if delta is not None else None,
        "complete": complete,
    }


def whole_dollars(value):
    return "N/A" if value is None else "$" + format(value, ",.0f")
