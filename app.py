import streamlit as st
import db_manager as db
import time
import pandas as pd
import numpy as np
import pandas_ta as ta
import requests
import pytz
from datetime import datetime

# THƯ VIỆN CHART AMIBROKER MỚI
from streamlit_lightweight_charts_ntpl import renderLightweightCharts

# ---------------------------------------------------------
# 1. CẤU HÌNH & XỬ LÝ API (GIỮ NGUYÊN CỦA BẠN)
# ---------------------------------------------------------
st.set_page_config(page_title="TAMDUY TRADING PRO", layout="wide", page_icon="🦅", initial_sidebar_state="collapsed")

# Xử lý thư viện xnoapi (Chỉ chạy khi có file local, lên Cloud tự tắt để không lỗi)
try:
    from xnoapi import client
    from xnoapi.vn.data.stocks import Trading
    # Token của bạn
    client(apikey="oWwDudF9ak5bhdIGVVNWetbQF26daMXluwItepTIBI1YQj9aWrlMlZui5lOWZ2JalVwVIhBd9LLLjmL1mXR-9ZHJZWgItFOQvihcrJLdtXAcVQzLJCiN0NrOtaYCNZf4")
    HAS_XNO = True
except ImportError:
    HAS_XNO = False

# ---------------------------------------------------------
# 2. LOGIC LẤY DỮ LIỆU (GIỮ NGUYÊN CODE CŨ CỦA BẠN)
# ---------------------------------------------------------
@st.cache_data(ttl=5) # Cache 5 giây
def get_market_data(symbol):
    data = {"df": None, "error": ""}
    tz_vn = pytz.timezone('Asia/Ho_Chi_Minh')
    
    current_price = 0
    current_vol = 0
    
    # A. Lấy giá Realtime (Nếu có xnoapi)
    if HAS_XNO:
        try:
            pb_data = Trading.price_board([symbol])
            if pb_data and len(pb_data) > 0:
                item = pb_data[0]
                raw_price = item.get('matchPrice', item.get('price', item.get('lastPrice', 0)))
                # Xử lý giá < 500 (đơn vị nghìn đồng)
                current_price = raw_price * 1000 if raw_price < 500 else raw_price
                current_vol = item.get('totalVol', item.get('volume', 0))
        except: pass

    # B. Lấy lịch sử nến từ Entrade (API Public)
    try:
        end_ts = int(time.time())
        start_ts = int(end_ts - (3 * 365 * 24 * 60 * 60)) # 3 năm
        url = f"https://services.entrade.com.vn/chart-api/v2/ohlcs/stock?symbol={symbol}&from={start_ts}&to={end_ts}&resolution=1D"
        
        res = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=5)
        if res.status_code == 200:
            raw = res.json()
            if 't' in raw and len(raw['t']) > 0:
                df = pd.DataFrame({
                    'time': pd.to_datetime(raw['t'], unit='s').tz_localize('UTC').tz_convert(tz_vn),
                    'open': raw['o'], 'high': raw['h'], 'low': raw['l'], 'close': raw['c'], 'volume': raw['v']
                })
                df['time'] = df['time'].dt.tz_localize(None) # Bắt buộc remove timezone cho Chart mới
                
                # C. Vá nến Realtime vào Lịch sử (Logic của bạn)
                if current_price > 0:
                    last_idx = df.index[-1]
                    last_date = df.iloc[-1]['time'].date()
                    today = datetime.now(tz_vn).date()
                    
                    if last_date < today: # Chưa có nến hôm nay -> Tạo mới
                        new_row = pd.DataFrame([{
                            'time': pd.Timestamp(datetime.now()), 
                            'open': current_price, 'high': current_price, 'low': current_price, 'close': current_price, 'volume': current_vol
                        }])
                        df = pd.concat([df, new_row], ignore_index=True)
                    elif last_date == today: # Đã có nến -> Update giá
                        idx = df.index[-1]
                        df.at[idx, 'close'] = current_price
                        df.at[idx, 'volume'] = current_vol
                        df.at[idx, 'high'] = max(df.at[idx, 'high'], current_price)
                        df.at[idx, 'low'] = min(df.at[idx, 'low'], current_price)
                
                data["df"] = df
            else: data["error"] = "Không có dữ liệu lịch sử"
        else: data["error"] = "Lỗi kết nối Entrade"
    except Exception as e: data["error"] = str(e)
    
    return data

# ---------------------------------------------------------
# 3. LOGIC AMIBROKER (TÍNH TOÁN MÀU NẾN & TÍN HIỆU)
# ---------------------------------------------------------
def calculate_amibroker_logic(df):
    if df is None or df.empty: return df
    df = df.copy()
    
    # 1. Chỉ báo kỹ thuật
    df['MA20'] = ta.sma(df['close'], length=20)
    df['MA50'] = ta.sma(df['close'], length=50)
    df['MA150'] = ta.sma(df['close'], length=150)
    df['MA200'] = ta.sma(df['close'], length=200)
    
    # 2. Logic Nền chặt (Base Tight) - Code cũ của bạn
    period_base = 25
    df['HH_25'] = df['high'].rolling(period_base).max().shift(1)
    df['LL_25'] = df['low'].rolling(period_base).min().shift(1)
    # Biên độ < 15% là nền chặt
    df['BaseTight'] = ((df['HH_25'] - df['LL_25']) / df['LL_25']) < 0.15
    
    # 3. LOGIC TÔ MÀU NẾN (State Machine)
    # Nguyên tắc: 
    # - MUA: Breakout nền hoặc Bật MA50
    # - GIỮ (Hold): Giá nằm trên MA50 (hoặc MA20 tùy chỉnh)
    # - BÁN: Gãy MA20/MA50
    
    colors = []
    signals = [] # 1: Mua, -1: Bán, 0: Hold/Wait
    
    # Giả lập trạng thái nắm giữ
    in_trade = False
    
    # Convert sang list để loop nhanh
    closes = df['close'].values
    ma50s = df['MA50'].fillna(0).values
    ma20s = df['MA20'].fillna(0).values
    
    for i in range(len(df)):
        if i < 50: # Bỏ qua 50 nến đầu chưa đủ data
            colors.append('#787b86'); signals.append(0); continue
            
        close = closes[i]
        ma50 = ma50s[i]
        prev_close = closes[i-1]
        prev_ma50 = ma50s[i-1]
        
        # LOGIC MUA (Đơn giản hóa để test): Cắt lên MA50
        is_buy = (close > ma50) and (prev_close <= prev_ma50)
        
        # LOGIC BÁN: Gãy MA50
        is_sell = (close < ma50) and (prev_close >= prev_ma50)
        
        # MÁY TRẠNG THÁI (State Machine)
        if is_buy:
            in_trade = True
            colors.append('#00E676') # XANH LÁ (Điểm Mua)
            signals.append(1)
        elif is_sell:
            in_trade = False
            colors.append('#FF5252') # ĐỎ TƯƠI (Điểm Bán)
            signals.append(-1)
        elif in_trade:
            colors.append('#089981') # XANH ĐẬM (Đang Hold)
            signals.append(0)
        else:
            # Không giữ hàng -> Màu xám hoặc đỏ nhạt
            if close < ma50: colors.append('#ef5350') # Đỏ nhạt (Downtrend)
            else: colors.append('#787b86') # Xám (Sideway)
            signals.append(0)
            
    df['BarColor'] = colors
    df['Signal'] = signals
    return df

# ---------------------------------------------------------
# 4. GIAO DIỆN CHÍNH (AMIBROKER STYLE)
# ---------------------------------------------------------
# Login check (Giữ nguyên logic của bạn)
if 'logged_in' not in st.session_state: st.session_state.logged_in = False

# HEADER & INPUT
c1, c2 = st.columns([1, 6])
with c1: st.markdown("### 🦅 TAMDUY")
with c2: symbol = st.text_input("MÃ CK", value="SSI", label_visibility="collapsed").upper()

if symbol:
    # 1. Lấy dữ liệu (Code cũ)
    d = get_market_data(symbol)
    
    if d["df"] is not None and not d["df"].empty:
        # 2. Chạy logic AmiBroker
        df = calculate_amibroker_logic(d["df"])
        last = df.iloc[-1]
        
        # 3. INFO PANEL (Thanh thông tin trên cùng)
        st.markdown(f"""
        <div style="background: #131722; padding: 10px; border-radius: 5px; display: flex; align-items: center; border: 1px solid #333; margin-bottom: 10px;">
            <div style="font-size: 24px; font-weight: bold; color: #d1d4dc; margin-right: 15px;">{symbol}</div>
            <div style="font-size: 24px; font-weight: bold; color: {'#00E676' if last['close']>=last['open'] else '#FF5252'}">{last['close']:,.0f}</div>
            <div style="color: #888; margin-left: 20px; font-size: 14px;">Vol: {last['volume']/1000:,.0f}K</div>
            <div style="margin-left: auto; padding: 5px 15px; background: {last['BarColor']}; color: #fff; font-weight: bold; border-radius: 3px;">
                {'MUA' if last['Signal']==1 else 'BÁN' if last['Signal']==-1 else 'HOLD' if last['BarColor']=='#089981' else 'WAIT'}
            </div>
        </div>
        """, unsafe_allow_html=True)
        
        # 4. VẼ BIỂU ĐỒ (Lightweight Charts)
        # Chuẩn bị data JSON
        chart_data = []
        vol_data = []
        ma50_data = []
        markers = []
        
        for i, row in df.iterrows():
            ts = int(row['time'].timestamp()) # Unix Timestamp
            
            # Chart Nến (Màu sắc theo cột BarColor đã tính)
            chart_data.append({
                "time": ts, 
                "open": row['open'], "high": row['high'], "low": row['low'], "close": row['close'],
                "color": row['BarColor'] # <-- ĂN TIỀN Ở CHỖ NÀY
            })
            
            # Volume
            vol_data.append({
                "time": ts, "value": row['volume'],
                "color": 'rgba(0, 230, 118, 0.4)' if row['close'] >= row['open'] else 'rgba(255, 82, 82, 0.4)'
            })
            
            # MA50
            if not pd.isna(row['MA50']): 
                ma50_data.append({"time": ts, "value": row['MA50']})
                
            # Markers (Mũi tên)
            if row['Signal'] == 1:
                markers.append({"time": ts, "position": "belowBar", "color": "#2196F3", "shape": "arrowUp", "text": "MUA"})
            elif row['Signal'] == -1:
                markers.append({"time": ts, "position": "aboveBar", "color": "#FF5252", "shape": "arrowDown", "text": "BÁN"})

        # Cấu hình Chart
        chart_options = {
            "layout": {"backgroundColor": "#131722", "textColor": "#d1d4dc"},
            "grid": {"vertLines": {"color": "#242832"}, "horzLines": {"color": "#242832"}},
            "height": 550,
            "rightPriceScale": {"borderColor": "#2B2B43"},
            "timeScale": {"borderColor": "#2B2B43", "timeVisible": True},
            "crosshair": {"mode": 1}
        }
        
        # Khai báo Series
        series_candle = {
            "type": "Candlestick", 
            "data": chart_data,
            "options": {"upColor": "#089981", "downColor": "#f23645", "borderVisible": False, "wickUpColor": "#089981", "wickDownColor": "#f23645"},
            "markers": markers
        }
        
        series_ma50 = {
            "type": "Line", "data": ma50_data, 
            "options": {"color": "#2962FF", "lineWidth": 2, "title": "MA50"}
        }
        
        series_vol = {
            "type": "Histogram", "data": vol_data, 
            "options": {"priceFormat": {"type": "volume"}, "priceScaleId": ""} # Volume nằm dưới đáy
        }
        
        # Render Chart
        st.subheader("BẢNG ĐIỀU KHIỂN CHIẾN LƯỢC")
        renderLightweightCharts([
            {"series": [series_candle, series_ma50, series_vol], "chartOptions": chart_options}
        ], key="main_chart")
        
    elif d["error"]:
        st.error(f"Lỗi tải dữ liệu: {d['error']}")
