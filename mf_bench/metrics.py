import pandas as pd
import numpy as np
from math import sqrt
from scipy.optimize import minimize, brentq
import datetime

TRAILING_PERIODS = [("1M", 30, False), ("3M", 91, False), ("6M", 182, False),
                    ("1Y", 365, True), ("3Y", 3*365, True), ("5Y", 5*365, True)]

def calculate_trailing_returns(nav_series):
    results = {}
    if nav_series.empty:
        return results
        
    latest_date = nav_series.index[-1]
    latest_nav = nav_series.iloc[-1]
    
    for label, days, is_annualized in TRAILING_PERIODS:
        target_date = latest_date - pd.Timedelta(days=days)
        # Find nearest date on or before target_date
        past_series = nav_series[nav_series.index <= target_date]
        if past_series.empty:
            results[label] = None
            continue
            
        past_nav = past_series.iloc[-1]
        
        if is_annualized:
            days_diff = (latest_date - past_series.index[-1]).days
            if days_diff > 0:
                ret = (latest_nav / past_nav) ** (365 / days_diff) - 1
            else:
                ret = None
        else:
            ret = (latest_nav / past_nav) - 1
            
        results[label] = ret
        
    return results

def calculate_risk_metrics(nav_series, bench_series, risk_free_rate):
    daily_ret = nav_series.pct_change().dropna()
    bench_daily_ret = bench_series.pct_change().dropna() if bench_series is not None else None
    
    if daily_ret.empty:
        return {}
        
    ann_vol = daily_ret.std() * sqrt(252)
    ann_ret = (1 + daily_ret.mean())**252 - 1
    sharpe = (ann_ret - risk_free_rate) / ann_vol if ann_vol > 0 else 0
    
    drawdown = nav_series / nav_series.cummax() - 1
    max_drawdown = drawdown.min()
    
    beta, alpha, tracking_error, info_ratio = None, None, None, None
    if bench_daily_ret is not None and not bench_daily_ret.empty:
        aligned = pd.concat([daily_ret, bench_daily_ret], axis=1, join="inner").dropna()
        if len(aligned) > 0:
            aligned.columns = ["fund", "bench"]
            if len(aligned) >= 30:
                var = aligned["bench"].var()
                if var > 0:
                    cov = aligned["fund"].cov(aligned["bench"])
                    beta = cov / var
                
                bench_ann_ret = (1 + aligned["bench"].mean())**252 - 1
                if beta is not None:
                    alpha = ann_ret - (risk_free_rate + beta * (bench_ann_ret - risk_free_rate))
                    
                tracking_error = (aligned["fund"] - aligned["bench"]).std() * sqrt(252)
                active_ann_ret = ann_ret - bench_ann_ret
                if tracking_error > 0:
                    info_ratio = active_ann_ret / tracking_error

    return {
        "annualized_volatility": ann_vol,
        "sharpe_ratio": sharpe,
        "max_drawdown": max_drawdown,
        "beta": beta,
        "alpha": alpha,
        "tracking_error": tracking_error,
        "information_ratio": info_ratio
    }

def calculate_rolling_returns(nav_series, window_days=365):
    trading_days = int(window_days * 252 / 365)
    rolled = nav_series.pct_change(trading_days)
    rolling_annualized = (1 + rolled)**(365/window_days) - 1
    return rolling_annualized

def xirr(cashflows):
    # cashflows is list of (date, amount)
    if len(cashflows) < 2:
        return None
    def npv(rate):
        t0 = cashflows[0][0]
        return sum(amt / (1+rate)**((d - t0).days/365) for d, amt in cashflows)
    
    try:
        return brentq(npv, -0.9999, 10)
    except:
        return None

def returns_based_style_analysis(fund_returns, factor_returns_matrix):
    def loss(w):
        predicted = factor_returns_matrix @ w
        return sum((fund_returns - predicted)**2)
    
    n_factors = factor_returns_matrix.shape[1]
    bounds = [(0, 1)] * n_factors
    constraints = {"type": "eq", "fun": lambda w: sum(w) - 1}
    equal_weights = np.ones(n_factors) / n_factors
    
    result = minimize(loss, x0=equal_weights, bounds=bounds, constraints=constraints)
    if result.success:
        return result.x
    return None
