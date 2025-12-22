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
from datetime import datetime

# ---------------------------------------------------------
# 1. KẾT NỐI API & CẤU HÌNH GIAO DIỆN
# ---------------------------------------------------------
try:
    from xnoapi import client
    from xnoapi.vn.data import get_stock_hist, get_market_index_snapshot
    from xnoapi.vn.data.stocks import Trading
    # [cite_start]Token của bạn [cite: 15]
    client(apikey="oWwDudF9ak5bhdIGVVNWetbQF26daMXluwItepTIBI1YQj9aWrlMlZui5lOWZ2JalVwVIhBd9LLLjmL1mXR-9ZHJZWgItFOQvihcrJLdtXAcVQzLJCiN0NrOtaYCNZf4")
    HAS_XNO = True
except ImportError:
    HAS_XNO = False

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
# 2. DATA ENGINE (FIX REAL-TIME: FORCE UPDATE STRATEGY)
# ---------------------------------------------------------
from xnoapi.vn.data import get_market_index_snapshot
from xnoapi.vn.data.stocks import Trading
import requests
import pytz # Cần đảm bảo đã cài thư viện này hoặc có sẵn

@st.cache_data(ttl=1) # Tắt cache hoặc để rất thấp (1s) để ép lấy dữ liệu mới liên tục
def get_market_data(symbol):
    data = {"df": None, "error": "", "market_index": {}, "realtime": {}}
    
    # 1. CẤU HÌNH GIỜ VIỆT NAM (Quan trọng)
    tz_vn = pytz.timezone('Asia/Ho_Chi_Minh')
    now_vn = datetime.now(tz_vn)
    
    current_price = 0
    current_vol = 0
    
    # 2. LẤY GIÁ REAL-TIME TỪ XNO
    if HAS_XNO:
        try:
            # [cite_start]A. VNINDEX [cite: 238]
            vnindex = get_market_index_snapshot("VNINDEX")
            if vnindex:
                 data["market_index"] = {
                     "name": "VNINDEX",
                     "price": vnindex.get('price', 0),
                     "change": vnindex.get('change', 0),
                     "percent": vnindex.get('percent', 0)
                 }

            # [cite_start]B. STOCK REAL-TIME [cite: 141]
            pb_data = Trading.price_board([symbol])
            if pb_data and len(pb_data) > 0:
                item = pb_data[0]
                # Ưu tiên lấy giá khớp lệnh (matchPrice/price)
                # API XNO có thể trả về các key khác nhau tùy thời điểm
                raw_price = item.get('matchPrice', item.get('price', item.get('lastPrice', 0)))
                raw_vol = item.get('totalVol', item.get('volume', 0))
                
                # Logic chuẩn hóa đơn vị (VND)
                # Nếu giá < 500 (tức là đơn vị nghìn), nhân 1000. VD: 21.85 -> 21850
                price_final = raw_price * 1000 if raw_price < 500 else raw_price
                
                # Cập nhật biến global để dùng ghép nến
                current_price = price_final
                current_vol = raw_vol
                
                data["realtime"] = {
                    "price": price_final,
                    "ceil": item.get('ceil', 0) * 1000 if item.get('ceil', 0) < 500 else item.get('ceil', 0),
                    "floor": item.get('floor', 0) * 1000 if item.get('floor', 0) < 500 else item.get('floor', 0),
                    "vol": raw_vol
                }
        except Exception as e:
            print(f"XNO Error: {e}") # Debug in ra console server

    # 3. LẤY LỊCH SỬ VÀ GHÉP NẾN
    try:
        # Lấy lịch sử Entrade (nến Ngày)
        end_ts = int(time.time())
        start_ts = int(end_ts - (3 * 365 * 24 * 60 * 60))
        url_hist = f"https://services.entrade.com.vn/chart-api/v2/ohlcs/stock?symbol={symbol}&from={start_ts}&to={end_ts}&resolution=1D"
        
        res = requests.get(url_hist, headers={'User-Agent': 'Mozilla/5.0'}, timeout=5)
        
        if res.status_code == 200:
            raw = res.json()
            if 't' in raw and len(raw['t']) > 0:
                # Xử lý DataFrame
                df = pd.DataFrame({
                    'time': pd.to_datetime(raw['t'], unit='s').tz_localize('UTC').tz_convert(tz_vn),
                    'open': raw['o'], 'high': raw['h'], 'low': raw['l'], 'close': raw['c'], 'volume': raw['v']
                })
                # Loại bỏ timezone info để tránh lỗi merge
                df['time'] = df['time'].dt.tz_localize(None)
                df.set_index('time', inplace=True)
                df.sort_index(inplace=True)
                
                for c in ['open', 'high', 'low', 'close', 'volume']: 
                    df[c] = pd.to_numeric(df[c], errors='coerce')

                # --- [CORE LOGIC] FORCE UPDATE ---
                if current_price > 0:
                    last_idx = df.index[-1]
                    last_date_in_hist = last_idx.date()
                    today_date = now_vn.date()
                    
                    # Logic kiểm tra chính xác
                    is_today_missing = last_date_in_hist < today_date
                    
                    if is_today_missing:
                        # TRƯỜNG HỢP: Lịch sử chưa có ngày hôm nay -> TẠO DÒNG MỚI
                        # Tạo Timestamp cho ngày hôm nay (lúc 00:00 hoặc giờ hiện tại đều được, miễn là đúng ngày)
                        new_idx = pd.Timestamp(now_vn.year, now_vn.month, now_vn.day)
                        
                        # Tạo nến mới từ giá realtime
                        new_candle = pd.Series({
                            'open': current_price,
                            'high': current_price,
                            'low': current_price,
                            'close': current_price,
                            'volume': current_vol
                        }, name=new_idx)
                        
                        # Dùng pd.concat thay vì append (cũ)
                        df = pd.concat([df, pd.DataFrame([new_candle])])
                        
                    elif last_date_in_hist == today_date:
                        # TRƯỜNG HỢP: Lịch sử đã có ngày hôm nay -> GHI ĐÈ GIÁ
                        df.at[last_idx, 'close'] = current_price
                        df.at[last_idx, 'volume'] = current_vol # Cập nhật volume
                        # Update High/Low
                        if current_price > df.at[last_idx, 'high']: df.at[last_idx, 'high'] = current_price
                        if current_price < df.at[last_idx, 'low']: df.at[last_idx, 'low'] = current_price

                data["df"] = df[df['volume'] > 0]
            else:
                data["error"] = f"Không có dữ liệu Entrade cho {symbol}"
        else:
             data["error"] = "Lỗi kết nối Entrade."

    except Exception as e:
        data["error"] = f"Lỗi xử lý dữ liệu: {str(e)}"
        
    return data
# ---------------------------------------------------------
# 3. CHIẾN LƯỢC PHÂN TÍCH (CHUẨN AMIBROKER DATCAP)
# ---------------------------------------------------------
def run_strategy_full(df):
    if len(df) < 200: return df
    df = df.copy()

    # --- 1. TÍNH TOÁN HEIKIN ASHI (Tạo nến mượt) ---
    # HA_Close = Trung bình 4 giá
    df['HA_Close'] = (df['open'] + df['high'] + df['low'] + df['close']) / 4
    
    # HA_Open = Trung bình của HA_Open và HA_Close phiên trước
    # (Phải dùng vòng lặp vì giá trị sau phụ thuộc giá trị trước)
    ha_open = [df['open'].iloc[0]]
    ha_close = df['HA_Close'].values
    for i in range(1, len(df)):
        ha_open.append((ha_open[i-1] + ha_close[i-1]) / 2)
    df['HA_Open'] = ha_open

    # HA_High/Low = Đỉnh/Đáy thực tế so với HA
    df['HA_High'] = df[['high', 'HA_Open', 'HA_Close']].max(axis=1)
    df['HA_Low'] = df[['low', 'HA_Open', 'HA_Close']].min(axis=1)

    # Xác định màu nến Heikin Ashi (Dùng để tô màu volume sau này)
    df['HA_Color'] = np.where(df['HA_Close'] > df['HA_Open'], 'green', 'red')
    # ----------------------------------------------------

    # --- 2. CÁC CHỈ BÁO KHÁC (GIỮ NGUYÊN) ---
    df['MA20'] = df.ta.sma(length=20)
    df['MA50'] = df.ta.sma(length=50)
    df['MA150'] = df.ta.sma(length=150)
    df['MA200'] = df.ta.sma(length=200)
    df['AvgVol'] = df.ta.sma(close='volume', length=50)
    df['RSI'] = df.ta.rsi(length=14)
    df['ADX'] = df.ta.adx(length=14)['ADX_14']
    
    # Ichimoku
    h9 = df['high'].rolling(9).max(); l9 = df['low'].rolling(9).min(); df['Tenkan'] = (h9 + l9) / 2
    h26 = df['high'].rolling(26).max(); l26 = df['low'].rolling(26).min(); df['Kijun'] = (h26 + l26) / 2
    df['SpanA'] = ((df['Tenkan'] + df['Kijun']) / 2).shift(26)
    h52 = df['high'].rolling(52).max(); l52 = df['low'].rolling(52).min(); df['SpanB'] = ((h52 + l52) / 2).shift(26)

    # Bollinger Bands (Vùng mây xám)
    std = df['close'].rolling(20).std()
    df['BB_Upper'] = df['MA20'] + 2 * std
    df['BB_Lower'] = df['MA20'] - 2 * std

    # Xu hướng & Signal
    df['Trend_OK'] = (df['close'] > df['MA50']) & (df['MA50'] > df['MA150']) & (df['MA150'] > df['MA200'])
    df['Trend_Phase'] = 'SIDEWAY'
    df.loc[df['Trend_OK'], 'Trend_Phase'] = 'POSITIVE'
    df.loc[df['close'] < df['MA200'], 'Trend_Phase'] = 'NEGATIVE'

    # Logic Mua/Bán (Dựa trên giá thực close, không dùng HA để tín hiệu chính xác)
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

    # Trailing Stop & Target
    df['SL'] = np.maximum(df['MA50'], df['close'] * 0.93) 
    risk = (df['close'] - df['SL']).abs()
    df['T1'] = df['close'] + (2.0 * risk)
    df['T2'] = df['close'] + (3.0 * risk)

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
    # KHAI BÁO SYMBOL TRƯỚC KHI DÙNG
    with c_input: symbol = st.text_input("MÃ CK", "", label_visibility="collapsed", placeholder="Nhập mã...").upper()
    with c_user:
        days = st.session_state.get('days_left', 0); expiry = st.session_state.get('expiry_date', 'N/A')
        color = "#ff4b4b" if days <= 7 else "#29b045"
        st.markdown(f"<div style='text-align: right; line-height: 1.2;'>User: <b>{st.session_state.name}</b> <br><span style='color: {color}; font-size: 0.85rem;'>Hạn: {expiry} (Còn {days} ngày)</span></div>", unsafe_allow_html=True)
    with c_out: 
        if st.button("EXIT"): st.session_state.logged_in = False; st.rerun()
    st.markdown("---")

    # LOGIC HIỂN THỊ DỮ LIỆU
    if symbol:
        d = get_market_data(symbol)
        
        # --- [NEW] HIỂN THỊ CHỈ SỐ VNINDEX ---
        if not d["error"]:
            idx = d.get("market_index", {})
            if idx:
                idx_color = "#00E676" if idx.get('change', 0) >= 0 else "#FF5252"
                st.markdown(f"""
                <div style="background: #1e222d; padding: 10px; border-radius: 5px; margin-bottom: 10px; border: 1px solid #333; display: flex; align-items: center; justify-content: space-between;">
                    <div>
                        <span style="color: #d4af37; font-weight: bold; margin-right: 10px;">🇻🇳 THỊ TRƯỜNG CHUNG:</span>
                        <span style="color: #fff; font-weight: bold;">{idx.get('name')}</span>
                    </div>
                    <span style="font-family: 'Roboto Mono'; font-size: 1.2rem; font-weight: bold; color: {idx_color}">
                        {idx.get('price'):,.2f} 
                        <span style="font-size: 0.9rem;">({idx.get('change'):+.2f} / {idx.get('percent'):+.2f}%)</span>
                    </span>
                </div>
                """, unsafe_allow_html=True)
            
            # --- LOGIC CŨ ---
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
                # 1. TẠO KHUNG BIỂU ĐỒ
                fig = make_subplots(rows=4, cols=1, shared_xaxes=True, 
                                    row_heights=[0.5, 0.15, 0.15, 0.2], 
                                    vertical_spacing=0.02)

                # 2. VẼ MÂY ICHIMOKU (Nền dưới cùng)
                fig.add_trace(go.Scatter(x=df.index, y=df['SpanA'], line=dict(width=0), showlegend=False, hoverinfo='skip'), row=1, col=1)
                fig.add_trace(go.Scatter(x=df.index, y=df['SpanB'], fill='tonexty', fillcolor='rgba(41, 98, 255, 0.3)', line=dict(width=0), showlegend=False, hoverinfo='skip'), row=1, col=1)

                # 3. VẼ NẾN (CANDLESTICK) - TỐI ƯU HIỂN THỊ
                # --- THAY THẾ ĐOẠN VẼ NẾN CŨ BẰNG ĐOẠN NÀY ---
                
                # Logic: Tô màu nến theo vị trí so với đường MA20 (Signal Line)
                # Tách dữ liệu thành 2 phe: Phe Bò (Trên MA20) và Phe Gấu (Dưới MA20)
                bull_df = df[df['close'] >= df['MA20']]
                bear_df = df[df['close'] < df['MA20']]

                # 1. VẼ NẾN XU HƯỚNG TĂNG (MÀU XANH CHỦ ĐẠO)
                fig.add_trace(go.Candlestick(
                    x=bull_df.index, 
                    open=bull_df['open'], high=bull_df['high'], low=bull_df['low'], close=bull_df['close'],
                    name='Trend Tăng',
                    # Nến tăng: Xanh đặc. Nến giảm: Viền Xanh, Ruột đen (để biết là điều chỉnh trong xu hướng tăng)
                    increasing_line_color='#00E676', increasing_fillcolor='#00E676',
                    decreasing_line_color='#00E676', decreasing_fillcolor='black', 
                    showlegend=False
                ), row=2, col=1)

                # 2. VẼ NẾN XU HƯỚNG GIẢM (MÀU ĐỎ CHỦ ĐẠO)
                fig.add_trace(go.Candlestick(
                    x=bear_df.index, 
                    open=bear_df['open'], high=bear_df['high'], low=bear_df['low'], close=bear_df['close'],
                    name='Trend Giảm',
                    # Nến giảm: Đỏ đặc. Nến hồi: Viền Đỏ, Ruột đen (để biết là hồi kỹ thuật trong xu hướng giảm)
                    increasing_line_color='#FF5252', increasing_fillcolor='black',
                    decreasing_line_color='#FF5252', decreasing_fillcolor='#FF5252',
                    showlegend=False
                ), row=2, col=1)
                
                # --- HẾT PHẦN THAY THẾ ---

                # 4. VẼ MŨI TÊN MUA/BÁN
                buys = df[df['SIGNAL'] == 'MUA']
                if not buys.empty:
                    fig.add_trace(go.Scatter(
                        x=buys.index, y=buys['low'] * 0.98,
                        mode='markers', marker=dict(symbol='triangle-up', size=15, color='#00E676', line=dict(width=1, color='black')),
                        name='ĐIỂM MUA', hovertemplate='<b>TÍN HIỆU MUA</b><br>Giá: %{y:,.2f}<extra></extra>'
                    ), row=1, col=1)

                sells = df[df['SIGNAL'] == 'BÁN']
                if not sells.empty:
                    fig.add_trace(go.Scatter(
                        x=sells.index, y=sells['high'] * 1.02,
                        mode='markers', marker=dict(symbol='triangle-down', size=15, color='#FF5252', line=dict(width=1, color='black')),
                        name='ĐIỂM BÁN', hovertemplate='<b>TÍN HIỆU BÁN</b><br>Giá: %{y:,.2f}<extra></extra>'
                    ), row=1, col=1)

                # 5. CÁC ĐƯỜNG CHỈ BÁO & HỖ TRỢ
                fig.add_hline(y=last['SL'], line_dash="dash", line_color="#f23645", annotation_text="SL", row=1, col=1)
                fig.add_hline(y=last['T1'], line_dash="dash", line_color="#00E676", annotation_text="T1", row=1, col=1)
                fig.add_hline(y=last['T2'], line_dash="dash", line_color="#00E5FF", annotation_text="T2", row=1, col=1)
                fig.add_trace(go.Scatter(x=df.index, y=df['MA50'], line=dict(color='rgba(41, 98, 255, 0.8)', width=1.8), name='MA50'), row=1, col=1)
                
                # 6. VOLUME, MACD, RSI
                fig.add_trace(go.Bar(x=df.index, y=df['volume'], marker_color=['#00C853' if c >= o else '#f23645' for c, o in zip(df['close'], df['open'])], opacity=0.8), row=2, col=1)
                fig.add_trace(go.Bar(x=df.index, y=df['MACD_Hist'], marker_color=['#00E676' if h > 0 else '#f23645' for h in df['MACD_Hist']], opacity=0.8), row=3, col=1)
                fig.add_trace(go.Scatter(x=df.index, y=df['RSI'], line=dict(color='#7e57c2', width=1.5)), row=4, col=1)
                
                # 7. CẤU HÌNH TRỤC VÀ GIAO DIỆN (ĐÃ TỐI ƯU CHO NẾN TO)
                # Ẩn ngày nghỉ (T7, CN) để nến sát nhau, trông to hơn
                fig.update_xaxes(
                    rangebreaks=[dict(bounds=["sat", "mon"])], 
                    showgrid=True, gridcolor='rgba(255, 255, 255, 0.05)'
                )

                for r in range(1, 5): 
                    fig.update_yaxes(side="right", showgrid=True, gridcolor='rgba(255, 255, 255, 0.05)', row=r, col=1)
                
                # Zoom mặc định vào 60 nến gần nhất để nến to rõ
                if len(df) > 60: fig.update_xaxes(range=[df.index[-60], df.index[-1] + timedelta(days=5)], row=1, col=1)
                
                fig.update_layout(
                    height=850, paper_bgcolor='#000', plot_bgcolor='#000', 
                    margin=dict(l=0, r=60, t=30, b=0), 
                    showlegend=False, xaxis_rangeslider_visible=False,
                    dragmode='pan', # Mặc định là chế độ kéo chart
                    hovermode='x unified' # Hiển thị thông tin dọc theo trục X
                )
                
                # 8. CẤU HÌNH TOOLBAR VẼ (TRADINGVIEW STYLE)
                config = {
                    'scrollZoom': True,
                    'displayModeBar': True,
                    'displaylogo': False,
                    'modeBarButtonsToAdd': [
                        'drawline',         # Vẽ đường thẳng
                        'drawopenpath',     # Vẽ tự do
                        'drawrect',         # Vẽ hình chữ nhật
                        'drawcircle',       # Vẽ hình tròn
                        'eraseshape'        # Cục tẩy
                    ],
                    'modeBarButtonsToRemove': ['lasso2d', 'select2d'] # Bỏ bớt nút thừa
                }
                
                st.plotly_chart(fig, use_container_width=True, config=config)
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

