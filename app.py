import streamlit as st
import db_manager as db
import time
import pandas as pd
import numpy as np
import pandas_ta as ta
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timedelta
import requests

# ---------------------------------------------------------
# 1. KẾT NỐI API & CẤU HÌNH GIAO DIỆN
# ---------------------------------------------------------
st.set_page_config(page_title="TAMDUY TRADER PRO", layout="wide", page_icon="🦅", initial_sidebar_state="collapsed")
db.init_db()

# --- CSS: TRADING TERMINAL STYLE ---
st.markdown("""
<style>
    .stApp {background-color: #000000; color: #e0e0e0;}
    @import url('https://fonts.googleapis.com/css2?family=Roboto+Mono:wght@400;700&display=swap');
    
    h1, h2, h3 {color: #d4af37 !important; font-family: 'Segoe UI', sans-serif;}
    header[data-testid="stHeader"] { visibility: hidden; height: 0px; }
    .stDeployButton {display:none;}
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    .block-container { padding-top: 0rem !important; padding-bottom: 0rem !important; }

    /* HUD Metrics Styling */
    .hud-box {
        background-color: #0d1117; border: 1px solid #333;
        padding: 8px; border-radius: 4px; text-align: center;
        border-top: 2px solid #d4af37; margin-bottom: 5px;
    }
    .hud-val {font-family: 'Roboto Mono', monospace; font-size: 17px; font-weight: bold;}
    .hud-lbl {font-size: 10px; color: #888; text-transform: uppercase;}
    
    .perf-box {
        background-color: #161b22; border: 1px solid #30363d;
        padding: 8px; border-radius: 4px; text-align: center;
        margin-bottom: 5px;
    }
    .perf-val {font-family: 'Roboto Mono', monospace; font-size: 15px; font-weight: bold;}
    .perf-lbl {font-size: 9px; color: #aaa; text-transform: uppercase;}

    /* AI Advisor Layout (TradingView Style) */
    .ai-panel {
        background-color: #0d1117; border: 1px solid #30363d;
        padding: 20px; border-radius: 8px; height: 850px; overflow-y: auto;
    }
    .ai-title {color: #d4af37; font-weight: bold; font-size: 18px; margin-bottom: 15px; border-bottom: 2px solid #d4af37; padding-bottom: 8px; text-transform: uppercase; letter-spacing: 1px;}
    .ai-section-title {color: #58a6ff; font-weight: bold; font-size: 14px; margin-top: 18px; margin-bottom: 8px; display: flex; align-items: center;}
    .ai-section-title::before {content: '◈'; margin-right: 8px; color: #d4af37;}
    .ai-text {font-size: 13px; line-height: 1.7; color: #c9d1d9; margin-left: 15px;}
    .ai-highlight {color: #fff; font-weight: 600;}
    .ai-expert-box { background-color: #161b22; border-left: 4px solid #d4af37; padding: 12px; margin: 15px 0; border-radius: 0 6px 6px 0; }
    
    ::-webkit-scrollbar {width: 6px;}
    ::-webkit-scrollbar-thumb {background: #333; border-radius: 3px;}
</style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------
# 2. DATA ENGINE (DNSE API)
# ---------------------------------------------------------
@st.cache_data(ttl=300)
def get_market_data(symbol):
    data = {"df": None, "error": ""}
    headers = {'User-Agent': 'Mozilla/5.0'}
    try:
        end_ts = int(time.time())
        start_ts = int(end_ts - (3 * 365 * 24 * 60 * 60))
        url = f"https://services.entrade.com.vn/chart-api/v2/ohlcs/stock?symbol={symbol}&from={start_ts}&to={end_ts}&resolution=1D"
        res = requests.get(url, headers=headers, timeout=10)
        if res.status_code == 200:
            raw = res.json()
            if 't' in raw and len(raw['t']) > 0:
                df = pd.DataFrame({
                    'time': pd.to_datetime(raw['t'], unit='s') + pd.Timedelta(hours=7),
                    'open': raw['o'], 'high': raw['h'], 'low': raw['l'], 'close': raw['c'], 'volume': raw['v']
                })
                df.set_index('time', inplace=True); df.sort_index(inplace=True)
                for c in ['open', 'high', 'low', 'close', 'volume']: df[c] = pd.to_numeric(df[c], errors='coerce')
                data["df"] = df[df['volume'] > 0]
            else: data["error"] = f"Mã {symbol} không có dữ liệu."
        else: data["error"] = f"Lỗi kết nối API: {res.status_code}"
    except Exception as e: data["error"] = str(e)
    return data

# ---------------------------------------------------------
# 3. CHIẾN LƯỢC PHÂN TÍCH
# ---------------------------------------------------------
def run_strategy_full(df):
    if len(df) < 52: return df
    df = df.copy()
    df['MA20'] = df.ta.sma(length=20)
    df['MA50'] = df.ta.sma(length=50)
    df['MA200'] = df.ta.sma(length=200)
    df['AvgVol'] = df.ta.sma(close='volume', length=50)
    df['ATR'] = df.ta.atr(length=14)
    try:
        adx_df = df.ta.adx(length=14)
        df['ADX'] = adx_df['ADX_14']
    except: df['ADX'] = 0
    macd = df.ta.macd(); df['MACD'] = macd['MACD_12_26_9']; df['MACD_Signal'] = macd['MACDs_12_26_9']; df['MACD_Hist'] = macd['MACDh_12_26_9']
    df['RSI'] = df.ta.rsi(length=14)
    # ICHIMOKU
    h9 = df['high'].rolling(9).max(); l9 = df['low'].rolling(9).min(); df['Tenkan'] = (h9 + l9) / 2
    h26 = df['high'].rolling(26).max(); l26 = df['low'].rolling(26).min(); df['Kijun'] = (h26 + l26) / 2
    df['SpanA'] = ((df['Tenkan'] + df['Kijun']) / 2).shift(26)
    h52 = df['high'].rolling(52).max(); l52 = df['low'].rolling(52).min(); df['SpanB'] = ((h52 + l52) / 2).shift(26)
    # TREND
    df['Trend_Phase'] = 'SIDEWAY'
    df.loc[df['close'] > df['MA50'], 'Trend_Phase'] = 'POSITIVE'
    df.loc[df['close'] < df['MA50'], 'Trend_Phase'] = 'NEGATIVE'
    # STOPLOSS & TARGET
    df['SL'] = np.where(df['close'] > df['MA50'], np.maximum(df['MA50'], df['Kijun']) - (0.5 * df['ATR']), df['close'] - (2 * df['ATR']))
    risk = (df['close'] - df['SL']).abs()
    df['T1'] = df['close'] + (1.5 * risk); df['T2'] = df['close'] + (3.0 * risk)
    # SIGNAL
    hhv20 = df['high'].rolling(20).max().shift(1)
    buy_cond = (df['close'] > hhv20) & (df['volume'] > 1.2 * df['AvgVol']) & (df['close'] > df['MA200'])
    sell_cond = (df['close'] < df['MA20']) & (df['close'].shift(1) >= df['MA20'].shift(1))
    signals = []; pos = 0
    for i in range(len(df)):
        if pos == 0:
            if buy_cond.iloc[i]: signals.append('MUA'); pos = 1
            else: signals.append('')
        else:
            if sell_cond.iloc[i]: signals.append('BÁN'); pos = 0
            else: signals.append('')
    df['SIGNAL'] = signals
    return df

# ---------------------------------------------------------
# 4. BACKTEST HIỆU SUẤT
# ---------------------------------------------------------
def run_backtest_fast(df):
    capital = 1_000_000_000; cash = capital; shares = 0; equity = []
    trades = 0; wins = 0; trade_logs = []
    if df.empty: return 0, 0, 0, pd.DataFrame(), 0
    start_date = df.index[0]; end_date = df.index[-1]
    duration_days = (end_date - start_date).days
    for i in range(len(df)):
        price = df['close'].iloc[i]; sig = df['SIGNAL'].iloc[i]; date = df.index[i]
        if sig == 'MUA' and cash > 0:
            shares = cash // price; cash -= shares * price; entry = price; entry_date = date
        elif sig == 'BÁN' and shares > 0:
            pnl = (price - entry)/entry; trades += 1
            if pnl > 0: wins += 1
            trade_logs.append({"Ngày Mua": entry_date.strftime('%d/%m/%Y'), "Giá Mua": entry, "Ngày Bán": date.strftime('%d/%m/%Y'), "Giá Bán": price, "Lãi/Lỗ %": pnl*100})
            cash += shares * price; shares = 0
        equity.append(cash + (shares * price))
    ret = (equity[-1] - capital)/capital * 100
    win_rate = (wins/trades * 100) if trades > 0 else 0
    return ret, win_rate, trades, pd.DataFrame(trade_logs), duration_days

# ---------------------------------------------------------
# 5. AI ADVISOR CHUYÊN SÂU
# ---------------------------------------------------------
def render_ai_analysis(df, symbol):
    last = df.iloc[-1]
    adx = last.get('ADX', 0); adx_st = "MẠNH" if adx > 25 else "YẾU/SIDEWAY"
    rsi = last['RSI']; rsi_st = "QUÁ MUA" if rsi > 70 else "QUÁ BÁN" if rsi < 30 else "TRUNG TÍNH"
    span_a = last.get('SpanA', 0); span_b = last.get('SpanB', 0)
    ichi_pos = "TRÊN MÂY (TÍCH CỰC)" if last['close'] > max(span_a, span_b) else "DƯỚI MÂY (TIÊU CỰC)" if last['close'] < min(span_a, span_b) else "TRONG MÂY"
    risk_val = (last['close'] - last['SL'])
    rr_ratio = (last['T1'] - last['close']) / risk_val if risk_val > 0 else 0
    expert_opinion = "Cổ phiếu đang giữ xu hướng tốt. Ưu tiên giải ngân tại hỗ trợ." if last['Trend_Phase'] == 'POSITIVE' else "Thị trường rủi ro, giá nằm dưới MA50. Nên hạ tỷ trọng."

    html = f"""
<div class='ai-panel'>
<div class='ai-title'>🤖 AI ADVISOR - {symbol}</div>
        
<div class='ai-section-title'>VÙNG MUA (BUY ZONE)</div>
<div class='ai-text'>
• <span class='ai-highlight'>Hỗ trợ:</span> {min(last['MA50'], last['Kijun']):,.2f} - {last['MA50']:,.2f}<br>
• <span class='ai-highlight'>Điểm mua kiến nghị:</span> Quanh mức {last['close'] * 0.995:,.2f}<br>
• <span class='ai-highlight'>Trạng thái:</span> {'Chờ mua' if last['RSI'] > 65 else 'Giải ngân thăm dò'}
</div>

<div class='ai-section-title'>VÙNG BÁN (SELL ZONE)</div>
<div class='ai-text'>
• <span class='ai-highlight'>Mục tiêu 1 (T1):</span> <span style='color:#00E676; font-weight:bold;'>{last['T1']:,.2f}</span><br>
• <span class='ai-highlight'>Mục tiêu 2 (T2):</span> <span style='color:#00E5FF; font-weight:bold;'>{last['T2']:,.2f}</span><br>
</div>

<div class='ai-section-title'>CHIẾN LƯỢC QUẢN TRỊ</div>
<div class='ai-expert-box'>
<div class='ai-text' style='margin-left:0;'>
• <span style='color:#FF5252; font-weight:bold;'>Dừng lỗ (SL): {last['SL']:,.1f}</span><br>
• <span class='ai-highlight'>Tỷ lệ R:R:</span> 1:{rr_ratio:.1f} ({'Đẹp' if rr_ratio > 1.5 else 'Thấp'})
</div>
</div>

<div class='ai-section-title'>PHÂN TÍCH KỸ THUẬT</div>
<div class='ai-text'>
• <span class='ai-highlight'>Xu hướng:</span> {last['Trend_Phase']} ({adx_st})<br>
• <span class='ai-highlight'>Động lượng (RSI):</span> {last['RSI']:.1f} ({rsi_st})<br>
• <span class='ai-highlight'>Ichimoku:</span> {ichi_pos}
</div>

<div class='ai-section-title'>NHẬN ĐỊNH</div>
<div class='ai-text' style='font-style: italic;'>
"{expert_opinion}"
</div>
</div>
"""
    return html

# ---------------------------------------------------------
# 6. GIAO DIỆN CHÍNH
# ---------------------------------------------------------
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False

# Kiểm tra Token bảo mật
if st.session_state.logged_in and not db.check_token_valid(st.session_state.username, st.session_state.token):
    st.session_state.logged_in = False
    st.rerun()

# --- MÀN HÌNH ĐĂNG NHẬP ---
if not st.session_state.logged_in:
    c1, c2, c3 = st.columns([1, 1, 1])
    with c2:
        st.markdown("<br><h1 style='text-align: center;'>TAMDUY CAPITAL</h1>", unsafe_allow_html=True)
        with st.form("login_form"):
            u = st.text_input("Username")
            p = st.text_input("Password", type="password")
            if st.form_submit_button("LOGIN TERMINAL", use_container_width=True):
                res = db.login_user(u, p)
                if res["status"] == "success":
                    st.session_state.update(
                        logged_in=True, username=u, name=res["name"], role=res["role"], 
                        token=res["token"], days_left=res["days_left"], expiry_date=res["expiry_date"]
                    )
                    st.toast(f"Chào {res['name']}!", icon="🚀")
                    time.sleep(1)
                    st.rerun()
                else:
                    st.error(res.get("msg", "Đăng nhập thất bại"))

# --- MÀN HÌNH CHÍNH (ĐÃ LOGIN) ---
else:
    c_logo, c_input, c_user, c_out = st.columns([2, 2, 4, 1])
    with c_logo: st.markdown("### 🦅 TAMDUY TRADER")
    with c_input: symbol = st.text_input("MÃ CK", "", label_visibility="collapsed", placeholder="Nhập mã...").upper()
    with c_user:
        days = st.session_state.get('days_left', 0); expiry = st.session_state.get('expiry_date', 'N/A')
        color = "#ff4b4b" if days <= 7 else "#29b045"
        st.markdown(f"<div style='text-align: right; line-height: 1.2;'>User: <b>{st.session_state.name}</b> <br><span style='color: {color}; font-size: 0.85rem;'>Hạn: {expiry} (Còn {days} ngày)</span></div>", unsafe_allow_html=True)
    with c_out: 
        if st.button("EXIT"): st.session_state.logged_in = False; st.rerun()
    st.markdown("---")

    if symbol:
        d = get_market_data(symbol)
        if not d["error"]:
            df = run_strategy_full(d["df"])
            ret_bt, win_bt, trades_bt, logs_bt, duration_days = run_backtest_fast(df)
            last = df.iloc[-1]; prev = df.iloc[-2] if len(df) > 1 else last
            
            # --- HUD METRICS ---
            k1, k2, k3, k4, k5 = st.columns(5)
            change_pct = (last['close'] - prev['close']) / prev['close'] if prev['close'] != 0 else 0
            p_color = "#CE55FF" if change_pct >= 0.069 else "#66CCFF" if change_pct <= -0.069 else "#00E676" if change_pct > 0 else "#FF5252"
            k1.markdown(f"<div class='hud-box'><div class='hud-val' style='color:{p_color}'>{last['close']:,.2f} ({change_pct:+.2%})</div><div class='hud-lbl'>GIÁ HIỆN TẠI</div></div>", unsafe_allow_html=True)
            s_col = "#00E676" if "MUA" in last['SIGNAL'] else "#FF5252" if "BÁN" in last['SIGNAL'] else "#888"
            k2.markdown(f"<div class='hud-box'><div class='hud-val' style='color:{s_col}'>{last['SIGNAL'] if last['SIGNAL'] else 'HOLD'}</div><div class='hud-lbl'>TÍN HIỆU</div></div>", unsafe_allow_html=True)
            k3.markdown(f"<div class='hud-box'><div class='hud-val' style='color:#FF5252'>{last['SL']:,.1f}</div><div class='hud-lbl'>STOP LOSS</div></div>", unsafe_allow_html=True)
            k4.markdown(f"<div class='hud-box'><div class='hud-val' style='color:#00E676'>{last['T1']:,.1f}</div><div class='hud-lbl'>TARGET 1</div></div>", unsafe_allow_html=True)
            k5.markdown(f"<div class='hud-box'><div class='hud-val' style='color:#00E5FF'>{last['T2']:,.1f}</div><div class='hud-lbl'>TARGET 2</div></div>", unsafe_allow_html=True)

            p1, p2, p3, p4 = st.columns(4)
            p1.markdown(f"<div class='perf-box'><div class='perf-val' style='color: #d4af37'>{trades_bt}</div><div class='perf-lbl'>TỔNG SỐ LỆNH</div></div>", unsafe_allow_html=True)
            p2.markdown(f"<div class='perf-box'><div class='perf-val' style='color: #d4af37'>{win_bt:.1f}%</div><div class='perf-lbl'>TỶ LỆ THẮNG</div></div>", unsafe_allow_html=True)
            ret_color = "#BB86FC" if ret_bt > 0 else "#FF5252"
            p3.markdown(f"<div class='perf-box'><div class='perf-val' style='color: {ret_color}'>{ret_bt:+.2f}%</div><div class='perf-lbl'>LỢI NHUẬN KỲ VỌNG</div></div>", unsafe_allow_html=True)
            p4.markdown(f"<div class='perf-box'><div class='perf-val' style='color: #d4af37'>{duration_days} NGÀY</div><div class='perf-lbl'>THỜI GIAN THEO DÕI</div></div>", unsafe_allow_html=True)

            col_chart, col_ai = st.columns([3, 1])
            with col_chart:
                fig = make_subplots(rows=4, cols=1, shared_xaxes=True, row_heights=[0.5, 0.15, 0.15, 0.2], vertical_spacing=0.015)
                fig.add_trace(go.Scatter(x=df.index, y=df['SpanA'], line=dict(width=0), showlegend=False), row=1, col=1)
                fig.add_trace(go.Scatter(x=df.index, y=df['SpanB'], fill='tonexty', fillcolor='rgba(41, 98, 255, 0.08)', line=dict(width=0), showlegend=False), row=1, col=1)
                for trend, color in [('POSITIVE', '#00E676'), ('NEGATIVE', '#f23645'), ('SIDEWAY', '#f0b90b')]:
                    tdf = df[df['Trend_Phase'] == trend]
                    if not tdf.empty: fig.add_trace(go.Candlestick(x=tdf.index, open=tdf['open'], high=tdf['high'], low=tdf['low'], close=tdf['close'], name=trend, increasing_line_color=color, increasing_fillcolor=color, decreasing_line_color=color, decreasing_fillcolor=color, whiskerwidth=0.8, line_width=1.5), row=1, col=1)
                fig.add_hline(y=last['SL'], line_dash="dash", line_color="#f23645", annotation_text="SL", row=1, col=1)
                fig.add_hline(y=last['T1'], line_dash="dash", line_color="#00E676", annotation_text="T1", row=1, col=1)
                fig.add_hline(y=last['T2'], line_dash="dash", line_color="#00E5FF", annotation_text="T2", row=1, col=1)
                fig.add_trace(go.Scatter(x=df.index, y=df['MA50'], line=dict(color='rgba(41, 98, 255, 0.8)', width=1.8), name='MA50'), row=1, col=1)
                fig.add_trace(go.Bar(x=df.index, y=df['volume'], marker_color=['#00C853' if c >= o else '#f23645' for c, o in zip(df['close'], df['open'])], opacity=0.8), row=2, col=1)
                fig.add_trace(go.Bar(x=df.index, y=df['MACD_Hist'], marker_color=['#00E676' if h > 0 else '#f23645' for h in df['MACD_Hist']], opacity=0.8), row=3, col=1)
                fig.add_trace(go.Scatter(x=df.index, y=df['RSI'], line=dict(color='#7e57c2', width=1.5)), row=4, col=1)
                for r in range(1, 5): fig.update_yaxes(side="right", showgrid=True, gridcolor='rgba(255, 255, 255, 0.05)', row=r, col=1)
                if len(df) > 90: fig.update_xaxes(range=[df.index[-90], df.index[-1] + timedelta(days=5)], row=1, col=1)
                fig.update_layout(height=850, paper_bgcolor='#000', plot_bgcolor='#000', margin=dict(l=0, r=60, t=30, b=0), showlegend=False, xaxis_rangeslider_visible=False, dragmode='pan')
                st.plotly_chart(fig, use_container_width=True, config={'scrollZoom': True, 'displayModeBar': True, 'displaylogo': False})
                t_log, t_adm = st.tabs(["📋 NHẬT KÝ LỆNH", "⚙️ ADMIN"])
                with t_log:
                    if not logs_bt.empty:
                        def style_pnl(val): return f"background-color: {'#1b5e20' if val > 0 else '#b71c1c'}; color: white; font-weight: bold;"
                        st.dataframe(logs_bt.style.applymap(style_pnl, subset=['Lãi/Lỗ %']).format({"Giá Mua": "{:,.2f}", "Giá Bán": "{:,.2f}", "Lãi/Lỗ %": "{:+.2f}%"}), use_container_width=True)
                with t_adm:
                    if st.session_state.role == "admin": st.dataframe(db.get_all_users(), use_container_width=True)
            with col_ai:
                st.markdown(render_ai_analysis(df, symbol), unsafe_allow_html=True)
        else: st.error(d["error"])

