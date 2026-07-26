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
    "MU","ARM","SMCI","INTC","MRVL","QCOM","ON","WOLF",
    # AI / cloud / software
    "PLTR","APP","RDDT","SNOW","NET","CRWD","DDOG","ZS","OKTA",
    "SHOP","MELI","SE","ABNB","DASH","LYFT",
    # Quantum / deep tech
    "IONQ","RGTI","QUBT",
    # Healthcare / biotech
    "HIMS","LLY","MRNA","BNTX","NVAX","CELH","GEHC",
    # Crypto proxies
    "COIN","MSTR","MARA","RIOT","CLSK","HUT","HOOD","IBIT","CIFR",
    # Fintech / consumer finance
    "AFRM","SOFI","DKNG","PYPL","SQ","UPST","NU",
    # Growth / consumer
    "UBER","SNAP","RBLX","NFLX","SPOT","PINS","BMBL",
    # EV / energy
    "RIVN","NIO","LCID","CHPT","BLNK",
    # China tech
    "BABA","JD","PDD","BIDU",
    # Leveraged ETFs (very high IV)
    "SOXL","TQQQ","ARKK","LABU",
    # Special situations / high IV
    "GME","AMC","CVNA","BYND","OPEN",
]
UNIVERSE = list(dict.fromkeys(UNIVERSE))

EARNINGS = {
    "TSLA":"2026-07-23","AMD":"2026-07-29","NVDA":"2026-08-27",
    "COIN":"2026-08-06","META":"2026-07-29","AAPL":"2026-07-31",
    "MSFT":"2026-07-29","AMZN":"2026-08-01","GOOGL":"2026-07-29",
    "NFLX":"2026-07-16","SNAP":"2026-07-22","PYPL":"2026-07-29",
    "UBER":"2026-08-05","PLTR":"2026-08-04","SMCI":"2026-08-06",
    "MU":"2026-09-24","INTC":"2026-07-24","ARM":"2026-07-30",
    "AVGO":"2026-09-10","JPM":"2026-07-14","GS":"2026-07-14",
    "BAC":"2026-07-15","LLY":"2026-07-30","UNH":"2026-07-15",
    "SOFI":"2026-07-28","HOOD":"2026-07-30","MRNA":"2026-08-06",
    "BNTX":"2026-08-06","NIO":"2026-09-05","BABA":"2026-08-14",
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
    """Store daily IV30 + OI snapshot for building rank history."""
    hist = load_iv_history()
    today_str = date.today().isoformat()
    if sym not in hist:
        hist[sym] = []
    # Remove duplicate for today
    hist[sym] = [e for e in hist[sym] if e["date"] != today_str]
    hist[sym].append({"date": today_str, "iv30": iv30, "oi": oi})
    # Keep only last 252 trading days (~1 year)
    hist[sym] = sorted(hist[sym], key=lambda x: x["date"])[-260:]
    save_iv_history(hist)
    return hist

def calc_iv_rank(sym, current_iv30, hist):
    """IV Rank % from actual IV30 history (52-week range)."""
    entries = hist.get(sym, [])
    # Filter last 252 calendar days
    cutoff = (date.today() - timedelta(days=365)).isoformat()
    vals = [e["iv30"] for e in entries if e["date"] >= cutoff and e["iv30"] is not None]
    if len(vals) < 5:
        return None, None, None  # not enough history
    lo, hi = min(vals), max(vals)
    if hi == lo:
        return 0.0, lo, hi
    rank = round((current_iv30 - lo) / (hi - lo) * 100, 1)
    return rank, round(lo, 1), round(hi, 1)

def calc_20d_hist_iv(sym, hist):
    """Average IV30 over past 20 trading days."""
    entries = hist.get(sym, [])
    recent = sorted(entries, key=lambda x: x["date"])[-20:]
    vals = [e["iv30"] for e in recent if e["iv30"] is not None]
    if len(vals) < 3:
        return None
    return round(sum(vals) / len(vals), 1)

def calc_oi_rank(sym, current_oi, hist):
    """OI Rank % from OI history (52-week range)."""
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
    run_btn     = st.button("🔄 Refresh Rankings", use_container_width=True)

    st.divider()
    st.subheader("📐 Signal Thresholds")
    st.caption("Tune what counts as a SELL PUTS signal")
    min_ivr         = st.slider("Min IV Rank %",        0, 100, 50,  help="IV must be in top X% of its 52-week range")
    min_iv_hv_gap   = st.slider("Min IV−HV Gap (pts)",  0, 30,  5,   help="IV30 must exceed 20D HV by at least this many vol points")
    min_iv_vs_20d   = st.slider("Min IV vs 20D Hist IV",  -20, 20, 0, help="IV30 vs its own 20-day average — positive = currently elevated")
    min_oi_rank     = st.slider("Min OI Rank %",         0, 100, 0,  help="Minimum open interest rank for liquidity (0 = no filter)")
    min_prem_yield  = st.slider("Min Prem Yield % (ann.)",0, 30, 10,  help="Annualised yield on the 25-delta put: (bid/strike) × (365/DTE). Filter out low-premium setups.")
    min_mktcap_b    = st.slider("Min Market Cap ($B)",    0, 100, 5,  help="Minimum market cap in billions — filters out micro-caps with thin option markets")
    earn_buffer     = st.slider("Earnings buffer (days)", 0, 21, 7,  help="Avoid tickers with earnings within this many days")

    st.divider()
    if cache_ok(cache, "rankings"):
        age = int((time.time() - cache["rankings"]["_ts"]) / 60)
        st.caption(f"Cache: {age} min old")
    iv_hist = load_iv_history()
    tracked = sum(1 for sym in UNIVERSE if len(iv_hist.get(sym, [])) > 0)
    st.caption(f"Universe: {len(UNIVERSE)} tickers")
    st.caption(f"IV history: {tracked} tickers tracked")
    if tracked < len(UNIVERSE):
        st.info(f"Building IV history — ranks improve after {len(UNIVERSE) - tracked} more daily scans.")

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
    """Fallback IVR from rolling HV (used until real IV history builds up)."""
    s = hv_series.dropna()
    if s.empty:
        return None
    lo, hi, cur = s.min(), s.max(), s.iloc[-1]
    if hi == lo:
        return 0.0
    return round((cur - lo) / (hi - lo) * 100, 1)

def get_iv30_and_oi(tk, price):
    """ATM put IV from nearest 20-40 DTE expiry + total open interest + 25-delta put details."""
    try:
        today = date.today()
        total_oi = 0
        iv30, iv_dte = None, None
        target_put = None  # (strike, bid, delta, dte, prem_yield)
        for i, exp in enumerate(tk.options[:5]):
            dte = (datetime.strptime(exp, "%Y-%m-%d").date() - today).days
            if dte > 75:
                break
            chain = tk.option_chain(exp)
            total_oi += int(chain.calls["openInterest"].fillna(0).sum() + chain.puts["openInterest"].fillna(0).sum())
            if 20 <= dte <= 45:
                puts = chain.puts[chain.puts["bid"] > 0].copy()
                if not puts.empty:
                    if iv30 is None:
                        puts_atm = puts.copy()
                        puts_atm["dist"] = abs(puts_atm["strike"] - price)
                        atm = puts_atm.loc[puts_atm["dist"].idxmin()]
                        iv30 = round(float(atm["impliedVolatility"]) * 100, 1)
                        iv_dte = int(dte)
                    # Find 25-delta put: look for strike ~10-20% OTM with delta closest to -0.25
                    if target_put is None and "delta" in puts.columns:
                        puts["delta_dist"] = abs(puts["delta"].fillna(0) + 0.25)
                        best = puts.loc[puts["delta_dist"].idxmin()]
                        strike = round(float(best["strike"]), 2)
                        bid    = round(float(best["bid"]), 2)
                        delta  = round(float(best["delta"]), 2) if pd.notna(best.get("delta")) else None
                        prem_yield = round((bid / strike) * (365 / dte) * 100, 1) if bid > 0 and dte > 0 else None
                        target_put = (strike, bid, delta, int(dte), prem_yield)
                    elif target_put is None:
                        # No delta column: use 15% OTM strike as proxy for ~25 delta
                        target_strike = price * 0.85
                        puts["dist"] = abs(puts["strike"] - target_strike)
                        best = puts.loc[puts["dist"].idxmin()]
                        strike = round(float(best["strike"]), 2)
                        bid    = round(float(best["bid"]), 2)
                        prem_yield = round((bid / strike) * (365 / dte) * 100, 1) if bid > 0 and dte > 0 else None
                        target_put = (strike, bid, None, int(dte), prem_yield)
        return iv30, iv_dte, total_oi if total_oi > 0 else None, target_put
    except:
        return None, None, None, None

def get_option_volume(tk):
    try:
        today = date.today()
        total_vol = 0
        for exp in tk.options[:3]:
            dte = (datetime.strptime(exp, "%Y-%m-%d").date() - today).days
            if dte > 60:
                break
            chain = tk.option_chain(exp)
            total_vol += int(chain.calls["volume"].fillna(0).sum() + chain.puts["volume"].fillna(0).sum())
        return total_vol
    except:
        return None

def days_to_earnings(sym):
    if sym not in EARNINGS:
        return None
    return (datetime.strptime(EARNINGS[sym], "%Y-%m-%d").date() - date.today()).days

def classify(ivr, iv30, hv20, hist_iv, dte_earn, above_ma, ret_30d,
             p_min_ivr=50, p_earn_buf=7, p_min_gap=5, p_min_vs20d=0):
    if dte_earn is not None:
        if 0 < dte_earn <= p_earn_buf:
            return f"📅 Earnings <{p_earn_buf}d", "🚫 AVOID", "red"
        if -7 <= dte_earn <= 0:
            return "💥 Post-earnings", "🔥 SELL NOW", "green"
        if p_earn_buf < dte_earn <= p_earn_buf + 7:
            return f"⚠️ Earnings {p_earn_buf}-{p_earn_buf+7}d", "⚠️ CAUTION", "yellow"
    if above_ma is False and ret_30d is not None and ret_30d < -8:
        return "📉 Trend fear", "❌ WAIT", "red"
    gap_ok   = (iv30 and hv20 and (iv30 - hv20) >= p_min_gap)
    vs20d_ok = (iv30 and hist_iv and (iv30 - hist_iv) >= p_min_vs20d) or hist_iv is None
    ivr_ok   = ivr is not None and ivr >= p_min_ivr
    if ivr_ok and above_ma and gap_ok and vs20d_ok:
        return "✅ Clean VRP", "🟢 SELL PUTS", "green"
    if ivr_ok and above_ma:
        return "⚠️ Partial signal", "⏳ MONITOR", "yellow"
    if ivr_ok:
        return "⚠️ Mixed signals", "⏳ MONITOR", "yellow"
    return "📉 Low IV", "⏳ MONITOR", "yellow"

# ── Tabs ─────────────────────────────────────────────────────────────────────
tab1, tab2, tab3 = st.tabs(["📊 Vol Rankings", "📅 Earnings Calendar", "📰 News Feed"])

# ════════════════════════════════════════════════════════════════════════════
with tab1:
    if run_btn:
        rows = []
        prog = st.progress(0, "Loading price history…")
        status_txt = st.empty()

        raw = yf.download(universe, period="1y", auto_adjust=True, progress=False)
        if isinstance(raw.columns, pd.MultiIndex):
            closes = raw["Close"]
        else:
            closes = raw[["Close"]] if "Close" in raw.columns else raw

        hv_rows = {}
        for sym in universe:
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
                ma20  = s.rolling(20).mean().iloc[-1]
                above_ma = bool(s.iloc[-1] > ma20)
                ret_30d  = round((s.iloc[-1] / s.iloc[-min(22, len(s))] - 1) * 100, 1)
                price_1d_chg = round((s.iloc[-1] / s.iloc[-2] - 1) * 100, 2) if len(s) >= 2 else None
                hv_rows[sym] = {
                    "price": round(float(s.iloc[-1]), 2),
                    "price_chg": price_1d_chg,
                    "hv20": hv20,
                    "hv1y": hv1y,
                    "hv_ivr": hv_ivr,
                    "above_ma": above_ma,
                    "ret_30d": ret_30d,
                }
            except:
                continue

        # Fetch IV for all tickers — apply IVR filter after getting real IV data
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
                iv30, iv_dte, total_oi, target_put = get_iv30_and_oi(tk, d["price"])
                put_strike = target_put[0] if target_put else None
                put_bid    = target_put[1] if target_put else None
                put_delta  = target_put[2] if target_put else None
                put_prem_yield = target_put[4] if target_put else None
                opt_vol = get_option_volume(tk)

                # Record snapshot for building history
                if iv30 is not None:
                    iv_hist = record_iv_snapshot(sym, iv30, total_oi)

                # Compute IV-based rank (uses real IV history)
                iv_rank, iv_52wk_lo, iv_52wk_hi = calc_iv_rank(sym, iv30, iv_hist) if iv30 else (None, None, None)
                # Fall back to HV-based rank if not enough IV history
                ivr = iv_rank if iv_rank is not None else d["hv_ivr"]
                iv_rank_source = "IV" if iv_rank is not None else "HV~"

                hist_iv_20d = calc_20d_hist_iv(sym, iv_hist)
                oi_rank = calc_oi_rank(sym, total_oi, iv_hist) if total_oi else None

                # 52wk position string
                if iv_52wk_lo is not None and iv_52wk_hi is not None:
                    iv_52wk_pos = f"{iv_52wk_lo:.0f}% – {iv_52wk_hi:.0f}%"
                else:
                    iv_52wk_pos = None

                dte_earn = days_to_earnings(sym)
                catalyst, action, sig_color = classify(
                    ivr, iv30, d["hv20"], hist_iv_20d, dte_earn, d["above_ma"], d["ret_30d"],
                    p_min_ivr=min_ivr, p_earn_buf=earn_buffer,
                    p_min_gap=min_iv_hv_gap, p_min_vs20d=min_iv_vs_20d
                )
                earn_str = EARNINGS.get(sym, "—")
                rows.append({
                    "Symbol":         sym,
                    "Mkt Cap $B":     mktcap_b,
                    "Price":          d["price"],
                    "1D %":           d["price_chg"],
                    "25D Strike":     put_strike,
                    "Put Bid":        put_bid,
                    "Delta":          put_delta,
                    "Prem Yield%":    put_prem_yield,
                    "IV30":           iv30,
                    "20D Hist IV":    hist_iv_20d,
                    "IV vs 20D":      round(iv30 - hist_iv_20d, 1) if iv30 and hist_iv_20d else None,
                    "20D HV":         d["hv20"],
                    "1Y HV":          d["hv1y"],
                    "IV Rank %":      round(ivr, 1) if ivr else None,
                    "Rank Source":    iv_rank_source,
                    "52wk IV Range":  iv_52wk_pos,
                    "IV−HV Gap":      round(iv30 - d["hv20"], 1) if iv30 and d["hv20"] else None,
                    "OI Rank %":      round(oi_rank, 1) if oi_rank is not None else None,
                    "Option Vol":     opt_vol,
                    "Earnings":       earn_str if earn_str != "—" else None,
                    "Days to Earn":   dte_earn,
                    "Catalyst":       catalyst,
                    "Action":         action,
                    "_sig_color":     sig_color,
                    "30D Return":     d["ret_30d"],
                })
                time.sleep(0.2)
            except:
                continue

        prog.empty()
        status_txt.empty()
        cache["rankings"] = {"data": rows, "_ts": time.time()}
        save_cache(cache)

    elif cache_ok(cache, "rankings"):
        rows = cache["rankings"]["data"]
        age  = int((time.time() - cache["rankings"]["_ts"]) / 60)
        st.info(f"Showing cached data from {age} min ago. Hit **Refresh Rankings** to update.")
    else:
        rows = []
        st.info("👈 Click **Refresh Rankings** to load the volatility table.")

    if rows:
        df = pd.DataFrame(rows)

        if show_filter == "✅ Sell signals only":
            df = df[df["Action"].str.contains("SELL|🔥", na=False)]
        elif show_filter == "🚫 Avoid (earnings soon)":
            df = df[df["Action"].str.contains("AVOID", na=False)]

        # Apply threshold filters (guard against missing columns from old cache)
        if min_ivr > 0 and "IV Rank %" in df.columns:
            df = df[df["IV Rank %"].fillna(0) >= min_ivr]
        if min_iv_hv_gap > 0 and "IV−HV Gap" in df.columns:
            df = df[df["IV−HV Gap"].fillna(-99) >= min_iv_hv_gap]
        if min_iv_vs_20d > 0 and "IV vs 20D" in df.columns:
            df = df[df["IV vs 20D"].fillna(-99) >= min_iv_vs_20d]
        if min_oi_rank > 0 and "OI Rank %" in df.columns:
            df = df[df["OI Rank %"].fillna(0) >= min_oi_rank]
        if min_prem_yield > 0 and "Prem Yield%" in df.columns:
            df = df[df["Prem Yield%"].fillna(0) >= min_prem_yield]
        if min_mktcap_b > 0 and "Mkt Cap $B" in df.columns:
            df = df[df["Mkt Cap $B"].fillna(0) >= min_mktcap_b]

        if df.empty:
            st.warning("No rows match current filters.")
        else:
            sort_col = "IV Rank %" if "IV Rank %" in df.columns else df.columns[0]
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

            # Column guide
            with st.expander("📖 Column guide", expanded=False):
                st.markdown("""
| Column | What it means |
|---|---|
| **25D Strike** | The put strike closest to 25 delta — the standard sweet spot for put selling |
| **Put Bid** | Current bid price for that 25-delta put — what you actually collect |
| **Delta** | Actual delta (probability of assignment, roughly) |
| **Prem Yield%** | Annualised return on capital: (bid/strike) × (365/DTE) — the real edge metric |
| **IV30** | Current implied vol for ~30-day options — your premium income rate |
| **20D Hist IV** | Average IV30 over past 20 days — is today's IV elevated vs recent? |
| **IV vs 20D** | IV30 minus 20D Hist IV — positive = IV spiked above recent norm |
| **20D HV** | Actual realised vol over past 20 days — what the stock actually moved |
| **IV Rank %** | Where IV30 sits in its 52-week range (0%=cheapest, 100%=most expensive) |
| **52wk IV Range** | The low–high IV30 range over the past year (context for the rank) |
| **IV−HV Gap** | IV30 minus 20D HV — the premium you're collecting above realised vol |
| **OI Rank %** | Where open interest sits in its 52-week range — higher = more liquid |
| **Rank Source** | IV = from real IV history · HV~ = HV proxy (builds after daily scans) |
""")

            display_cols = [
                "Symbol","Mkt Cap $B","Price","1D %",
                "25D Strike","Put Bid","Delta","Prem Yield%",
                "IV30","20D Hist IV","IV vs 20D",
                "20D HV","IV Rank %","52wk IV Range",
                "IV−HV Gap","OI Rank %","Days to Earn",
                "Catalyst","Action"
            ]
            df_show = df[[c for c in display_cols if c in df.columns]].copy()
            # Drop columns where ALL values are missing
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

            def colour_vs20d(val):
                if pd.isna(val): return ""
                v = float(val)
                if v >= 5:  return "color:#4ade80;font-weight:bold"
                if v >= 0:  return "color:#facc15"
                return "color:#f87171"

            def colour_oi_rank(val):
                if pd.isna(val): return ""
                v = float(val)
                if v >= 70: return "color:#4ade80;font-weight:bold"
                if v >= 40: return "color:#facc15"
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

            fmt = {
                "Mkt Cap $B":    lambda x: f"${x:.0f}B" if pd.notna(x) else "—",
                "Price":         "${:.2f}",
                "25D Strike":    "${:.2f}",
                "Put Bid":       "${:.2f}",
                "Delta":         lambda x: f"{x:.2f}" if pd.notna(x) else "—",
                "Prem Yield%":   lambda x: f"{x:.1f}%" if pd.notna(x) else "—",
                "1D %":          "{:+.2f}%",
                "IV30":          "{:.1f}%",
                "20D Hist IV":   "{:.1f}%",
                "IV vs 20D":     "{:+.1f}",
                "20D HV":        "{:.1f}%",
                "1Y HV":         "{:.1f}%",
                "IV Rank %":     "{:.0f}%",
                "IV−HV Gap":     "{:+.1f}",
                "OI Rank %":     lambda x: f"{x:.0f}%" if pd.notna(x) else "—",
                "Option Vol":    lambda x: f"{int(x):,}" if pd.notna(x) else "—",
                "Days to Earn":  lambda x: f"{int(x)}d" if pd.notna(x) else "—",
            }

            cols = set(df_show.columns)
            styled = df_show.style
            if "IV Rank %"   in cols: styled = styled.map(colour_ivr,        subset=["IV Rank %"])
            if "Action"      in cols: styled = styled.map(colour_action,     subset=["Action"])
            if "IV−HV Gap"   in cols: styled = styled.map(colour_gap,        subset=["IV−HV Gap"])
            if "IV vs 20D"   in cols: styled = styled.map(colour_vs20d,      subset=["IV vs 20D"])
            if "OI Rank %"   in cols: styled = styled.map(colour_oi_rank,    subset=["OI Rank %"])
            if "1D %"        in cols: styled = styled.map(colour_1d,         subset=["1D %"])
            if "Prem Yield%" in cols: styled = styled.map(colour_prem_yield, subset=["Prem Yield%"])
            fmt_filtered = {k: v for k, v in fmt.items() if k in cols}
            styled = styled.format(fmt_filtered, na_rep="—")
            st.dataframe(styled, use_container_width=True, height=620, hide_index=True)

            csv = df_show.to_csv(index=False)
            st.download_button("⬇ Download CSV", csv, "vol_rankings.csv", "text/csv")

            st.divider()

            sell_df = df[df["Action"].str.contains("SELL|🔥", na=False)].head(8)
            if not sell_df.empty:
                st.subheader("🎯 Top Put-Selling Setups")
                for _, r in sell_df.iterrows():
                    earn_note = f" | Earnings: {r['Earnings']} ({r['Days to Earn']}d)" if pd.notna(r.get('Earnings')) else ""
                    iv_gap = f" | IV−HV Gap: +{r['IV−HV Gap']:.1f}pts" if pd.notna(r.get('IV−HV Gap')) else ""
                    hist_note = f" | vs 20D IV: {r['IV vs 20D']:+.1f}" if pd.notna(r.get('IV vs 20D')) else ""
                    oi_note = f" | OI Rank: {r['OI Rank %']:.0f}%" if pd.notna(r.get('OI Rank %')) else ""
                    st.success(
                        f"**{r['Symbol']}** ${r['Price']:.2f} · "
                        f"IV30: {r['IV30']:.0f}% · IV Rank: {r['IV Rank %']:.0f}%"
                        f"{hist_note}{iv_gap}{oi_note} · "
                        f"{r['Catalyst']}{earn_note}"
                    )

# ════════════════════════════════════════════════════════════════════════════
with tab2:
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
with tab3:
    st.subheader("📰 News Feed + Sentiment")
    st.caption("Auto-tags headlines as positive / negative / neutral to help understand IV drivers.")

    news_sym = st.selectbox("Select ticker", universe, index=0)

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
