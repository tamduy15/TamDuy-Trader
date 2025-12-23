import streamlit as st
import db_manager as db
import time
import pandas as pd
import numpy as np
import pandas_ta as ta
from datetime import datetime
import requests
import pytz

# Thư viện Chart AmiBroker (Mới thêm)
from streamlit_lightweight_charts_ntpl import renderLightweightCharts

# ---------------------------------------------------------
# 1. KẾT NỐI API & CẤU HÌNH (GIỮ NGUYÊN CODE CŨ CỦA BẠN)
# ---------------------------------------------------------
try:
    from xnoapi import client
    from xnoapi.vn.data import get_market_index_snapshot
    from xnoapi.vn.data.stocks import Trading
    # Token cũ của bạn
    client(apikey="oWwDudF9ak5bhdIGVVNWetbQF26daMXluwItepTIBI1YQj9aWrlMlZui5lOWZ2JalVwVIhBd9LLLjmL1mXR-9ZHJZWgItFOQvihcrJLdtXAcVQzLJCiN0NrOtaYCNZf4")
    HAS_XNO = True
except ImportError:
    HAS_XNO = False

st.set_page_config(page_title="TAMDUY TRADER PRO", layout="wide", page_icon="🦅", initial_sidebar_state="collapsed")
st.markdown("""<style>.block-container {padding-top: 0rem; padding-bottom: 0rem;} header {visibility: hidden;}</style>""", unsafe_allow_html=True)

# ---------------------------------------------------------
# 2. DATA ENGINE (GIỮ NGUYÊN CODE CŨ CỦA BẠN)
# ---------------------------------------------------------
@st.cache_data(ttl=1)
def get_market_data(symbol):
    data = {"df": None, "error": "", "realtime": {}}
    tz_vn = pytz.timezone('Asia/Ho_Chi_Minh')
    now_vn = datetime.now(tz_vn)
    current_price = 0; current_vol = 0
    
    # 2.1 Lấy Realtime XNO
    if HAS_XNO:
        try:
            pb_data = Trading.price_board([symbol])
            if pb_data and len(pb_data) > 0:
                item = pb_data[0]
                raw_price = item.get('matchPrice', item.get('price', item.get('lastPrice', 0)))
                raw_vol = item.get('totalVol', item.get('volume', 0))
                price_final = raw_price * 1000 if raw_price < 500 else raw_price
                current_price = price_final; current_vol = raw_vol
                data["realtime"] = {"price": price_final, "vol": raw_vol}
        except: pass

    # 2.2 Lấy Lịch sử Entrade & Vá nến
    try:
        end_ts = int(time.time())
        start_ts = int(end_ts - (3 * 365 * 24 * 60 * 60))
        url_hist = f"https://services.entrade.com.vn/chart-api/v2/ohlcs/stock?symbol={symbol}&from={start_ts}&to={end_ts}&resolution=1D"
        res = requests.get(url_hist, headers={'User-Agent': 'Mozilla/5.0'}, timeout=5)
        
        if res.status_code == 200:
            raw = res.json()
            if 't' in raw and len(raw['t']) > 0:
                df = pd.DataFrame({'time': pd.to_datetime(raw['t'], unit='s').tz_localize('UTC').tz_convert(tz_vn), 'open': raw['o'], 'high': raw['h'], 'low': raw['l'], 'close': raw['c'], 'volume': raw['v']})
                df['time'] = df['time'].dt.tz_localize(None) # Fix lỗi thư viện chart
                
                # Logic vá nến Realtime của bạn
                if current_price > 0:
                    last_idx = df.index[-1]
                    last_date = df['time'].iloc[-1].date()
                    today = now_vn.date()
                    if last_date < today: # Thêm nến mới
                        new_row = pd.DataFrame([{'time': pd.Timestamp(now_vn.replace(tzinfo=None)), 'open': current_price, 'high': current_price, 'low': current_price, 'close': current_price, 'volume': current_vol}])
                        df = pd.concat([df, new_row], ignore_index=True)
                    elif last_date == today: # Cập nhật nến cuối
                        idx = df.index[-1]
                        df.at[idx, 'close'] = current_price
                        df.at[idx, 'volume'] = current_vol
                        if current_price > df.at[idx, 'high']: df.at[idx, 'high'] = current_price
                        if current_price < df.at[idx, 'low']: df.at[idx, 'low'] = current_price
                
                data["df"] = df
            else: data["error"] = "No Data"
        else: data["error"] = "API Error"
    except Exception as e: data["error"] = str(e)
    return data

# ---------------------------------------------------------
# 3. XỬ LÝ LOGIC AMIBROKER (TÔ MÀU & TÍN HIỆU)
# ---------------------------------------------------------
def process_amibroker_logic(df):
    if df is None or df.empty: return df
    df = df.copy()
    
    # Chỉ báo cơ bản
    df['MA20'] = ta.sma(df['close'], length=20)
    df['MA50'] = ta.sma(df['close'], length=50)
    df['MA200'] = ta.sma(df['close'], length=200)
    
    # Logic Nền chặt & Trend (Mô phỏng lại logic của bạn)
    period_base = 25
    df['HH_25'] = df['high'].rolling(period_base).max().shift(1)
    df['LL_25'] = df['low'].rolling(period_base).min().shift(1)
    df['BaseTight'] = ((df['HH_25'] - df['LL_25']) / df['LL_25']) < 0.15
    
    # Xác định trạng thái để tô màu nến (State Machine)
    # Xanh: Đang giữ lệnh (Giá > MA20/MA50)
    # Đỏ: Đã bán hoặc Downtrend
    # Xám: Sideway
    
    colors = []
    signals = [] # 1: Mua, -1: Bán, 0: Không
    in_trade = False
    
    for i in range(len(df)):
        close = df['close'].iloc[i]
        ma50 = df['MA50'].iloc[i] if not pd.isna(df['MA50'].iloc[i]) else 0
        
        # Điều kiện MUA (Giản lược từ logic của bạn để chạy nhanh)
        # Breakout nền hoặc Cắt lên MA50
        is_buy_signal = (close > ma50) and (df['close'].iloc[i-1] <= df['MA50'].iloc[i-1])
        
        # Điều kiện BÁN: Gãy MA20 (hoặc MA50 tùy chỉnh)
        is_sell_signal = (close < ma50) and (df['close'].iloc[i-1] >= df['MA50'].iloc[i-1])
        
        # Xử lý trạng thái
        if is_buy_signal:
            in_trade = True
            colors.append('#00E676') # Xanh lá (Điểm mua)
            signals.append(1)
        elif is_sell_signal:
            in_trade = False
            colors.append('#FF5252') # Đỏ (Điểm bán)
            signals.append(-1)
        elif in_trade:
            colors.append('#089981') # Xanh đậm (Đang nắm giữ)
            signals.append(0)
        else:
            # Không giữ lệnh
            if close < ma50: colors.append('#ef5350') # Đỏ nhạt (Downtrend)
            else: colors.append('#787b86') # Xám (Sideway)
            signals.append(0)
            
    df['BarColor'] = colors
    df['Signal'] = signals
    return df

# ---------------------------------------------------------
# 4. GIAO DIỆN CHÍNH (LIGHTWEIGHT CHART THAY CHO PLOTLY)
# ---------------------------------------------------------
# --- HEADER ---
c1, c2 = st.columns([1, 6])
with c1: st.markdown("### 🦅 DATCAP")
with c2: symbol = st.text_input("MÃ CK", value="SSI", label_visibility="collapsed").upper()

if symbol:
    d = get_market_data(symbol) # Gọi hàm Data Cũ của bạn
    
    if d["df"] is not None and not d["df"].empty:
        df = process_amibroker_logic(d["df"])
        last = df.iloc[-1]
        
        # --- INFO BAR ---
        status_color = last['BarColor']
        st.markdown(f"""
        <div style="background: #131722; padding: 12px; border-radius: 4px; display: flex; align-items: center; border: 1px solid #333; margin-bottom: 10px;">
            <div style="font-size: 24px; font-weight: bold; color: #d1d4dc; margin-right: 20px;">{symbol}</div>
            <div style="font-size: 24px; font-weight: bold; color: {'#00E676' if last['close']>=last['open'] else '#FF5252'}">{last['close']:,.0f}</div>
            <div style="color: #888; margin-left: 20px;">Vol: {last['volume']/1000:,.0f}K</div>
            <div style="margin-left: auto; padding: 4px 12px; background: {status_color}; color: #fff; font-weight: bold; border-radius: 4px;">
                {'NẮM GIỮ' if last['Signal']==0 and status_color=='#089981' else 'MUA' if last['Signal']==1 else 'BÁN' if last['Signal']==-1 else 'QUAN SÁT'}
            </div>
        </div>
        """, unsafe_allow_html=True)

        # --- LIGHTWEIGHT CHART (THAY THẾ PLOTLY) ---
        chart_data = []
        vol_data = []
        ma50_data = []
        markers = []

        for i, row in df.iterrows():
            ts = int(row['time'].timestamp())
            # Nến có màu Custom theo Logic AmiBroker
            chart_data.append({"time": ts, "open": row['open'], "high": row['high'], "low": row['low'], "close": row['close'], "color": row['BarColor']})
            # Volume
            vol_data.append({"time": ts, "value": row['volume'], "color": 'rgba(0, 230, 118, 0.4)' if row['close'] >= row['open'] else 'rgba(255, 82, 82, 0.4)'})
            # MA50
            if not pd.isna(row['MA50']): ma50_data.append({"time": ts, "value": row['MA50']})
            # Mũi tên tín hiệu
            if row['Signal'] == 1: markers.append({"time": ts, "position": "belowBar", "color": "#2196F3", "shape": "arrowUp", "text": "MUA"})
            if row['Signal'] == -1: markers.append({"time": ts, "position": "aboveBar", "color": "#FF5252", "shape": "arrowDown", "text": "BÁN"})

        # Cấu hình hiển thị
        chart_options = {
            "layout": {"backgroundColor": "#131722", "textColor": "#d1d4dc"},
            "grid": {"vertLines": {"color": "#242832"}, "horzLines": {"color": "#242832"}},
            "height": 600,
            "rightPriceScale": {"borderColor": "#2B2B43"},
            "timeScale": {"borderColor": "#2B2B43", "timeVisible": True},
            "crosshair": {"mode": 1}
        }

        series_candle = {
            "type": "Candlestick", 
            "data": chart_data,
            "options": {"upColor": "#089981", "downColor": "#f23645", "borderVisible": False, "wickUpColor": "#089981", "wickDownColor": "#f23645"},
            "markers": markers
        }
        series_ma50 = {"type": "Line", "data": ma50_data, "options": {"color": "#2962FF", "lineWidth": 2, "title": "MA50"}}
        series_vol = {"type": "Histogram", "data": vol_data, "options": {"priceFormat": {"type": "volume"}, "priceScaleId": ""}}

        # RENDER CHART
        renderLightweightCharts([{"series": [series_candle, series_ma50, series_vol], "chartOptions": chart_options}], key="main_chart")
        
    elif d["error"]:
        st.error(f"Lỗi dữ liệu: {d['error']}")
