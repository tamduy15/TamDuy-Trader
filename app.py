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

# --- CSS: PRO TRADING TERMINAL (DARK MODE) ---
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

    .hud-box {
        background-color: #0d1117; border: 1px solid #333;
        padding: 8px; border-radius: 4px; text-align: center;
        border-top: 2px solid #d4af37; margin-bottom: 5px;
    }
    .hud-val {font-family: 'Roboto Mono', monospace; font-size: 18px; font-weight: bold; color: #fff;}
    .hud-lbl {font-size: 10px; color: #888; text-transform: uppercase;}
    
    .perf-box {
        background-color: #161b22; border: 1px solid #30363d;
        padding: 8px; border-radius: 4px; text-align: center;
        margin-bottom: 5px;
    }
    .perf-val {font-family: 'Roboto Mono', monospace; font-size: 16px; font-weight: bold;}
    .perf-lbl {font-size: 9px; color: #aaa; text-transform: uppercase;}

    .ai-panel {
        background-color: #0d1117; border: 1px solid #30363d;
        padding: 15px; border-radius: 5px; height: 850px; overflow-y: auto;
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
# 2. DATA ENGINE (SSI API - NEW SOURCE)
# ---------------------------------------------------------
@st.cache_data(ttl=30) # Refresh mỗi 30 giây
def get_market_data(symbol):
    data = {"df": None, "error": ""}
    headers = {'User-Agent': 'Mozilla/5.0'}
    try:
        # --- A. LẤY DỮ LIỆU LỊCH SỬ TỪ ENTRADE (Ổn định cho Chart) ---
        end_ts = int(time.time())
        start_ts = int(end_ts - (3 * 365 * 24 * 60 * 60))
        url_hist = f"https://services.entrade.com.vn/chart-api/v2/ohlcs/stock?symbol={symbol}&from={start_ts}&to={end_ts}&resolution=1D"
        
        res = requests.get(url_hist, headers=headers, timeout=10)
        if res.status_code != 200:
            data["error"] = f"Lỗi kết nối History: {res.status_code}"
            return data
            
        raw = res.json()
        if 't' not in raw or len(raw['t']) == 0:
            data["error"] = f"Mã {symbol} không có dữ liệu lịch sử."
            return data

        df = pd.DataFrame({
            'time': pd.to_datetime(raw['t'], unit='s') + pd.Timedelta(hours=7),
            'open': raw['o'], 'high': raw['h'], 'low': raw['l'], 'close': raw['c'], 'volume': raw['v']
        })
        df.set_index('time', inplace=True); df.sort_index(inplace=True)
        for c in ['open', 'high', 'low', 'close', 'volume']: 
            df[c] = pd.to_numeric(df[c], errors='coerce')
        
        # Lọc bỏ nến volume 0 (ngày nghỉ/lỗi)
        df = df[df['volume'] > 0]

        # --- B. LẤY GIÁ REAL-TIME TỪ TCBS (Để cập nhật nến cuối) ---
        # Đây là bước quan trọng để bảng điện HUD hiển thị giá khớp lệnh tức thì
        try:
            url_rt = f"https://apipubaws.tcbs.com.vn/stock-insight/v1/stock/overview?ticker={symbol}"
            res_rt = requests.get(url_rt, headers=headers, timeout=5)
            if res_rt.status_code == 200:
                rt_json = res_rt.json()
                # TCBS trả về giá (ví dụ 25500) trong field 'price' hoặc 'c' tùy endpoint
                # Với endpoint overview, giá thường nằm ở 'price'
                if 'price' in rt_json and rt_json['price'] > 0:
                    current_price = float(rt_json['price'])
                    
                    # Logic ghép nến Real-time
                    today = datetime.now().date()
                    last_idx = df.index[-1]
                    last_date = last_idx.date()
                    
                    if last_date == today:
                        # Nếu đã có nến hôm nay (từ Entrade), cập nhật giá Close mới nhất
                        df.at[last_idx, 'close'] = current_price
                        # Cập nhật High/Low nếu giá vượt biên độ
                        if current_price > df.at[last_idx, 'high']: df.at[last_idx, 'high'] = current_price
                        if current_price < df.at[last_idx, 'low']: df.at[last_idx, 'low'] = current_price
                    elif last_date < today:
                        # Nếu chưa có nến hôm nay, tạo nến mới tạm thời
                        new_row = pd.DataFrame({
                            'open': [current_price], 'high': [current_price], 
                            'low': [current_price], 'close': [current_price], 
                            'volume': [0] # Volume tạm thời
                        }, index=[pd.Timestamp(datetime.now())])
                        df = pd.concat([df, new_row])
        except Exception as e:
            # Nếu lỗi Realtime thì thôi, vẫn hiển thị chart lịch sử bình thường
            print(f"Lỗi Realtime TCBS: {e}")
            pass

        data["df"] = df

    except Exception as e: 
        data["error"] = str(e)
        
    return data
# ---------------------------------------------------------
# 3. STRATEGY ENGINE (AMIBROKER INTEGRATION)
# ---------------------------------------------------------
def run_strategy_amibroker(df):
    if len(df) < 200: return df
    df = df.copy()
    
    # --- INDICATORS TỪ AMIBROKER ---
    df['MA10'] = df.ta.sma(length=10)
    df['MA20'] = df.ta.sma(length=20)
    df['MA50'] = df.ta.sma(length=50)
    df['MA150'] = df.ta.sma(length=150)
    df['MA200'] = df.ta.sma(length=200)
    df['AvgVol'] = df.ta.sma(close='volume', length=50)
    df['ATR'] = df.ta.atr(length=14)
    
    # 1. TREND FILTER (File LOC CP MANH.afl)
    # Trend = C >= MA50 AND MA50 >= MA150 AND MA150 >= MA200
    df['Trend_Strong'] = (df['close'] > df['MA50']) & (df['MA50'] > df['MA150']) & (df['MA150'] > df['MA200'])
    
    # 2. WYCKOFF BASE (File LOC TIN HIEU MUA TU NEN.afl)
    # Nền giá chặt chẽ < 10%
    period = 25
    df['HHV_25'] = df['high'].rolling(period).max().shift(1)
    df['LLV_25'] = df['low'].rolling(period).min()
    base_range = (df['HHV_25'] - df['LLV_25']) / df['LLV_25']
    df['Base_Tight'] = np.where(df['LLV_25'] > 0, base_range < 0.10, False)
    
    # 3. BREAKOUT (Bùng nổ theo đà)
    # C > HHV_25 AND V > 1.5 * AvgVol
    df['Breakout'] = (df['close'] > df['HHV_25']) & (df['volume'] > 1.5 * df['AvgVol'])
    
    # 4. POCKET PIVOT (File CODE LOC TIN HIEU MUA BAN SOM.afl)
    # Vol > Max Down Volume 10 phiên trước
    down_vol_arr = np.where(df['close'] < df['close'].shift(1), df['volume'], 0)
    down_vol_series = pd.Series(down_vol_arr, index=df.index)
    max_down_vol = down_vol_series.rolling(10).max().shift(1)
    
    pocket_pivot = (df['volume'] > max_down_vol) & \
                   (df['close'] > df['close'].shift(1)) & \
                   (df['close'] > df['MA10']) & \
                   (df['close'] > df['MA50'])

    # --- ADVANCED INDICATORS CHO BIỂU ĐỒ ---
    # Ichimoku
    h9 = df['high'].rolling(9).max(); l9 = df['low'].rolling(9).min(); df['Tenkan'] = (h9 + l9) / 2
    h26 = df['high'].rolling(26).max(); l26 = df['low'].rolling(26).min(); df['Kijun'] = (h26 + l26) / 2
    df['SpanA'] = ((df['Tenkan'] + df['Kijun']) / 2).shift(26)
    h52 = df['high'].rolling(52).max(); l52 = df['low'].rolling(52).min(); df['SpanB'] = ((h52 + l52) / 2).shift(26)
    
    # MACD & RSI
    macd = df.ta.macd(fast=12, slow=26, signal=9)
    df['MACD'] = macd['MACD_12_26_9']; df['MACD_Signal'] = macd['MACDs_12_26_9']; df['MACD_Hist'] = macd['MACDh_12_26_9']
    df['RSI'] = df.ta.rsi(length=14)
    
    # ADX
    try: df['ADX'] = df.ta.adx(length=14)['ADX_14']
    except: df['ADX'] = 0

    # --- TẠO TÍN HIỆU (PRIORITY) ---
    # Ưu tiên 1: Breakout từ nền chặt + Trend mạnh (Mua chuẩn)
    # Ưu tiên 2: Pocket Pivot (Mua sớm)
    
    buy_breakout = df['Breakout'] & df['Base_Tight'] & df['Trend_Strong']
    buy_pocket = pocket_pivot
    
    # Bán: Gãy MA20 hoặc MA50
    sell_cond = (df['close'] < df['MA20']) & (df['close'].shift(1) >= df['MA20'].shift(1))
    
    df['SIGNAL'] = np.select(
        [buy_breakout, buy_pocket, sell_cond], 
        ['MUA (BREAKOUT)', 'MUA (POCKET)', 'BÁN'], 
        default=''
    )

    # --- TARGET / STOPLOSS (DYNAMIC) ---
    df['SL'] = np.where(df['close'] > df['MA50'], df['MA50'] - 0.5*df['ATR'], df['close'] - 2*df['ATR'])
    risk = (df['close'] - df['SL']).abs()
    risk = np.where(risk == 0, df['close']*0.01, risk)
    df['T1'] = df['close'] + 1.5*risk
    df['T2'] = df['close'] + 3.0*risk
    
    return df

# ---------------------------------------------------------
# 4. BACKTEST ENGINE
# ---------------------------------------------------------
def run_backtest(df):
    capital = 1_000_000_000; cash = capital; shares = 0; trades = []; wins = 0
    if df.empty: return 0, 0, 0, pd.DataFrame(), 0
    start_date = df.index[0]; end_date = df.index[-1]
    duration = (end_date - start_date).days
    
    for i in range(len(df)):
        price = df['close'].iloc[i]; sig = df['SIGNAL'].iloc[i]; date = df.index[i]
        
        if 'MUA' in sig and cash > 0:
            shares = cash // price; cash -= shares * price; entry = price; entry_date = date
        elif 'BÁN' in sig and shares > 0:
            pnl = (price - entry)/entry
            if pnl > 0: wins += 1
            trades.append({
                "Ngày Mua": entry_date.strftime('%d/%m/%Y'), "Giá Mua": entry, 
                "Ngày Bán": date.strftime('%d/%m/%Y'), "Giá Bán": price, 
                "Lãi/Lỗ %": pnl*100, "Loại": sig
            })
            cash += shares * price; shares = 0
            
    final_nav = cash + (shares * df['close'].iloc[-1])
    ret = (final_nav - capital)/capital * 100
    win_rate = (wins/len(trades) * 100) if len(trades) > 0 else 0
    return ret, win_rate, len(trades), pd.DataFrame(trades), duration

# ---------------------------------------------------------
# 5. AI ADVISOR
# ---------------------------------------------------------
def render_ai_analysis(df, symbol):
    last = df.iloc[-1]
    
    # Phân tích
    trend_st = "TĂNG MẠNH (SUPER STOCK)" if last['Trend_Strong'] else "YẾU/SIDEWAY"
    base_st = "CHẶT CHẼ (<10%)" if last['Base_Tight'] else "LỎNG LẺO"
    vol_st = f"{(last['volume']/last['AvgVol']):.1f}x TB50"
    
    # Lời khuyên
    if "MUA" in last['SIGNAL']:
        advice = "Tín hiệu MUA xuất hiện. Dòng tiền và xu hướng đồng thuận. Cân nhắc giải ngân."
        color = "#00E676"
    elif "BÁN" in last['SIGNAL']:
        advice = "Cảnh báo BÁN. Giá vi phạm xu hướng ngắn hạn. Nên hạ tỷ trọng."
        color = "#FF5252"
    else:
        advice = "Tiếp tục nắm giữ nếu đã có vị thế. Chờ tín hiệu bùng nổ tiếp theo."
        color = "#d4af37"

    html = f"""
<div class='ai-panel'>
    <div class='ai-title'>🤖 CHIẾN LƯỢC AMIBROKER - {symbol}</div>
    
    <div class='ai-section-title'>VÙNG MUA (BUY ZONE)</div>
    <div class='ai-text'>
        • <span class='ai-highlight'>Hỗ trợ MA50:</span> {last['MA50']:,.2f}<br>
        • <span class='ai-highlight'>Đỉnh hộp (Breakout):</span> {last['HHV_25']:,.2f}<br>
        • <span class='ai-highlight'>Nền giá:</span> {base_st}
    </div>

    <div class='ai-section-title'>VÙNG BÁN (SELL ZONE)</div>
    <div class='ai-text'>
        • <span class='ai-highlight'>Mục tiêu 1:</span> <span style='color:#00E676; font-weight:bold;'>{last['T1']:,.2f}</span><br>
        • <span class='ai-highlight'>Mục tiêu 2:</span> <span style='color:#00E5FF; font-weight:bold;'>{last['T2']:,.2f}</span>
    </div>

    <div class='ai-section-title'>QUẢN TRỊ RỦI RO</div>
    <div class='ai-expert-box'>
        <div class='ai-text' style='margin-left:0;'>
            • <span style='color:#FF5252; font-weight:bold;'>STOPLOSS: {last['SL']:,.2f}</span><br>
            • <span class='ai-highlight'>Xu hướng:</span> {trend_st}<br>
            • <span class='ai-highlight'>Vol sức mạnh:</span> {vol_st}
        </div>
    </div>

    <div class='ai-section-title'>TÍN HIỆU HỆ THỐNG</div>
    <div class='ai-text'>
        • <span class='ai-highlight'>Trạng thái:</span> <span style='color:{color}; font-weight:bold; font-size:16px;'>{last['SIGNAL'] if last['SIGNAL'] else 'NẮM GIỮ'}</span>
    </div>

    <div class='ai-section-title'>NHẬN ĐỊNH</div>
    <div class='ai-text' style='font-style: italic; color: #d4af37;'>
        "{advice}"
    </div>
</div>
"""
    return html

# ---------------------------------------------------------
# 6. UI LOGIC
# ---------------------------------------------------------
if 'logged_in' not in st.session_state: st.session_state.logged_in = False
if st.session_state.logged_in and not db.check_token_valid(st.session_state.username, st.session_state.token):
    st.session_state.logged_in = False; st.rerun()

if not st.session_state.logged_in:
    c1, c2, c3 = st.columns([1, 1, 1])
    with c2:
        st.markdown("<br><h1 style='text-align: center; color: #d4af37;'>TAMDUY CAPITAL</h1>", unsafe_allow_html=True)
        with st.form("login"):
            u = st.text_input("Username"); p = st.text_input("Password", type="password")
            if st.form_submit_button("LOGIN", use_container_width=True):
                res = db.login_user(u, p)
                if res["status"] == "success": st.session_state.update(logged_in=True, username=u, name=res["name"], role=res["role"], token=res["token"], days_left=res.get("days_left", 0), expiry_date=res.get("expiry_date", "N/A")); st.rerun()
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
            df = run_strategy_amibroker(d["df"])
            ret_bt, win_bt, trades_bt, logs_bt, duration_days = run_backtest(df)
            last = df.iloc[-1]; prev = df.iloc[-2] if len(df) > 1 else last
            
            # HUD
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
                
                # Ichimoku & MAs
                fig.add_trace(go.Scatter(x=df.index, y=df['SpanA'], line=dict(width=0), showlegend=False), row=1, col=1)
                fig.add_trace(go.Scatter(x=df.index, y=df['SpanB'], fill='tonexty', fillcolor='rgba(41, 98, 255, 0.08)', line=dict(width=0), showlegend=False), row=1, col=1)
                
                # Candles Color logic (Trend Strong)
                df_up = df[df['Trend_Strong']]; df_down = df[~df['Trend_Strong']]
                if not df_up.empty: fig.add_trace(go.Candlestick(x=df_up.index, open=df_up['open'], high=df_up['high'], low=df_up['low'], close=df_up['close'], name='Strong Trend', increasing_line_color='#00E676', increasing_fillcolor='#00E676', decreasing_line_color='#006400', decreasing_fillcolor='#006400'), row=1, col=1)
                if not df_down.empty: fig.add_trace(go.Candlestick(x=df_down.index, open=df_down['open'], high=df_down['high'], low=df_down['low'], close=df_down['close'], name='Weak Trend', increasing_line_color='#FF1744', increasing_fillcolor='#FF1744', decreasing_line_color='#D50000', decreasing_fillcolor='#D50000'), row=1, col=1)

                fig.add_hline(y=last['SL'], line_dash="dash", line_color="#FF5252", row=1, col=1)
                fig.add_hline(y=last['T1'], line_dash="dash", line_color="#00E676", row=1, col=1)
                fig.add_hline(y=last['T2'], line_dash="dash", line_color="#00E5FF", row=1, col=1)
                
                fig.add_trace(go.Scatter(x=df.index, y=df['MA50'], line=dict(color='#2962FF', width=1.5), name='MA50'), row=1, col=1)
                fig.add_trace(go.Scatter(x=df.index, y=df['MA200'], line=dict(color='#d4af37', width=1.5), name='MA200'), row=1, col=1)

                # Signals
                buys = df[df['SIGNAL'].str.contains('MUA')]
                if not buys.empty: fig.add_trace(go.Scatter(x=buys.index, y=buys['low']*0.985, mode='markers', marker=dict(symbol='triangle-up', size=16, color='#00E676', line=dict(width=1, color='white')), name='BUY'), row=1, col=1)
                sells = df[df['SIGNAL'] == 'BÁN']
                if not sells.empty: fig.add_trace(go.Scatter(x=sells.index, y=sells['high']*1.015, mode='markers', marker=dict(symbol='triangle-down', size=16, color='#FF5252', line=dict(width=1, color='white')), name='SELL'), row=1, col=1)

                # Indicators
                fig.add_trace(go.Bar(x=df.index, y=df['volume'], marker_color=['#00C853' if c >= o else '#FF5252' for c, o in zip(df['close'], df['open'])], opacity=0.8), row=2, col=1)
                fig.add_trace(go.Bar(x=df.index, y=df['MACD_Hist'], marker_color=['#00E676' if h > 0 else '#FF5252' for h in df['MACD_Hist']], opacity=0.8), row=3, col=1)
                fig.add_trace(go.Scatter(x=df.index, y=df['RSI'], line=dict(color='#AA00FF', width=1.5)), row=4, col=1)

                # Layout
                for r in range(1, 5):
                    fig.update_yaxes(side="right", showgrid=True, gridcolor='rgba(255, 255, 255, 0.05)', row=r, col=1)
                    fig.update_xaxes(showgrid=False, row=r, col=1)
                
                if len(df) > 90: fig.update_xaxes(range=[df.index[-90], df.index[-1]+timedelta(days=5)], row=1, col=1)
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



