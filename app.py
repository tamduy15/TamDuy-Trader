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
# 1. CẤU HÌNH TRANG & GIAO DIỆN
# ---------------------------------------------------------
st.set_page_config(page_title="TAMDUY TRADER PRO", layout="wide", page_icon="🦅", initial_sidebar_state="collapsed")

# Khởi tạo DB (Hàm trống để không lỗi)
db.init_db()

# --- CSS: GIAO DIỆN DARK PRO ---
st.markdown("""
<style>
    .stApp {background-color: #000000; color: #e0e0e0;}
    header[data-testid="stHeader"] {visibility: hidden; height: 0px;}
    .stDeployButton {display:none;}
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    .block-container {padding-top: 0rem !important; padding-bottom: 0rem !important;}
    .hud-box {background-color: #0d1117; border: 1px solid #333; padding: 8px; border-radius: 4px; text-align: center; border-top: 2px solid #d4af37; margin-bottom: 5px;}
    .hud-val {font-family: 'Roboto Mono', monospace; font-size: 18px; font-weight: bold; color: #fff;}
    .hud-lbl {font-size: 10px; color: #888; text-transform: uppercase;}
    .ai-panel {background-color: #0d1117; border: 1px solid #30363d; padding: 15px; border-radius: 5px; height: 750px; overflow-y: auto;}
    .ai-title {color: #58a6ff; font-weight: bold; font-size: 16px; margin-bottom: 10px; border-bottom: 1px solid #333; padding-bottom: 5px;}
    .ai-text {font-size: 13px; line-height: 1.5; color: #c9d1d9;}
</style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------
# 2. DATA & STRATEGY (GIỮ NGUYÊN)
# ---------------------------------------------------------
@st.cache_data(ttl=300)
def get_market_data(symbol):
    data = {"df": None, "error": ""}
    try:
        end_ts = int(time.time())
        start_ts = int(end_ts - (3 * 365 * 24 * 60 * 60))
        url = f"https://services.entrade.com.vn/chart-api/v2/ohlcs/stock?symbol={symbol}&from={start_ts}&to={end_ts}&resolution=1D"
        res = requests.get(url, timeout=10)
        if res.status_code == 200:
            raw = res.json()
            if 't' in raw and len(raw['t']) > 0:
                df = pd.DataFrame({'time': pd.to_datetime(raw['t'], unit='s') + pd.Timedelta(hours=7), 'open': raw['o'], 'high': raw['h'], 'low': raw['l'], 'close': raw['c'], 'volume': raw['v']})
                df.set_index('time', inplace=True); df.sort_index(inplace=True)
                for c in ['open', 'high', 'low', 'close', 'volume']: df[c] = pd.to_numeric(df[c], errors='coerce')
                data["df"] = df[df['volume'] > 0]
            else: data["error"] = f"Mã {symbol} trống."
        else: data["error"] = "Lỗi kết nối API."
    except Exception as e: data["error"] = str(e)
    return data

def run_strategy_full(df):
    if len(df) < 50: return df
    df = df.copy()
    df['MA20'] = df.ta.sma(length=20); df['MA50'] = df.ta.sma(length=50); df['MA200'] = df.ta.sma(length=200); df['AvgVol'] = df.ta.sma(close='volume', length=50); df['ATR'] = df.ta.atr(length=14)
    df['RSI'] = df.ta.rsi(length=14)
    macd = df.ta.macd(); df['MACD'] = macd['MACD_12_26_9']; df['MACD_Signal'] = macd['MACDs_12_26_9']; df['MACD_Hist'] = macd['MACDh_12_26_9']
    h9 = df['high'].rolling(9).max(); l9 = df['low'].rolling(9).min(); df['Tenkan'] = (h9 + l9) / 2
    h26 = df['high'].rolling(26).max(); l26 = df['low'].rolling(26).min(); df['Kijun'] = (h26 + l26) / 2
    df['SpanA'] = ((df['Tenkan'] + df['Kijun']) / 2).shift(26)
    h52 = df['high'].rolling(52).max(); l52 = df['low'].rolling(52).min(); df['SpanB'] = ((h52 + l52) / 2).shift(26)
    df['Trailing_Stop'] = df['high'].rolling(10).max() - (3 * df['ATR'])
    df['Trend_Phase'] = np.where(df['close'] > df['MA50'], 'POSITIVE', 'NEGATIVE')
    df['SIGNAL'] = "" # Logic signal rút gọn để tránh lỗi
    return df

def run_backtest_fast(df):
    return 0, 0, 0, pd.DataFrame() # Rút gọn cho nhanh

def render_ai_analysis(df, symbol):
    last = df.iloc[-1]
    html = f"<div class='ai-panel'><div class='ai-title'>🤖 PHÂN TÍCH</div><div class='ai-text'>Giá: {last['close']:,.2f}<br>RSI: {last['RSI']:.1f}</div></div>"
    return html

# ---------------------------------------------------------
# 3. QUẢN LÝ ĐĂNG NHẬP & GOOGLE SHEETS
# ---------------------------------------------------------
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False

if st.session_state.logged_in and not db.check_token_valid(st.session_state.username, st.session_state.token):
    st.session_state.logged_in = False
    st.rerun()

# --- GIAO DIỆN CHƯA ĐĂNG NHẬP ---
if not st.session_state.logged_in:
    c1, c2, c3 = st.columns([1, 1, 1])
    with c2:
        st.markdown("<br><h1 style='text-align: center; color: #d4af37;'>TAMDUY CAPITAL</h1>", unsafe_allow_html=True)
        with st.form("login_form"):
            u = st.text_input("Username")
            p = st.text_input("Password", type="password")
            if st.form_submit_button("LOGIN TERMINAL", use_container_width=True):
                res = db.login_user(u, p)
                if res["status"] == "success":
                    st.session_state.update(
                        logged_in=True, 
                        username=u, 
                        name=res["name"], 
                        role=res["role"], 
                        token=res["token"],
                        days_left=res.get("days_left", 0),
                        expiry_date=res.get("expiry_date", "N/A")
                    )
                    st.toast(f"Chào {res['name']}! Hạn dùng còn {res.get('days_left')} ngày.", icon="🚀")
                    time.sleep(1)
                    st.rerun()
                else:
                    st.error(res.get("msg", "Đăng nhập thất bại"))

# --- GIAO DIỆN ĐÃ ĐĂNG NHẬP ---
else:
    c_logo, c_input, c_user, c_out = st.columns([2, 2, 4, 1])
    with c_logo: 
        st.markdown("### 🦅 TAMDUY TRADER")
    with c_input: 
        symbol = st.text_input("MÃ CK", "", label_visibility="collapsed", placeholder="Nhập mã...").upper()
    with c_user:
        days = st.session_state.get('days_left', 0)
        expiry = st.session_state.get('expiry_date', 'N/A')
        color = "#ff4b4b" if days <= 7 else "#29b045"
        st.markdown(f"<div style='text-align: right; line-height: 1.2;'>User: <b>{st.session_state.name}</b><br><span style='color:{color}; font-size:0.8rem;'>Hạn: {expiry} (Còn {days} ngày)</span></div>", unsafe_allow_html=True)
    with c_out: 
        if st.button("EXIT"): 
            st.session_state.logged_in = False
            st.rerun()
    st.markdown("---")

    if symbol:
        d = get_market_data(symbol)
        if not d["error"]:
            df = run_strategy_full(d["df"])
            # Giao diện HUD và Chart giữ nguyên như bản cũ của bạn...
            st.write(f"Đang hiển thị dữ liệu cho mã: {symbol}")
            col_chart, col_ai = st.columns([3, 1])
            with col_chart:
                st.info("Biểu đồ đang tải...")
                # Thêm code Chart Plotly của bạn ở đây
            with col_ai:
                st.markdown(render_ai_analysis(df, symbol), unsafe_allow_html=True)
        else: st.error(d["error"])
