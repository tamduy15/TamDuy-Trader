import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime
import time
from streamlit_lightweight_charts_ntpl import renderLightweightCharts
import strategy_engine as se  # File logic vừa tạo
import db_manager as db       # File login cũ của bạn

# --- 1. SETUP & DATA (GIỮ NGUYÊN LOGIC CŨ CỦA BẠN) ---
try:
    from xnoapi import client
    from xnoapi.vn.data import get_market_index_snapshot
    from xnoapi.vn.data.stocks import Trading
    # Token XNO cũ của bạn
    client(apikey="oWwDudF9ak5bhdIGVVNWetbQF26daMXluwItepTIBI1YQj9aWrlMlZui5lOWZ2JalVwVIhBd9LLLjmL1mXR-9ZHJZWgItFOQvihcrJLdtXAcVQzLJCiN0NrOtaYCNZf4")
    HAS_XNO = True
except: HAS_XNO = False

st.set_page_config(layout="wide", page_title="DATCAP PRO", initial_sidebar_state="collapsed")
st.markdown("""<style>.block-container {padding-top: 0rem; padding-bottom: 0rem;} header {visibility: hidden;}</style>""", unsafe_allow_html=True)

@st.cache_data(ttl=5) 
def get_data_realtime(symbol):
    """Hàm lấy dữ liệu (đã rút gọn từ code cũ của bạn)"""
    # ... (Giữ logic lấy API Entrade và vá nến Realtime của bạn ở đây)
    # ĐỂ TIẾT KIỆM CHỖ DEMO, TÔI GIẢ LẬP DỮ LIỆU NẾU KHÔNG GỌI ĐƯỢC API
    # KHI CHẠY THẬT, BẠN COPY LẠI HÀM GET_MARKET_DATA TỪ APP.PY CŨ VÀO ĐÂY
    # Tạm thời return DataFrame mẫu để test giao diện:
    import requests
    end = int(time.time()); start = end - 30*24*60*60*12 # 3 năm
    url = f"https://services.entrade.com.vn/chart-api/v2/ohlcs/stock?symbol={symbol}&from={start}&to={end}&resolution=1D"
    try:
        res = requests.get(url).json()
        df = pd.DataFrame({'time': pd.to_datetime(res['t'], unit='s'), 'open': res['o'], 'high': res['h'], 'low': res['l'], 'close': res['c'], 'volume': res['v']})
        df['time'] = df['time'].dt.tz_localize(None) # Remove timezone
        return df
    except: return pd.DataFrame()

# --- 2. MAIN APP ---
c1, c2 = st.columns([1, 6])
with c1: 
    st.markdown("### 🦅 DATCAP")
with c2:
    symbol = st.text_input("SYMBOL", value="SSI", label_visibility="collapsed").upper()

if symbol:
    # A. Lấy dữ liệu & Tính toán
    raw_df = get_data_realtime(symbol)
    if not raw_df.empty:
        df = se.calculate_datcap_logic(raw_df) # Chạy qua bộ não Strategy Engine
        last = df.iloc[-1]

        # B. PHÂN TÍCH NHANH (HEADER)
        st.markdown(f"""
        <div style="display: flex; gap: 20px; align-items: center; background: #131722; padding: 10px; border-radius: 4px; margin-bottom: 10px;">
            <div style="font-size: 24px; font-weight: bold; color: #d1d4dc">{symbol}</div>
            <div style="font-size: 24px; color: {'#00E676' if last['close']>=last['open'] else '#FF5252'}">{last['close']:,.0f}</div>
            <div style="color: #999">Vol: {last['volume']/1000:,.0f}K</div>
            <div style="margin-left: auto; padding: 5px 15px; background: {last['BarColor']}; color: #000; font-weight: bold; border-radius: 3px;">
                TRẠNG THÁI: {last['Status']}
            </div>
        </div>
        """, unsafe_allow_html=True)

        # C. CẤU HÌNH CHART LIGHTWEIGHT (AMIBROKER STYLE)
        # 1. Chuẩn bị dữ liệu JSON cho Chart
        chart_data = []
        vol_data = []
        marker_data = []
        ma50_data = []
        ma200_data = []

        for i, row in df.iterrows():
            ts = int(row['time'].timestamp()) # Time Unix
            
            # Nến (Màu sắc theo logic Strategy Engine)
            chart_data.append({
                "time": ts, 
                "open": row['open'], "high": row['high'], "low": row['low'], "close": row['close'],
                "color": row['BarColor'] # <-- ĂN TIỀN Ở CHỖ NÀY (Màu custom từng nến)
            })
            
            # Volume (Xanh/Đỏ theo nến)
            vol_color = 'rgba(0, 230, 118, 0.5)' if row['close'] >= row['open'] else 'rgba(255, 82, 82, 0.5)'
            vol_data.append({"time": ts, "value": row['volume'], "color": vol_color})
            
            # MA Lines
            if not pd.isna(row['MA50']): ma50_data.append({"time": ts, "value": row['MA50']})
            if not pd.isna(row['MA200']): ma200_data.append({"time": ts, "value": row['MA200']})

            # Mũi tên tín hiệu (Markers)
            if row['Signal_Point'] == 1: # MUA
                marker_data.append({
                    "time": ts, "position": "belowBar", "color": "#2196F3", "shape": "arrowUp", "text": "MUA"
                })
            elif row['Signal_Point'] == -1: # BÁN
                marker_data.append({
                    "time": ts, "position": "aboveBar", "color": "#FF5252", "shape": "arrowDown", "text": "BÁN"
                })

        # 2. Cấu hình Chart Options
        chartOptions = {
            "layout": {"backgroundColor": "#131722", "textColor": "#d1d4dc"},
            "grid": {"vertLines": {"color": "#333"}, "horzLines": {"color": "#333"}},
            "crosshair": {"mode": 1},
            "priceScale": {"borderColor": "#485c7b"},
            "timeScale": {"borderColor": "#485c7b", "timeVisible": True},
            "height": 600
        }

        # 3. Khai báo Series
        seriesCandle = {
            "type": "Candlestick",
            "data": chart_data,
            "options": {
                "upColor": "#089981", "downColor": "#f23645", # Màu mặc định (sẽ bị ghi đè bởi data color)
                "borderVisible": False, "wickUpColor": "#089981", "wickDownColor": "#f23645"
            },
            "markers": marker_data # Gắn mũi tên vào đây
        }

        seriesMA50 = {
            "type": "Line", "data": ma50_data,
            "options": {"color": "#2962FF", "lineWidth": 2, "title": "MA50"}
        }
        
        seriesMA200 = {
            "type": "Line", "data": ma200_data,
            "options": {"color": "#FF6D00", "lineWidth": 2, "title": "MA200", "lineStyle": 2} # Style 2 = Dashed
        }

        seriesVol = {
            "type": "Histogram", "data": vol_data,
            "options": {"priceFormat": {"type": "volume"}, "priceScaleId": ""} # Overlay volume xuống dưới
        }

        # 4. RENDER CHART
        st.subheader("CHART: CHIẾN LƯỢC HIỆU SUẤT CAO")
        renderLightweightCharts([
            {"series": [seriesCandle, seriesMA50, seriesMA200, seriesVol], "chartOptions": chartOptions}
        ], key="main_chart")

        # D. DATCAP ANALYSIS PANEL (BÊN DƯỚI CHART)
        # Tự động sinh nhận định
        trend_text = "TĂNG DÀI HẠN" if last['close'] > last['MA200'] else "GIẢM / SIDEWAY"
        action_text = "NẮM GIỮ (HOLD)" if last['Status'] == 'HOLD' else "CHỜ MUA" if last['Status'] == 'NEUTRAL' else "CÓ TÍN HIỆU MUA" if last['Status'] == 'BUY' else "BÁN / QUAN SÁT"
        
        col_panel, col_metrics = st.columns([2, 1])
        with col_panel:
            st.info(f"💡 **NHẬN ĐỊNH:** Cổ phiếu đang trong xu hướng **{trend_text}**. Trạng thái hiện tại là **{action_text}**. RSI={last['RSI']:.1f}.")
        with col_metrics:
            st.error(f"🛑 STOPLOSS GỢI Ý: {last['MA50']:,.0f}")
