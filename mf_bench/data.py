import pandas as pd
import requests
import yfinance as yf
import streamlit as st
from config import CATEGORY_RULES, SCHEME_LIST_CACHE_TTL, NAV_HISTORY_CACHE_TTL, BENCHMARK_CACHE_TTL
import time
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

def _get_with_retry(url, retries=3):
    delay = 1
    for attempt in range(retries):
        try:
            resp = requests.get(url, timeout=10, verify=False)
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.RequestException as e:
            if attempt == retries - 1:
                raise e
            time.sleep(delay)
            delay *= 2
    return None

@st.cache_data(ttl=SCHEME_LIST_CACHE_TTL, show_spinner=False)
def search_schemes(query: str):
    if len(query) < 3:
        return []
    url = f"https://api.mfapi.in/mf/search?q={query}"
    try:
        data = _get_with_retry(url)
        return data if data else []
    except:
        return []

@st.cache_data(ttl=NAV_HISTORY_CACHE_TTL, show_spinner=False)
def fetch_scheme_history(scheme_code: str):
    url = f"https://api.mfapi.in/mf/{scheme_code}"
    try:
        data = _get_with_retry(url)
        if not data or "data" not in data:
            return None, None
            
        meta = data.get("meta", {})
        df = pd.DataFrame(data["data"])
        if df.empty:
            return meta, pd.Series()
            
        df["date"] = pd.to_datetime(df["date"], format="%d-%m-%Y", errors="coerce")
        df["nav"] = pd.to_numeric(df["nav"], errors="coerce")
        df = df.dropna(subset=["date", "nav"]).sort_values("date")
        df.set_index("date", inplace=True)
        
        return meta, df["nav"]
    except:
        return None, None

@st.cache_data(ttl=BENCHMARK_CACHE_TTL, show_spinner=False)
def fetch_benchmark_series(ticker, start_date):
    if not ticker:
        return None
    try:
        data = yf.download(ticker, start=start_date, progress=False)
        if not data.empty and "Close" in data:
            return data["Close"]
        return None
    except:
        return None

def classify_category(category_string):
    if not category_string:
        return "Other", None
    for keyword, label, ticker in CATEGORY_RULES:
        if keyword in category_string:
            return label, ticker
    return "Other", None
