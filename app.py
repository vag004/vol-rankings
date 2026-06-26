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
.rank-high { color:#4ade80; font-weight:bold; }
.rank-med  { color:#facc15; }
.rank-low  { color:#f87171; }
thead tr th { background:#1a1d27 !important; color:#e2e8f0 !important; position:sticky; top:0; }
</style>
""", unsafe_allow_html=True)

st.title("📊 Volatility Rankings")
st.caption("IV30 Rank · Historical Vol · Option Volume — same data as Market Chameleon, built on Yahoo Finance")

# ── Universe ────────────────────────────────────────────────────────────────
UNIVERSE = [
    # Mega-cap tech
    "AAPL","MSFT","NVDA","GOOGL","META","AMZN","TSLA","AVGO","AMD","INTC",
    # Growth / momentum
    "COIN","MSTR","PLTR","ARM","SMCI","MU","AFRM","SOFI","HOOD","DKNG",
    # Crypto proxies
    "MARA","RIOT","CLSK","HUT",
    # Retail / consumer
    "NFLX","AMZN","PYPL","UBER","SNAP","RBLX",
    # Biotech / pharma
    "LLY","PFE","ABBV","MRNA","BNTX",
    # Financials
    "JPM","GS","BAC","MS",
    # Energy
    "XOM","CVX","XLE",
    # China
    "BABA","JD","NIO",
    # EV
    "RIVN","LCID",
    # ETFs
    "SPY","QQQ","IWM","GLD","SLV","ARKK","SOXL","TQQQ",
]
UNIVERSE = list(dict.fromkeys(UNIVERSE))  # dedup

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

cache = load_cache()

# ── Sidebar ──────────────────────────────────────────────────────────────────
with st.sidebar:
    st.header("⚙️ Filters")
    min_ivr     = st.slider("Min IV Rank %", 0, 100, 0)
    show_filter = st.selectbox("Show", ["All", "✅ Sell signals only", "🚫 Avoid (earnings soon)"])
    custom_add  = st.text_input("Add tickers (comma-sep)", "")
    run_btn     = st.button("🔄 Refresh Rankings", use_container_width=True)
    st.divider()
    if cache_ok(cache, "rankings"):
        age = int((time.time() - cache["rankings"]["_ts"]) / 60)
        st.caption(f"Cache: {age} min old")
    st.caption(f"Universe: {len(UNIVERSE)} tickers")

universe = UNIVERSE.copy()
if custom_add:
    universe += [t.strip().upper() for t in custom_add.split(",") if t.strip()]
universe = list(dict.fromkeys(universe))

# ── Helpers ──────────────────────────────────────────────────────────────────
def calc_hv(close_series, days):
    """Annualised historical volatility over N trading days."""
    if len(close_series) < days + 2:
        return None
    lr = np.log(close_series / close_series.shift(1)).dropna()
    return round(float(lr.tail(days).std() * np.sqrt(252) * 100), 1)

def calc_ivr(hv_series):
    """IVR from rolling 30-day HV series (52-week range)."""
    s = hv_series.dropna()
    if s.empty:
        return None
    lo, hi, cur = s.min(), s.max(), s.iloc[-1]
    if hi == lo:
        return 0.0
    return round((cur - lo) / (hi - lo) * 100, 1)

def get_iv30(tk, price):
    """ATM put IV from nearest expiry 20-40 DTE as proxy for IV30."""
    try:
        today = date.today()
        for exp in tk.options:
            dte = (datetime.strptime(exp, "%Y-%m-%d").date() - today).days
            if 20 <= dte <= 40:
                puts = tk.option_chain(exp).puts
                puts = puts[puts["bid"] > 0]
                if puts.empty:
                    continue
                puts = puts.copy()
                puts["dist"] = abs(puts["strike"] - price)
                atm = puts.loc[puts["dist"].idxmin()]
                return round(float(atm["impliedVolatility"]) * 100, 1), int(dte)
        return None, None
    except:
        return None, None

def get_option_volume(tk):
    """Total option volume across all near-term expiries."""
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

def classify(ivr, iv30, hv20, dte_earn, above_ma, ret_30d):
    """Return (catalyst, action, signal_color)."""
    if dte_earn is not None:
        if 0 < dte_earn <= 7:
            return "📅 Earnings <7d", "🚫 AVOID", "red"
        if -7 <= dte_earn <= 0:
            return "💥 Post-earnings", "🔥 SELL NOW", "green"
        if 7 < dte_earn <= 14:
            return "⚠️ Earnings 7-14d", "⚠️ CAUTION", "yellow"
    if above_ma is False and ret_30d is not None and ret_30d < -8:
        return "📉 Trend fear", "❌ WAIT", "red"
    if ivr is not None and ivr >= 50 and above_ma:
        return "✅ Clean VRP", "🟢 SELL PUTS", "green"
    if ivr is not None and ivr >= 50:
        return "⚠️ Mixed signals", "⏳ MONITOR", "yellow"
    return "📉 Low IV", "⏳ MONITOR", "yellow"

# ── Tabs ─────────────────────────────────────────────────────────────────────
tab1, tab2, tab3 = st.tabs(["📊 Vol Rankings", "📅 Earnings Calendar", "📰 News Feed"])

# ════════════════════════════════════════════════════════════════════════════
with tab1:
    # ── Run or load cache ──
    if run_btn:
        rows = []
        prog = st.progress(0, "Loading price history…")
        status_txt = st.empty()

        # Step 1: Bulk download 1y price history
        raw = yf.download(universe, period="1y", auto_adjust=True, progress=False)
        if isinstance(raw.columns, pd.MultiIndex):
            closes = raw["Close"]
        else:
            closes = raw[["Close"]] if "Close" in raw.columns else raw

        # Step 2: Compute HV metrics from price history (no API calls)
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
                ivr   = calc_ivr(hv_s)
                ma20  = s.rolling(20).mean().iloc[-1]
                above_ma = bool(s.iloc[-1] > ma20)
                ret_30d  = round((s.iloc[-1] / s.iloc[-min(22, len(s))] - 1) * 100, 1)
                price_1d_chg = round((s.iloc[-1] / s.iloc[-2] - 1) * 100, 2) if len(s) >= 2 else None
                hv_rows[sym] = {
                    "price": round(float(s.iloc[-1]), 2),
                    "price_chg": price_1d_chg,
                    "hv20": hv20,
                    "hv1y": hv1y,
                    "ivr": ivr,
                    "above_ma": above_ma,
                    "ret_30d": ret_30d,
                }
            except:
                continue

        # Step 3: Filter by IVR, then fetch IV30 + option volume only for qualifying tickers
        qualifying = [s for s, v in hv_rows.items() if v.get("ivr") is not None and v["ivr"] >= min_ivr]
        status_txt.text(f"{len(qualifying)} tickers passed IVR≥{min_ivr}% — fetching live IV…")

        for i, sym in enumerate(qualifying):
            prog.progress((i + 1) / max(len(qualifying), 1), f"IV fetch: {sym}")
            try:
                d = hv_rows[sym]
                tk = yf.Ticker(sym)
                iv30, iv_dte = get_iv30(tk, d["price"])
                opt_vol = get_option_volume(tk)
                dte_earn = days_to_earnings(sym)
                catalyst, action, sig_color = classify(
                    d["ivr"], iv30, d["hv20"], dte_earn, d["above_ma"], d["ret_30d"]
                )
                earn_str = EARNINGS.get(sym, "—")
                rows.append({
                    "Symbol":       sym,
                    "Price":        d["price"],
                    "1D %":         d["price_chg"],
                    "IV30":         iv30,
                    "IV DTE":       iv_dte,
                    "20D HV":       d["hv20"],
                    "1Y HV":        d["hv1y"],
                    "IV Rank %":    d["ivr"],
                    "IV−HV Gap":    round(iv30 - d["hv20"], 1) if iv30 and d["hv20"] else None,
                    "Option Vol":   opt_vol,
                    "Earnings":     earn_str if earn_str != "—" else None,
                    "Days to Earn": dte_earn,
                    "Catalyst":     catalyst,
                    "Action":       action,
                    "_sig_color":   sig_color,
                    "30D Return":   d["ret_30d"],
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

    # ── Apply filters ──
    if rows:
        df = pd.DataFrame(rows)

        if show_filter == "✅ Sell signals only":
            df = df[df["Action"].str.contains("SELL|🔥", na=False)]
        elif show_filter == "🚫 Avoid (earnings soon)":
            df = df[df["Action"].str.contains("AVOID", na=False)]

        if df.empty:
            st.warning("No rows match current filters.")
        else:
            df = df.sort_values("IV Rank %", ascending=False).reset_index(drop=True)

            # ── Summary metrics ──
            sells   = df["Action"].str.contains("SELL|🔥", na=False).sum()
            avoids  = df["Action"].str.contains("AVOID|WAIT", na=False).sum()
            monitors= df["Action"].str.contains("MONITOR|CAUTION", na=False).sum()

            c1,c2,c3,c4 = st.columns(4)
            c1.metric("🟢 Sell signals", int(sells))
            c2.metric("⏳ Monitor", int(monitors))
            c3.metric("🚫 Avoid / Wait", int(avoids))
            c4.metric("Tickers shown", len(df))
            st.divider()

            # ── Display table (mimicking Market Chameleon layout) ──
            display_cols = [
                "Symbol","Price","1D %","IV30","20D HV","1Y HV",
                "IV Rank %","IV−HV Gap","Option Vol","Earnings","Days to Earn",
                "Catalyst","Action"
            ]
            df_show = df[[c for c in display_cols if c in df.columns]].copy()

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

            styled = (
                df_show.style
                .map(colour_ivr,    subset=["IV Rank %"])
                .map(colour_action, subset=["Action"])
                .map(colour_gap,    subset=["IV−HV Gap"])
                .map(colour_1d,     subset=["1D %"])
                .format({
                    "Price":       "${:.2f}",
                    "1D %":        "{:+.2f}%",
                    "IV30":        "{:.1f}%",
                    "20D HV":      "{:.1f}%",
                    "1Y HV":       "{:.1f}%",
                    "IV Rank %":   "{:.0f}%",
                    "IV−HV Gap":   "{:+.1f}",
                    "Option Vol":  lambda x: f"{int(x):,}" if pd.notna(x) else "—",
                    "Days to Earn":lambda x: f"{int(x)}d" if pd.notna(x) else "—",
                }, na_rep="—")
            )
            st.dataframe(styled, use_container_width=True, height=600, hide_index=True)

            # ── Download ──
            csv = df_show.to_csv(index=False)
            st.download_button("⬇ Download CSV", csv, "vol_rankings.csv", "text/csv")

            st.divider()

            # ── Top sell setups detail ──
            sell_df = df[df["Action"].str.contains("SELL|🔥", na=False)].head(8)
            if not sell_df.empty:
                st.subheader("🎯 Top Put-Selling Setups")
                for _, r in sell_df.iterrows():
                    earn_note = f" | Earnings: {r['Earnings']} ({r['Days to Earn']}d)" if pd.notna(r.get('Earnings')) else ""
                    iv_gap = f" | IV−HV Gap: +{r['IV−HV Gap']:.1f}pts" if pd.notna(r.get('IV−HV Gap')) else ""
                    st.success(
                        f"**{r['Symbol']}** ${r['Price']:.2f} · "
                        f"IV30: {r['IV30']:.0f}% · 20D HV: {r['20D HV']:.0f}% · "
                        f"IV Rank: {r['IV Rank %']:.0f}%{iv_gap} · "
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
            df_e.style.map(sty_status, subset=["Status"])
                      .format({"Days Away": "{}d"}),
            use_container_width=True, height=520, hide_index=True
        )

        # Timeline chart
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

        st.info("**Rule:** Never sell puts within 7 days BEFORE earnings. Best window: 1-3 days AFTER earnings — binary risk gone, IV still elevated.")

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
                        if not t:
                            continue
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
                st.warning(f"⚠️  Mostly negative news for **{news_sym}** — IV likely driven by fear/uncertainty. Higher risk to sell puts.")
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
**Decision framework:**
1. Check **Vol Rankings** → find stocks with IV Rank ≥ 50% + Action = 🟢 SELL PUTS
2. Check **Earnings Calendar** → confirm no earnings within 7 days of your put expiry
3. Check **News Feed** → if mostly negative, understand it's fear-driven IV (riskier)
4. Only enter if: Clean VRP or Post-earnings + neutral/positive news + trend intact
""")
