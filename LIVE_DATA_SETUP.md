# Enable real-time Kalshi ticker updates (read-only)

The scanner uses the public REST API to discover open tennis markets every 60 seconds.
When authorized, it also listens to the Kalshi **ticker** WebSocket channel
for exchange-reported **`dollar_volume`**, contract `volume_fp`, prices and quotes. Streamlit redraws
the selected dashboard approximately every **2 seconds** while the app is open.

## Configure in Streamlit Community Cloud

1. Generate a **market-data-only** API key in Kalshi settings. No trading/portfolio permission is needed.
2. In your Streamlit Cloud app, open **Manage app → Settings → Secrets**.
3. Add the following TOML secrets, replacing values with your actual key ID
   and PEM contents:

```toml
KALSHI_API_KEY_ID = "your-key-id"
KALSHI_PRIVATE_KEY_PEM = """-----BEGIN PRIVATE KEY-----
your-private-key-data
-----END PRIVATE KEY-----"""
```

4. Save secrets and restart the app. Never commit a private key to GitHub,
   share it in chat, or place it in a public frontend.
5. Look for the **Live feed connected** status in the dashboard. Open a match with
   active trading; ticker messages only arrive for markets with changes.

If secrets are absent or the WebSocket connection fails, the scanner falls
back to a 60-second REST refresh for prices and contract volumes. The dropdown
shows **N/A for dollar volume** rather than inventing an equivalent from contracts.

## What this does **not** guarantee

* Kalshi documents that ticker updates are combined in a roughly one-second
  flush cycle; that is not a guarantee of identical pixels or simultaneous
  figures on Kalshi.com and Streamlit.
* Streamlit's UI currently redraws about every 2 seconds, and browser sleep
  or connection interruption can delay it.
* The dropdown uses **`dollar_volume` directly from the WebSocket** for each distinct
  market and sums those reported dollar figures across the event. We do NOT turn
  `volume_fp` contract counts into dollars. The exact Kalshi.com match-page
  event aggregation is not independently verified, so exact parity is NOT guaranteed.
* When a contract has not emitted recent dollar-volume data, the whole event shows
  **N/A** rather than a misleading estimate. Individual ticker updates are
  scheduled by Kalshi approximately once a second when there are changes.
* No order placement or portfolio access exists.
* WebSocket connections are session/process dependent. For continuous 24/7
  collection, host a persistent worker or data service separately.

Official docs:
* https://docs.kalshi.com/websockets
* https://docs.kalshi.com/websockets/market-ticker
* https://docs.kalshi.com/getting_started/quick_start_websockets
