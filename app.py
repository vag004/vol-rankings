"""
Options Intelligence Dashboard — Market Chameleon style
Volatility Rankings | Earnings Calendar | News Feed
"""

import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, date, timedelta
import json, os, time
import plotly.graph_objects as go

st.set_page_config(page_title="Vol Rankings", layout="wide", page_icon="📊")

st.markdown("""
<style>
[data-testid="stAppViewContainer"] { background: #0e1117; }
div[data-testid="metric-container"] { background:#1a1d27; border-radius:8px; padding:10px; }
thead tr th { background:#1a1d27 !important; color:#e2e8f0 !important; position:sticky; top:0; }
</style>
""", unsafe_allow_html=True)

st.title("📊 Volatility Rankings")
st.caption("IV30 · IV Rank · 20D Hist IV · 52wk Position · OI Rank — Market Chameleon style, built on Yahoo Finance")

# ── Universe ────────────────────────────────────────────────────────────────
UNIVERSE = [
    # Mega-cap tech
    "NVDA","META","TSLA","AMZN","MSFT","AAPL","GOOGL","AVGO","AMD",
    # Semiconductors
    "MU","ARM","SMCI","INTC","MRVL","QCOM","ON","WOLF","DELL","ANET","HPE",
    # AI / cloud / software
    "PLTR","APP","RDDT","SNOW","NET","CRWD","DDOG","ZS","OKTA",
    "SHOP","MELI","SE","ABNB","DASH","LYFT",
    # Enterprise SaaS
    "CRM","NOW","WDAY","HUBS","MDB","TEAM","PATH","GTLB","CFLT","ZI","DOCN",
    # Cybersecurity
    "PANW","S","CYBR",
    # Quantum / deep tech
    "IONQ","RGTI","QUBT",
    # Healthcare / biotech
    "HIMS","LLY","MRNA","BNTX","NVAX","CELH","GEHC",
    # Crypto proxies
    "COIN","MSTR","MARA","RIOT","CLSK","HUT","HOOD","IBIT","CIFR",
    # Fintech / consumer finance
    "AFRM","SOFI","DKNG","PYPL","UPST","NU",
    # Growth / consumer
    "UBER","SNAP","RBLX","NFLX","SPOT","PINS","BMBL",
    # EV / energy
    "RIVN","NIO","LCID","CHPT","BLNK",
    # China tech
    "BABA","JD","PDD","BIDU",
    # Nuclear / power (AI data centre demand)
    "VST","CEG","NRG","SMR","OKLO",
    # Defence / aerospace
    "LMT","RTX","NOC",
    # Leveraged ETFs (very high IV)
    "SOXL","TQQQ","ARKK","LABU",
    # Special situations / high IV
    "GME","AMC","CVNA","BYND","OPEN",
]
UNIVERSE = list(dict.fromkeys(UNIVERSE))

# ── Quality Universe ─────────────────────────────────────────────────────────
QUALITY_UNIVERSE = [
    # Tier 1 — core hold: wide moat, steady cash flow, you'd happily own if assigned
    "MSFT","GOOGL","AAPL","AMZN","MA","V","BRK-B","JPM","ISRG","COST","WM","HON",
    # Tier 2 — growth + put-sell candidate: faster growth, still high quality
    "META","NVDA","AVGO","LLY","NFLX","ADBE",
    # Tier 3 — event-driven, higher risk: geopolitical / sector sensitivity
    "TSM","NVO",
]
QUALITY_UNIVERSE = list(dict.fromkeys(QUALITY_UNIVERSE))

QUALITY_TIERS = {
    "MSFT": "T1","GOOGL": "T1","AAPL": "T1","AMZN": "T1","MA": "T1","V": "T1",
    "BRK-B": "T1","JPM": "T1","ISRG": "T1","COST": "T1","WM": "T1","HON": "T1",
    "META": "T2","NVDA": "T2","AVGO": "T2","LLY": "T2","NFLX": "T2","ADBE": "T2",
    "TSM": "T3","NVO": "T3",
}

TIER_LABELS = {
    "T1": "🔵 Core Hold",
    "T2": "🟡 Growth",
    "T3": "🔴 Event-Driven",
}

EARNINGS = {
    "TSLA":"2026-07-23","AMD":"2026-07-29","NVDA":"2026-08-27",
    "COIN":"2026-08-06","META":"2026-07-29","AAPL":"2026-07-31",
    "MSFT":"2026-07-29","AMZN":"2026-08-01","GOOGL":"2026-07-29",
    "NFLX":"2026-07-16","SNAP":"2026-07-22","PYPL":"2026-07-29",
    "UBER":"2026-08-05","PLTR":"2026-08-04","SMCI":"2026-08-06",
    "MU":"2026-09-24","INTC":"2026-07-24","ARM":"2026-07-30",
    "AVGO":"2026-09-10","JPM":"2026-07-14","GS":"2026-07-14",
    "BAC":"2026-07-15","LLY":"2026-07-30","UNH":"2026-07-15",
    "QCOM":"2026-07-29","SOFI":"2026-07-28","HOOD":"2026-07-30","MRNA":"2026-08-06",
    "BNTX":"2026-08-06","NIO":"2026-09-05","BABA":"2026-08-14",
    "MA":"2026-07-30","V":"2026-07-22","ISRG":"2026-07-22","COST":"2026-09-25",
    "TSM":"2026-07-17","NVO":"2026-08-06","ADBE":"2026-09-17",
    "HON":"2026-07-31","WM":"2026-07-29","JPM":"2026-07-14",
}

CACHE_FILE = os.path.join(os.path.dirname(__file__), "intel_cache.json")
CACHE_TTL  = 4 * 3600  # 4 hours
IV_HISTORY_FILE = os.path.join(os.path.dirname(__file__), "iv_history.json")

def load_cache():
    try:
        if os.path.exists(CACHE_FILE):
            with open(CACHE_FILE) as f:
                return json.load(f)
    except:
        pass
    return {}

def save_cache(data):
    try:
        with open(CACHE_FILE, "w") as f:
            json.dump(data, f, indent=2)
    except:
        pass

def cache_ok(cache, key):
    return key in cache and (time.time() - cache.get(key, {}).get("_ts", 0)) < CACHE_TTL

def load_iv_history():
    try:
        if os.path.exists(IV_HISTORY_FILE):
            with open(IV_HISTORY_FILE) as f:
                return json.load(f)
    except:
        pass
    return {}

def save_iv_history(data):
    try:
        with open(IV_HISTORY_FILE, "w") as f:
            json.dump(data, f, indent=2)
    except:
        pass

def record_iv_snapshot(sym, iv30, oi):
    hist = load_iv_history()
    today_str = date.today().isoformat()
    if sym not in hist:
        hist[sym] = []
    hist[sym] = [e for e in hist[sym] if e["date"] != today_str]
    hist[sym].append({"date": today_str, "iv30": iv30, "oi": oi})
    hist[sym] = sorted(hist[sym], key=lambda x: x["date"])[-260:]
    save_iv_history(hist)
    return hist

def calc_iv_rank(sym, current_iv30, hist):
    entries = hist.get(sym, [])
    cutoff = (date.today() - timedelta(days=365)).isoformat()
    vals = [e["iv30"] for e in entries if e["date"] >= cutoff and e["iv30"] is not None]
    if len(vals) < 5:
        return None, None, None
    lo, hi = min(vals), max(vals)
    if hi == lo:
        return 0.0, lo, hi
    rank = round((current_iv30 - lo) / (hi - lo) * 100, 1)
    return rank, round(lo, 1), round(hi, 1)

def calc_20d_hist_iv(sym, hist):
    entries = hist.get(sym, [])
    recent = sorted(entries, key=lambda x: x["date"])[-20:]
    vals = [e["iv30"] for e in recent if e["iv30"] is not None]
    if len(vals) < 3:
        return None
    return round(sum(vals) / len(vals), 1)

def calc_oi_rank(sym, current_oi, hist):
    entries = hist.get(sym, [])
    cutoff = (date.today() - timedelta(days=365)).isoformat()
    vals = [e["oi"] for e in entries if e["date"] >= cutoff and e.get("oi") is not None]
    if len(vals) < 5:
        return None
    lo, hi = min(vals), max(vals)
    if hi == lo:
        return 0.0
    return round((current_oi - lo) / (hi - lo) * 100, 1)

cache = load_cache()

# ── Sidebar ──────────────────────────────────────────────────────────────────
with st.sidebar:
    st.header("⚙️ Filters")
    show_filter = st.selectbox("Show", ["All", "✅ Sell signals only", "🚫 Avoid (earnings soon)"])
    custom_add  = st.text_input("Add tickers (comma-sep)", "")

    st.divider()
    st.subheader("📐 Filters")
    st.caption("Yield-first — premium is the primary signal")
    min_prem_yield  = st.slider("Min Prem Yield % (ann.)", 0, 40, 15, help="(bid/strike) × (365/DTE) — primary filter. 15%+ = real premium")
    min_mktcap_b    = st.slider("Min Market Cap ($B)",      0, 100, 5, help="Filters micro-caps with thin option markets")
    earn_buffer     = st.slider("Earnings buffer (days)",   0, 21,  7, help="Avoid selling puts within this many days of earnings")
    max_spread_pct  = st.slider("Max Spread % (liquidity)", 0, 50, 30, help="Bid-ask spread as % of mid — lower = more liquid. 30% = loose filter")
    st.divider()
    st.subheader("🔬 Context filters (optional)")
    st.caption("Refine by technicals — set to 0/max to disable")
    min_rsi         = st.slider("Min RSI",  0,  50, 25, help="Below 25 = panic/collapse. 25-40 = fear dip sweet spot")
    max_rsi         = st.slider("Max RSI", 50, 100, 70, help="Above 70 = overbought, IV often low")
    max_ret_30d     = st.slider("Max 30D Return %", -80, 0, -5, help="Only show stocks that have pulled back (negative return)")

    st.divider()
    if cache_ok(cache, "rankings"):
        age = int((time.time() - cache["rankings"]["_ts"]) / 60)
        st.caption(f"Vol cache: {age} min old")
    if cache_ok(cache, "quality_rankings"):
        age = int((time.time() - cache["quality_rankings"]["_ts"]) / 60)
        st.caption(f"Quality cache: {age} min old")
    st.caption("↑ Refresh buttons are inside each tab")
    iv_hist = load_iv_history()
    all_tickers = list(dict.fromkeys(UNIVERSE + QUALITY_UNIVERSE))
    tracked = sum(1 for sym in all_tickers if len(iv_hist.get(sym, [])) > 0)
    st.caption(f"Vol universe: {len(UNIVERSE)} tickers")
    st.caption(f"Quality universe: {len(QUALITY_UNIVERSE)} tickers")
    st.caption(f"IV history: {tracked} tickers tracked")

universe = UNIVERSE.copy()
if custom_add:
    universe += [t.strip().upper() for t in custom_add.split(",") if t.strip()]
universe = list(dict.fromkeys(universe))

# ── Helpers ──────────────────────────────────────────────────────────────────
def calc_hv(close_series, days):
    if len(close_series) < days + 2:
        return None
    lr = np.log(close_series / close_series.shift(1)).dropna()
    return round(float(lr.tail(days).std() * np.sqrt(252) * 100), 1)

def calc_hv_ivr(hv_series):
    s = hv_series.dropna()
    if s.empty:
        return None
    lo, hi, cur = s.min(), s.max(), s.iloc[-1]
    if hi == lo:
        return 0.0
    return round((cur - lo) / (hi - lo) * 100, 1)

def calc_rsi(close_series, period=14):
    s = close_series.dropna()
    if len(s) < period + 1:
        return None
    delta = s.diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = (-delta.clip(upper=0)).rolling(period).mean()
    rs = gain / loss.replace(0, float("nan"))
    rsi = 100 - (100 / (1 + rs))
    val = rsi.iloc[-1]
    return round(float(val), 1) if pd.notna(val) else None

def get_iv30_and_oi(tk, price):
    try:
        today = date.today()
        total_oi = 0
        total_call_vol, total_put_vol = 0, 0
        iv30, iv_dte = None, None
        target_put = None
        for exp in tk.options[:10]:
            dte = (datetime.strptime(exp, "%Y-%m-%d").date() - today).days
            if dte > 75:
                break
            chain = tk.option_chain(exp)
            calls, puts_all = chain.calls, chain.puts
            total_oi += int(calls["openInterest"].fillna(0).sum() + puts_all["openInterest"].fillna(0).sum())
            total_call_vol += int(calls["volume"].fillna(0).sum())
            total_put_vol  += int(puts_all["volume"].fillna(0).sum())
            if 20 <= dte <= 45:
                puts = puts_all[puts_all["bid"] > 0].copy()
                if not puts.empty:
                    if iv30 is None:
                        atm_puts = puts.copy()
                        atm_puts["dist"] = abs(atm_puts["strike"] - price)
                        atm = atm_puts.loc[atm_puts["dist"].idxmin()]
                        iv30 = round(float(atm["impliedVolatility"]) * 100, 1)
                        iv_dte = int(dte)
                    if target_put is None:
                        if "delta" in puts.columns:
                            puts["delta_dist"] = abs(puts["delta"].fillna(0) + 0.25)
                            best = puts.loc[puts["delta_dist"].idxmin()]
                        else:
                            puts["dist"] = abs(puts["strike"] - price * 0.85)
                            best = puts.loc[puts["dist"].idxmin()]
                        strike = round(float(best["strike"]), 2)
                        bid    = round(float(best["bid"]), 2)
                        ask    = round(float(best["ask"]), 2) if "ask" in best.index and pd.notna(best["ask"]) else None
                        delta  = round(float(best["delta"]), 2) if "delta" in best.index and pd.notna(best["delta"]) else None
                        mid    = (bid + ask) / 2 if ask else bid
                        spread_pct = round((ask - bid) / mid * 100, 1) if ask and mid > 0 else None
                        prem_yield = round((bid / strike) * (365 / dte) * 100, 1) if bid > 0 and dte > 0 else None
                        target_put = (strike, bid, delta, int(dte), prem_yield, spread_pct)
        pc_ratio = round(total_put_vol / total_call_vol, 2) if total_call_vol > 0 else None
        return iv30, iv_dte, total_oi if total_oi > 0 else None, target_put, pc_ratio
    except:
        return None, None, None, None, None

def fetch_next_earnings(tk, sym):
    try:
        cal = tk.calendar
        if cal is not None and "Earnings Date" in cal:
            dates = cal["Earnings Date"]
            if dates is not None and len(dates) > 0:
                d = dates[0]
                if hasattr(d, "date"):
                    d = d.date()
                elif isinstance(d, str):
                    d = datetime.strptime(d[:10], "%Y-%m-%d").date()
                if d >= date.today():
                    return d.isoformat()
    except:
        pass
    return EARNINGS.get(sym)

def days_to_earnings(sym, earn_date_str=None):
    s = earn_date_str or EARNINGS.get(sym)
    if not s:
        return None
    return (datetime.strptime(s, "%Y-%m-%d").date() - date.today()).days

def classify(prem_yield, dte_earn, above_ma200, above_ma50, rsi, ret_30d,
             iv30, hv20, hist_iv, p_earn_buf=7, p_min_yield=10):
    if dte_earn is not None and 0 < dte_earn <= p_earn_buf:
        return f"📅 Earnings <{p_earn_buf}d", "🚫 AVOID", "red"
    if rsi is not None and rsi < 25:
        return "🆘 RSI Panic <25", "❌ WAIT", "red"
    if ret_30d is not None and ret_30d < -35:
        return "💥 Down >35% (30d)", "❌ WAIT", "red"
    if not above_ma200 and ret_30d is not None and ret_30d < -15:
        return "📉 Downtrend break", "❌ WAIT", "red"

    if dte_earn is not None and -5 <= dte_earn <= 0:
        return "💥 Post-earnings", "🔥 SELL NOW", "green"

    yield_ok = prem_yield is not None and prem_yield >= p_min_yield
    rsi_ok       = rsi is not None and 30 <= rsi <= 60
    trend_ok     = above_ma50 or (above_ma200 and ret_30d is not None and ret_30d > -20)
    fear_dip     = ret_30d is not None and -25 <= ret_30d <= -8
    iv_spike     = iv30 and hv20 and (iv30 - hv20) >= 5
    iv_above_avg = iv30 and hist_iv and (iv30 - hist_iv) >= 0

    if yield_ok and trend_ok and rsi_ok and (iv_spike or iv_above_avg):
        return "✅ Strong setup", "🟢 SELL PUTS", "green"
    if yield_ok and fear_dip and rsi_ok:
        return "😨 Fear dip", "🟢 SELL PUTS", "green"
    if yield_ok and trend_ok:
        return "⚠️ Partial setup", "⏳ MONITOR", "yellow"
    if yield_ok:
        return "💰 Yield OK/trend weak", "⏳ MONITOR", "yellow"
    if dte_earn is not None and p_earn_buf < dte_earn <= p_earn_buf + 7:
        return f"⚠️ Earnings {dte_earn}d", "⚠️ CAUTION", "yellow"
    return "📉 Low yield", "⏳ MONITOR", "yellow"

# ── Scan logic (shared) ───────────────────────────────────────────────────────
def run_scan(universe_list, cache_key, tier_map=None):
    """Run the full IV scan for a given universe. Returns list of row dicts."""
    rows = []
    prog = st.progress(0, "Loading price history…")
    status_txt = st.empty()

    raw = yf.download(universe_list, period="1y", auto_adjust=True, progress=False)
    if isinstance(raw.columns, pd.MultiIndex):
        closes = raw["Close"]
    else:
        closes = raw[["Close"]] if "Close" in raw.columns else raw

    hv_rows = {}
    for sym in universe_list:
        try:
            if sym not in closes.columns:
                continue
            s = closes[sym].dropna()
            if len(s) < 65:
                continue
            hv20  = calc_hv(s, 20)
            hv1y  = calc_hv(s, 252)
            lr    = np.log(s / s.shift(1)).dropna()
            hv_s  = lr.rolling(30).std() * np.sqrt(252) * 100
            hv_ivr = calc_hv_ivr(hv_s)
            ma50  = s.rolling(50).mean().iloc[-1]
            ma200 = s.rolling(200).mean().iloc[-1]
            cur   = float(s.iloc[-1])
            above_ma50  = bool(cur > float(ma50))  if pd.notna(ma50)  else None
            above_ma200 = bool(cur > float(ma200)) if pd.notna(ma200) else None
            vs_50ma_pct = round((cur / float(ma50)  - 1) * 100, 1) if pd.notna(ma50)  else None
            ret_30d     = round((cur / float(s.iloc[-min(22, len(s))]) - 1) * 100, 1)
            price_1d_chg = round((cur / float(s.iloc[-2]) - 1) * 100, 2) if len(s) >= 2 else None
            rsi = calc_rsi(s)
            hv_rows[sym] = {
                "price":       round(cur, 2),
                "price_chg":   price_1d_chg,
                "hv20":        hv20,
                "hv1y":        hv1y,
                "hv_ivr":      hv_ivr,
                "above_ma50":  above_ma50,
                "above_ma200": above_ma200,
                "vs_50ma_pct": vs_50ma_pct,
                "ret_30d":     ret_30d,
                "rsi":         rsi,
            }
        except:
            continue

    qualifying = list(hv_rows.keys())
    status_txt.text(f"{len(qualifying)} tickers — fetching live IV + OI…")

    iv_hist = load_iv_history()

    for i, sym in enumerate(qualifying):
        prog.progress((i + 1) / max(len(qualifying), 1), f"IV fetch: {sym}")
        try:
            d = hv_rows[sym]
            tk = yf.Ticker(sym)
            try:
                mktcap = tk.fast_info.market_cap
                mktcap_b = round(mktcap / 1e9, 1) if mktcap else None
            except:
                mktcap_b = None
            earn_date_str = fetch_next_earnings(tk, sym)
            iv30, iv_dte, total_oi, target_put, pc_ratio = get_iv30_and_oi(tk, d["price"])
            put_strike     = target_put[0] if target_put else None
            put_bid        = target_put[1] if target_put else None
            put_delta      = target_put[2] if target_put else None
            put_prem_yield = target_put[4] if target_put else None
            put_spread_pct = target_put[5] if target_put else None

            if iv30 is not None:
                iv_hist = record_iv_snapshot(sym, iv30, total_oi)

            iv_rank, iv_52wk_lo, iv_52wk_hi = calc_iv_rank(sym, iv30, iv_hist) if iv30 else (None, None, None)
            ivr = iv_rank if iv_rank is not None else d["hv_ivr"]

            hist_iv_20d = calc_20d_hist_iv(sym, iv_hist)
            oi_rank = calc_oi_rank(sym, total_oi, iv_hist) if total_oi else None

            if iv_52wk_lo is not None and iv_52wk_hi is not None:
                iv_52wk_pos = f"{iv_52wk_lo:.0f}% – {iv_52wk_hi:.0f}%"
            else:
                iv_52wk_pos = None

            dte_earn = days_to_earnings(sym, earn_date_str)
            catalyst, action, sig_color = classify(
                put_prem_yield, dte_earn,
                d["above_ma200"], d["above_ma50"], d["rsi"], d["ret_30d"],
                iv30, d["hv20"], hist_iv_20d,
                p_earn_buf=earn_buffer, p_min_yield=min_prem_yield
            )

            row = {
                "Symbol":         sym,
                "Mkt Cap $B":     mktcap_b,
                "Price":          d["price"],
                "1D %":           d["price_chg"],
                "RSI":            d["rsi"],
                "vs 50MA%":       d["vs_50ma_pct"],
                "30D Ret%":       d["ret_30d"],
                "25D Strike":     put_strike,
                "Put Bid":        put_bid,
                "Delta":          put_delta,
                "Prem Yield%":    put_prem_yield,
                "Spread%":        put_spread_pct,
                "P/C Ratio":      pc_ratio,
                "IV30":           iv30,
                "20D HV":         d["hv20"],
                "IV−HV Gap":      round(iv30 - d["hv20"], 1) if iv30 and d["hv20"] else None,
                "IV Rank %":      round(ivr, 1) if ivr else None,
                "Days to Earn":   dte_earn,
                "Catalyst":       catalyst,
                "Action":         action,
                "_sig_color":     sig_color,
            }
            if tier_map:
                tier_code = tier_map.get(sym, "")
                row["Tier"] = TIER_LABELS.get(tier_code, "")
            rows.append(row)
            time.sleep(0.2)
        except:
            continue

    prog.empty()
    status_txt.empty()
    return rows

# ── Display logic (shared) ────────────────────────────────────────────────────
def display_results(rows, show_tier=False, show_all=False):
    """Render the results table given a list of row dicts.
    show_all=True: skip sidebar filters, show every stock, sort sells to top.
    """
    if not rows:
        st.info("👈 Click **Refresh** to load the volatility table.")
        return

    df = pd.DataFrame(rows)

    if show_all:
        # Sort order: sells first, then monitors, then avoids — within each group by Prem Yield%
        def action_rank(a):
            if "SELL" in str(a) or "🔥" in str(a): return 0
            if "MONITOR" in str(a) or "CAUTION" in str(a): return 1
            return 2
        df["_rank"] = df["Action"].apply(action_rank)
        df = df.sort_values(["_rank", "Prem Yield%"], ascending=[True, False]).drop(columns=["_rank"]).reset_index(drop=True)
    else:
        if show_filter == "✅ Sell signals only":
            df = df[df["Action"].str.contains("SELL|🔥", na=False)]
        elif show_filter == "🚫 Avoid (earnings soon)":
            df = df[df["Action"].str.contains("AVOID", na=False)]

        if min_prem_yield > 0 and "Prem Yield%" in df.columns:
            df = df[df["Prem Yield%"].fillna(0) >= min_prem_yield]
        if min_mktcap_b > 0 and "Mkt Cap $B" in df.columns:
            df = df[df["Mkt Cap $B"].fillna(0) >= min_mktcap_b]
        if max_spread_pct < 50 and "Spread%" in df.columns:
            df = df[df["Spread%"].fillna(999) <= max_spread_pct]
        if min_rsi > 0 and "RSI" in df.columns:
            df = df[df["RSI"].fillna(0) >= min_rsi]
        if max_rsi < 100 and "RSI" in df.columns:
            df = df[df["RSI"].fillna(100) <= max_rsi]
        if max_ret_30d < 0 and "30D Ret%" in df.columns:
            df = df[df["30D Ret%"].fillna(0) <= max_ret_30d]

        if df.empty:
            st.warning("No rows match current filters.")
            return

        sort_col = "Prem Yield%" if "Prem Yield%" in df.columns else df.columns[0]
        df = df.sort_values(sort_col, ascending=False).reset_index(drop=True)

    sells    = df["Action"].str.contains("SELL|🔥", na=False).sum()
    avoids   = df["Action"].str.contains("AVOID|WAIT", na=False).sum()
    monitors = df["Action"].str.contains("MONITOR|CAUTION", na=False).sum()

    c1,c2,c3,c4 = st.columns(4)
    c1.metric("🟢 Sell signals", int(sells))
    c2.metric("⏳ Monitor", int(monitors))
    c3.metric("🚫 Avoid / Wait", int(avoids))
    c4.metric("Tickers shown", len(df))
    st.divider()

    with st.expander("📖 Column guide", expanded=False):
        st.markdown("""
| Column | What it means |
|---|---|
| **25D Strike** | The put strike closest to 25 delta — the standard sweet spot for put selling |
| **Put Bid** | Current bid price for that 25-delta put — what you actually collect |
| **Delta** | Actual delta (probability of assignment, roughly) |
| **Prem Yield%** | Annualised return on capital: (bid/strike) × (365/DTE) — the real edge metric |
| **IV30** | Current implied vol for ~30-day options — your premium income rate |
| **20D HV** | Actual realised vol over past 20 days — what the stock actually moved |
| **IV−HV Gap** | IV30 minus 20D HV — the premium you're collecting above realised vol |
| **IV Rank %** | Where IV30 sits in its 52-week range (0%=cheapest, 100%=most expensive) |
""")

    base_display_cols = [
        "Symbol","Mkt Cap $B","Price","1D %",
        "RSI","vs 50MA%","30D Ret%",
        "25D Strike","Put Bid","Delta","Prem Yield%","Spread%",
        "P/C Ratio","IV30","20D HV","IV−HV Gap","IV Rank %",
        "Days to Earn","Catalyst","Action"
    ]
    if show_tier:
        base_display_cols = ["Tier"] + base_display_cols

    df_show = df[[c for c in base_display_cols if c in df.columns]].copy()
    df_show = df_show.loc[:, df_show.notna().any()]

    def colour_ivr(val):
        if pd.isna(val): return ""
        v = float(val)
        if v >= 70: return "background-color:#1a472a;color:#4ade80;font-weight:bold"
        if v >= 50: return "background-color:#2d5a1e;color:#86efac"
        if v >= 30: return "background-color:#4a3a00;color:#facc15"
        return "background-color:#3b0f0f;color:#f87171"

    def colour_action(val):
        s = str(val)
        if "SELL" in s or "🔥" in s: return "background-color:#14532d;color:#4ade80;font-weight:bold"
        if "AVOID" in s: return "background-color:#450a0a;color:#f87171;font-weight:bold"
        if "WAIT" in s:  return "background-color:#450a0a;color:#f87171"
        if "CAUTION" in s: return "background-color:#4a3a00;color:#facc15"
        return "color:#9ca3af"

    def colour_gap(val):
        if pd.isna(val): return ""
        v = float(val)
        if v >= 10: return "color:#4ade80;font-weight:bold"
        if v >= 5:  return "color:#86efac"
        if v >= 0:  return "color:#facc15"
        return "color:#f87171"

    def colour_1d(val):
        if pd.isna(val): return ""
        return "color:#4ade80" if float(val) >= 0 else "color:#f87171"

    def colour_prem_yield(val):
        if pd.isna(val): return ""
        v = float(val)
        if v >= 15: return "color:#4ade80;font-weight:bold"
        if v >= 8:  return "color:#86efac"
        if v >= 4:  return "color:#facc15"
        return "color:#f87171"

    def colour_rsi(val):
        if pd.isna(val): return ""
        v = float(val)
        if v < 25:  return "background-color:#450a0a;color:#f87171;font-weight:bold"
        if v <= 40: return "color:#4ade80;font-weight:bold"
        if v <= 55: return "color:#86efac"
        if v <= 70: return "color:#facc15"
        return "color:#f87171"

    def colour_ret(val):
        if pd.isna(val): return ""
        v = float(val)
        if v <= -25: return "color:#f87171;font-weight:bold"
        if v <= -10: return "color:#4ade80;font-weight:bold"
        if v <= -5:  return "color:#86efac"
        if v >= 0:   return "color:#9ca3af"
        return "color:#facc15"

    def colour_pc(val):
        if pd.isna(val): return ""
        v = float(val)
        if v >= 1.5: return "color:#4ade80;font-weight:bold"
        if v >= 1.0: return "color:#86efac"
        if v >= 0.7: return "color:#facc15"
        return "color:#f87171"

    def colour_spread(val):
        if pd.isna(val): return ""
        v = float(val)
        if v <= 5:  return "color:#4ade80"
        if v <= 15: return "color:#facc15"
        return "color:#f87171"

    def colour_tier(val):
        s = str(val)
        if "T1" in s or "Core" in s: return "color:#60a5fa;font-weight:bold"
        if "T2" in s or "Growth" in s: return "color:#facc15;font-weight:bold"
        if "T3" in s or "Event" in s: return "color:#f87171;font-weight:bold"
        return ""

    fmt = {
        "Mkt Cap $B":  lambda x: f"${x:.0f}B" if pd.notna(x) else "—",
        "Price":       "${:.2f}",
        "1D %":        "{:+.2f}%",
        "RSI":         lambda x: f"{x:.0f}" if pd.notna(x) else "—",
        "vs 50MA%":    lambda x: f"{x:+.1f}%" if pd.notna(x) else "—",
        "30D Ret%":    lambda x: f"{x:+.1f}%" if pd.notna(x) else "—",
        "25D Strike":  "${:.2f}",
        "Put Bid":     "${:.2f}",
        "Delta":       lambda x: f"{x:.2f}" if pd.notna(x) else "—",
        "Prem Yield%": lambda x: f"{x:.1f}%" if pd.notna(x) else "—",
        "Spread%":     lambda x: f"{x:.1f}%" if pd.notna(x) else "—",
        "P/C Ratio":   lambda x: f"{x:.2f}" if pd.notna(x) else "—",
        "IV30":        "{:.1f}%",
        "20D HV":      "{:.1f}%",
        "IV−HV Gap":   "{:+.1f}",
        "IV Rank %":   lambda x: f"{x:.0f}%" if pd.notna(x) else "—",
        "Days to Earn":lambda x: f"{int(x)}d" if pd.notna(x) else "—",
    }

    cols = set(df_show.columns)
    styled = df_show.style
    if "Prem Yield%" in cols: styled = styled.map(colour_prem_yield, subset=["Prem Yield%"])
    if "Action"      in cols: styled = styled.map(colour_action,     subset=["Action"])
    if "RSI"         in cols: styled = styled.map(colour_rsi,        subset=["RSI"])
    if "30D Ret%"    in cols: styled = styled.map(colour_ret,        subset=["30D Ret%"])
    if "P/C Ratio"   in cols: styled = styled.map(colour_pc,         subset=["P/C Ratio"])
    if "Spread%"     in cols: styled = styled.map(colour_spread,     subset=["Spread%"])
    if "IV−HV Gap"   in cols: styled = styled.map(colour_gap,        subset=["IV−HV Gap"])
    if "IV Rank %"   in cols: styled = styled.map(colour_ivr,        subset=["IV Rank %"])
    if "1D %"        in cols: styled = styled.map(colour_1d,         subset=["1D %"])
    if "Tier"        in cols: styled = styled.map(colour_tier,       subset=["Tier"])
    fmt_filtered = {k: v for k, v in fmt.items() if k in cols}
    styled = styled.format(fmt_filtered, na_rep="—")
    st.dataframe(styled, use_container_width=True, height=620, hide_index=True)

    csv = df_show.to_csv(index=False)
    st.download_button("⬇ Download CSV", csv, "vol_rankings.csv", "text/csv")

# ── Sector Momentum Data ─────────────────────────────────────────────────────
SECTORS = [
    # theme                    etf      individual names for context
    ("🤖 AI / Semis",         "SMH",   ["NVDA","AVGO","AMD","ARM","MU"]),
    ("☁️ Cloud / SaaS",       "WCLD",  ["NOW","SNOW","DDOG","NET","CRWD"]),
    ("🔐 Cybersecurity",      "HACK",  ["CRWD","PANW","ZS","CYBR","S"]),
    ("₿ Crypto",              "BITO",  ["COIN","MSTR","MARA","RIOT","IBIT"]),
    ("⚡ Nuclear / Power",    "URNM",  ["VST","CEG","SMR","OKLO","NRG"]),
    ("🛡️ Defence",            "ITA",   ["LMT","RTX","NOC","PLTR","HII"]),
    ("🏭 Reshoring / Indust", "XLI",   ["GE","ETN","PWR","HUBB","MMM"]),
    ("💊 Biotech",            "XBI",   ["MRNA","BNTX","NVAX","CELH","HIMS"]),
    ("🚗 EV / Clean Energy",  "DRIV",  ["TSLA","RIVN","NIO","CHPT","BLNK"]),
    ("🇨🇳 China Tech",        "KWEB",  ["BABA","JD","PDD","BIDU","SE"]),
    ("💳 Fintech",            "FINX",  ["PYPL","AFRM","SOFI","HOOD","NU"]),
    ("💉 GLP-1 / Health",     "XLV",   ["LLY","NVO","ISRG","GEHC","UNH"]),
]

def fetch_sector_momentum():
    """Fetch price momentum for all sector ETFs. Lightweight — no options chain."""
    etfs = [s[1] for s in SECTORS]
    raw = yf.download(etfs, period="1y", auto_adjust=True, progress=False)
    if isinstance(raw.columns, pd.MultiIndex):
        closes = raw["Close"]
    else:
        closes = raw

    rows = []
    today_idx = -1
    for theme, etf, names in SECTORS:
        try:
            if etf not in closes.columns:
                continue
            s = closes[etf].dropna()
            if len(s) < 65:
                continue
            cur   = float(s.iloc[-1])
            ret1d = round((cur / float(s.iloc[-2]) - 1) * 100, 2) if len(s) >= 2 else None
            ret1w = round((cur / float(s.iloc[-6]) - 1) * 100, 1) if len(s) >= 6 else None
            ret1m = round((cur / float(s.iloc[-22]) - 1) * 100, 1) if len(s) >= 22 else None
            ret3m = round((cur / float(s.iloc[-66]) - 1) * 100, 1) if len(s) >= 66 else None
            ret6m = round((cur / float(s.iloc[-130]) - 1) * 100, 1) if len(s) >= 130 else None
            rsi   = calc_rsi(s)
            ma50  = s.rolling(50).mean().iloc[-1]
            ma200 = s.rolling(200).mean().iloc[-1]
            vs50  = round((cur / float(ma50) - 1) * 100, 1) if pd.notna(ma50) else None
            # 52-week high/low position
            hi52  = float(s.rolling(252).max().iloc[-1])
            lo52  = float(s.rolling(252).min().iloc[-1])
            pct52 = round((cur - lo52) / (hi52 - lo52) * 100, 0) if hi52 > lo52 else None

            # Momentum signal
            if ret1m is not None and ret3m is not None and rsi is not None:
                if ret1m > 5 and ret3m > 10 and rsi > 55:
                    signal = "🔥 Strong"
                elif ret1m > 0 and ret3m > 0:
                    signal = "📈 Building"
                elif ret1m < -5 and ret3m < -10:
                    signal = "📉 Weak"
                elif ret1m < 0:
                    signal = "⚠️ Fading"
                else:
                    signal = "➡️ Neutral"
            else:
                signal = "—"

            rows.append({
                "Theme":      theme,
                "ETF":        etf,
                "Price":      round(cur, 2),
                "1D %":       ret1d,
                "1W %":       ret1w,
                "1M %":       ret1m,
                "3M %":       ret3m,
                "6M %":       ret6m,
                "RSI":        rsi,
                "vs 50MA%":   vs50,
                "52wk Pos%":  pct52,
                "Key Names":  " · ".join(names),
                "Momentum":   signal,
            })
        except:
            continue
    return rows

# ── Tabs ─────────────────────────────────────────────────────────────────────
tab1, tab2, tab3, tab4, tab5 = st.tabs(["📊 Vol Rankings", "🏆 Quality Universe", "🌡️ Sector Momentum", "📅 Earnings Calendar", "📰 News Feed"])

# ════════════════════════════════════════════════════════════════════════════
with tab1:

    with st.expander("📘 Strategy Guide — How to read this scanner", expanded=False):
        st.markdown("""
<div style="background:#1a1d27;border-radius:12px;padding:20px 24px;color:#e2e8f0">

<h3 style="color:#60a5fa;margin-top:0">The idea: sell put options where the premium justifies the risk</h3>

<p style="color:#94a3b8">When you sell a put, you collect cash upfront. If the stock stays above your strike, you keep it all.
If it falls below, you buy the stock at the strike — so <strong style="color:#e2e8f0">only sell puts on stocks you'd want to own</strong>.</p>

<hr style="border-color:#2d3748;margin:16px 0">

<h4 style="color:#fbbf24">🎯 Primary filter — Is the premium worth it?</h4>

<table style="width:100%;border-collapse:collapse;font-size:0.88em">
<tr style="background:#252836">
  <th style="padding:8px 12px;text-align:left;color:#94a3b8;border-bottom:1px solid #2d3748">Metric</th>
  <th style="padding:8px 12px;text-align:left;color:#94a3b8;border-bottom:1px solid #2d3748">What it measures</th>
  <th style="padding:8px 12px;text-align:left;color:#4ade80;border-bottom:1px solid #2d3748">Green zone</th>
  <th style="padding:8px 12px;text-align:left;color:#f87171;border-bottom:1px solid #2d3748">Red zone</th>
</tr>
<tr style="border-bottom:1px solid #2d3748"><td style="padding:7px 12px"><strong style="color:#e2e8f0">Prem Yield%</strong></td><td style="padding:7px 12px;color:#94a3b8">Annualised return: (bid/strike) × (365/DTE)</td><td style="padding:7px 12px;color:#4ade80">≥ 15%</td><td style="padding:7px 12px;color:#f87171">< 8%</td></tr>
<tr style="border-bottom:1px solid #2d3748;background:#1e2130"><td style="padding:7px 12px"><strong style="color:#e2e8f0">Put Bid</strong></td><td style="padding:7px 12px;color:#94a3b8">Cash collected per contract (×100 shares)</td><td style="padding:7px 12px;color:#4ade80">Higher = better</td><td style="padding:7px 12px;color:#f87171">—</td></tr>
<tr style="border-bottom:1px solid #2d3748"><td style="padding:7px 12px"><strong style="color:#e2e8f0">25D Strike</strong></td><td style="padding:7px 12px;color:#94a3b8">Strike at ~25% probability of assignment</td><td style="padding:7px 12px;color:#4ade80">10–20% OTM</td><td style="padding:7px 12px;color:#f87171">—</td></tr>
<tr style="border-bottom:1px solid #2d3748;background:#1e2130"><td style="padding:7px 12px"><strong style="color:#e2e8f0">Spread%</strong></td><td style="padding:7px 12px;color:#94a3b8">Bid-ask spread as % of mid — liquidity quality</td><td style="padding:7px 12px;color:#4ade80">< 10%</td><td style="padding:7px 12px;color:#f87171">> 25%</td></tr>
</table>

<hr style="border-color:#2d3748;margin:16px 0">

<h4 style="color:#fbbf24">📊 Technical signals — Is now a good time to sell?</h4>

<table style="width:100%;border-collapse:collapse;font-size:0.88em">
<tr style="background:#252836">
  <th style="padding:8px 12px;text-align:left;color:#94a3b8;border-bottom:1px solid #2d3748">Metric</th>
  <th style="padding:8px 12px;text-align:left;color:#94a3b8;border-bottom:1px solid #2d3748">What it measures</th>
  <th style="padding:8px 12px;text-align:left;color:#4ade80;border-bottom:1px solid #2d3748">Sweet spot</th>
  <th style="padding:8px 12px;text-align:left;color:#f87171;border-bottom:1px solid #2d3748">Avoid</th>
</tr>
<tr style="border-bottom:1px solid #2d3748"><td style="padding:7px 12px"><strong style="color:#e2e8f0">RSI (14)</strong></td><td style="padding:7px 12px;color:#94a3b8">Momentum — oversold (fear) or overbought?</td><td style="padding:7px 12px;color:#4ade80">30–55: fear dip</td><td style="padding:7px 12px;color:#f87171">< 25 panic · > 70 overbought</td></tr>
<tr style="border-bottom:1px solid #2d3748;background:#1e2130"><td style="padding:7px 12px"><strong style="color:#e2e8f0">30D Ret%</strong></td><td style="padding:7px 12px;color:#94a3b8">How much the stock pulled back in 30 days</td><td style="padding:7px 12px;color:#4ade80">-8% to -25%</td><td style="padding:7px 12px;color:#f87171">< -35%: structural break</td></tr>
<tr style="border-bottom:1px solid #2d3748"><td style="padding:7px 12px"><strong style="color:#e2e8f0">vs 50MA%</strong></td><td style="padding:7px 12px;color:#94a3b8">Distance above/below 50-day moving average</td><td style="padding:7px 12px;color:#4ade80">Above 0%: uptrend</td><td style="padding:7px 12px;color:#f87171">Far below: downtrend</td></tr>
<tr style="border-bottom:1px solid #2d3748;background:#1e2130"><td style="padding:7px 12px"><strong style="color:#e2e8f0">P/C Ratio</strong></td><td style="padding:7px 12px;color:#94a3b8">Put-to-call volume — fear proxy</td><td style="padding:7px 12px;color:#4ade80">> 1.0: fear-driven IV</td><td style="padding:7px 12px;color:#f87171">< 0.5: complacency</td></tr>
</table>

<hr style="border-color:#2d3748;margin:16px 0">

<h4 style="color:#fbbf24">📈 Volatility context — Why is IV elevated?</h4>

<table style="width:100%;border-collapse:collapse;font-size:0.88em">
<tr style="background:#252836">
  <th style="padding:8px 12px;text-align:left;color:#94a3b8;border-bottom:1px solid #2d3748">Metric</th>
  <th style="padding:8px 12px;text-align:left;color:#94a3b8;border-bottom:1px solid #2d3748">What it measures</th>
  <th style="padding:8px 12px;text-align:left;color:#4ade80;border-bottom:1px solid #2d3748">Good to see</th>
  <th style="padding:8px 12px;text-align:left;color:#f87171;border-bottom:1px solid #2d3748">Concerning</th>
</tr>
<tr style="border-bottom:1px solid #2d3748"><td style="padding:7px 12px"><strong style="color:#e2e8f0">IV30</strong></td><td style="padding:7px 12px;color:#94a3b8">Implied vol of 30-day ATM put — fear gauge</td><td style="padding:7px 12px;color:#4ade80">Elevated but not crisis</td><td style="padding:7px 12px;color:#f87171">Very low = no premium</td></tr>
<tr style="border-bottom:1px solid #2d3748;background:#1e2130"><td style="padding:7px 12px"><strong style="color:#e2e8f0">20D HV</strong></td><td style="padding:7px 12px;color:#94a3b8">Actual realised vol over past 20 days</td><td style="padding:7px 12px;color:#4ade80">Lower than IV30 = VRP edge</td><td style="padding:7px 12px;color:#f87171">Higher than IV30 = selling cheap</td></tr>
<tr style="border-bottom:1px solid #2d3748"><td style="padding:7px 12px"><strong style="color:#e2e8f0">IV−HV Gap</strong></td><td style="padding:7px 12px;color:#94a3b8">IV30 minus HV20 — the VRP premium</td><td style="padding:7px 12px;color:#4ade80">≥ +5 pts</td><td style="padding:7px 12px;color:#f87171">Negative = vol risk uncompensated</td></tr>
<tr style="border-bottom:1px solid #2d3748;background:#1e2130"><td style="padding:7px 12px"><strong style="color:#e2e8f0">IV Rank%</strong></td><td style="padding:7px 12px;color:#94a3b8">Where today's IV sits in its 52-week range</td><td style="padding:7px 12px;color:#4ade80">> 50%: historically elevated</td><td style="padding:7px 12px;color:#f87171">< 30%: IV near yearly lows</td></tr>
</table>

<hr style="border-color:#2d3748;margin:16px 0">

<h4 style="color:#fbbf24">🚦 Signal logic (Catalyst → Action)</h4>

<table style="width:100%;border-collapse:collapse;font-size:0.88em">
<tr style="background:#252836">
  <th style="padding:8px 12px;text-align:left;color:#94a3b8;border-bottom:1px solid #2d3748">Signal</th>
  <th style="padding:8px 12px;text-align:left;color:#94a3b8;border-bottom:1px solid #2d3748">Meaning</th>
</tr>
<tr style="border-bottom:1px solid #2d3748"><td style="padding:7px 12px;color:#4ade80;font-weight:bold">🟢 SELL PUTS</td><td style="padding:7px 12px;color:#94a3b8">Yield ≥ threshold · RSI 30-60 · trend intact · IV elevated above HV</td></tr>
<tr style="border-bottom:1px solid #2d3748;background:#1e2130"><td style="padding:7px 12px;color:#4ade80;font-weight:bold">😨 SELL PUTS (Fear dip)</td><td style="padding:7px 12px;color:#94a3b8">Yield OK · RSI 30-55 · stock down 8-25% — selling into panic, best setups</td></tr>
<tr style="border-bottom:1px solid #2d3748"><td style="padding:7px 12px;color:#4ade80;font-weight:bold">🔥 SELL NOW (Post-earnings)</td><td style="padding:7px 12px;color:#94a3b8">Earnings just passed, binary risk gone, IV still elevated — best window</td></tr>
<tr style="border-bottom:1px solid #2d3748;background:#1e2130"><td style="padding:7px 12px;color:#facc15;font-weight:bold">⏳ MONITOR</td><td style="padding:7px 12px;color:#94a3b8">Some conditions met but not all — watch for better entry</td></tr>
<tr style="border-bottom:1px solid #2d3748"><td style="padding:7px 12px;color:#f87171;font-weight:bold">🚫 AVOID</td><td style="padding:7px 12px;color:#94a3b8">Earnings within buffer · RSI < 25 · stock down > 35% — too risky</td></tr>
</table>

<hr style="border-color:#2d3748;margin:16px 0">

<div style="background:#1e3a2f;border-left:3px solid #4ade80;padding:10px 16px;border-radius:6px">
<strong style="color:#4ade80">Rule of thumb:</strong>
<span style="color:#94a3b8"> A good setup = stock you'd want to own + Prem Yield ≥ 15% + RSI 30-55 + no earnings within 7 days</span>
</div>

</div>
""", unsafe_allow_html=True)

    run_btn = st.button("🔄 Refresh Vol Universe", use_container_width=True, key="run_vol")

    if run_btn:
        rows = run_scan(universe, "rankings")
        cache["rankings"] = {"data": rows, "_ts": time.time()}
        save_cache(cache)
    elif cache_ok(cache, "rankings"):
        rows = cache["rankings"]["data"]
        age  = int((time.time() - cache["rankings"]["_ts"]) / 60)
        st.info(f"Showing cached data from {age} min ago. Hit **Refresh Vol Universe** to update.")
    else:
        rows = []

    display_results(rows, show_tier=False)

# ════════════════════════════════════════════════════════════════════════════
with tab2:
    st.subheader("🏆 Quality Universe — 20 Stocks Worth Owning")
    st.markdown("""
<div style="background:#1a1d27;border-radius:10px;padding:14px 20px;margin-bottom:16px">
<p style="color:#94a3b8;margin:0 0 10px 0">These are stocks you'd <strong style="color:#e2e8f0">genuinely want to own</strong> if your put got assigned.
The put-selling edge here is lower premium than the vol universe — but the fundamental downside protection is far stronger.</p>
<table style="width:100%;border-collapse:collapse;font-size:0.88em">
<tr>
  <td style="padding:6px 12px;color:#60a5fa;font-weight:bold;width:120px">🔵 Tier 1 — Core Hold</td>
  <td style="padding:6px 12px;color:#94a3b8">MSFT · GOOGL · AAPL · AMZN · MA · V · BRK-B · JPM · ISRG · COST · WM · HON — wide moat, steady cash flow, hold forever</td>
</tr>
<tr>
  <td style="padding:6px 12px;color:#facc15;font-weight:bold">🟡 Tier 2 — Growth</td>
  <td style="padding:6px 12px;color:#94a3b8">META · NVDA · AVGO · LLY · NFLX · ADBE — faster growth, still high quality, higher IV = better premiums</td>
</tr>
<tr>
  <td style="padding:6px 12px;color:#f87171;font-weight:bold">🔴 Tier 3 — Event-Driven</td>
  <td style="padding:6px 12px;color:#94a3b8">TSM · NVO — geopolitical / sector sensitivity adds risk; size positions smaller</td>
</tr>
</table>
</div>
""", unsafe_allow_html=True)

    run_quality = st.button("🔄 Refresh Quality Universe", use_container_width=True, key="run_quality")

    if run_quality:
        quality_rows = run_scan(QUALITY_UNIVERSE, "quality_rankings", tier_map=QUALITY_TIERS)
        cache["quality_rankings"] = {"data": quality_rows, "_ts": time.time()}
        save_cache(cache)
    elif cache_ok(cache, "quality_rankings"):
        quality_rows = cache["quality_rankings"]["data"]
        age = int((time.time() - cache["quality_rankings"]["_ts"]) / 60)
        st.info(f"Showing cached data from {age} min ago. Hit **Refresh Quality Universe** to update.")
    else:
        quality_rows = []
        st.info("Click **Refresh Quality Universe** above to load the quality table.")

    display_results(quality_rows, show_tier=True, show_all=True)

# ════════════════════════════════════════════════════════════════════════════
with tab3:
    st.subheader("🌡️ Sector Momentum — Where Is Money Flowing?")
    st.caption("Price momentum on 12 themes tracked via ETF proxies. Green themes = hunt for put candidates within them. Red = avoid even if yield looks good.")

    run_sectors = st.button("🔄 Refresh Sector Momentum", use_container_width=True, key="run_sectors")

    sec_cache_key = "sector_momentum"
    if run_sectors:
        with st.spinner("Fetching sector ETF data…"):
            sec_rows = fetch_sector_momentum()
        cache[sec_cache_key] = {"data": sec_rows, "_ts": time.time()}
        save_cache(cache)
    elif cache_ok(cache, sec_cache_key):
        sec_rows = cache[sec_cache_key]["data"]
        age = int((time.time() - cache[sec_cache_key]["_ts"]) / 60)
        st.info(f"Cached {age} min ago — sector data is slow moving, refresh daily is enough.")
    else:
        sec_rows = []
        st.info("Click **Refresh Sector Momentum** above to load the panel.")

    if sec_rows:
        df_s = pd.DataFrame(sec_rows)

        # Sort: strong first
        momentum_order = {"🔥 Strong": 0, "📈 Building": 1, "➡️ Neutral": 2, "⚠️ Fading": 3, "📉 Weak": 4, "—": 5}
        df_s["_ord"] = df_s["Momentum"].map(momentum_order).fillna(5)
        df_s = df_s.sort_values(["_ord","3M %"], ascending=[True, False]).drop(columns=["_ord"]).reset_index(drop=True)

        # Summary metrics
        strong = (df_s["Momentum"].str.contains("Strong|Building", na=False)).sum()
        weak   = (df_s["Momentum"].str.contains("Weak|Fading", na=False)).sum()
        c1,c2,c3 = st.columns(3)
        c1.metric("🔥 Strong / Building themes", int(strong))
        c2.metric("📉 Weak / Fading themes", int(weak))
        c3.metric("➡️ Neutral", len(df_s) - strong - weak)
        st.divider()

        def colour_momentum(val):
            s = str(val)
            if "Strong"   in s: return "background-color:#14532d;color:#4ade80;font-weight:bold"
            if "Building" in s: return "background-color:#1a3a1a;color:#86efac"
            if "Fading"   in s: return "background-color:#4a3a00;color:#facc15"
            if "Weak"     in s: return "background-color:#450a0a;color:#f87171;font-weight:bold"
            return "color:#9ca3af"

        def colour_pct(val):
            if pd.isna(val): return ""
            v = float(val)
            if v >= 15: return "color:#4ade80;font-weight:bold"
            if v >= 5:  return "color:#86efac"
            if v >= 0:  return "color:#facc15"
            if v >= -10: return "color:#f87171"
            return "color:#f87171;font-weight:bold"

        def colour_rsi_s(val):
            if pd.isna(val): return ""
            v = float(val)
            if v >= 60: return "color:#4ade80;font-weight:bold"
            if v >= 50: return "color:#86efac"
            if v >= 40: return "color:#facc15"
            return "color:#f87171"

        def colour_52wk(val):
            if pd.isna(val): return ""
            v = float(val)
            if v >= 75: return "color:#4ade80;font-weight:bold"
            if v >= 50: return "color:#86efac"
            if v >= 25: return "color:#facc15"
            return "color:#f87171"

        fmt_s = {
            "Price":     "${:.2f}",
            "1D %":      "{:+.2f}%",
            "1W %":      lambda x: f"{x:+.1f}%" if pd.notna(x) else "—",
            "1M %":      lambda x: f"{x:+.1f}%" if pd.notna(x) else "—",
            "3M %":      lambda x: f"{x:+.1f}%" if pd.notna(x) else "—",
            "6M %":      lambda x: f"{x:+.1f}%" if pd.notna(x) else "—",
            "RSI":       lambda x: f"{x:.0f}" if pd.notna(x) else "—",
            "vs 50MA%":  lambda x: f"{x:+.1f}%" if pd.notna(x) else "—",
            "52wk Pos%": lambda x: f"{x:.0f}%" if pd.notna(x) else "—",
        }

        disp_cols = ["Theme","ETF","Price","1D %","1W %","1M %","3M %","6M %","RSI","vs 50MA%","52wk Pos%","Key Names","Momentum"]
        df_s_show = df_s[[c for c in disp_cols if c in df_s.columns]]
        cols_s = set(df_s_show.columns)

        styled_s = df_s_show.style
        for col in ["1D %","1W %","1M %","3M %","6M %","vs 50MA%"]:
            if col in cols_s: styled_s = styled_s.map(colour_pct, subset=[col])
        if "RSI"       in cols_s: styled_s = styled_s.map(colour_rsi_s,  subset=["RSI"])
        if "52wk Pos%" in cols_s: styled_s = styled_s.map(colour_52wk,   subset=["52wk Pos%"])
        if "Momentum"  in cols_s: styled_s = styled_s.map(colour_momentum, subset=["Momentum"])
        fmt_s_filtered = {k: v for k, v in fmt_s.items() if k in cols_s}
        styled_s = styled_s.format(fmt_s_filtered, na_rep="—")

        st.dataframe(styled_s, use_container_width=True, height=500, hide_index=True)

        st.divider()

        # Bar chart: 1M and 3M return by theme
        fig = go.Figure()
        fig.add_trace(go.Bar(
            name="1M %", x=df_s["Theme"], y=df_s["1M %"],
            marker_color=["#4ade80" if v >= 0 else "#f87171" for v in df_s["1M %"].fillna(0)],
            opacity=0.85,
        ))
        fig.add_trace(go.Bar(
            name="3M %", x=df_s["Theme"], y=df_s["3M %"],
            marker_color=["#60a5fa" if v >= 0 else "#f59e0b" for v in df_s["3M %"].fillna(0)],
            opacity=0.65,
        ))
        fig.update_layout(
            template="plotly_dark", barmode="group", height=380,
            title="Sector momentum — 1M vs 3M return",
            yaxis_title="Return %", xaxis_tickangle=-30,
            margin=dict(l=40,r=20,t=50,b=120),
            legend=dict(orientation="h", y=1.1),
        )
        fig.add_hline(y=0, line_color="white", opacity=0.3)
        st.plotly_chart(fig, use_container_width=True)

        st.markdown("""
**How to use this panel:**
- **🔥 Strong / 📈 Building** → hunt for put candidates in these themes on the Vol Rankings tab
- **⚠️ Fading / 📉 Weak** → avoid selling puts even if individual stock yield looks good — sector headwind will hurt
- **52wk Pos%** — how close to the 52-week high. >75% = momentum intact; <25% = sector in a downtrend
- **RSI > 55** on an ETF = sector trend confirmed, not overbought yet
""")

# ════════════════════════════════════════════════════════════════════════════
with tab4:
    st.subheader("📅 Earnings Calendar — Next 60 Days")

    today = date.today()
    earn_rows = []
    for sym, earn_str in EARNINGS.items():
        earn_dt = datetime.strptime(earn_str, "%Y-%m-%d").date()
        dte = (earn_dt - today).days
        if -7 <= dte <= 60:
            if dte < 0:
                status = "💥 Post-earnings NOW"; advice = "Sell puts — IV still elevated, binary risk gone"; bg = "#14532d"
            elif dte <= 7:
                status = "🚫 Danger zone";       advice = "AVOID — do not open new puts"; bg = "#450a0a"
            elif dte <= 14:
                status = "⚠️ Approaching";       advice = "Close or reduce existing positions"; bg = "#4a3a00"
            else:
                status = "✅ Safe window";        advice = "OK to sell puts expiring before earnings"; bg = "#14532d"
            earn_rows.append({"Ticker": sym, "Earnings Date": earn_str, "Days Away": dte,
                              "Status": status, "Action / Note": advice, "_bg": bg})

    earn_rows.sort(key=lambda x: x["Days Away"])

    if earn_rows:
        df_e = pd.DataFrame(earn_rows).drop(columns=["_bg"])

        def sty_status(val):
            if "Post-earnings" in str(val) or "Safe" in str(val): return "background-color:#14532d;color:#4ade80"
            if "Danger" in str(val): return "background-color:#450a0a;color:#f87171"
            if "Approaching" in str(val): return "background-color:#4a3a00;color:#facc15"
            return ""

        st.dataframe(
            df_e.style.map(sty_status, subset=["Status"]).format({"Days Away": "{}d"}),
            use_container_width=True, height=520, hide_index=True
        )

        st.divider()
        st.subheader("Earnings Timeline")
        cmap = {
            "💥 Post-earnings NOW": "#4ade80",
            "🚫 Danger zone": "#f87171",
            "⚠️ Approaching": "#facc15",
            "✅ Safe window": "#60a5fa",
        }
        fig = go.Figure()
        for r in earn_rows:
            fig.add_trace(go.Scatter(
                x=[r["Days Away"]], y=[r["Ticker"]],
                mode="markers+text",
                marker=dict(size=14, color=cmap.get(r["Status"],"#9ca3af"), line=dict(width=1,color="white")),
                text=[f"{r['Days Away']}d"], textposition="middle right",
                showlegend=False,
                hovertemplate=f"<b>{r['Ticker']}</b><br>{r['Earnings Date']}<br>{r['Status']}<extra></extra>"
            ))
        fig.add_vline(x=0, line_dash="dash", line_color="white", opacity=0.4, annotation_text="Today")
        fig.add_vrect(x0=-7, x1=7, fillcolor="red", opacity=0.06, line_width=0)
        fig.update_layout(template="plotly_dark", height=520,
                          xaxis_title="Days from Today", yaxis_title="",
                          xaxis=dict(range=[-10,65]),
                          margin=dict(l=80,r=40,t=20,b=40))
        st.plotly_chart(fig, use_container_width=True)
        st.info("**Rule:** Never sell puts within 7 days BEFORE earnings. Best window: 1-3 days AFTER — binary risk gone, IV still elevated.")

# ════════════════════════════════════════════════════════════════════════════
with tab5:
    st.subheader("📰 News Feed + Sentiment")
    st.caption("Auto-tags headlines as positive / negative / neutral to help understand IV drivers.")

    all_universe = list(dict.fromkeys(universe + QUALITY_UNIVERSE))
    news_sym = st.selectbox("Select ticker", all_universe, index=0)

    cache_key = f"news_{news_sym}"
    if st.button("📡 Fetch News", key="news_btn") or cache_ok(cache, cache_key):
        if cache_ok(cache, cache_key):
            items = cache[cache_key]["data"]
            age   = int((time.time() - cache[cache_key]["_ts"]) / 60)
            st.caption(f"Cached {age} min ago")
        else:
            with st.spinner(f"Fetching {news_sym} news…"):
                try:
                    tk = yf.Ticker(news_sym)
                    raw_news = tk.news or []
                    pos_w = ["beat","surge","rally","gain","rises","upgrade","strong","record","top","outperform","bullish","boost","soar"]
                    neg_w = ["miss","drop","fall","cut","downgrade","weak","loss","decline","crash","bearish","warn","risk","concern","tumble","plunge","probe","lawsuit","fine"]
                    items = []
                    for n in raw_news[:8]:
                        t = n.get("title","")
                        if not t: continue
                        tl = t.lower()
                        pos = sum(1 for w in pos_w if w in tl)
                        neg = sum(1 for w in neg_w if w in tl)
                        items.append({
                            "title": t,
                            "sentiment": "🟢 Positive" if pos > neg else ("🔴 Negative" if neg > pos else "⚪ Neutral"),
                            "date": datetime.fromtimestamp(n.get("providerPublishTime",0)).strftime("%b %d") if n.get("providerPublishTime") else "—",
                            "url": n.get("link",""),
                        })
                    cache[cache_key] = {"data": items, "_ts": time.time()}
                    save_cache(cache)
                except:
                    items = []

        if items:
            pos = sum(1 for i in items if "Positive" in i["sentiment"])
            neg = sum(1 for i in items if "Negative" in i["sentiment"])
            neu = sum(1 for i in items if "Neutral"  in i["sentiment"])
            c1,c2,c3 = st.columns(3)
            c1.metric("🟢 Positive", pos)
            c2.metric("🔴 Negative", neg)
            c3.metric("⚪ Neutral",  neu)
            if neg > pos:
                st.warning(f"⚠️ Mostly negative news for **{news_sym}** — IV likely fear-driven. Higher risk to sell puts.")
            elif pos > neg:
                st.success(f"✅ Mostly positive news for **{news_sym}** — IV elevated but not fear-driven. Cleaner premium opportunity.")
            else:
                st.info(f"Mixed/neutral news for **{news_sym}** — check earnings calendar for primary IV catalyst.")
            st.divider()
            for item in items:
                color = {"🟢 Positive":"#4ade80","🔴 Negative":"#f87171","⚪ Neutral":"#9ca3af"}.get(item["sentiment"],"#9ca3af")
                link  = f'&nbsp;<a href="{item["url"]}" target="_blank" style="color:#60a5fa;font-size:0.8em">↗ Read</a>' if item["url"] else ""
                st.markdown(f"""
<div style="background:#1a1d27;border:1px solid #2d3748;border-radius:8px;padding:14px;margin:6px 0">
<span style="color:{color};font-size:0.85em;font-weight:bold">{item['sentiment']}</span>
<span style="color:#6b7280;font-size:0.8em">&nbsp;&nbsp;{item['date']}</span>{link}<br/>
<span style="font-size:0.95em">{item['title']}</span>
</div>""", unsafe_allow_html=True)
        else:
            st.info(f"No news found for {news_sym}.")

    st.divider()
    st.markdown("""
**Decision checklist:**
1. **IV Rank % > 60%** — IV historically expensive (sell into elevated vol)
2. **IV vs 20D > 0** — IV spiked above recent norm (don't sell into a quiet market)
3. **IV−HV Gap > +5** — collecting premium above what stock actually moves
4. **OI Rank % > 40%** — enough liquidity, tight spreads
5. **No earnings within 7 days** of your put expiry
6. **Action = 🟢 SELL PUTS** — all conditions aligned
""")
