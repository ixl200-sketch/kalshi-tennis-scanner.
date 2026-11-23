"""Human-readable tennis matchup labels, independent of contract ticker parsing."""
from __future__ import annotations

import re
import requests

from scanner import BASE, SERIES

_MATCH = re.compile(r"(.+?)\s+(?:vs\.?|versus|v\.)\s+(.+)", re.IGNORECASE)
_WIN = re.compile(r"\s+(?:wins?|to win)(?:\s+the\s+match)?\s*[?.!]*$", re.IGNORECASE)


def player_name(text):
    """Clean a Kalshi outcome label without guessing from opaque tickers."""
    name = str(text or "").strip()
    name = _WIN.sub("", name)
    return name.strip(" .?!:-")


def matchup_name(group, event=None):
    """Prefer event matchup title; otherwise combine both event outcome names."""
    event = event or {}
    for candidate in (event.get("title"), event.get("sub_title")):
        m = _MATCH.search(str(candidate or ""))
        if m:
            return f"{m.group(1).strip()} vs. {m.group(2).strip()}"
    players = []
    for market in group:
        raw = market.get("yes_label") or market.get("title")
        person = player_name(raw)
        if person and person.lower() not in {x.lower() for x in players}:
            players.append(person)
    if len(players) >= 2:
        return f"{players[0]} vs. {players[1]}"
    for market in group:
        m = _MATCH.search(str(market.get("title") or ""))
        if m:
            return f"{m.group(1).strip()} vs. {m.group(2).strip()}"
    return (group[0].get("title") or "Match details unavailable").strip()


def tournament_name(group, event=None):
    """Display known event tournament metadata, otherwise an honest tour fallback."""
    event = event or {}
    matchup = matchup_name(group, event)
    candidates = (
        event.get("tournament"), event.get("tournament_name"),
        event.get("competition_name"), event.get("competition"),
        event.get("league"), event.get("sub_title"),
    )
    for raw in candidates:
        value = str(raw or "").strip()
        if value and value.lower() != matchup.lower() and not _MATCH.search(value):
            return value
    return str(group[0].get("tour") or "Tennis")


def event_labels(rows, events=None):
    """Return event_ticker -> 'Tournament | Player 1 vs. Player 2'."""
    groups = {}
    for row in rows:
        key = row.get("event_ticker") or row["ticker"]
        groups.setdefault(key, []).append(row)
    events = events or {}
    return {key: f"{tournament_name(group, events.get(key))} | {matchup_name(group, events.get(key))}"
            for key, group in groups.items()}


def fetch_event_metadata(tours, session=None, timeout=12):
    """Get the published event titles/subtitles in a few batched requests.

    Network issues only affect the display label; pricing uses market rows.
    """
    client = session or requests
    result = {}
    for tour in tours:
        ticker = SERIES.get(tour)
        if not ticker:
            continue
        cursor = None
        for _ in range(4):
            params = {"series_ticker": ticker, "status": "open", "limit": 200}
            if cursor:
                params["cursor"] = cursor
            try:
                response = client.get(BASE + "/events", params=params, timeout=timeout)
                response.raise_for_status()
                payload = response.json()
            except (requests.RequestException, ValueError):
                break
            for event in payload.get("events", []):
                event_id = event.get("event_ticker")
                if event_id:
                    result[event_id] = event
            cursor = payload.get("cursor")
            if not cursor:
                break
    return result
