"""Read-only Kalshi tennis market collection and quote analysis."""
from __future__ import annotations
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
import requests

BASE = 'https://external-api.kalshi.com/trade-api/v2'
SERIES = {
    'ATP': 'KXATPMATCH',
    'WTA': 'KXWTAMATCH',
    'ATP Challenger': 'KXATPCHALLENGERMATCH',
    'WTA Challenger': 'KXWTACHALLENGERMATCH',
    'ITF': 'KXITFMATCH',
}
DB = Path(__file__).parent / 'snapshots.sqlite3'


def dollars_to_cents(value):
    if value is None or value == '':
        return None
    return round(float(value) * 100, 4)


def number(value):
    if value is None or value == '':
        return 0.0
    return float(value)


def fetch_series(series, session=None, pages=4, timeout=12):
    """Get open match-winner markets, following cursors and respecting 429."""
    session = session or requests.Session()
    markets, cursor = [], None
    for _ in range(pages):
        params = {'series_ticker': series, 'status': 'open', 'limit': 200, 'mve_filter': 'exclude'}
        if cursor:
            params['cursor'] = cursor
        for attempt in range(3):
            response = session.get(BASE + '/markets', params=params, timeout=timeout)
            if response.status_code == 429 and attempt < 2:
                time.sleep(min(float(response.headers.get('Retry-After', 2)), 8))
                continue
            response.raise_for_status()
            break
        payload = response.json()
        markets.extend(payload.get('markets', []))
        cursor = payload.get('cursor')
        if not cursor:
            break
    return markets


def normalize(market, tour, timestamp=None):
    bid = dollars_to_cents(market.get('yes_bid_dollars'))
    ask = dollars_to_cents(market.get('yes_ask_dollars'))
    no_bid = dollars_to_cents(market.get('no_bid_dollars'))
    no_ask = dollars_to_cents(market.get('no_ask_dollars'))
    # Ask can also be derived from the opposite side, but do not fill unknown
    # or absent quotes with a fictitious price.
    if (ask is None or ask == 0) and no_bid is not None and no_bid > 0:
        ask = round(100 - no_bid, 4)
    if (bid is None or bid == 0) and no_ask is not None and no_ask > 0:
        bid = round(100 - no_ask, 4)
    if bid == 0: bid = None
    if ask == 0: ask = None
    return {
        'observed_at': timestamp or datetime.now(timezone.utc).isoformat(timespec='seconds'),
        'tour': tour, 'ticker': market['ticker'],
        'event_ticker': market.get('event_ticker', ''),
        'title': market.get('title') or market.get('yes_sub_title') or market['ticker'],
        'yes_label': market.get('yes_sub_title') or 'YES',
        'bid_c': bid, 'ask_c': ask,
        'spread_c': round(ask - bid, 4) if bid is not None and ask is not None and ask >= bid else None,
        'last_c': dollars_to_cents(market.get('last_price_dollars')),
        'volume_24h': (number(market['volume_24h_fp'])
                       if market.get('volume_24h_fp') not in (None, '') else None),
        'open_interest': number(market.get('open_interest_fp')),
        'bid_size': number(market.get('yes_bid_size_fp')),
        'ask_size': number(market.get('yes_ask_size_fp')),
        'close_time': market.get('close_time', ''),
    }


def scan(tours=None, session=None):
    tours = tours or list(SERIES)
    rows, errors = [], []
    for tour in tours:
        try:
            markets = fetch_series(SERIES[tour], session=session)
            rows.extend(normalize(m, tour) for m in markets if m.get('ticker'))
        except (requests.RequestException, ValueError, KeyError) as exc:
            errors.append(f'{tour}: {exc}')
    return rows, errors


def initialize_db(path=DB):
    with sqlite3.connect(path) as db:
        db.execute('''CREATE TABLE IF NOT EXISTS snapshots (
            observed_at TEXT NOT NULL, ticker TEXT NOT NULL, tour TEXT,
            title TEXT, bid_c REAL, ask_c REAL, last_c REAL,
            spread_c REAL, volume_24h REAL, open_interest REAL,
            PRIMARY KEY (observed_at, ticker))''')
        db.execute('CREATE INDEX IF NOT EXISTS snapshot_ticker_time ON snapshots(ticker, observed_at)')


def save_snapshots(rows, path=DB):
    initialize_db(path)
    with sqlite3.connect(path) as db:
        db.executemany('''INSERT OR REPLACE INTO snapshots
          (observed_at,ticker,tour,title,bid_c,ask_c,last_c,spread_c,volume_24h,open_interest)
          VALUES (?,?,?,?,?,?,?,?,?,?)''',
          [tuple(r.get(k) for k in ('observed_at','ticker','tour','title','bid_c','ask_c','last_c','spread_c','volume_24h','open_interest')) for r in rows])


def history(ticker, path=DB, limit=500):
    initialize_db(path)
    with sqlite3.connect(path) as db:
        db.row_factory = sqlite3.Row
        return [dict(r) for r in db.execute('''SELECT * FROM (SELECT * FROM snapshots
          WHERE ticker=? ORDER BY observed_at DESC LIMIT ?) ORDER BY observed_at''', (ticker,limit))]


def best_opportunity(row, fair_prob, fee_per_contract_c=0):
    """Fair probability in [0,1], flat *estimated* per-contract fee in cents.
    A flat fee is only a user-provided scenario; not Kalshi fee calculation.
    """
    p = float(fair_prob)
    if not 0 <= p <= 1:
        raise ValueError('Probability must be 0..1')
    results = []
    if row['ask_c'] is not None:
        results.append(('BUY YES', round(100*p-row['ask_c']-fee_per_contract_c, 3),row['ask_c']))
    if row['bid_c'] is not None:
        no_ask = 100-row['bid_c']
        results.append(('BUY NO', round(100*(1-p)-no_ask-fee_per_contract_c,3),no_ask))
    return max(results, key=lambda x:x[1]) if results else None
