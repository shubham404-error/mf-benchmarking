import streamlit as st
import pandas as pd
import numpy as np
import datetime
import os
from google import genai
import plotly.express as px

from data import search_schemes, fetch_scheme_history, fetch_benchmark_series, classify_category
from metrics import calculate_trailing_returns, calculate_risk_metrics, calculate_rolling_returns, xirr, returns_based_style_analysis
from config import CATEGORY_RULES, STYLE_FACTORS, DEFAULT_RISK_FREE_RATE

st.set_page_config(page_title="MF Benchmarking", layout="wide")

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&display=swap');
@import url('https://api.fontshare.com/v2/css?f[]=clash-display@400,500,600,700&display=swap');

html, body, [class*="css"]  {
    font-family: 'Inter', sans-serif !important;
}
h1, h2, h3, h4, h5, h6 {
    font-family: 'Clash Display', sans-serif !important;
}

/* Hide Hamburger Menu and Footer */
#MainMenu {visibility: hidden;}
footer {visibility: hidden;}

/* KPI Metric Cards Styling */
[data-testid="stMetric"] {
    background-color: #1E1E1E; /* Dark theme background */
    border: 1px solid #333333;
    border-radius: 8px;
    padding: 15px;
    box-shadow: 0 4px 6px rgba(0, 0, 0, 0.3);
}
</style>
""", unsafe_allow_html=True)

# Sidebar setup
st.sidebar.title("Settings")
rfr_input = st.sidebar.slider("Risk Free Rate (%)", 0.0, 15.0, DEFAULT_RISK_FREE_RATE * 100) / 100.0

try:
    gemini_api_key = st.secrets.get("GEMINI_API_KEY") or os.environ.get("GEMINI_API_KEY")
    if gemini_api_key:
        gemini_client = genai.Client(api_key=gemini_api_key)
    else:
        gemini_client = None
except Exception:
    gemini_client = None

def get_gemini_insights(prompt, retries=3):
    if not gemini_client:
        return "Please configure the Gemini API Key in Streamlit secrets (.streamlit/secrets.toml) to view AI insights."
    
    delay = 2
    for attempt in range(retries):
        try:
            response = gemini_client.models.generate_content(
                model='gemini-2.5-flash',
                contents=prompt
            )
            return response.text
        except Exception as e:
            error_str = str(e).lower()
            if "503" in error_str or "unavailable" in error_str or "429" in error_str or "quota" in error_str:
                if attempt == retries - 1:
                    return "⚠️ **AI Insights Temporarily Unavailable**\n\nThe Gemini AI model is currently experiencing high demand. Please wait a few minutes and try again."
                import time
                time.sleep(delay)
                delay *= 2
            else:
                if attempt == retries - 1:
                    return f"⚠️ **Error Fetching Insights:**\n\n{str(e)}"
                import time
                time.sleep(delay)
                delay *= 2
    return "⚠️ **Error:** Max retries exceeded while connecting to the AI."

# Shared helper
def fund_picker(key_prefix):
    query = st.text_input("Search Fund (min 3 chars)", key=f"{key_prefix}_search")
    if len(query) >= 3:
        results = search_schemes(query)
        if results:
            # Filter to streamline list: only growth options, no regular, no dividend, no idcw
            filtered = []
            for r in results:
                name = r['schemeName'].lower()
                # Exclude regular, dividend, idcw
                if "regular" in name or "dividend" in name or "idcw" in name or "div" in name:
                    continue
                # Ensure it's a growth option (often contains "growth" or is implied in some direct plans)
                if "growth" in name or "direct" in name:
                    filtered.append(r)
                    
            if not filtered:
                st.info("No matching Growth options found. Try another search.")
                return None
                
            options = {f"{r['schemeName']} ({r['schemeCode']})": str(r['schemeCode']) for r in filtered}
            selected = st.selectbox("Select Scheme", options.keys(), key=f"{key_prefix}_select")
            return options[selected]
    return None

page = st.sidebar.radio("Navigation", ["Scorecard", "Comparison", "Style Drift", "Client Holdings"])

if page == "Scorecard":
    st.header("Fund Scorecard")
    scheme_code = fund_picker("sc")
    
    if scheme_code:
        with st.spinner("Fetching data..."):
            meta, nav_series = fetch_scheme_history(scheme_code)
            if nav_series is not None and not nav_series.empty:
                cat_string = meta.get("scheme_category", "")
                cat_label, default_bench = classify_category(cat_string)
                
                # Header Block
                st.markdown(f"<h1>{meta.get('scheme_name', 'Unknown')}</h1>", unsafe_allow_html=True)
                st.markdown(f"**Category:** `{cat_label}` | **AMFI String:** `{cat_string}`")
                
                # Benchmark override
                bench_options = {label: ticker for _, label, ticker in CATEGORY_RULES if ticker}
                bench_options["None (No Benchmark)"] = None
                
                default_idx = len(bench_options) - 1 # Default to 'None (No Benchmark)'
                if default_bench:
                    bench_names = list(bench_options.keys())
                    for i, (name, ticker) in enumerate(bench_options.items()):
                        if ticker == default_bench:
                            default_idx = i
                            break
                            
                selected_bench_name = st.selectbox("Benchmark", list(bench_options.keys()), index=default_idx)
                selected_bench_ticker = bench_options[selected_bench_name]
                
                if selected_bench_ticker:
                    st.caption("*Note: Benchmark data uses tradeable ETF/Index proxies (e.g., ^NSEMDCP50, HDFCSML250.NS). Minor tracking errors vs AMC reported benchmarks may exist.*")
                
                # Fetch Benchmark
                bench_series = None
                if selected_bench_ticker:
                    start_date = nav_series.index[0]
                    bench_series = fetch_benchmark_series(selected_bench_ticker, start_date)
                    if bench_series is not None:
                        if isinstance(bench_series, pd.DataFrame):
                            bench_series = bench_series.iloc[:, 0]
                        bench_series.index = bench_series.index.tz_localize(None)

                # Computations
                trailing = calculate_trailing_returns(nav_series)
                risk = calculate_risk_metrics(nav_series, bench_series, rfr_input)
                
                # KPI Row (Top)
                st.markdown("### Key Metrics")
                kpi_col1, kpi_col2, kpi_col3 = st.columns(3)
                
                with kpi_col1:
                    ret_1y = trailing.get("1Y")
                    st.metric("1Y Return", f"{ret_1y*100:.2f}%" if ret_1y is not None else "N/A")
                with kpi_col2:
                    alpha = risk.get("alpha")
                    st.metric("Risk-Adjusted Alpha", f"{alpha*100:.2f}%" if alpha is not None else "N/A")
                with kpi_col3:
                    max_dd = risk.get("max_drawdown")
                    st.metric("Max Drawdown", f"{max_dd*100:.2f}%" if max_dd is not None else "N/A")

                st.markdown("---")
                
                # The Main Visual (Center) & Narrative Block (Right)
                main_col, narr_col = st.columns([2, 1])
                
                with main_col:
                    st.write("### Growth of ₹10,000")
                    if bench_series is not None and not bench_series.empty:
                        aligned = pd.concat([nav_series, bench_series], axis=1, join="inner").dropna()
                        if not aligned.empty:
                            aligned.columns = ["Fund", "Benchmark"]
                            growth = (aligned / aligned.iloc[0]) * 10000
                            fig = px.line(growth, color_discrete_sequence=['#4A7056', '#888888'])
                        else:
                            growth = (nav_series / nav_series.iloc[0]) * 10000
                            fig = px.line(growth, color_discrete_sequence=['#4A7056'])
                    else:
                        growth = (nav_series / nav_series.iloc[0]) * 10000
                        fig = px.line(growth, color_discrete_sequence=['#4A7056'])
                    
                    fig.update_layout(xaxis_title="", yaxis_title="Value (₹)", margin=dict(l=0, r=0, t=30, b=0), paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
                    st.plotly_chart(fig, use_container_width=True)
                
                with narr_col:
                    st.write("### Analyst Summary")
                    with st.spinner("Analyzing with Gemini..."):
                        prompt = f"""
                        Act as a financial advisor. Summarize the performance of the mutual fund {meta.get('scheme_name', 'Unknown')}.
                        Category: {cat_label}
                        Trailing Returns: {trailing}
                        Risk Metrics: {risk}
                        
                        Provide a 2-3 paragraph summary focusing on:
                        1. Is this fund earning its keep against the benchmark?
                        2. How does the risk-adjusted return (Sharpe, Alpha) look?
                        Keep it professional but easy to understand for a client.
                        """
                        insights = get_gemini_insights(prompt)
                        st.info(insights)

                st.markdown("---")
                
                # Progressive Disclosure (Bottom)
                st.write("### Detailed Analysis")
                with st.expander("View Trailing Returns"):
                    trail_df = pd.DataFrame([{"Period": k, "Return": f"{v*100:.2f}%" if v is not None else "N/A"} for k, v in trailing.items()])
                    st.dataframe(trail_df, hide_index=True)
                
                with st.expander("View Risk Matrix"):
                    risk_display = {
                        "Volatility": f"{risk.get('annualized_volatility', 0)*100:.2f}%",
                        "Sharpe Ratio": f"{risk.get('sharpe_ratio', 0):.2f}",
                        "Max Drawdown": f"{risk.get('max_drawdown', 0)*100:.2f}%",
                        "Beta": f"{risk.get('beta'):.2f}" if risk.get('beta') is not None else "N/A",
                        "Alpha": f"{risk.get('alpha', 0)*100:.2f}%" if risk.get('alpha') is not None else "N/A",
                    }
                    st.table(pd.DataFrame(list(risk_display.items()), columns=["Metric", "Value"]))
                    
                with st.expander("View 1-Year Rolling Returns Chart"):
                    rolling = calculate_rolling_returns(nav_series)
                    if not rolling.dropna().empty:
                        fig_roll = px.line(rolling.dropna() * 100, color_discrete_sequence=['#4A7056'])
                        fig_roll.update_layout(xaxis_title="", yaxis_title="Rolling 1Y Return (%)", margin=dict(l=0, r=0, t=10, b=0))
                        st.plotly_chart(fig_roll, use_container_width=True)
                    else:
                        st.info("Not enough data to calculate 1-Year Rolling Returns (requires > 1 year of NAV history).")
            else:
                st.error("Could not fetch NAV history for this scheme.")

elif page == "Comparison":
    st.header("Fund Comparison")
    st.caption("Build your own comparison list by searching and adding funds one at a time.")
    
    if "compare_list" not in st.session_state:
        st.session_state.compare_list = []
        
    col1, col2 = st.columns([3, 1])
    with col1:
        scheme_code = fund_picker("comp")
    with col2:
        if st.button("Add to Comparison") and scheme_code:
            if scheme_code not in st.session_state.compare_list:
                st.session_state.compare_list.append(scheme_code)
                st.success("Added!")
            else:
                st.warning("Already in list.")
                
    if st.button("Clear List"):
        st.session_state.compare_list = []
        
    if st.session_state.compare_list:
        st.write("### Comparison Matrix")
        compare_data = []
        for code in st.session_state.compare_list:
            meta, nav = fetch_scheme_history(code)
            if nav is not None and not nav.empty:
                trail = calculate_trailing_returns(nav)
                risk = calculate_risk_metrics(nav, None, rfr_input) # Simplified, no benchmark for grid
                
                compare_data.append({
                    "Fund": meta.get("scheme_name", code),
                    "1Y CAGR": trail.get("1Y"),
                    "3Y CAGR": trail.get("3Y"),
                    "Volatility": risk.get("annualized_volatility"),
                    "Sharpe": risk.get("sharpe_ratio"),
                    "Max Drawdown": risk.get("max_drawdown")
                })
        
        if compare_data:
            df_comp = pd.DataFrame(compare_data)
            # Format
            df_comp_fmt = df_comp.copy()
            for col in ["1Y CAGR", "3Y CAGR", "Volatility", "Max Drawdown"]:
                df_comp_fmt[col] = df_comp_fmt[col].apply(lambda x: f"{x*100:.2f}%" if pd.notnull(x) else "N/A")
            df_comp_fmt["Sharpe"] = df_comp_fmt["Sharpe"].apply(lambda x: f"{x:.2f}" if pd.notnull(x) else "N/A")
            st.dataframe(df_comp_fmt, hide_index=True)

            if st.button("Generate AI Comparison"):
                with st.spinner("Analyzing with Gemini..."):
                    prompt = f"""
                    Act as a financial advisor. Compare the following mutual funds based on their metrics:
                    {df_comp.to_string()}
                    
                    Identify the best performer in terms of returns, the least volatile fund, and give a recommendation based on risk-adjusted returns (Sharpe).
                    """
                    insights = get_gemini_insights(prompt)
                    st.info(insights)

elif page == "Style Drift":
    st.header("Style Drift Monitor")
    scheme_code = fund_picker("drift")
    
    if scheme_code:
        with st.spinner("Analyzing Style..."):
            meta, nav = fetch_scheme_history(scheme_code)
            if nav is not None and len(nav) > 252 * 1.5: # ~1.5 years
                st.write(f"**{meta.get('scheme_name')}** - Stated Category: {meta.get('scheme_category')}")
                
                # Fetch style factors
                factor_navs = {}
                start_date = nav.index[0]
                for factor_name, ticker in STYLE_FACTORS.items():
                    s = fetch_benchmark_series(ticker, start_date)
                    if s is not None:
                        if isinstance(s, pd.DataFrame):
                            s = s.iloc[:, 0]
                        s.index = s.index.tz_localize(None)
                        factor_navs[factor_name] = s
                        
                if len(factor_navs) == 3:
                    factor_df = pd.DataFrame(factor_navs).dropna()
                    aligned = pd.concat([nav, factor_df], axis=1, join="inner").dropna()
                    
                    if not aligned.empty:
                        # Weekly resample
                        weekly = aligned.resample("W-FRI").last().pct_change().dropna()
                        fund_weekly = weekly.iloc[:, 0]
                        factors_weekly = weekly.iloc[:, 1:]
                        
                        # Rolling 52-week regression
                        window = 52
                        step = 4
                        
                        drift_records = []
                        for i in range(0, len(weekly) - window + 1, step):
                            w_fund = fund_weekly.iloc[i:i+window]
                            w_factors = factors_weekly.iloc[i:i+window]
                            
                            weights = returns_based_style_analysis(w_fund, w_factors.values)
                            if weights is not None:
                                date = w_fund.index[-1]
                                drift_records.append({
                                    "Date": date,
                                    "Large Cap": weights[0],
                                    "Mid Cap": weights[1],
                                    "Small Cap": weights[2]
                                })
                                
                        if drift_records:
                            drift_df = pd.DataFrame(drift_records).set_index("Date")
                            st.area_chart(drift_df * 100)
                            
                            current_style = drift_df.iloc[-1]
                            dom_style = current_style.idxmax()
                            st.write(f"**Current Dominant Style (Returns-based):** {dom_style} ({current_style.max()*100:.1f}%)")
                else:
                    st.warning("Could not fetch all style factor benchmarks.")
            else:
                st.warning("Not enough history (requires ~1.5 years) for rolling style analysis.")

elif page == "Client Holdings":
    st.header("Client Holdings Benchmarking")
    
    col1, col2, col3 = st.columns(3)
    with col1:
        scheme_code = fund_picker("hold")
    with col2:
        amount = st.number_input("Investment Amount (₹)", min_value=1000, step=1000)
    with col3:
        purch_date = st.date_input("Purchase Date", max_value=datetime.date.today())
        
    if st.button("Add Holding") and scheme_code:
        if "holdings" not in st.session_state:
            st.session_state.holdings = []
        st.session_state.holdings.append({
            "code": scheme_code,
            "amount": amount,
            "date": purch_date
        })
        st.success("Holding added.")
        
    if "holdings" in st.session_state and st.session_state.holdings:
        st.write("### Portfolio Benchmarking")
        
        results = []
        for h in st.session_state.holdings:
            meta, nav = fetch_scheme_history(h["code"])
            if nav is not None and not nav.empty:
                pd_date = pd.Timestamp(h["date"])
                
                past_navs = nav[nav.index <= pd_date]
                if past_navs.empty:
                    st.warning(f"Purchase date {pd_date.date()} is before {meta.get('scheme_name')} inception or data is unavailable.")
                    continue
                nav_at_purch = past_navs.iloc[-1]
                units = h["amount"] / nav_at_purch
                
                latest_nav = nav.iloc[-1]
                latest_date = nav.index[-1]
                current_val = units * latest_nav
                
                cashflows = [(pd_date, -h["amount"]), (latest_date, current_val)]
                fund_xirr = xirr(cashflows)
                
                # Benchmark equivalent
                bench_xirr = None
                cat_label, default_bench = classify_category(meta.get("scheme_category"))
                if default_bench:
                    bench = fetch_benchmark_series(default_bench, nav.index[0])
                    if bench is not None:
                        if isinstance(bench, pd.DataFrame):
                            bench = bench.iloc[:, 0]
                        bench.index = bench.index.tz_localize(None)
                        past_bench = bench[bench.index <= pd_date]
                        if not past_bench.empty:
                            bench_at_purch = past_bench.iloc[-1]
                            bench_units = h["amount"] / bench_at_purch
                            latest_bench = bench.iloc[-1]
                            bench_val = bench_units * latest_bench
                            
                            bench_cfs = [(pd_date, -h["amount"]), (bench.index[-1], bench_val)]
                            bench_xirr = xirr(bench_cfs)
                            
                results.append({
                    "Fund": meta.get("scheme_name"),
                    "Amount Invested": h["amount"],
                    "Current Value": current_val,
                    "Fund XIRR": fund_xirr,
                    "Benchmark XIRR": bench_xirr
                })
                
        if results:
            df_res = pd.DataFrame(results)
            df_fmt = df_res.copy()
            df_fmt["Current Value"] = df_fmt["Current Value"].apply(lambda x: f"₹{x:,.2f}")
            df_fmt["Fund XIRR"] = df_fmt["Fund XIRR"].apply(lambda x: f"{x*100:.2f}%" if x else "N/A")
            df_fmt["Benchmark XIRR"] = df_fmt["Benchmark XIRR"].apply(lambda x: f"{x*100:.2f}%" if x else "N/A")
            st.dataframe(df_fmt, hide_index=True)
