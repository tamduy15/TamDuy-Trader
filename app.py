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
    @import url('https://fonts.googleapis.com/css2?family=Roboto+Mono:wght@500&display=swap');
    
    h1, h2, h3 {color: #d4af37 !important; font-family: 'Segoe UI', sans-serif;}
    
    header[data-testid="stHeader"] { visibility: hidden; height: 0px; }
    .stDeployButton {display:none;}
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    
    .block-container { padding-top: 0rem !important; padding-bottom: 0rem !important; }

    .hud-box {
        background-color: #0d1117; border: 1px solid #333;
        padding: 8px; border-radius: 4px; text-align: center;
        border-top: 2px solid #d4af37; margin-bottom: 5px;
    }
    .hud-val {font-family: 'Roboto Mono', monospace; font-size: 18px; font-weight: bold; color: #fff;}
    .hud-lbl {font-size: 10px; color: #888; text-transform: uppercase;}
    
    .ai-panel {
        background-color: #0d1117; border: 1px solid #30363d;
        padding: 15px; border-radius: 5px; height: 800px; overflow-y: auto;
    }
    .ai-title {color: #58a6ff; font-weight: bold; font-size: 16px; margin-bottom: 10px; border-bottom: 1px solid #333; padding-bottom: 5px;}
    .ai-text {font-size: 13px; line-height: 1.6; color: #c9d1d9;}
    .ai-expert-box { background-color: #161b22; border-left: 3px solid #d4af37; padding: 10px; margin: 10px 0; border-radius: 0 4px 4px 0; }
    
    ::-webkit-scrollbar {width: 6px;}
    ::-webkit-scrollbar-thumb {background: #333; border-radius: 3px;}
    
    .stTabs [data-baseweb="tab-list"] {gap: 2px;}
    .stTabs [data-baseweb="tab"] {background-color: #111; border: 1px solid #333; color: #888; font-size: 11px; padding: 5px 10px;}
    .stTabs [aria-selected="true"] {background-color: #d4af37 !important; color: #000 !important; font-weight: bold;}
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
                df.set_index('time', inplace=True)
                df.sort_index(inplace=True)
                for c in ['open', 'high', 'low', 'close', 'volume']: df[c] = pd.to_numeric(df[c], errors='coerce')
                df = df[df['volume'] > 0]
                data["df"] = df
            else: data["error"] = f"Mã {symbol} không có dữ liệu."
        else: data["error"] = f"Lỗi DNSE: {res.status_code}"
    except Exception as e: data["error"] = str(e)
    return data

# ---------------------------------------------------------
# 3. STRATEGY ENGINE (ADVANCED)
# ---------------------------------------------------------
def run_strategy_full(df):
    if len(df) < 52: return df
    df = df.copy()
    
    # INDICATORS CƠ BẢN
    df['MA20'] = df.ta.sma(length=20)
    df['MA50'] = df.ta.sma(length=50)
    df['MA200'] = df.ta.sma(length=200)
    df['AvgVol'] = df.ta.sma(close='volume', length=50)
    df['ATR'] = df.ta.atr(length=14)
    
    # ADX SỨC MẠNH XU HƯỚNG
    try:
        adx_df = df.ta.adx(length=14)
        df['ADX'] = adx_df['ADX_14']
        df['DMP'] = adx_df['DMP_14']
        df['DMN'] = adx_df['DMN_14']
    except: 
        df['ADX'] = 0; df['DMP'] = 0; df['DMN'] = 0

    # MACD & RSI
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
    
    # TREND PHASE
    conditions = [(df['close'] > df['MA50']), (df['close'] < df['MA50'])]
    choices = ['POSITIVE', 'NEGATIVE']
    df['Trend_Phase'] = np.select(conditions, choices, default='SIDEWAY')

    # SIGNALS & QUẢN TRỊ RỦI RO (TARGET/STOPLOSS)
    hhv_20 = df['high'].rolling(20).max().shift(1)
    llv_20 = df['low'].rolling(20).min().shift(1)
    
    # Tính toán Stoploss/Target động
    # Stoploss = Max(MA50, Kijun) hoặc Price - 1.5 * ATR
    df['SL'] = np.where(df['close'] > df['MA50'], 
                        np.maximum(df['MA50'], df['Kijun']) - (0.5 * df['ATR']), 
                        df['close'] - (2 * df['ATR']))
    
    # Target 1: Tỷ lệ R:R = 1:1.5
    df['T1'] = df['close'] + 1.5 * (df['close'] - df['SL']).abs()
    # Target 2: Tỷ lệ R:R = 1:3 hoặc Kháng cự 20 phiên
    df['T2'] = df['close'] + 3.0 * (df['close'] - df['SL']).abs()

    # Tín hiệu Pocket Pivot / Breakout
    breakout = (df['close'] > hhv_20) & (df['volume'] > 1.3 * df['AvgVol']) & (df['close'] > df['MA50'])
    down_vol_10 = pd.Series(np.where(df['close'] < df['close'].shift(1), df['volume'], 0), index=df.index).rolling(10).max().shift(1)
    pocket = (df['volume'] > down_vol_10) & (df['close'] > df['MA20']) & (df['close'] > df['close'].shift(1))
    
    buy_cond = (breakout | pocket) & (df['close'] > df['MA200'])
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
    
    for i in range(len(df)):
        price = df['close'].iloc[i]; sig = df['SIGNAL'].iloc[i]; date = df.index[i]
        if sig == 'MUA' and cash > 0:
            shares = cash // price; cash -= shares * price; entry = price; entry_date = date
        elif sig == 'BÁN' and shares > 0:
            cash += shares * price; trades += 1; pnl = (price - entry)/entry
            if pnl > 0: wins += 1
            trade_logs.append({"Ngày Mua": entry_date, "Giá Mua": entry, "Ngày Bán": date, "Giá Bán": price, "Lãi/Lỗ %": pnl*100})
            shares = 0
        equity.append(cash + (shares * price))
        
    ret = (equity[-1] - capital)/capital * 100
    win_rate = (wins/trades * 100) if trades > 0 else 0
    return ret, win_rate, trades, pd.DataFrame(trade_logs)

# ---------------------------------------------------------
# 5. AI TECHNICAL ADVISOR (ENHANCED)
# ---------------------------------------------------------
def render_ai_analysis(df, symbol):
    last = df.iloc[-1]
    adx = last.get('ADX', 0)
    adx_st = "MẠNH" if adx > 25 else "YẾU" if adx < 20 else "HÌNH THÀNH"
    
    rsi = last['RSI']
    rsi_st = "QUÁ MUA" if rsi > 70 else "QUÁ BÁN" if rsi < 30 else "TRUNG TÍNH"
    
    span_a = last.get('SpanA', 0); span_b = last.get('SpanB', 0)
    cloud_st = "TRÊN MÂY (TÍCH CỰC)" if last['close'] > max(span_a, span_b) else "DƯỚI MÂY (TIÊU CỰC)" if last['close'] < min(span_a, span_b) else "TRONG MÂY"
    cloud_color = "#00FF00" if "TÍCH CỰC" in cloud_st else "#FF4B4B" if "TIÊU CỰC" in cloud_st else "#FFD700"
    
    phase = last.get('Trend_Phase', 'SIDEWAY')
    phase_text = "TÍCH CỰC (UPTREND)" if phase == 'POSITIVE' else "TIÊU CỰC (DOWNTREND)"
    phase_color = "#00FF00" if phase == 'POSITIVE' else "#FF4B4B"
    
    # Đánh giá rủi ro
    rr_ratio = (last['T1'] - last['close']) / (last['close'] - last['SL']) if (last['close'] - last['SL']) != 0 else 0
    rr_st = "HẤP DẪN" if rr_ratio >= 1.5 else "KÉM"

    html = f"""
<div class='ai-panel'>
<div class='ai-title'>🤖 AI TECHNICAL ADVISOR - {symbol}</div>
<div class='ai-text'>
<p><b>1. CẤU TRÚC XU HƯỚNG:</b><br>
• Giai đoạn: <span style='color:{phase_color}'><b>{phase_text}</b></span><br>
• Sức mạnh xu hướng (ADX): <b>{adx:.1f} ({adx_st})</b><br>
• Vị thế Ichimoku: <span style='color:{cloud_color}'><b>{cloud_st}</b></span></p>

<p><b>2. ĐỘNG LƯỢNG KỸ THUẬT:</b><br>
• RSI (14): <b>{rsi:.1f} ({rsi_st})</b><br>
• MACD: <b>{'Hội tụ/Cắt lên' if last['MACD']>last['MACD_Signal'] else 'Phân kỳ/Cắt xuống'}</b><br>
• Khối lượng: <b>{(last['volume']/last['AvgVol']):.1f}x</b> trung bình 50 phiên</p>

<div class='ai-expert-box'>
<b>🎯 MỤC TIÊU & QUẢN TRỊ RỦI RO:</b><br>
• <b>Vùng Mua Kiến nghị:</b> {last['close'] * 0.99:,.1f} - {last['close'] * 1.01:,.1f}<br>
• <span style='color:#FF4B4B;'><b>Dừng lỗ (SL): {last['SL']:,.1f}</b></span> (Phòng vệ dưới hỗ trợ)<br>
• <span style='color:#00FF00;'><b>Mục tiêu 1 (T1): {last['T1']:,.1f}</b></span> (+{(last['T1']/last['close']-1)*100:.1f}%)<br>
• <span style='color:#00E5FF;'><b>Mục tiêu 2 (T2): {last['T2']:,.1f}</b></span> (+{(last['T2']/last['close']-1)*100:.1f}%)<br>
• Tỷ lệ Risk/Reward: <b>1:{rr_ratio:.1f} ({rr_st})</b>
</div>

<p><b>💡 NHẬN ĐỊNH CHUYÊN SÂU:</b><br>
{f"Thị trường đang trong pha tăng giá mạnh với ADX > 25. Ưu tiên giải ngân tại các nhịp rung lắc về vùng MA50 ({last['MA50']:,.1f})." if phase == 'POSITIVE' and adx > 25 
else f"Thị trường đang suy yếu, giá nằm dưới MA50. Khuyến nghị đứng ngoài hoặc hạ tỷ trọng về mức an toàn." if phase == 'NEGATIVE' 
else "Trạng thái đi ngang tích lũy. Cần quan sát thêm tín hiệu bùng nổ khối lượng để xác nhận xu hướng mới."}</p>
</div>
</div>
"""
    return html

# ---------------------------------------------------------
# 6. GIAO DIỆN CHÍNH
# ---------------------------------------------------------
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False

if st.session_state.logged_in and not db.check_token_valid(st.session_state.username, st.session_state.token):
    st.session_state.logged_in = False
    st.rerun()

if not st.session_state.logged_in:
    c1, c2, c3 = st.columns([1, 1, 1])
    with c2:
        st.markdown("<br><h1 style='text-align: center; color: #d4af37;'>TAMDUY CAPITAL</h1>", unsafe_allow_html=True)
        with st.form("login_form"):
            u = st.text_input("Username"); p = st.text_input("Password", type="password")
            if st.form_submit_button("LOGIN TERMINAL", use_container_width=True):
                res = db.login_user(u, p)
                if res["status"] == "success":
                    st.session_state.update(logged_in=True, username=u, name=res["name"], role=res["role"], 
                                            token=res["token"], days_left=res.get("days_left", 0), expiry_date=res.get("expiry_date", "N/A"))
                    st.toast(f"Chào {res['name']}!", icon="🚀"); time.sleep(1); st.rerun()
                else: st.error(res.get("msg", "Đăng nhập thất bại"))
else:
    # Header & Nav
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
            ret_bt, win_bt, trades_bt, logs_bt = run_backtest_fast(df)
            last = df.iloc[-1]
            
            # --- HUD ---
            k1, k2, k3, k4, k5 = st.columns(5)
            k1.markdown(f"<div class='hud-box'><div class='hud-val'>{last['close']:,.2f}</div><div class='hud-lbl'>GIÁ HIỆN TẠI</div></div>", unsafe_allow_html=True)
            s_col = "#00FF00" if "MUA" in last['SIGNAL'] else "#FF4B4B" if "BÁN" in last['SIGNAL'] else "#888"
            k2.markdown(f"<div class='hud-box'><div class='hud-val' style='color:{s_col}'>{last['SIGNAL'] if last['SIGNAL'] else 'HOLD'}</div><div class='hud-lbl'>TÍN HIỆU</div></div>", unsafe_allow_html=True)
            k3.markdown(f"<div class='hud-box'><div class='hud-val' style='color:#FF4B4B'>{last['SL']:,.1f}</div><div class='hud-lbl'>STOP LOSS</div></div>", unsafe_allow_html=True)
            k4.markdown(f"<div class='hud-box'><div class='hud-val' style='color:#00FF00'>{last['T1']:,.1f}</div><div class='hud-lbl'>TARGET 1</div></div>", unsafe_allow_html=True)
            k5.markdown(f"<div class='hud-box'><div class='hud-val' style='color:#00E5FF'>{last['T2']:,.1f}</div><div class='hud-lbl'>TARGET 2</div></div>", unsafe_allow_html=True)

            st.write("")
            col_chart, col_ai = st.columns([3, 1])
            
            # --- CHART ---
            with col_chart:
                fig = make_subplots(rows=4, cols=1, shared_xaxes=True, row_heights=[0.5, 0.15, 0.15, 0.2], vertical_spacing=0.01)
                
                # Ichimoku Cloud
                fig.add_trace(go.Scatter(x=df.index, y=df['SpanA'], line=dict(width=0), showlegend=False), row=1, col=1)
                fig.add_trace(go.Scatter(x=df.index, y=df['SpanB'], fill='tonexty', fillcolor='rgba(0, 255, 0, 0.05)', line=dict(width=0), showlegend=False), row=1, col=1)
                
                # Candlestick
                fig.add_trace(go.Candlestick(x=df.index, open=df['open'], high=df['high'], low=df['low'], close=df['close'], name='Price'), row=1, col=1)
                
                # Vẽ SL và Target tại điểm cuối
                fig.add_hline(y=last['SL'], line_dash="dash", line_color="#FF4B4B", annotation_text="SL", row=1, col=1)
                fig.add_hline(y=last['T1'], line_dash="dash", line_color="#00FF00", annotation_text="T1", row=1, col=1)
                fig.add_hline(y=last['T2'], line_dash="dash", line_color="#00E5FF", annotation_text="T2", row=1, col=1)

                fig.add_trace(go.Scatter(x=df.index, y=df['MA50'], line=dict(color='#2962FF', width=1.5), name='MA50'), row=1, col=1)
                fig.add_trace(go.Scatter(x=df.index, y=df['Kijun'], line=dict(color='#FF6D00', width=1), name='Kijun-sen'), row=1, col=1)
                
                # Signals markers
                buys = df[df['SIGNAL'] == 'MUA']
                if not buys.empty: fig.add_trace(go.Scatter(x=buys.index, y=buys['low']*0.98, mode='markers', marker=dict(symbol='triangle-up', size=12, color='#00FF00'), name='Buy'), row=1, col=1)
                sells = df[df['SIGNAL'] == 'BÁN']
                if not sells.empty: fig.add_trace(go.Scatter(x=sells.index, y=sells['high']*1.02, mode='markers', marker=dict(symbol='triangle-down', size=12, color='#FF4B4B'), name='Sell'), row=1, col=1)

                # Volume, MACD, RSI
                colors_vol = ['#00C853' if c >= o else '#FF3D00' for c, o in zip(df['close'], df['open'])]
                fig.add_trace(go.Bar(x=df.index, y=df['volume'], marker_color=colors_vol, name='Volume'), row=2, col=1)
                
                fig.add_trace(go.Bar(x=df.index, y=df['MACD_Hist'], marker_color=['#00C853' if h > 0 else '#FF3D00' for h in df['MACD_Hist']]), row=3, col=1)
                fig.add_trace(go.Scatter(x=df.index, y=df['MACD'], line=dict(color='#2962FF')), row=3, col=1)
                
                fig.add_trace(go.Scatter(x=df.index, y=df['RSI'], line=dict(color='#AA00FF')), row=4, col=1)
                fig.add_hline(y=70, line_dash="dot", line_color="red", row=4, col=1)
                fig.add_hline(y=30, line_dash="dot", line_color="green", row=4, col=1)

                fig.update_layout(height=850, paper_bgcolor='#000', plot_bgcolor='#080808', margin=dict(l=0, r=50, t=30, b=0), showlegend=False, xaxis_rangeslider_visible=False)
                st.plotly_chart(fig, use_container_width=True)
                
                # --- TABS ---
                t1, t2 = st.tabs(["📋 NHẬT KÝ LỆNH", "⚙️ QUẢN TRỊ"])
                with t1:
                    if not logs_bt.empty: st.dataframe(logs_bt.style.format({"Giá Mua": "{:,.2f}", "Giá Bán": "{:,.2f}", "Lãi/Lỗ %": "{:+.2f}"}), use_container_width=True)
                    else: st.info("Hệ thống chưa ghi nhận lệnh trong giai đoạn này.")
                with t2:
                    st.write(f"Cấp độ tài khoản: **{st.session_state.role}**")
                    if st.session_state.role == "admin":
                        st.dataframe(db.get_all_users(), use_container_width=True)
                    else: st.warning("Bạn không có quyền truy cập bảng quản trị.")

            with col_ai:
                st.markdown(render_ai_analysis(df, symbol), unsafe_allow_html=True)
        else: st.error(d["error"])
