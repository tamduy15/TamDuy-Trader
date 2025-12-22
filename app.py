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
import pytz

# ---------------------------------------------------------
# 1. KẾT NỐI API & CẤU HÌNH GIAO DIỆN
# ---------------------------------------------------------
try:
    from xnoapi import client
    # Token của bạn
    client(apikey="oWwDudF9ak5bhdIGVVNWetbQF26daMXluwItepTIBI1YQj9aWrlMlZui5lOWZ2JalVwVIhBd9LLLjmL1mXR-9ZHJZWgItFOQvihcrJLdtXAcVQzLJCiN0NrOtaYCNZf4")
    HAS_XNO = True
except ImportError:
    HAS_XNO = False

st.set_page_config(page_title="TAMDUY TRADER PRO", layout="wide", page_icon="🦅", initial_sidebar_state="collapsed")
db.init_db()

# --- CSS: TRADING TERMINAL STYLE (GIỮ NGUYÊN) ---
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

    /* AI Advisor Layout */
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
</style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------
# 2. DATA ENGINE (GIỮ NGUYÊN LOGIC CŨ)
# ---------------------------------------------------------
from xnoapi.vn.data import get_market_index_snapshot
from xnoapi.vn.data.stocks import Trading

@st.cache_data(ttl=1)
def get_market_data(symbol):
    data = {"df": None, "error": "", "market_index": {}, "realtime": {}}
    tz_vn = pytz.timezone('Asia/Ho_Chi_Minh')
    now_vn = datetime.now(tz_vn)
    current_price = 0; current_vol = 0
    
    if HAS_XNO:
        try:
            vnindex = get_market_index_snapshot("VNINDEX")
            if vnindex:
                 data["market_index"] = { "name": "VNINDEX", "price": vnindex.get('price', 0), "change": vnindex.get('change', 0), "percent": vnindex.get('percent', 0) }
            pb_data = Trading.price_board([symbol])
            if pb_data and len(pb_data) > 0:
                item = pb_data[0]
                raw_price = item.get('matchPrice', item.get('price', item.get('lastPrice', 0)))
                raw_vol = item.get('totalVol', item.get('volume', 0))
                price_final = raw_price * 1000 if raw_price < 500 else raw_price
                current_price = price_final; current_vol = raw_vol
                data["realtime"] = { "price": price_final, "ceil": item.get('ceil', 0) * 1000 if item.get('ceil', 0) < 500 else item.get('ceil', 0), "floor": item.get('floor', 0) * 1000 if item.get('floor', 0) < 500 else item.get('floor', 0), "vol": raw_vol }
        except Exception as e: print(f"XNO Error: {e}")

    try:
        end_ts = int(time.time())
        start_ts = int(end_ts - (3 * 365 * 24 * 60 * 60))
        url_hist = f"https://services.entrade.com.vn/chart-api/v2/ohlcs/stock?symbol={symbol}&from={start_ts}&to={end_ts}&resolution=1D"
        res = requests.get(url_hist, headers={'User-Agent': 'Mozilla/5.0'}, timeout=5)
        
        if res.status_code == 200:
            raw = res.json()
            if 't' in raw and len(raw['t']) > 0:
                df = pd.DataFrame({'time': pd.to_datetime(raw['t'], unit='s').tz_localize('UTC').tz_convert(tz_vn), 'open': raw['o'], 'high': raw['h'], 'low': raw['l'], 'close': raw['c'], 'volume': raw['v']})
                df['time'] = df['time'].dt.tz_localize(None)
                df.set_index('time', inplace=True); df.sort_index(inplace=True)
                for c in ['open', 'high', 'low', 'close', 'volume']: df[c] = pd.to_numeric(df[c], errors='coerce')

                if current_price > 0:
                    last_idx = df.index[-1]; last_date_in_hist = last_idx.date(); today_date = now_vn.date()
                    if last_date_in_hist < today_date:
                        new_idx = pd.Timestamp(now_vn.year, now_vn.month, now_vn.day)
                        new_candle = pd.Series({'open': current_price, 'high': current_price, 'low': current_price, 'close': current_price, 'volume': current_vol}, name=new_idx)
                        df = pd.concat([df, pd.DataFrame([new_candle])])
                    elif last_date_in_hist == today_date:
                        df.at[last_idx, 'close'] = current_price; df.at[last_idx, 'volume'] = current_vol
                        if current_price > df.at[last_idx, 'high']: df.at[last_idx, 'high'] = current_price
                        if current_price < df.at[last_idx, 'low']: df.at[last_idx, 'low'] = current_price
                data["df"] = df[df['volume'] > 0]
            else: data["error"] = f"Không có dữ liệu Entrade cho {symbol}"
        else: data["error"] = "Lỗi kết nối Entrade."
    except Exception as e: data["error"] = f"Lỗi xử lý dữ liệu: {str(e)}"
    return data

# ---------------------------------------------------------
# 3. CHIẾN LƯỢC PHÂN TÍCH (CẬP NHẬT ĐỂ GIỐNG MẪU AMIBROKER)
# ---------------------------------------------------------
def run_strategy_full(df):
    if len(df) < 200: return df
    df = df.copy()
    
    # 1. Các chỉ báo cơ bản
    df['MA10'] = df.ta.sma(length=10)
    df['MA20'] = df.ta.sma(length=20)
    df['MA50'] = df.ta.sma(length=50)
    df['MA150'] = df.ta.sma(length=150)
    df['MA200'] = df.ta.sma(length=200)
    df['AvgVol'] = df.ta.sma(close='volume', length=50)
    df['RSI'] = df.ta.rsi(length=14)
    df['ADX'] = df.ta.adx(length=14)['ADX_14']
    
    # ICHIMOKU (Để dùng cho Panel trên cùng)
    h9 = df['high'].rolling(9).max(); l9 = df['low'].rolling(9).min(); df['Tenkan'] = (h9 + l9) / 2
    h26 = df['high'].rolling(26).max(); l26 = df['low'].rolling(26).min(); df['Kijun'] = (h26 + l26) / 2
    df['SpanA'] = ((df['Tenkan'] + df['Kijun']) / 2).shift(26)
    h52 = df['high'].rolling(52).max(); l52 = df['low'].rolling(52).min(); df['SpanB'] = ((h52 + l52) / 2).shift(26)

    # *** MỚI: Bollinger Bands & Grey Cloud (Để vẽ giống AmiBroker khung giữa) ***
    std = df['close'].rolling(20).std()
    df['BB_Upper'] = df['MA20'] + 2 * std
    df['BB_Lower'] = df['MA20'] - 2 * std

    # 2. Xu hướng
    df['Trend_OK'] = (df['close'] > df['MA50']) & (df['MA50'] > df['MA150']) & (df['MA150'] > df['MA200'])
    df['Trend_Phase'] = 'SIDEWAY'
    df.loc[df['Trend_OK'], 'Trend_Phase'] = 'POSITIVE'
    df.loc[df['close'] < df['MA200'], 'Trend_Phase'] = 'NEGATIVE'

    # 3. Logic Mua/Bán
    high_range = df['high'].rolling(30).max().shift(1)
    breakout_cond = (df['close'] > high_range) & (df['volume'] > 1.5 * df['AvgVol'])
    cross_ma50 = (df['close'] > df['MA50']) & (df['close'].shift(1) <= df['MA50'].shift(1))
    buy_final = df['Trend_OK'] & ( breakout_cond | cross_ma50 )

    sell_ma20 = (df['close'] < df['MA20']) & (df['close'].shift(1) >= df['MA20'].shift(1))
    
    signals = []; pos = 0
    for i in range(len(df)):
        if pos == 0:
            if buy_final.iloc[i]: signals.append('MUA'); pos = 1
            else: signals.append('')
        else:
            if sell_ma20.iloc[i]: signals.append('BÁN'); pos = 0
            else: signals.append('')
    df['SIGNAL'] = signals

    # 4. Trailing Stop (Để vẽ khung dưới cùng)
    # Logic: Dùng giá trị lớn nhất của (MA50 hoặc Close - 7%)
    df['SL'] = np.maximum(df['MA50'], df['close'] * 0.93) 
    
    # Target
    risk = (df['close'] - df['SL']).abs()
    df['T1'] = df['close'] + (2.0 * risk)
    df['T2'] = df['close'] + (3.0 * risk)

    return df

# ---------------------------------------------------------
# 4. BACKTEST (GIỮ NGUYÊN)
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
# 5. AI ADVISOR (GIỮ NGUYÊN)
# ---------------------------------------------------------
def render_ai_analysis(df, symbol):
    last = df.iloc[-1]
    adx = last.get('ADX', 0); adx_st = "MẠNH" if adx > 25 else "YẾU/SIDEWAY"
    rsi = last['RSI']; rsi_st = "QUÁ MUA" if rsi > 70 else "QUÁ BÁN" if rsi < 30 else "TRUNG TÍNH"
    expert_opinion = "Cổ phiếu đang giữ xu hướng tốt." if last['Trend_Phase'] == 'POSITIVE' else "Cổ phiếu yếu, cẩn trọng."
    html = f"""
    <div class='ai-panel'>
    <div class='ai-title'>🤖 AI ADVISOR - {symbol}</div>
    <div class='ai-text'>
    • <b>Giá:</b> {last['close']:,.2f}<br>
    • <b>Xu hướng:</b> {last['Trend_Phase']}<br>
    • <b>Stoploss:</b> <span style='color:red'>{last['SL']:,.2f}</span><br>
    • <b>Nhận định:</b> {expert_opinion}
    </div>
    </div>
    """
    return html

# ---------------------------------------------------------
# 6. GIAO DIỆN CHÍNH
# ---------------------------------------------------------
if 'logged_in' not in st.session_state: st.session_state.logged_in = False
if st.session_state.logged_in and not db.check_token_valid(st.session_state.username, st.session_state.token):
    st.session_state.logged_in = False; st.rerun()

if not st.session_state.logged_in:
    c1, c2, c3 = st.columns([1, 1, 1])
    with c2:
        st.markdown("<br><h1 style='text-align: center;'>TAMDUY CAPITAL</h1>", unsafe_allow_html=True)
        with st.form("login_form"):
            u = st.text_input("Username"); p = st.text_input("Password", type="password")
            if st.form_submit_button("LOGIN TERMINAL", use_container_width=True):
                res = db.login_user(u, p)
                if res["status"] == "success":
                    st.session_state.update(logged_in=True, username=u, name=res["name"], role=res["role"], token=res["token"], days_left=res["days_left"], expiry_date=res["expiry_date"])
                    st.toast(f"Chào {res['name']}!", icon="🚀"); time.sleep(1); st.rerun()
                else: st.error(res.get("msg", "Lỗi đăng nhập"))
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
            idx = d.get("market_index", {})
            if idx:
                idx_color = "#00E676" if idx.get('change', 0) >= 0 else "#FF5252"
                st.markdown(f"<div style='background:#1e222d;padding:10px;border-radius:5px;border:1px solid #333;display:flex;justify-content:space-between;'><div><span style='color:#d4af37;font-weight:bold;'>🇻🇳 VNINDEX:</span> <span style='color:#fff'>{idx.get('name')}</span></div><span style='font-family:Roboto Mono;font-weight:bold;color:{idx_color}'>{idx.get('price'):,.2f} ({idx.get('percent'):+.2f}%)</span></div>", unsafe_allow_html=True)
            
            df = run_strategy_full(d["df"])
            ret_bt, win_bt, trades_bt, logs_bt, duration_days = run_backtest_fast(df)
            last = df.iloc[-1]; prev = df.iloc[-2] if len(df) > 1 else last
            
            # HUD
            k1, k2, k3, k4, k5 = st.columns(5)
            change_pct = (last['close'] - prev['close']) / prev['close'] if prev['close'] != 0 else 0
            p_color = "#CE55FF" if change_pct >= 0.069 else "#66CCFF" if change_pct <= -0.069 else "#00E676" if change_pct > 0 else "#FF5252"
            k1.markdown(f"<div class='hud-box'><div class='hud-val' style='color:{p_color}'>{last['close']:,.2f} ({change_pct:+.2%})</div><div class='hud-lbl'>GIÁ HIỆN TẠI</div></div>", unsafe_allow_html=True)
            s_col = "#00E676" if "MUA" in last['SIGNAL'] else "#FF5252" if "BÁN" in last['SIGNAL'] else "#888"
            k2.markdown(f"<div class='hud-box'><div class='hud-val' style='color:{s_col}'>{last['SIGNAL'] if last['SIGNAL'] else 'HOLD'}</div><div class='hud-lbl'>TÍN HIỆU</div></div>", unsafe_allow_html=True)
            k3.markdown(f"<div class='hud-box'><div class='hud-val' style='color:#FF5252'>{last['SL']:,.1f}</div><div class='hud-lbl'>TRAILING STOP</div></div>", unsafe_allow_html=True)
            
            p1, p2, p3, p4 = st.columns(4)
            p1.markdown(f"<div class='perf-box'><div class='perf-val' style='color: #d4af37'>{trades_bt}</div><div class='perf-lbl'>SỐ LỆNH</div></div>", unsafe_allow_html=True)
            p2.markdown(f"<div class='perf-box'><div class='perf-val' style='color: #d4af37'>{win_bt:.1f}%</div><div class='perf-lbl'>WIN RATE</div></div>", unsafe_allow_html=True)
            
            col_chart, col_ai = st.columns([3, 1])
            with col_chart:
                # -------------------------------------------------------------
                # *** PLOTLY CHART MỚI: GIAO DIỆN AMIBROKER (3 ROWS) ***
                # -------------------------------------------------------------
                fig = make_subplots(
                    rows=3, cols=1, shared_xaxes=True, 
                    row_heights=[0.20, 0.60, 0.20], # Tỷ lệ chia 3 khung: Trên (nhỏ) - Giữa (to) - Dưới (nhỏ)
                    vertical_spacing=0.02,
                    subplot_titles=("TREND INDICATOR (Span A/B)", f"STRATEGY - {symbol} (Wyckoff Style)", "TRAILING STOP")
                )

                # --- KHUNG 1: TREND INDICATOR (Mây Ichimoku) ---
                fig.add_trace(go.Scatter(x=df.index, y=df['SpanA'], mode='lines', line=dict(width=0), showlegend=False, hoverinfo='skip'), row=1, col=1)
                fig.add_trace(go.Scatter(x=df.index, y=df['SpanB'], mode='lines', fill='tonexty', fillcolor='rgba(0, 230, 118, 0.1)', line=dict(width=0), showlegend=False, name="Cloud"), row=1, col=1)
                fig.add_trace(go.Scatter(x=df.index, y=df['MA200'], line=dict(color='orange', width=1), name='MA200'), row=1, col=1)

                # --- KHUNG 2: MAIN STRATEGY (Giá + Bands Xám + Mũi tên) ---
                # 1. Vẽ Vùng mây xám (Bollinger Bands Background)
                fig.add_trace(go.Scatter(x=df.index, y=df['BB_Upper'], mode='lines', line=dict(width=0), showlegend=False, hoverinfo='skip'), row=2, col=1)
                fig.add_trace(go.Scatter(x=df.index, y=df['BB_Lower'], mode='lines', fill='tonexty', fillcolor='rgba(200, 200, 200, 0.15)', line=dict(width=0), showlegend=False, name="Band"), row=2, col=1)
                
                # 2. Vẽ Nến (Candlestick)
                fig.add_trace(go.Candlestick(
                    x=df.index, open=df['open'], high=df['high'], low=df['low'], close=df['close'],
                    name='Price', increasing_line_color='#00E676', decreasing_line_color='#FF5252',
                    increasing_fillcolor='#00E676', decreasing_fillcolor='#FF5252' # Tô đặc nến
                ), row=2, col=1)

                # 3. Vẽ đường tín hiệu giữa (MA20)
                fig.add_trace(go.Scatter(x=df.index, y=df['MA20'], line=dict(color='blue', width=1), name='Signal'), row=2, col=1)

                # 4. Vẽ Mũi tên MUA/BÁN
                buys = df[df['SIGNAL'] == 'MUA']
                if not buys.empty:
                    fig.add_trace(go.Scatter(
                        x=buys.index, y=buys['low'] * 0.98,
                        mode='markers+text', text="▲", textposition="bottom center",
                        marker=dict(symbol='triangle-up', size=14, color='#00E676'),
                        name='BUY'
                    ), row=2, col=1)
                
                sells = df[df['SIGNAL'] == 'BÁN']
                if not sells.empty:
                    fig.add_trace(go.Scatter(
                        x=sells.index, y=sells['high'] * 1.02,
                        mode='markers', marker=dict(symbol='triangle-down', size=14, color='#FF5252'),
                        name='SELL'
                    ), row=2, col=1)

                # --- KHUNG 3: TRAILING STOP (Step Line màu đỏ) ---
                # Vẽ bóng nến mờ ở dưới để tham chiếu
                fig.add_trace(go.Candlestick(
                    x=df.index, open=df['open'], high=df['high'], low=df['low'], close=df['close'],
                    increasing_line_color='rgba(100,100,100,0.3)', decreasing_line_color='rgba(100,100,100,0.3)', showlegend=False
                ), row=3, col=1)
                
                # Vẽ đường Stoploss dạng bậc thang (hv shape)
                fig.add_trace(go.Scatter(
                    x=df.index, y=df['SL'], 
                    mode='lines', 
                    line=dict(color='red', width=2, shape='hv'), # shape='hv' tạo hiệu ứng bậc thang vuông góc
                    name='Trailing Stop'
                ), row=3, col=1)

                # CẤU HÌNH CHUNG
                fig.update_layout(
                    height=800, 
                    template="plotly_dark", # Giao diện tối
                    paper_bgcolor='#000000', plot_bgcolor='#000000',
                    margin=dict(l=0, r=60, t=30, b=0),
                    showlegend=False, xaxis_rangeslider_visible=False,
                    dragmode='pan', hovermode='x unified'
                )
                
                # Ẩn ngày nghỉ, hiện lưới mờ
                fig.update_xaxes(rangebreaks=[dict(bounds=["sat", "mon"])], showgrid=True, gridcolor='rgba(255,255,255,0.1)')
                fig.update_yaxes(showgrid=True, gridcolor='rgba(255,255,255,0.1)', side="right") # Trục giá bên phải giống AmiBroker
                
                # Zoom vào 60 phiên gần nhất
                if len(df) > 60: fig.update_xaxes(range=[df.index[-60], df.index[-1] + timedelta(days=5)], row=2, col=1)

                st.plotly_chart(fig, use_container_width=True, config={'scrollZoom': True, 'displayModeBar': False})
                
                # Tab Nhật ký lệnh
                t_log, t_adm = st.tabs(["📋 NHẬT KÝ BACKTEST", "⚙️ ADMIN"])
                with t_log:
                    if not logs_bt.empty:
                        def style_pnl(val): return f"background-color: {'#1b5e20' if val > 0 else '#b71c1c'}; color: white; font-weight: bold;"
                        st.dataframe(logs_bt.style.applymap(style_pnl, subset=['Lãi/Lỗ %']).format({"Giá Mua": "{:,.2f}", "Giá Bán": "{:,.2f}", "Lãi/Lỗ %": "{:+.2f}%"}), use_container_width=True)
                with t_adm:
                    if st.session_state.role == "admin": st.dataframe(db.get_all_users(), use_container_width=True)
            with col_ai:
                st.markdown(render_ai_analysis(df, symbol), unsafe_allow_html=True)
        else: st.error(d["error"])
