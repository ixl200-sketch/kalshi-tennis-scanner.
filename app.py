"""Kalshi Tennis Scanner — market data only, no orders or portfolio access."""
from datetime import datetime, timezone
import pandas as pd
import streamlit as st
from scanner import SERIES, scan, save_snapshots, history, best_opportunity

st.set_page_config(page_title='Kalshi Tennis Scanner', page_icon='🎾', layout='wide')
st.title('Kalshi Tennis Scanner')
st.caption('Read-only public Kalshi market data · polling, not tick-by-tick · no live tennis score feed')

with st.sidebar:
    st.header('Scanner controls')
    tours = st.multiselect('Match-winner series', list(SERIES), default=['ATP','WTA','ATP Challenger','WTA Challenger','ITF'])
    refresh = st.selectbox('Refresh while dashboard is open', ['Manual', '30 seconds', '60 seconds', '120 seconds'], index=1)
    max_spread = st.slider('Maximum YES spread (¢)', 1, 50, 20)
    min_volume = st.number_input('Minimum 24h contracts traded', min_value=0, value=0, step=25)
    st.info('Prices are quotes, not guarantees of fill. No trades are submitted.')
    st.markdown('[Kalshi API documentation](https://docs.kalshi.com/api-reference/market/get-markets)')

if not tours:
    st.warning('Select at least one series.'); st.stop()

interval = {'Manual': None, '30 seconds':'30s','60 seconds':'60s','120 seconds':'120s'}[refresh]

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
    overview, watchlist, price_history, trade_value = st.tabs([
        'Market Overview',
        'Market Watchlist',
        'Price History',
        'Trade Value Analysis',
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
        selected = st.selectbox(
            'Ticker',
            df['ticker'].tolist(),
            format_func=lambda t: f"{df.loc[df['ticker'] == t, 'title'].iloc[0]} | {t}",
            help='Select a market for Price History and Trade Value Analysis.',
        )
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
            show_cols = ['tour','title','yes_label','bid_c','ask_c','spread_c','last_c','volume_24h','open_interest','ticker']
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
        st.markdown(f'**Market ticker:** `{selected}` · **Event:** `{row["event_ticker"]}`')

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


dashboard()
