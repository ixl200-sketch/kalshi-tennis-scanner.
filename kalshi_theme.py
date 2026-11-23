"""Kalshi-inspired presentation only; no market/trading calculations."""
import streamlit as st

def apply_theme():
    """Apply scoped CSS to Streamlit's existing dashboard components."""
    st.markdown("""
    <style>
    :root {
        --kalshi-green: #00B67A;
        --kalshi-dark: #014737;
        --kalshi-bright: #00DD94;
        --kalshi-surface: #F5F7F4;
        --kalshi-text: #050D0A;
    }

    .stApp, [data-testid="stAppViewContainer"] {
        background-color: #FFFFFF;
        color: var(--kalshi-text);
    }
    [data-testid="stSidebar"] {
        background-color: var(--kalshi-surface);
        border-right: 1px solid #E1E8E2;
    }
    h1, h2, h3, h4 { color: var(--kalshi-dark); }
    a, a:visited { color: var(--kalshi-dark); }

    /* Clearly labeled navigation and active state. */
    .stTabs [data-baseweb="tab-list"] {
        gap: .45rem;
        border-bottom: 1px solid #DCE8DF;
        flex-wrap: wrap;
    }
    .stTabs [data-baseweb="tab"] {
        color: var(--kalshi-dark);
        background: var(--kalshi-surface);
        border-radius: .65rem .65rem 0 0;
        font-weight: 600;
        padding: .65rem 1rem;
    }
    .stTabs [data-baseweb="tab"][aria-selected="true"] {
        color: var(--kalshi-dark);
        background: #E2F8EE;
        box-shadow: inset 0 -3px 0 var(--kalshi-green);
    }
    .stTabs [data-baseweb="tab-highlight"] {
        background-color: var(--kalshi-green);
    }

    /* Metric cards: readable on the light background. */
    [data-testid="stMetric"] {
        background: var(--kalshi-surface);
        border: 1px solid #E0EAE3;
        border-radius: 12px;
        padding: 1rem;
    }
    [data-testid="stMetricValue"] {
        color: var(--kalshi-dark);
        font-weight: 700;
    }

    /* Streamlit primary buttons and form focus. */
    .stButton button[kind="primary"],
    .stDownloadButton button[kind="primary"] {
        background-color: var(--kalshi-green);
        border-color: var(--kalshi-green);
        color: var(--kalshi-text);
        font-weight: 700;
    }
    .stButton button[kind="primary"]:hover,
    .stDownloadButton button[kind="primary"]:hover {
        background-color: var(--kalshi-dark);
        border-color: var(--kalshi-dark);
        color: #FFFFFF;
    }
    button:focus-visible, [role="tab"]:focus-visible {
        outline: 3px solid var(--kalshi-green);
        outline-offset: 2px;
    }

    /* Tables and charts keep their native Streamlit behavior. */
    [data-testid="stDataFrame"] {
        border: 1px solid #E0EAE3;
        border-radius: 10px;
        overflow: hidden;
    }
    [data-testid="stAlert"] { border-radius: 10px; }
    </style>
    """, unsafe_allow_html=True)
