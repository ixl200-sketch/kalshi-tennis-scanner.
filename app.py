"""Kalshi Tennis Scanner — market data only, no orders or portfolio access."""
from datetime import datetime, timezone
import pandas as pd
import streamlit as st
from kalshi_theme import apply_theme
from scanner import SERIES, scan, save_snapshots, history, best_opportunity
from kalshi_data import get_market, get_orderbook, orderbook_rows, get_trades, get_candlesticks, candle_rows
import requests
from match_labels import event_labels, fetch_event_metadata, player_name, ranked_exchange_dollar_volumes, format_notional_volume
from kalshi_live import LiveTicker, overlay_market_data, apply_exchange_dollar_volumes
from volume_reconcile import get_event_snapshot, reconciliation_report, whole_dollars

st.set_page_config(page_title='Kalshi Tennis Scanner', page_icon='🎾', layout='wide')
apply_theme()
st.title('Kalshi Tennis Scanner')
st.caption('Independent project · not affiliated with Kalshi · read-only public market data · live ticker streaming when configured · no live tennis score feed')

with st.sidebar:
    st.header('Explore tennis markets')
    st.caption('Choose which tours to follow. The match list is ranked by cumulative market volume.')
    tours = st.multiselect('Tours', list(SERIES), default=['ATP','WTA','ATP Challenger','WTA Challenger','ITF'])
    with st.expander('Watchlist filters', expanded=False):
        max_spread = st.slider('Maximum YES spread (¢)', 1, 50, 20,
                               help='Smaller spreads may be easier to trade, but do not guarantee a good price.')
        min_volume = st.number_input('Minimum 24h contracts traded', min_value=0, value=0, step=25,
                                     help='Applies to the Market Watchlist, not the match selector.')
    st.divider()
    st.caption('Market updates: streaming when connected; otherwise the REST data refreshes every 60 seconds.')
    with st.expander('About this scanner'):
        st.caption('Independent project, not affiliated with Kalshi. Read-only: it cannot place orders. Prices are quotes, not guaranteed fills.')
        st.markdown('[Kalshi API documentation](https://docs.kalshi.com/api-reference/market/get-markets)')

if not tours:
    st.warning('Select at least one series.'); st.stop()

interval = '2s'  # Keep the browser view close to the streaming market state.

@st.cache_data(ttl=600, show_spinner=False)
def cached_event_metadata(selected_tours):
    return fetch_event_metadata(selected_tours)

@st.cache_data(ttl=60, show_spinner=False)
def cached_market_scan(selected_tours):
    # REST is used for initial snapshots and discovery of new tennis markets.
    return scan(list(selected_tours))

@st.cache_resource(show_spinner=False)
def live_stream(api_key_id, private_key_pem):
    return LiveTicker(api_key_id, private_key_pem)

# Kalshi requires API-key authorization for its WebSocket handshake.
# Secrets must only be entered in Streamlit Cloud's private Secrets manager.
try:
    _live_key_id = st.secrets.get('KALSHI_API_KEY_ID')
    _live_key_pem = st.secrets.get('KALSHI_PRIVATE_KEY_PEM')
except Exception:
    _live_key_id = _live_key_pem = None
_feed = live_stream(_live_key_id, _live_key_pem) if _live_key_id and _live_key_pem else None

@st.fragment(run_every=interval)
def dashboard():
    if st.button('Refresh now', type='primary'):
        cached_market_scan.clear()
    started = datetime.now(timezone.utc)
    with st.spinner('Fetching open markets from Kalshi…'):
        rows, errors = cached_market_scan(tuple(tours))
    if _feed:
        live_data, last_live, stream_status, stream_error = _feed.snapshot()
        rows, updated_count = overlay_market_data(rows, live_data, last_live)
        rows = apply_exchange_dollar_volumes(rows, live_data)
        if last_live and updated_count:
            lag_seconds = max(0, int(__import__('time').time() - last_live))
            st.caption(f'Live feed connected · latest update {lag_seconds}s ago · {updated_count} tennis contracts updated')
        else:
            st.caption(f'Data connection: {stream_status} · REST market data updates every 60s')
        if stream_status in ('error', 'reconnecting') and stream_error:
            st.warning('Live feed unavailable. Displaying the latest REST snapshot.')
    else:
        st.warning('Live dollar volume is unavailable: Kalshi API credentials are not configured in Streamlit Secrets. Open Manage app → Settings → Secrets and configure KALSHI_API_KEY_ID and KALSHI_PRIVATE_KEY_PEM. Until then, only exchange-provided REST dollar values (if supplied) can be displayed.')
    if errors:
        st.warning('Some requests failed: ' + ' | '.join(errors))
    market_controls = st.container()
    overview, watchlist, price_history, trade_value, data_explorer = st.tabs([
        'Market Overview',
        'Market Watchlist',
        'Price History',
        'Trade Value Analysis',
        'Market Data Explorer',
    ])
    if not rows:
        with market_controls:
            st.info('No open tennis markets returned. This can happen between tournaments, or if the API is unavailable. Try different series or refresh later.')
        return
    # Persist the REST/streaming market snapshot. Streaming updates are read-only.
    # Preserve snapshots even when active display filters hide the rows.
    try:
        save_snapshots(rows)
    except Exception as exc:
        st.warning(f'Unable to store local history: {exc}')
    df = pd.DataFrame(rows)
    with market_controls:
        st.caption(f'Last checked {started.strftime("%H:%M:%S UTC")} · {len(rows)} open contracts · {len(tours)} tours')
        # Display tournament + matchup to users; ticker IDs remain internal API keys.
        match_rows = df.to_dict('records')
        event_info = cached_event_metadata(tuple(tours))
        labels = event_labels(match_rows, event_info)
        event_groups = {}
        for market in match_rows:
            group_id = market.get('event_ticker') or market['ticker']
            event_groups.setdefault(group_id, []).append(market)
        # Never label Kalshi contract volume_fp as dollar volume.
        # Use only fresh exchange-reported dollar_volume ticker messages.
        ranked_events = ranked_exchange_dollar_volumes(event_groups)
        event_volume = dict(ranked_events)
        known_volume_count = sum(volume is not None for volume in event_volume.values())
        if known_volume_count == 0:
            if _feed:
                st.info('Waiting for Kalshi dollar-volume updates. The ticker feed only sends changes; no exchange-reported dollar values have been received for all contracts of any listed match. Keep the app open during active trading and check the feed status above.')
            else:
                st.info('Dollar volume is N/A because no authenticated Kalshi ticker feed is configured and the REST market data has not supplied dollar_volume. Contract volume is intentionally not displayed as cash.')
        st.caption(f'Exchange-dollar coverage: {known_volume_count} of {len(event_volume)} matches. Only directly reported dollar_volume is used. Aggregating contracts may still differ from Kalshi.com event volume.')
        # Recreate display options from the latest stream on EVERY
        # 2-second fragment rerun. String options force Streamlit to refresh the
        # visible label when the volume changes; internal event IDs stay stable.
        event_ids = [event_id for event_id, _volume in ranked_events]
        option_by_event = {
            event_id: f"{labels[event_id]} | {format_notional_volume(event_volume[event_id])}"
            for event_id in event_ids
        }
        event_by_option = {label: event_id for event_id, label in option_by_event.items()}
        if len(event_by_option) != len(event_ids):
            # Rare case: distinguish identically formatted match labels.
            option_by_event = {
                event_id: f"{option_by_event[event_id]} ({i + 1})"
                for i, event_id in enumerate(event_ids)
            }
            event_by_option = {label: event_id for event_id, label in option_by_event.items()}
        previous_event = st.session_state.get('match_event_id')
        if previous_event not in option_by_event:
            previous_event = event_ids[0]

        def remember_match():
            st.session_state['match_event_id'] = event_by_option[
                st.session_state['matchup_display_option']
            ]

        selected_option = st.selectbox(
            'Tournament | Player 1 vs. Player 2',
            [option_by_event[event_id] for event_id in event_ids],
            index=event_ids.index(previous_event),
            key='matchup_display_option',
            on_change=remember_match,
            help='Sum of exchange-reported dollar_volume fields for each distinct contract in the event. Requires live WebSocket credentials and recent ticker messages. N/A rather than a contract-count estimate when unavailable. Website aggregation is not independently verified.',
        )
        chosen_event = event_by_option[selected_option]
        candidates = event_groups[chosen_event]
        if len(candidates) > 1:
            selected = st.selectbox(
                'Player / contract outcome to analyze',
                [market['ticker'] for market in candidates],
                format_func=lambda ticker: player_name(next(
                    market['yes_label'] for market in candidates if market['ticker'] == ticker
                )) or 'YES outcome',
                help='Each player can have a separate YES contract for the same match.',
            )
        else:
            selected = candidates[0]['ticker']
        display_match = labels[chosen_event]
        row = df.set_index('ticker').loc[selected].to_dict()

        st.markdown('##### Selected match at a glance')
        q1, q2, q3, q4 = st.columns(4)
        q1.metric('YES bid', f"{row['bid_c']:,.1f}¢" if pd.notna(row['bid_c']) else 'No quote')
        q2.metric('YES ask', f"{row['ask_c']:,.1f}¢" if pd.notna(row['ask_c']) else 'No quote')
        q3.metric('Spread', f"{row['spread_c']:,.1f}¢" if pd.notna(row['spread_c']) else 'N/A')
        q4.metric('Exchange dollar volume', format_notional_volume(event_volume[chosen_event]))
        st.caption('Volume figures come from the exchange dollar-volume feed; an event total is computed from its distinct contract messages. No exact website match is promised until verified.')

    with overview:
        st.subheader('Market overview')
        st.caption('A quick snapshot of the open tennis contracts currently returned by Kalshi.')
        c1,c2,c3,c4 = st.columns(4)
        c1.metric('Open contracts',len(df))
        c2.metric('With two-sided quotes', int(df['spread_c'].notna().sum()))
        c3.metric('Median quoted spread', f"{df['spread_c'].median():.1f}¢" if df['spread_c'].notna().any() else 'N/A')
        c4.metric('24h volume (sum)', f"{df['volume_24h'].sum():,.0f}")

    with watchlist:
        st.subheader('Market watchlist')
        filtered = df.loc[(df['spread_c'].notna()) & (df['spread_c'] <= max_spread) & (df['volume_24h'] >= min_volume)].copy()
        st.caption('Compare tradable contracts by spread and recent volume. Filters are in the sidebar. These are market quotes, not trade recommendations.')
        if filtered.empty:
            st.info('No contracts pass your current spread and volume filters.')
        else:
            filtered = filtered.sort_values(['spread_c','volume_24h'],ascending=[True,False])
            filtered['Match'] = filtered['event_ticker'].map(labels)
            show_cols = ['Match','yes_label','bid_c','ask_c','spread_c','last_c','volume_24h','open_interest']
            st.dataframe(filtered[show_cols].rename(columns={'bid_c':'YES bid ¢','ask_c':'YES ask ¢','spread_c':'Spread ¢','last_c':'Last ¢','volume_24h':'24h volume','open_interest':'Open interest','yes_label':'YES outcome'}), hide_index=True, use_container_width=True)
            st.download_button('Export watchlist CSV', filtered.to_csv(index=False), file_name='kalshi_tennis_watchlist.csv', mime='text/csv')

    with price_history:
        st.subheader('Price history')
        st.caption('Tracks quotes observed by this scanner, not a complete exchange archive.')
        k1,k2,k3 = st.columns(3)
        k1.metric('Current YES bid',f"{row['bid_c']}¢" if pd.notna(row['bid_c']) else 'No quote')
        k2.metric('Current YES ask',f"{row['ask_c']}¢" if pd.notna(row['ask_c']) else 'No quote')
        k3.metric('Quoted spread',f"{row['spread_c']}¢" if pd.notna(row['spread_c']) else 'N/A')
        hist = pd.DataFrame(history(selected))
        if not hist.empty:
            hist['observed_at'] = pd.to_datetime(hist['observed_at'],utc=True)
            st.line_chart(hist.set_index('observed_at')[['bid_c','ask_c']], y_label='YES price (¢)')
            st.caption('Chart contains only snapshots collected while this app is running. It does not backfill historical quotes.')
        st.markdown(f'**Match:** {display_match}')

    with trade_value:
        st.subheader('Optional: your independent fair-value estimate')
        st.caption('Manual scenario only. No tennis probability model is connected yet. A positive theoretical edge is not an executable profit.')
        p_pct = st.number_input('Your estimated chance of YES (%)', min_value=0.0,max_value=100.0,value=50.0,step=0.5)
        estimated_fee_c = st.number_input('Assumed total trading costs per contract (¢)', min_value=0.0,max_value=100.0,value=2.0,step=0.5,help='Illustrative flat cost for both entry and eventual exit. NOT an official Kalshi fee calculation.')
        opp = best_opportunity(row,p_pct/100,estimated_fee_c)
        if opp:
            action, edge, price = opp
            st.metric('Best theoretical contract edge',f'{edge:+.2f}¢',help='Value relative to your own probability estimate after your assumed costs; ignores model uncertainty, market moves and inability to fill at displayed size.')
            st.write(f'**Scenario:** {action} at approximately {price:.2f}¢ · **Estimated value difference:** {edge:+.2f}¢/contract')
            if edge <= 0:
                st.info('No positive theoretical edge under these assumptions.')
            else:
                st.warning('Positive model-based edge is hypothetical. Verify market settlement rules and actual fees before acting.')
        else:
            st.info('No usable quote for value comparison.')

    with data_explorer:
        st.subheader('Kalshi Market Data Explorer')
        st.caption('Public Kalshi API data for the selected tennis contract. Quotes and trades are exchange data, not an independent tennis prediction. No account access or orders.')
        st.write(f'**Selected match:** {display_match}')
        st.caption('Advanced data is loaded only when you request it. Start with market details, then order-book depth or recent trades.')
        depth = st.selectbox('Order-book levels per side', [5, 10, 20, 50, 100, 0], index=2,
                             format_func=lambda x: 'All levels' if x == 0 else str(x))
        details_col, book_col, trades_col, candles_col = st.columns(4)

        if details_col.button('Load market details', key='load_market_details'):
            try:
                details = get_market(selected)
                st.session_state['kalshi_market_details'] = {'ticker': selected, 'data': details}
            except (requests.RequestException, ValueError) as exc:
                st.error(f'Market details unavailable: {exc}')
        if book_col.button('Load order book', key='load_order_book'):
            try:
                ladder = get_orderbook(selected, depth=depth)
                st.session_state['kalshi_orderbook'] = {'ticker': selected, 'depth': depth, 'data': ladder}
            except (requests.RequestException, ValueError) as exc:
                st.error(f'Order book unavailable: {exc}')
        if trades_col.button('Load recent trades', key='load_recent_trades'):
            try:
                trades = get_trades(selected)
                st.session_state['kalshi_trades'] = {'ticker': selected, 'data': trades}
            except (requests.RequestException, ValueError) as exc:
                st.error(f'Recent trades unavailable: {exc}')

        candles_col.caption('Historical candles below')
        candle_period = st.selectbox('Candle interval', ['1 hour', '1 minute', '1 day'], index=0)
        candle_days = st.slider('Historical window (days)', min_value=1, max_value=7, value=2)
        period = {'1 minute': 1, '1 hour': 60, '1 day': 1440}[candle_period]
        if st.button('Load historical candles', key='load_candles'):
            try:
                candles = get_candlesticks(selected, row['tour'], days=candle_days, period_minutes=period)
                st.session_state['kalshi_candles'] = {'ticker': selected, 'period': period, 'days': candle_days, 'data': candles}
            except (requests.RequestException, ValueError) as exc:
                st.error(f'Candlesticks unavailable: {exc}')

        st.markdown('#### Market information and settlement rules')
        detail_record = st.session_state.get('kalshi_market_details', {})
        if detail_record.get('ticker') == selected:
            info = detail_record['data']
            summary_keys = ['ticker', 'status', 'title', 'yes_sub_title', 'no_sub_title',
                            'volume_fp', 'volume_24h_fp', 'open_interest_fp', 'liquidity_dollars',
                            'open_time', 'close_time', 'settlement_ts', 'rules_primary', 'rules_secondary']
            st.json({key: info.get(key) for key in summary_keys if key in info})
            with st.expander('All returned market fields'):
                st.json(info)
        else:
            st.caption('Select Load market details to view the available exchange metadata.')

        st.markdown('#### Order-book depth')
        book_record = st.session_state.get('kalshi_orderbook', {})
        if book_record.get('ticker') == selected:
            ladder_df = pd.DataFrame(orderbook_rows(book_record['data']))
            if ladder_df.empty:
                st.info('No active orders in the returned book.')
            else:
                st.dataframe(ladder_df, use_container_width=True, hide_index=True)
            st.caption('Kalshi returns YES and NO bids; the opposite-side ask is inferred as 100¢ minus the bid, not a separate posted ask.')
        else:
            st.caption('Select Load order book to view current bids and size.')

        st.markdown('#### Latest completed trades')
        trade_record = st.session_state.get('kalshi_trades', {})
        if trade_record.get('ticker') == selected:
            trades_df = pd.DataFrame(trade_record['data'])
            if trades_df.empty:
                st.info('No trades returned for this contract.')
            else:
                st.dataframe(trades_df, use_container_width=True, hide_index=True)
                st.download_button('Download recent trades CSV', trades_df.to_csv(index=False),
                                   file_name=f'{selected}_trades.csv', mime='text/csv')
        else:
            st.caption('Select Load recent trades to inspect transaction prices, sizes and times.')

        st.markdown('#### Kalshi historical candles')
        candle_record = st.session_state.get('kalshi_candles', {})
        if candle_record.get('ticker') == selected:
            candles_df = pd.DataFrame(candle_rows(candle_record['data']))
            if candles_df.empty:
                st.info('No candle records returned for the selected timeframe.')
            else:
                candles_df['Time (UTC)'] = pd.to_datetime(candles_df['Time (UTC)'], utc=True)
                plot = candles_df.set_index('Time (UTC)')
                st.line_chart(plot[['YES bid close (¢)', 'YES ask close (¢)', 'Last traded close (¢)']],
                              y_label='YES contract price (¢)')
                st.dataframe(candles_df, use_container_width=True, hide_index=True)
        else:
            st.caption('Select Load historical candles to retrieve exchange historical prices.')

        st.divider()
        st.caption('Historical Kalshi.com screenshot: Huertas Del Pino vs. Schenekenberg showed **$662,768 vol**. Live WebSocket dollar volume is the preferred data source; the audit below compares REST contract counts for diagnosis only.')
        with st.expander('Verify Kalshi volume against the exchange', expanded=False):
            st.caption('Fetch a fresh, uncached Kalshi event snapshot and inspect cumulative volume for each outcome. The dropdown total is calculated by this app; this check does not assume Kalshi.com uses the same event formula.')
            audit_event = st.text_input(
                'Event ID to check',
                value='KXATPCHALLENGERMATCH-26NOV23HUESCH' if chosen_event == 'KXATPCHALLENGERMATCH-26NOV23HUESCH' else chosen_event,
                help='Use the match you selected, or enter the Huertas Del Pino vs Schenekenberg event KXATPCHALLENGERMATCH-26NOV23HUESCH.',
                key='audit_event_id',
            ).strip()
            website_reference = st.number_input(
                'Volume currently displayed on Kalshi.com (optional)',
                min_value=0, value=0, step=1,
                help='Enter the full number without a dollar sign. Compare values captured at approximately the same time; an old screenshot is not a live reference.',
            )
            if st.button('Fetch and compare volume', key='audit_volume_now'):
                try:
                    live_snapshot = get_event_snapshot(audit_event)
                    st.session_state['volume_audit_result'] = reconciliation_report(
                        live_snapshot, website_reference if website_reference > 0 else None
                    )
                except (requests.RequestException, ValueError, TypeError) as exc:
                    st.error(f'Unable to retrieve event volume: {exc}')
            audit = st.session_state.get('volume_audit_result')
            if audit:
                st.caption(f"API snapshot at {audit.get('retrieved_at', 'unknown')} · event {audit.get('event_ticker') or audit_event}")
                x1, x2, x3 = st.columns(3)
                x1.metric('Sum of contracts', whole_dollars(audit['sum']))
                x2.metric('Largest single contract', whole_dollars(audit['largest']))
                x3.metric('Kalshi event field', whole_dollars(audit['published_event_volume']))
                st.caption('The event-volume field shows N/A when Kalshi did not return one. Sum and largest-contract values are calculations, not authoritative website totals.')
                if audit['contracts']:
                    st.dataframe(pd.DataFrame(audit['contracts']), hide_index=True, use_container_width=True)
                else:
                    st.warning('No child markets returned for this event. A historical event may require a different API path.')
                if audit['reference'] is not None:
                    st.metric('Website reference entered', whole_dollars(audit['reference']))
                    if audit['difference'] is None:
                        st.warning('Cannot compare: at least one contract volume is missing.')
                    elif audit['matches_sum']:
                        st.success('The summed API volumes match the website reference at the times sampled. This does not establish a universal calculation rule.')
                    else:
                        st.warning(f"Difference from sum: {whole_dollars(abs(audit['difference']))}. The website may use a different rule or the figures may be from different times.")
                st.caption('The $662,768 screenshot is from November 23, 2026. A later live API snapshot cannot independently verify the earlier figure without timestamped volume history.')

        st.caption('For authenticated real-time WebSocket streams, portfolio data, and long-term archival storage, a separate service is required.')


dashboard()
