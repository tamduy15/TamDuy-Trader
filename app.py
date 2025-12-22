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
# 1. KẾT NỐI API & CẤU HÌNH
# ---------------------------------------------------------
st.set_page_config(page_title="TAMDUY TRADER PRO", layout="wide", page_icon="🦅", initial_sidebar_state="collapsed")
db.init_db()

# --- CSS: PRO TRADING TERMINAL (CLEAN MODE) ---
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

    /* HUD Box Styling */
    .hud-box {
        background-color: #0d1117; border: 1px solid #333;
        padding: 8px; border-radius: 4px; text-align: center;
        border-top: 2px solid #d4af37; margin-bottom: 5px;
    }
    .hud-val {font-family: 'Roboto Mono', monospace; font-size: 18px; font-weight: bold; color: #fff;}
    .hud-lbl {font-size: 10px; color: #888; text-transform: uppercase;}
    
    /* Performance Box */
    .perf-box {
        background-color: #161b22; border: 1px solid #30363d;
        padding: 8px; border-radius: 4px; text-align: center;
        margin-bottom: 5px;
    }
    .perf-val {font-family: 'Roboto Mono', monospace; font-size: 16px; font-weight: bold;}
    .perf-lbl {font-size: 9px; color: #aaa; text-transform: uppercase;}

    /* AI Advisor Layout Modernized */
    .ai-panel {
        background-color: #0d1117; border: 1px solid #30363d;
        padding: 20px; border-radius: 8px; height: 850px; overflow-y: auto;
    }
    .ai-title {color: #d4af37; font-weight: bold; font-size: 18px; margin-bottom: 15px; border-bottom: 2px solid #d4af37; padding-bottom: 8px; text-transform: uppercase; letter-spacing: 1px;}
    .ai-section-title {
        color: #58a6ff; font-weight: bold; font-size: 14px; 
        margin-top: 20px; margin-bottom: 8px; 
        display: flex; align-items: center;
        text-transform: uppercase;
        border-bottom: 1px dashed #333;
        padding-bottom: 4px;
    }
    .ai-section-title::before {content: '◈'; margin-right: 8px; color: #d4af37;}
    .ai-text {font-size: 13px; line-height: 1.7; color: #c9d1d9; margin-left: 5px;}
    .ai-highlight {color: #fff; font-weight: 600;}
    .ai-expert-box { background-color: #161b22; border-left: 4px solid #d4af37; padding: 12px; margin: 15px 0; border-radius: 0 6px 6px 0; }
    
    ::-webkit-scrollbar {width: 6px;}
    ::-webkit-scrollbar-thumb {background: #333; border-radius: 3px;}
    
    .stTabs [data-baseweb="tab-list"] {gap: 2px;}
    .stTabs [data-baseweb="tab"] {background-color: #111; border: 1px solid #333; color: #888; font-size: 11px; padding: 5px 10px;}
    .stTabs [aria-selected="true"] {background-color: #d4af37 !important; color: #000 !important; font-weight: bold;}
</style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------
# 2. DATA ENGINE (DNSE API - REALTIME)
# ---------------------------------------------------------
# QUAN TRỌNG: Giảm ttl xuống 5s để cập nhật giá gần như tức thời khi reload
@st.cache_data(ttl=1) 
def get_market_data(symbol):
    data = {"df": None, "error": ""}
    headers = {'User-Agent': 'Mozilla/5.0'}
    try:
        # Lấy dữ liệu đến thời điểm hiện tại (Realtime)
        end_ts = int(time.time())
        start_ts = int(end_ts - (3 * 365 * 24 * 60 * 60)) # 3 năm
        
        url = f"https://services.entrade.com.vn/chart-api/v2/ohlcs/stock?symbol={symbol}&from={start_ts}&to={end_ts}&resolution=1D"
        res = requests.get(url, headers=headers, timeout=5)
        
        if res.status_code == 200:
            raw = res.json()
            if 't' in raw and len(raw['t']) > 0:
                df = pd.DataFrame({
                    'time': pd.to_datetime(raw['t'], unit='s') + pd.Timedelta(hours=7),
                    'open': raw['o'], 'high': raw['h'], 'low': raw['l'], 'close': raw['c'], 'volume': raw['v']
                })
                df.set_index('time', inplace=True)
                df.sort_index(inplace=True)
                
                for c in ['open', 'high', 'low', 'close', 'volume']: 
                    df[c] = pd.to_numeric(df[c], errors='coerce')
                
                # Lọc bỏ volume 0 (ngày nghỉ) nhưng giữ lại phiên hôm nay dù vol nhỏ
                df = df[df['volume'] >= 0] 
                data["df"] = df
            else: 
                data["error"] = f"Mã {symbol} không có dữ liệu."
        else: 
            data["error"] = f"Lỗi DNSE: {res.status_code}"
    except Exception as e: 
        data["error"] = str(e)
    return data

# ---------------------------------------------------------
# 3. STRATEGY ENGINE (CHUYÊN SÂU)
# ---------------------------------------------------------
def run_strategy_full(df):
    if len(df) < 52: return df
    df = df.copy()
    
    # --- INDICATORS CƠ BẢN ---
    df['MA20'] = df.ta.sma(length=20)
    df['MA50'] = df.ta.sma(length=50)
    df['MA200'] = df.ta.sma(length=200)
    df['AvgVol'] = df.ta.sma(close='volume', length=50)
    df['ATR'] = df.ta.atr(length=14)
    
    # --- INDICATORS NÂNG CAO ---
    try:
        adx_df = df.ta.adx(length=14)
        df['ADX'] = adx_df['ADX_14']
    except: df['ADX'] = 0

    macd = df.ta.macd(fast=12, slow=26, signal=9)
    if macd is not None:
        df['MACD'] = macd['MACD_12_26_9']
        df['MACD_Signal'] = macd['MACDs_12_26_9']
        df['MACD_Hist'] = macd['MACDh_12_26_9']
    
    df['RSI'] = df.ta.rsi(length=14)
    
    # ICHIMOKU CLOUD
    h9 = df['high'].rolling(9).max(); l9 = df['low'].rolling(9).min(); df['Tenkan'] = (h9 + l9) / 2
    h26 = df['high'].rolling(26).max(); l26 = df['low'].rolling(26).min(); df['Kijun'] = (h26 + l26) / 2
    df['SpanA'] = ((df['Tenkan'] + df['Kijun']) / 2).shift(26)
    h52 = df['high'].rolling(52).max(); l52 = df['low'].rolling(52).min(); df['SpanB'] = ((h52 + l52) / 2).shift(26)
    
    # --- XÁC ĐỊNH TRẠNG THÁI XU HƯỚNG ---
    df['Trend_Phase'] = 'SIDEWAY'
    df.loc[df['close'] > df['MA50'], 'Trend_Phase'] = 'POSITIVE'
    df.loc[df['close'] < df['MA50'], 'Trend_Phase'] = 'NEGATIVE'

    # --- TÍNH TOÁN TARGET / STOPLOSS ĐỘNG (Risk Management) ---
    # Stoploss: Dùng Kijun hoặc MA50 làm hỗ trợ cứng, trừ đi biên độ ATR
    # Nếu giá đang cao hơn MA50 -> SL dưới MA50 một chút
    # Nếu giá thấp hơn -> SL theo đáy gần nhất (Swing Low - giả lập bằng Low - 2ATR)
    
    support_level = np.where(df['close'] > df['MA50'], 
                             np.maximum(df['MA50'], df['Kijun']), 
                             df['close'])
    
    df['SL'] = support_level - (1.5 * df['ATR']) # SL cách hỗ trợ 1.5 ATR
    
    # Risk per share
    risk = (df['close'] - df['SL']).abs()
    risk = np.where(risk == 0, df['close']*0.05, risk) # Tránh lỗi chia 0
    
    # Target theo tỷ lệ Risk:Reward
    df['T1'] = df['close'] + (1.5 * risk) # R:R = 1:1.5
    df['T2'] = df['close'] + (3.0 * risk) # R:R = 1:3.0

    # --- TẠO TÍN HIỆU ---
    # Điều kiện Mua: Vượt đỉnh 20 phiên + Vol lớn + Trên MA200
    hhv_20 = df['high'].rolling(20).max().shift(1)
    buy_cond = (df['close'] > hhv_20) & (df['volume'] > 1.2 * df['AvgVol']) & (df['close'] > df['MA200'])
    
    # Điều kiện Bán: Gãy MA20
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
# 4. BACKTEST ENGINE
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
            pnl = (price - entry)/entry
            trades += 1
            if pnl > 0: wins += 1
            trade_logs.append({
                "Ngày Mua": entry_date.strftime('%d/%m/%Y'), 
                "Giá Mua": entry, 
                "Ngày Bán": date.strftime('%d/%m/%Y'), 
                "Giá Bán": price, 
                "Lãi/Lỗ %": pnl*100
            })
            cash += shares * price; shares = 0
        equity.append(cash + (shares * price))
        
    ret = (equity[-1] - capital)/capital * 100
    win_rate = (wins/trades * 100) if trades > 0 else 0
    return ret, win_rate, trades, pd.DataFrame(trade_logs), duration_days

# ---------------------------------------------------------
# 5. AI TECHNICAL ADVISOR (CHUYÊN SÂU THEO BỐ CỤC)
# ---------------------------------------------------------
def render_ai_analysis(df, symbol):
    last = df.iloc[-1]
    
    # Lấy thông số
    adx = last.get('ADX', 0)
    adx_st = "MẠNH" if adx > 25 else "YẾU/SIDEWAY"
    rsi = last['RSI']; rsi_st = "QUÁ MUA" if rsi > 70 else "QUÁ BÁN" if rsi < 30 else "TRUNG TÍNH"
    
    # Ichimoku Status
    span_a = last.get('SpanA', 0); span_b = last.get('SpanB', 0)
    cloud_top = max(span_a, span_b)
    cloud_bot = min(span_a, span_b)
    
    if last['close'] > cloud_top: ichi_pos = "TRÊN MÂY (BULLISH)"
    elif last['close'] < cloud_bot: ichi_pos = "DƯỚI MÂY (BEARISH)"
    else: ichi_pos = "TRONG MÂY (GIẰNG CO)"
    
    # Tính toán Risk/Reward
    risk_val = (last['close'] - last['SL'])
    reward_val = (last['T1'] - last['close'])
    rr_ratio = reward_val / risk_val if risk_val > 0 else 0
    
    # Nhận định tổng quan
    trend = last['Trend_Phase']
    if trend == 'POSITIVE':
        verdict = "Xu hướng tăng được xác nhận. Giá nằm trên các đường trung bình động quan trọng. Dòng tiền ổn định."
        action = "NẮM GIỮ / CANH MUA KHI CHỈNH"
        action_color = "#00FF00"
    else:
        verdict = "Xu hướng tiêu cực, giá nằm dưới vùng hỗ trợ. Áp lực bán vẫn còn."
        action = "QUAN SÁT / CƠ CẤU DANH MỤC"
        action_color = "#FF4B4B"

    # HTML Output
    html = f"""
<div class='ai-panel'>
    <div class='ai-title'>🤖 AI ADVISOR - {symbol}</div>
    
    <div class='ai-section-title'>VÙNG MUA (BUY ZONE)</div>
    <div class='ai-text'>
        • <span class='ai-highlight'>Hỗ trợ gần nhất:</span> {min(last['MA50'], last['Kijun']):,.2f}<br>
        • <span class='ai-highlight'>Vùng gom hàng:</span> {last['MA20']:,.2f} - {last['close']:,.2f}<br>
        • <span class='ai-highlight'>Điều kiện kích hoạt:</span> Giá vượt {last['high']:,.2f} với Vol > {last['AvgVol']:,.0f}
    </div>

    <div class='ai-section-title'>VÙNG BÁN (SELL ZONE)</div>
    <div class='ai-text'>
        • <span class='ai-highlight'>Mục tiêu 1 (T1):</span> <span style='color:#00E676; font-weight:bold;'>{last['T1']:,.2f}</span> (+{(last['T1']/last['close']-1)*100:.1f}%)<br>
        • <span class='ai-highlight'>Mục tiêu 2 (T2):</span> <span style='color:#00E5FF; font-weight:bold;'>{last['T2']:,.2f}</span> (+{(last['T2']/last['close']-1)*100:.1f}%)<br>
        • <span class='ai-highlight'>Kháng cự tâm lý:</span> {max(last['T2'], df['high'].tail(60).max()):,.2f}
    </div>

    <div class='ai-section-title'>CHIẾN LƯỢC QUẢN TRỊ</div>
    <div class='ai-expert-box'>
        <div class='ai-text' style='margin-left:0;'>
            • <span style='color:#FF5252; font-weight:bold;'>Cắt lỗ (STOPLOSS): {last['SL']:,.2f}</span><br>
            • <span class='ai-highlight'>Tỷ lệ R:R:</span> 1:{rr_ratio:.1f} ({'Tốt' if rr_ratio > 1.5 else 'Thấp'})<br>
            • <span class='ai-highlight'>Khuyến nghị:</span> {action}
        </div>
    </div>

    <div class='ai-section-title'>PHÂN TÍCH KỸ THUẬT</div>
    <div class='ai-text'>
        • <span class='ai-highlight'>Xu hướng (Trend):</span> {trend} ({adx_st})<br>
        • <span class='ai-highlight'>RSI (14):</span> {last['RSI']:.1f} ({rsi_st})<br>
        • <span class='ai-highlight'>Ichimoku Cloud:</span> {ichi_pos}<br>
        • <span class='ai-highlight'>MACD:</span> {'Cắt Lên Signal' if last['MACD'] > last['MACD_Signal'] else 'Cắt Xuống Signal'}
    </div>

    <div class='ai-section-title'>NHẬN ĐỊNH</div>
    <div class='ai-text' style='font-style: italic; color: #d4af37; border-left: 2px solid #58a6ff; padding-left: 10px;'>
        "{verdict} Nhà đầu tư nên tuân thủ kỷ luật cắt lỗ tại {last['SL']:,.0f} nếu giá quay đầu."
    </div>
</div>
"""
    return html

# ---------------------------------------------------------
# 6. GIAO DIỆN CHÍNH & LOGIC ĐĂNG NHẬP
# ---------------------------------------------------------
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False

if st.session_state.logged_in and not db.check_token_valid(st.session_state.username, st.session_state.token):
    st.session_state.logged_in = False
    st.rerun()

# --- FORM ĐĂNG NHẬP ---
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
                    st.session_state.update(logged_in=True, username=u, name=res["name"], role=res["role"], 
                                            token=res["token"], days_left=res.get("days_left", 0), expiry_date=res.get("expiry_date", "N/A"))
                    st.toast(f"Chào {res['name']}!", icon="🚀"); time.sleep(1); st.rerun()
                else: st.error(res.get("msg", "Đăng nhập thất bại"))

# --- TRADING TERMINAL ---
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
            
            # --- HUD ---
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
                # ... (Giữ nguyên logic vẽ biểu đồ như cũ để đảm bảo tính năng zoom/pan)
                fig.add_trace(go.Scatter(x=df.index, y=df['SpanA'], line=dict(width=0), showlegend=False), row=1, col=1)
                fig.add_trace(go.Scatter(x=df.index, y=df['SpanB'], fill='tonexty', fillcolor='rgba(41, 98, 255, 0.08)', line=dict(width=0), showlegend=False), row=1, col=1)
                
                df_pos = df[df['Trend_Phase'] == 'POSITIVE']; df_neg = df[df['Trend_Phase'] == 'NEGATIVE']; df_sdw = df[df['Trend_Phase'] == 'SIDEWAY']
                for trend_df, color, name in [(df_pos, '#00E676', 'Positive'), (df_neg, '#f23645', 'Negative'), (df_sdw, '#f0b90b', 'Sideway')]:
                    if not trend_df.empty:
                        fig.add_trace(go.Candlestick(x=trend_df.index, open=trend_df['open'], high=trend_df['high'], low=trend_df['low'], close=trend_df['close'], name=name, increasing_line_color=color, increasing_fillcolor=color, decreasing_line_color=color, decreasing_fillcolor=color, whiskerwidth=0.8, line_width=1.5), row=1, col=1)

                fig.add_hline(y=last['SL'], line_dash="dash", line_color="#f23645", annotation_text="SL", annotation_position="bottom right", row=1, col=1)
                fig.add_hline(y=last['T1'], line_dash="dash", line_color="#00E676", annotation_text="T1", annotation_position="top right", row=1, col=1)
                fig.add_hline(y=last['T2'], line_dash="dash", line_color="#00E5FF", annotation_text="T2", annotation_position="top right", row=1, col=1)
                fig.add_trace(go.Scatter(x=df.index, y=df['MA50'], line=dict(color='rgba(41, 98, 255, 0.8)', width=1.8), name='MA50'), row=1, col=1)
                
                buys = df[df['SIGNAL'] == 'MUA']
                if not buys.empty: fig.add_trace(go.Scatter(x=buys.index, y=buys['low']*0.985, mode='markers', marker=dict(symbol='triangle-up', size=16, color='#00E676', line=dict(width=1, color='#ffffff')), name='BUY Signal'), row=1, col=1)
                sells = df[df['SIGNAL'] == 'BÁN']
                if not sells.empty: fig.add_trace(go.Scatter(x=sells.index, y=sells['high']*1.015, mode='markers', marker=dict(symbol='triangle-down', size=16, color='#f23645', line=dict(width=1, color='#ffffff')), name='SELL Signal'), row=1, col=1)

                fig.add_trace(go.Bar(x=df.index, y=df['volume'], marker_color=['#00C853' if c >= o else '#f23645' for c, o in zip(df['close'], df['open'])], name='Volume', opacity=0.8), row=2, col=1)
                fig.add_trace(go.Bar(x=df.index, y=df['MACD_Hist'], marker_color=['#00E676' if h > 0 else '#f23645' for h in df['MACD_Hist']], opacity=0.8), row=3, col=1)
                fig.add_trace(go.Scatter(x=df.index, y=df['RSI'], line=dict(color='#7e57c2', width=1.5)), row=4, col=1)

                for r in range(1, 5):
                    fig.update_yaxes(side="right", showgrid=True, gridcolor='rgba(255, 255, 255, 0.05)', zeroline=False, row=r, col=1, tickfont=dict(color='#888', family='Roboto Mono'))
                    fig.update_xaxes(showgrid=False, zeroline=False, row=r, col=1, tickfont=dict(color='#888'))

                if len(df) > 90:
                    start_date = df.index[-90]; end_date = df.index[-1] + timedelta(days=5)
                    fig.update_xaxes(range=[start_date, end_date], row=1, col=1)

                fig.update_layout(height=850, paper_bgcolor='#000', plot_bgcolor='#000', margin=dict(l=0, r=60, t=30, b=0), showlegend=False, xaxis_rangeslider_visible=False, hovermode='x unified', dragmode='pan')
                st.plotly_chart(fig, use_container_width=True, config={'scrollZoom': True, 'displayModeBar': True, 'modeBarButtonsToAdd': ['drawline', 'drawrect', 'eraseshape'], 'displaylogo': False})
                
                t1, t2 = st.tabs(["📋 NHẬT KÝ LỆNH", "⚙️ QUẢN TRỊ"])
                with t1:
                    if not logs_bt.empty:
                        def style_pnl(val): return f"background-color: {'#1b5e20' if val > 0 else '#b71c1c'}; color: white; font-weight: bold;"
                        st.dataframe(logs_bt.style.applymap(style_pnl, subset=['Lãi/Lỗ %']).format({"Giá Mua": "{:,.2f}", "Giá Bán": "{:,.2f}", "Lãi/Lỗ %": "{:+.2f}%"}), use_container_width=True)
                with t2:
                    if st.session_state.role == "admin": st.dataframe(db.get_all_users(), use_container_width=True)

            with col_ai:
                st.markdown(render_ai_analysis(df, symbol), unsafe_allow_html=True)
        else: st.error(d["error"])

