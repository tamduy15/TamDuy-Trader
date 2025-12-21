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
db.create_user("admin", "123456", "Administrator", "admin")

# --- CSS: PRO TRADING TERMINAL (CLEAN MODE) ---
st.markdown("""
<style>
    .stApp {background-color: #000000; color: #e0e0e0;}
    @import url('https://fonts.googleapis.com/css2?family=Roboto+Mono:wght@500&display=swap');
    
    h1, h2, h3 {color: #d4af37 !important; font-family: 'Segoe UI', sans-serif;}
    
    /* --- ẨN THANH HEADER CỦA STREAMLIT --- */
    header[data-testid="stHeader"] {
        visibility: hidden;
        height: 0px;
    }
    
    /* Ẩn luôn nút 3 gạch và nút Deploy nếu còn sót */
    .stDeployButton {display:none;}
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    
    /* Đẩy nội dung lên sát mép trên */
    .block-container {
        padding-top: 0rem !important; 
        padding-bottom: 0rem !important;
    }

    /* HUD Box */
    .hud-box {
        background-color: #0d1117; border: 1px solid #333;
        padding: 8px; border-radius: 4px; text-align: center;
        border-top: 2px solid #d4af37;
        margin-bottom: 5px;
    }
    .hud-val {font-family: 'Roboto Mono', monospace; font-size: 18px; font-weight: bold; color: #fff;}
    .hud-lbl {font-size: 10px; color: #888; text-transform: uppercase;}
    
    /* AI Panel */
    .ai-panel {
        background-color: #0d1117; border: 1px solid #30363d;
        padding: 15px; border-radius: 5px; height: 750px; overflow-y: auto;
    }
    .ai-title {color: #58a6ff; font-weight: bold; font-size: 16px; margin-bottom: 10px; border-bottom: 1px solid #333; padding-bottom: 5px;}
    .ai-text {font-size: 13px; line-height: 1.5; color: #c9d1d9;}
    
    /* Scrollbar */
    ::-webkit-scrollbar {width: 6px;}
    ::-webkit-scrollbar-thumb {background: #333; border-radius: 3px;}
    
    /* Tabs */
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
                    'open': raw['o'],
                    'high': raw['h'],
                    'low': raw['l'],
                    'close': raw['c'],
                    'volume': raw['v']
                })
                df.set_index('time', inplace=True)
                df.sort_index(inplace=True)
                
                cols = ['open', 'high', 'low', 'close', 'volume']
                for c in cols: df[c] = pd.to_numeric(df[c], errors='coerce')
                
                df = df[df['volume'] > 0]
                data["df"] = df
            else:
                data["error"] = f"Mã {symbol} không có dữ liệu."
        else:
            data["error"] = f"Lỗi DNSE: {res.status_code}"

    except Exception as e:
        data["error"] = str(e)
    
    return data

# ---------------------------------------------------------
# 3. STRATEGY ENGINE
# ---------------------------------------------------------
def run_strategy_full(df):
    if len(df) < 50: return df
    df = df.copy()
    
    # INDICATORS
    df['MA20'] = df.ta.sma(length=20)
    df['MA50'] = df.ta.sma(length=50)
    df['MA200'] = df.ta.sma(length=200)
    df['AvgVol'] = df.ta.sma(close='volume', length=50)
    df['ATR'] = df.ta.atr(length=14)
    
    try:
        adx = df.ta.adx(length=14)
        df['ADX'] = adx['ADX_14'] if adx is not None and 'ADX_14' in adx.columns else 0
    except: df['ADX'] = 0

    macd = df.ta.macd(fast=12, slow=26, signal=9)
    if macd is not None:
        df['MACD'] = macd['MACD_12_26_9']
        df['MACD_Signal'] = macd['MACDs_12_26_9']
        df['MACD_Hist'] = macd['MACDh_12_26_9']

    df['RSI'] = df.ta.rsi(length=14)
    
    # ICHIMOKU
    h9 = df['high'].rolling(9).max(); l9 = df['low'].rolling(9).min(); df['Tenkan'] = (h9 + l9) / 2
    h26 = df['high'].rolling(26).max(); l26 = df['low'].rolling(26).min(); df['Kijun'] = (h26 + l26) / 2
    df['SpanA'] = ((df['Tenkan'] + df['Kijun']) / 2).shift(26)
    h52 = df['high'].rolling(52).max(); l52 = df['low'].rolling(52).min(); df['SpanB'] = ((h52 + l52) / 2).shift(26)
    
    # TRAILING STOP
    high_lookup = df['high'].rolling(10).max()
    df['Trailing_Stop'] = high_lookup - (3 * df['ATR'])
    
    # TREND PHASE
    conditions = [(df['close'] > df['MA50']), (df['close'] < df['MA50'])]
    choices = ['POSITIVE', 'NEGATIVE']
    df['Trend_Phase'] = np.select(conditions, choices, default='SIDEWAY')

    # SIGNALS
    hhv = df['high'].rolling(20).max().shift(1)
    llv = df['low'].rolling(20).min()
    base_tight = np.where(llv>0, (hhv-llv)/llv < 0.15, False)
    
    breakout = (df['close'] > hhv) & (df['volume'] > 1.3 * df['AvgVol']) & (df['close'] > df['MA50']) & base_tight
    
    down_vol_arr = np.where(df['close'] < df['close'].shift(1), df['volume'], 0)
    max_down_10 = pd.Series(down_vol_arr, index=df.index).rolling(10).max().shift(1)
    pocket = (df['volume'] > max_down_10) & (df['close'] > df['MA20']) & (df['close'] > df['close'].shift(1))
    
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
# 4. BACKTEST FAST
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
# 5. AI INSIGHT
# ---------------------------------------------------------
def render_ai_analysis(df, symbol):
    last = df.iloc[-1]
    adx = last.get('ADX', 0); adx_st = "MẠNH" if adx > 25 else "YẾU" if adx < 20 else "HÌNH THÀNH"
    
    span_a = last.get('SpanA', 0); span_b = last.get('SpanB', 0)
    cloud_st = "TRÊN MÂY (TÍCH CỰC)" if last['close'] > max(span_a, span_b) else "DƯỚI MÂY (TIÊU CỰC)" if last['close'] < min(span_a, span_b) else "TRONG MÂY"
    cloud_color = "#00FF00" if "TÍCH CỰC" in cloud_st else "#FF4B4B" if "TIÊU CỰC" in cloud_st else "#FFD700"
    
    sig = last['SIGNAL'] if last['SIGNAL'] else "NẮM GIỮ"
    sig_color = "#00FF00" if "MUA" in sig else "#FF4B4B" if "BÁN" in sig else "#d4af37"
    
    phase = last.get('Trend_Phase', 'SIDEWAY')
    phase_text = "TÍCH CỰC (UPTREND)" if phase == 'POSITIVE' else "TIÊU CỰC (DOWNTREND)"
    phase_color = "#00FF00" if phase == 'POSITIVE' else "#FF4B4B"

    html = f"""
<div class='ai-panel'>
<div class='ai-title'>🤖 PHÂN TÍCH KỸ THUẬT</div>
<div class='ai-text'>
<p><b>1. TRẠNG THÁI THỊ TRƯỜNG:</b><br>
• <b>Giai đoạn:</b> <span style='color:{phase_color}'><b>{phase_text}</b></span>.<br>
• <b>ADX:</b> {adx:.1f} ({adx_st}).<br>
• <b>Ichimoku:</b> <span style='color:{cloud_color}'><b>{cloud_st}</b></span>.</p>
<p><b>2. ĐỘNG LƯỢNG:</b><br>
• <b>RSI (14):</b> {last['RSI']:.1f}.<br>
• <b>MACD:</b> {'Cắt lên' if last['MACD']>last['MACD_Signal'] else 'Cắt xuống'}.<br>
• <b>Vol:</b> {(last['volume']/last['AvgVol']):.1f}x TB20.</p>
<hr style='border-color: #333'>
<p style='font-size: 15px'><b>TÍN HIỆU: <span style='color:{sig_color}'>{sig}</span></b></p>
<p><i>Giá hiện tại: <b>{last['close']:,.2f}</b></i><br>
<i>Hỗ trợ cứng: {last['MA50']:,.2f}</i><br>
<i>Trailing Stop: {last['Trailing_Stop']:,.2f}</i></p>
</div>
</div>
"""
    return html

# ---------------------------------------------------------
# 6. GIAO DIỆN CHÍNH
# ---------------------------------------------------------
# 1. Quản lý trạng thái đăng nhập
if 'logged_in' not in st.session_state: 
    st.session_state.logged_in = False

# Kiểm tra tính hợp lệ của token (Nếu bị khóa trên Sheet, web tự văng ra)
if st.session_state.logged_in and not db.check_token_valid(st.session_state.username, st.session_state.token):
    st.session_state.logged_in = False
    st.rerun()

# 2. GIAO DIỆN CHƯA ĐĂNG NHẬP
if not st.session_state.logged_in:
    c1, c2, c3 = st.columns([1, 1, 1])
    with c2:
        st.markdown("<br><h1 style='text-align: center; color: #d4af37;'>TAMDUY CAPITAL</h1>", unsafe_allow_html=True)
        with st.form("login_form"):
            u = st.text_input("Username")
            p = st.text_input("Password", type="password")
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
            # Dòng dưới đây phải thẳng hàng với st.session_state.update
            st.toast(f"Chào {res['name']}! Hạn dùng còn {res['days_left']} ngày.", icon="🚀")
            time.sleep(1)
            st.rerun()

# 3. GIAO DIỆN ĐÃ ĐĂNG NHẬP THÀNH CÔNG
# Trong file app.py, phần GIAO DIỆN ĐÃ ĐĂNG NHẬP
else:
    # Lưu thông tin hạn dùng vào session nếu mới đăng nhập
    if "days_left" not in st.session_state and 'res' in locals():
        st.session_state.days_left = res.get("days_left")
        st.session_state.expiry_date = res.get("expiry_date")

    c_logo, c_input, c_user, c_out = st.columns([2, 2, 4, 1])
    
    with c_logo: 
        st.markdown("### 🦅 TAMDUY TRADER")
    
    with c_input: 
        symbol = st.text_input("MÃ CK", "", label_visibility="collapsed", placeholder="Nhập mã...").upper()
    
    with c_user:
        # HIỂN THỊ THÔNG BÁO HẠN SỬ DỤNG Ở ĐÂY
        days = st.session_state.get('days_left', 0)
        expiry = st.session_state.get('expiry_date', 'N/A')
        
        color = "#ff4b4b" if days <= 7 else "#29b045" # Đỏ nếu dưới 7 ngày, xanh nếu còn dài
        
        st.markdown(f"""
            <div style='text-align: right; line-height: 1.2;'>
                User: <b>{st.session_state.name}</b> <br>
                <span style='color: {color}; font-size: 0.85rem;'>
                    Hạn dùng: {expiry} (Còn {days} ngày)
                </span>
            </div>
        """, unsafe_allow_html=True)

    with c_out: 
        if st.button("EXIT"): 
            st.session_state.logged_in = False
            st.rerun()
    st.markdown("---")
    
    # Tiếp tục phần xử lý biểu đồ bên dưới...

    if symbol:
        d = get_market_data(symbol)
        if not d["error"]:
            df = d["df"]
            df = run_strategy_full(df)
            ret_bt, win_bt, trades_bt, logs_bt = run_backtest_fast(df)
            last = df.iloc[-1]
            
            # --- HUD ---
            k1, k2, k3, k4, k5 = st.columns(5)
            p_col = "#00FF00" if last['close']>=last['open'] else "#FF0000"
            k1.markdown(f"<div class='hud-box'><div class='hud-val' style='color:{p_col}'>{last['close']:,.2f}</div><div class='hud-lbl'>GIÁ HIỆN TẠI</div></div>", unsafe_allow_html=True)
            
            s_txt = last['SIGNAL'] if last['SIGNAL'] else "HOLD"
            s_col = "#00FF00" if "MUA" in s_txt else "#FF0000" if "BÁN" in s_txt else "#888"
            k2.markdown(f"<div class='hud-box'><div class='hud-val' style='color:{s_col}'>{s_txt}</div><div class='hud-lbl'>TÍN HIỆU</div></div>", unsafe_allow_html=True)
            
            k3.markdown(f"<div class='hud-box'><div class='hud-val'>{ret_bt:.1f}%</div><div class='hud-lbl'>LỢI NHUẬN (3Y)</div></div>", unsafe_allow_html=True)
            k4.markdown(f"<div class='hud-box'><div class='hud-val' style='color:#00E5FF'>{win_bt:.0f}%</div><div class='hud-lbl'>TỶ LỆ THẮNG</div></div>", unsafe_allow_html=True)
            
            rsi_col = "#FF4B4B" if last['RSI']>70 else "#00FF00" if last['RSI']<30 else "#fff"
            k5.markdown(f"<div class='hud-box'><div class='hud-val' style='color:{rsi_col}'>{last['RSI']:.1f}</div><div class='hud-lbl'>RSI (14)</div></div>", unsafe_allow_html=True)

            st.write("")
            col_chart, col_ai = st.columns([3, 1])
            
            # --- CHART ---
            with col_chart:
                fig = make_subplots(rows=4, cols=1, shared_xaxes=True, row_heights=[0.5, 0.15, 0.15, 0.2], vertical_spacing=0.01, subplot_titles=("Price & Ichimoku", "Volume", "MACD", "RSI"))
                
                # 1. Price
                fig.add_trace(go.Scatter(x=df.index, y=df['SpanA'], line=dict(width=0), showlegend=False), row=1, col=1)
                fig.add_trace(go.Scatter(x=df.index, y=df['SpanB'], fill='tonexty', fillcolor='rgba(0, 255, 0, 0.1)', line=dict(width=0), showlegend=False), row=1, col=1)
                
                df_pos = df[df['Trend_Phase'] == 'POSITIVE']
                df_neg = df[df['Trend_Phase'] == 'NEGATIVE']
                if not df_pos.empty: fig.add_trace(go.Candlestick(x=df_pos.index, open=df_pos['open'], high=df_pos['high'], low=df_pos['low'], close=df_pos['close'], name='Uptrend', increasing_line_color='#00E676', increasing_fillcolor='#00E676', decreasing_line_color='#006400', decreasing_fillcolor='#006400'), row=1, col=1)
                if not df_neg.empty: fig.add_trace(go.Candlestick(x=df_neg.index, open=df_neg['open'], high=df_neg['high'], low=df_neg['low'], close=df_neg['close'], name='Downtrend', increasing_line_color='#B71C1C', increasing_fillcolor='#B71C1C', decreasing_line_color='#FF1744', decreasing_fillcolor='#FF1744'), row=1, col=1)

                fig.add_trace(go.Scatter(x=df.index, y=df['Trailing_Stop'], line=dict(color='#FF0000', width=2, shape='hv'), name='Trailing Stop'), row=1, col=1)
                fig.add_trace(go.Scatter(x=df.index, y=df['MA50'], line=dict(color='#2962FF', width=1.5), name='MA50'), row=1, col=1)
                
                buys = df[df['SIGNAL'] == 'MUA']
                if not buys.empty: 
                    fig.add_trace(go.Scatter(x=buys.index, y=buys['low']*0.97, mode='markers', marker=dict(symbol='triangle-up', size=15, color='#00FF00'), name='Buy', text=[f"BUY {x:,.2f}" for x in buys['close']], hoverinfo='text'), row=1, col=1)
                sells = df[df['SIGNAL'] == 'BÁN']
                if not sells.empty: 
                    fig.add_trace(go.Scatter(x=sells.index, y=sells['high']*1.03, mode='markers', marker=dict(symbol='triangle-down', size=15, color='#FF0000'), name='Sell', text=[f"SELL {x:,.2f}" for x in sells['close']], hoverinfo='text'), row=1, col=1)

                # 2. Volume
                colors_vol = ['#00C853' if c >= o else '#FF3D00' for c, o in zip(df['close'], df['open'])]
                fig.add_trace(go.Bar(x=df.index, y=df['volume'], marker_color=colors_vol, name='Volume'), row=2, col=1)
                
                # 3. MACD
                colors_macd = ['#00C853' if h > 0 else '#FF3D00' for h in df['MACD_Hist']]
                fig.add_trace(go.Bar(x=df.index, y=df['MACD_Hist'], marker_color=colors_macd), row=3, col=1)
                fig.add_trace(go.Scatter(x=df.index, y=df['MACD'], line=dict(color='#2962FF', width=1)), row=3, col=1)
                fig.add_trace(go.Scatter(x=df.index, y=df['MACD_Signal'], line=dict(color='#FF6D00', width=1)), row=3, col=1)

                # 4. RSI
                fig.add_trace(go.Scatter(x=df.index, y=df['RSI'], line=dict(color='#AA00FF', width=1.5)), row=4, col=1)
                fig.add_hline(y=70, line_dash="dot", line_color="red", row=4, col=1)
                fig.add_hline(y=30, line_dash="dot", line_color="green", row=4, col=1)

                # Zoom 90 Days
                end_date = df.index[-1]
                start_date = end_date - pd.Timedelta(days=250)
                fig.update_xaxes(range=[start_date, end_date])
                
                fig.update_layout(height=800, paper_bgcolor='#000', plot_bgcolor='#111', margin=dict(l=0, r=50, t=30, b=0), showlegend=False, xaxis_rangeslider_visible=False, dragmode='pan')
                st.plotly_chart(fig, use_container_width=True, config={'scrollZoom': True})
                
                # --- TABS ---
                t1, t2 = st.tabs(["📋 NHẬT KÝ LỆNH", "⚙️ ADMIN"])
                with t1:
                    if not logs_bt.empty:
                        st.dataframe(logs_bt.style.format({"Giá Mua": "{:,.2f}", "Giá Bán": "{:,.2f}", "Lãi/Lỗ %": "{:+.2f}"}).applymap(lambda x: 'color: #00FF00' if x > 0 else 'color: #FF0000', subset=['Lãi/Lỗ %']), use_container_width=True)
                    else: st.info("Chưa có lệnh.")
                with t2:
                    if st.session_state.role == "admin":
                        with st.form("new"):
                            u=st.text_input("U"); p=st.text_input("P"); n=st.text_input("N")
                            if st.form_submit_button("ADD"): db.create_user(u,p,n)
                        users = db.get_all_users()
                        for i, r in users.iterrows():
                            c1,c2 = st.columns([3,1])
                            c1.write(f"{r['username']} ({r['status']})")
                            if r['role']!='admin':
                                if c2.button("LOCK/UNLOCK", key=r['username']): db.toggle_user_status(r['username'], 'locked' if r['status']=='active' else 'active'); st.rerun()
                    else: st.warning("Admin only")

            # RIGHT: AI TECHNICAL
            with col_ai:
                st.markdown(render_ai_analysis(df, symbol), unsafe_allow_html=True)
        else: st.error(d["error"])










