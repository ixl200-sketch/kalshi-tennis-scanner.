"""Public, read-only Kalshi market detail endpoints for tennis contract exploration."""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
from urllib.parse import quote

import requests

from scanner import BASE, SERIES


def _request(path, params=None, session=None, timeout=12):
    client = session or requests
    response = client.get(BASE + path, params=params, timeout=timeout)
    response.raise_for_status()
    return response.json()


def _ticker_path(ticker):
    # Encode user-selected path segments, never accept slash-separated paths.
    return quote(str(ticker), safe="")


def get_market(ticker, session=None):
    return _request(f"/markets/{_ticker_path(ticker)}", session=session).get("market", {})


def get_orderbook(ticker, depth=20, session=None):
    if not 0 <= int(depth) <= 100:
        raise ValueError("Orderbook depth must be between 0 and 100.")
    return _request(
        f"/markets/{_ticker_path(ticker)}/orderbook",
        params={"depth": int(depth)}, session=session,
    ).get("orderbook_fp", {})


def orderbook_rows(book):
    """Return YES and NO bid ladders; asks are inferred from opposite bids."""
    rows = []
    for side in ("yes", "no"):
        for price, quantity in book.get(side + "_dollars", []):
            rows.append({
                "Side": side.upper() + " bid",
                "Bid (¢)": round(float(price) * 100, 4),
                "Quantity": float(quantity),
                "Implied opposite ask (¢)": round((1 - float(price)) * 100, 4),
            })
    return sorted(rows, key=lambda item: (item["Side"], -item["Bid (¢)"]))


def get_trades(ticker, limit=100, session=None):
    return _request(
        "/markets/trades",
        params={"ticker": ticker, "limit": int(limit)},
        session=session,
    ).get("trades", [])


def get_candlesticks(ticker, tour, days=2, period_minutes=60, session=None, now=None):
    if tour not in SERIES:
        raise ValueError("Unknown tennis series.")
    if period_minutes not in (1, 60, 1440):
        raise ValueError("Invalid interval.")
    if days < 1 or days * 1440 / period_minutes > 5000:
        raise ValueError("Requested window exceeds API candle limit.")
    end = now or datetime.now(timezone.utc)
    start = end - timedelta(days=days)
    payload = _request(
        f"/series/{_ticker_path(SERIES[tour])}/markets/{_ticker_path(ticker)}/candlesticks",
        params={
            "start_ts": int(start.timestamp()),
            "end_ts": int(end.timestamp()),
            "period_interval": period_minutes,
        },
        session=session,
    )
    return payload.get("candlesticks", [])


def candle_rows(candles):
    rows = []
    for c in candles:
        trade = c.get("price") or {}
        rows.append({
            "Time (UTC)": datetime.fromtimestamp(int(c["end_period_ts"]), timezone.utc).isoformat(),
            "YES bid close (¢)": _cents((c.get("yes_bid") or {}).get("close_dollars")),
            "YES ask close (¢)": _cents((c.get("yes_ask") or {}).get("close_dollars")),
            "Last traded close (¢)": _cents(trade.get("close_dollars")),
            "Volume": float(c.get("volume_fp") or 0),
            "Open interest": float(c.get("open_interest_fp") or 0),
        })
    return rows


def _cents(value):
    return None if value in (None, "") else round(float(value) * 100, 4)
