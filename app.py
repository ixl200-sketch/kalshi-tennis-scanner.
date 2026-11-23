"""Kalshi Tennis Scanner — market data only, no orders or portfolio access."""
from datetime import datetime, timezone
import pandas as pd
import streamlit as st
from kalshi_theme import apply_theme
from scanner import SERIES, scan, save_snapshots, history, best_opportunity
from kalshi_data import get_market, get_orderbook, orderbook_rows, get_trades, get_candlesticks, candle_rows
import requests
from match_labels import event_labels, fetch_event_metadata, player_name, ranked_event_volumes, format_notional_volume

st.set_page_config(page_title='Kalshi Tennis Scanner', page_icon='🎾', layout='wide')
apply_theme()
st.title('Kalshi Tennis Scanner')
st.caption('Independent project · not affiliated with Kalshi · read-only public market data · polling, not tick-by-tick · no live tennis score feed')

with st.sidebar:
    st.header('Scanner controls')
    tours = st.multiselect('Match-winner series', list(SERIES), default=['ATP','WTA','ATP Challenger','WTA Challenger','ITF'])
    st.caption('Market data refreshes automatically every 60 seconds while this dashboard is open.')
    max_spread = st.slider('Maximum YES spread (¢)', 1, 50, 20)
    min_volume = st.number_input('Minimum 24h contracts traded', min_value=0, value=0, step=25)
    st.info('Prices are quotes, not guarantees of fill. No trades are submitted.')
    st.markdown('[Kalshi API documentation](https://docs.kalshi.com/api-reference/market/get-markets)')

if not tours:
    st.warning('Select at least one series.'); st.stop()

interval = '60s'  # Refresh live market data every minute while the page is open.

@st.cache_data(ttl=600, show_spinner=False)
def cached_event_metadata(selected_tours):
    return fetch_event_metadata(selected_tours)


@st.fragment(run_every=interval)
def dashboard():
    if st.button('Refresh now', type='primary'):
        pass
    started = datetime.now(timezone.utc)
    with st.spinner('Fetching open markets from Kalshi…'):
        rows, errors = scan(tours)
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
    # Preserve snapshots even when active display filters hide the rows.
    try:
        save_snapshots(rows)
    except Exception as exc:
        st.warning(f'Unable to store local history: {exc}')
    df = pd.DataFrame(rows)
    with market_controls:
        st.caption(f'Last requested: {started.strftime("%Y-%m-%d %H:%M:%S UTC")} · {len(rows)} open market contracts received · {len(tours)} series queried')
        # Display tournament + matchup to users; ticker IDs remain internal API keys.
        match_rows = df.to_dict('records')
        event_info = cached_event_metadata(tuple(tours))
        labels = event_labels(match_rows, event_info)
        event_groups = {}
        for market in match_rows:
            group_id = market.get('event_ticker') or market['ticker']
            event_groups.setdefault(group_id, []).append(market)
        # Aggregate cumulative Kalshi volume_fp across distinct match contracts.
        # Notional $ amounts represent $1 settlement face value per contract.
        ranked_events = ranked_event_volumes(event_groups)
        event_volume = dict(ranked_events)
        st.caption('Total match volume since opening (Kalshi volume_fp). Whole-dollar $1-per-contract notional; not actual cash paid. Refreshed every 60 seconds.')
        # Recreate the display options from the newly fetched volume on EVERY
        # 60-second fragment rerun. String options force Streamlit to refresh the
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
            help='Cumulative volume from Kalshi volume_fp across distinct open contracts in this match, refreshed every 60 seconds. Displayed as whole-dollar settlement notional; N/A means missing data. Kalshi website totals may use different event accounting.',
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

    with overview:
        c1,c2,c3,c4 = st.columns(4)
        c1.metric('Open contracts',len(df))
        c2.metric('With two-sided quotes', int(df['spread_c'].notna().sum()))
        c3.metric('Median quoted spread', f"{df['spread_c'].median():.1f}¢" if df['spread_c'].notna().any() else 'N/A')
        c4.metric('24h volume (sum)', f"{df['volume_24h'].sum():,.0f}")

    with watchlist:
        filtered = df.loc[(df['spread_c'].notna()) & (df['spread_c'] <= max_spread) & (df['volume_24h'] >= min_volume)].copy()
        st.caption('Filters identify liquid, tighter-spread contracts — not necessarily mispricings. Match events may have two separate player contracts; do not add their volumes as unique matches.')
        if filtered.empty:
            st.info('No contracts pass your current spread and volume filters.')
        else:
            filtered = filtered.sort_values(['spread_c','volume_24h'],ascending=[True,False])
            filtered['Match'] = filtered['event_ticker'].map(labels)
            show_cols = ['Match','yes_label','bid_c','ask_c','spread_c','last_c','volume_24h','open_interest']
            st.dataframe(filtered[show_cols].rename(columns={'bid_c':'YES bid ¢','ask_c':'YES ask ¢','spread_c':'Spread ¢','last_c':'Last ¢','volume_24h':'24h volume','open_interest':'Open interest','yes_label':'YES outcome'}), hide_index=True, use_container_width=True)
            st.download_button('Export watchlist CSV', filtered.to_csv(index=False), file_name='kalshi_tennis_watchlist.csv', mime='text/csv')

    with price_history:
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
        st.info('Use the buttons below to request detailed data on demand. This avoids fetching every order book on every dashboard refresh.')
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
        st.caption('For authenticated real-time WebSocket streams, portfolio data, and long-term archival storage, a separate service is required.')


dashboard()
