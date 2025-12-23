import streamlit as st
import pandas as pd
import numpy as np
import time
# Thư viện biểu đồ mới
from streamlit_lightweight_charts_ntpl import renderLightweightCharts
# Import file logic vừa tạo
import strategy_engine as se
# Import file DB cũ của bạn (vẫn giữ nguyên file db_manager.py trong repo nhé)
import db_manager as db

# --- SETUP ---
try:
    from xnoapi import client
    # Đoạn này giữ code cũ của bạn nếu cần
    HAS_XNO = False # Tạm tắt để test giao diện trước, bật lại sau
except: HAS_XNO = False

st.set_page_config(layout="wide", page_title="DATCAP PRO", initial_sidebar_state="collapsed")
st.markdown("""<style>.block-container {padding-top: 0rem; padding-bottom: 0rem;} header {visibility: hidden;}</style>""", unsafe_allow_html=True)

# --- DATA FAKE ĐỂ TEST (VÌ CHƯA CÓ API TRÊN CLOUD) ---
@st.cache_data(ttl=60) 
def get_data_test(symbol):
    # Lấy dữ liệu free từ Entrade public API để test logic
    import requests
    end = int(time.time())
    start = end - 30*24*60*60*24 # 2 năm
    url = f"https://services.entrade.com.vn/chart-api/v2/ohlcs/stock?symbol={symbol}&from={start}&to={end}&resolution=1D"
    
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        res = requests.get(url, headers=headers, timeout=10).json()
        if 't' not in res or not res['t']: return pd.DataFrame()
        
        df = pd.DataFrame({
            'time': pd.to_datetime(res['t'], unit='s'), 
            'open': res['o'], 'high': res['h'], 'low': res['l'], 'close': res['c'], 'volume': res['v']
        })
        # Quan trọng: Remove timezone để khớp với Lightweight Chart
        df['time'] = df['time'].dt.tz_localize(None)
        return df
    except Exception as e:
        st.error(f"Lỗi lấy data: {e}")
        return pd.DataFrame()

# --- MAIN APP ---
c1, c2 = st.columns([1, 6])
with c1: 
    st.markdown("### 🦅 DATCAP")
with c2:
    symbol = st.text_input("SYMBOL", value="SSI", label_visibility="collapsed").upper()

if symbol:
    # 1. Lấy dữ liệu
    raw_df = get_data_test(symbol)
    
    if not raw_df.empty:
        # 2. Chạy logic Strategy Engine
        df = se.calculate_datcap_logic(raw_df)
        last = df.iloc[-1]

        # 3. Header thông tin
        st.markdown(f"""
        <div style="display: flex; gap: 20px; align-items: center; background: #131722; padding: 10px; border-radius: 4px; margin-bottom: 10px; border: 1px solid #333;">
            <div style="font-size: 24px; font-weight: bold; color: #d1d4dc">{symbol}</div>
            <div style="font-size: 24px; color: {'#00E676' if last['close']>=last['open'] else '#FF5252'}">{last['close']:,.0f}</div>
            <div style="color: #999">Vol: {last['volume']/1000:,.0f}K</div>
            <div style="margin-left: auto; padding: 5px 15px; background: {last['BarColor']}; color: #fff; font-weight: bold; border-radius: 3px; border: 1px solid #555;">
                {last['Status']}
            </div>
        </div>
        """, unsafe_allow_html=True)

        # 4. Chuẩn bị dữ liệu vẽ Chart
        chart_data = []
        vol_data = []
        marker_data = []
        ma50_data = []
        ma200_data = []

        for i, row in df.iterrows():
            ts = int(row['time'].timestamp()) # Time Unix
            
            # Nến
            chart_data.append({
                "time": ts, 
                "open": row['open'], "high": row['high'], "low": row['low'], "close": row['close'],
                "color": row['BarColor'] # <-- MÀU SẮC THEO TRẠNG THÁI
            })
            
            # Volume
            vol_color = 'rgba(0, 230, 118, 0.5)' if row['close'] >= row['open'] else 'rgba(255, 82, 82, 0.5)'
            vol_data.append({"time": ts, "value": row['volume'], "color": vol_color})
            
            # MA Lines
            if not pd.isna(row['MA50']): ma50_data.append({"time": ts, "value": row['MA50']})
            if not pd.isna(row['MA200']): ma200_data.append({"time": ts, "value": row['MA200']})

            # Mũi tên tín hiệu
            if row['Signal_Point'] == 1:
                marker_data.append({
                    "time": ts, "position": "belowBar", "color": "#2196F3", "shape": "arrowUp", "text": "MUA"
                })
            elif row['Signal_Point'] == -1:
                marker_data.append({
                    "time": ts, "position": "aboveBar", "color": "#FF5252", "shape": "arrowDown", "text": "BÁN"
                })

        # 5. Cấu hình Chart
        chartOptions = {
            "layout": {"backgroundColor": "#131722", "textColor": "#d1d4dc"},
            "grid": {"vertLines": {"color": "#242832"}, "horzLines": {"color": "#242832"}},
            "crosshair": {"mode": 1},
            "rightPriceScale": {"borderColor": "#242832"},
            "timeScale": {"borderColor": "#242832", "timeVisible": True},
            "height": 550
        }

        seriesCandle = {
            "type": "Candlestick",
            "data": chart_data,
            "options": {
                "upColor": "#089981", "downColor": "#f23645",
                "borderVisible": False, "wickUpColor": "#089981", "wickDownColor": "#f23645"
            },
            "markers": marker_data
        }

        seriesMA50 = {
            "type": "Line", "data": ma50_data,
            "options": {"color": "#2962FF", "lineWidth": 2, "title": "MA50"}
        }

        seriesMA200 = {
            "type": "Line", "data": ma200_data,
            "options": {"color": "#FF6D00", "lineWidth": 2, "title": "MA200", "lineStyle": 2}
        }

        seriesVol = {
            "type": "Histogram", "data": vol_data,
            "options": {"priceFormat": {"type": "volume"}, "priceScaleId": ""}
        }

        # Render Chart
        renderLightweightCharts([
            {"series": [seriesCandle, seriesMA50, seriesMA200, seriesVol], "chartOptions": chartOptions}
        ], key="main_chart")

        # 6. Panel nhận định
        trend_txt = "UPTREND" if last['close'] > last['MA200'] else "DOWNTREND"
        st.info(f"Hệ thống DATCAP: Xu hướng **{trend_txt}**. Trạng thái **{last['Status']}**. RSI: {last['RSI']:.1f}")

    else:
        st.warning(f"Không tìm thấy dữ liệu cho mã {symbol}")
