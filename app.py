import streamlit as st
import db_manager as db
import time
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import requests
import indicators as ind # Import file indicators.py vừa tạo

# ---------------------------------------------------------
# 1. CẤU HÌNH TRANG
# ---------------------------------------------------------
st.set_page_config(page_title="TAMDUY TRADER PRO", layout="wide", page_icon="🦅", initial_sidebar_state="collapsed")
db.init_db()

# CSS Tùy chỉnh (Dark Mode & TradingView Style)
st.markdown("""
<style>
    .stApp {background-color: #000000; color: #e0e0e0;}
    header[data-testid="stHeader"] {visibility: hidden; height: 0px;}
    .hud-box {background-color: #0d1117; border: 1px solid #333; padding: 10px; border-radius: 4px; text-align: center; border-top: 2px solid #d4af37;}
    .hud-val {font-family: 'Roboto Mono', monospace; font-size: 20px; font-weight: bold; color: #fff;}
    .hud-lbl {font-size: 11px; color: #888; text-transform: uppercase;}
    .stTabs [aria-selected="true"] {background-color: #d4af37 !important; color: #000 !important; font-weight: bold;}
    
    /* Insight Box Style */
    .insight-container {
        background-color: #161b22; 
        border: 1px solid #30363d; 
        border-left: 5px solid #d4af37;
        padding: 15px; 
        border-radius: 5px;
        margin-bottom: 20px;
    }
    .insight-title {color: #58a6ff; font-weight: bold; font-size: 16px; margin-bottom: 8px; text-transform: uppercase;}
    .insight-text {font-size: 14px; line-height: 1.6;}
</style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------
# 2. DATA ENGINE
# ---------------------------------------------------------
@st.cache_data(ttl=5)
def get_stock_data(symbol):
    """Lấy dữ liệu giá và thông tin cơ bản"""
    data = {"df": None, "name": symbol, "error": ""}
    
    # 1. Lấy tên công ty (Dùng API VNDirect public)
    try:
        url_profile = f"https://finfo-api.vndirect.com.vn/v4/stocks?q=code:{symbol}"
        res_p = requests.get(url_profile, headers={'User-Agent': 'Mozilla/5.0'}, timeout=5)
        if res_p.status_code == 200 and len(res_p.json()['data']) > 0:
            data["name"] = res_p.json()['data'][0]['companyName']
    except: pass

    # 2. Lấy dữ liệu giá (Entrade/DNSE)
    try:
        end_ts = int(time.time())
        start_ts = int(end_ts - (3 * 365 * 24 * 60 * 60))
        url = f"https://services.entrade.com.vn/chart-api/v2/ohlcs/stock?symbol={symbol}&from={start_ts}&to={end_ts}&resolution=1D"
        res = requests.get(url, timeout=10)
        if res.status_code == 200:
            raw = res.json()
            if 't' in raw and len(raw['t']) > 0:
                df = pd.DataFrame({'time': pd.to_datetime(raw['t'], unit='s') + pd.Timedelta(hours=7), 
                                   'open': raw['o'], 'high': raw['h'], 'low': raw['l'], 'close': raw['c'], 'volume': raw['v']})
                df.set_index('time', inplace=True); df.sort_index(inplace=True)
                for c in ['open','high','low','close','volume']: df[c] = pd.to_numeric(df[c], errors='coerce')
                data["df"] = df[df['volume'] > 0]
            else: data["error"] = f"Mã {symbol} không có dữ liệu giao dịch."
        else: data["error"] = "Lỗi kết nối API giá."
    except Exception as e: data["error"] = str(e)
    
    return data

# ---------------------------------------------------------
# 3. NHẬN ĐỊNH THÔNG MINH (THEO BỘ QUY TẮC)
# ---------------------------------------------------------
def render_insight_panel(df, symbol, company_name):
    last = df.iloc[-1]
    
    # 1. Xác định màu nến (Xu hướng Flower)
    trend_color = last['trend_color'] # 1: Xanh, -1: Đỏ
    trend_status = "TÍCH CỰC (UPTREND)" if trend_color == 1 else "TIÊU CỰC (DOWNTREND)"
    trend_css = "color: #00E676;" if trend_color == 1 else "color: #FF5252;"
    
    # 2. Tín hiệu Mua/Bán
    signal = "NẮM GIỮ / QUAN SÁT"
    sig_color = "#E0E0E0"
    
    if last['Breakout']: 
        signal = "MUA GIA TĂNG (BREAKOUT)"
        sig_color = "#00E676" # Xanh lá
    elif last['Pocket_Pivot']:
        signal = "MUA SỚM (POCKET PIVOT)"
        sig_color = "#FFD600" # Vàng
    elif last['Sell_Signal']:
        signal = "BÁN / HẠ TỶ TRỌNG"
        sig_color = "#FF5252" # Đỏ

    # 3. Hành động giá
    price_change = last['close'] - df.iloc[-2]['close']
    pct_change = (price_change / df.iloc[-2]['close']) * 100
    p_color = "#00E676" if price_change >= 0 else "#FF5252"

    html = f"""
    <div class='insight-container'>
        <div class='insight-title'>🦅 NHẬN ĐỊNH CỔ PHIẾU: {symbol}</div>
        <div style='font-size: 18px; font-weight: bold; margin-bottom: 10px; color: #FFF;'>
            {company_name}
        </div>
        <div class='insight-text'>
            <p><b>1. TRẠNG THÁI XU HƯỚNG (FLOWER):</b><br>
            Hiện tại cổ phiếu đang trong trạng thái <span style='{trend_css} font-weight:bold;'>{trend_status}</span>. 
            {'Nến màu XANH thể hiện phe Mua đang kiểm soát.' if trend_color==1 else 'Nến màu ĐỎ thể hiện áp lực Bán vẫn còn mạnh.'}</p>
            
            <p><b>2. TÍN HIỆU HỆ THỐNG:</b><br>
            Khuyến nghị hiện tại: <span style='color:{sig_color}; font-weight:bold; font-size: 15px;'>{signal}</span>.<br>
            Giá đóng cửa: <span style='color:{p_color}'>{last['close']:,.0f} ({pct_change:+.2f}%)</span>.</p>
            
            <p><b>3. VÙNG HÀNH ĐỘNG:</b><br>
            - Hỗ trợ cứng (Stoploss): <b style='color:#FF5252'>{last['SL']:,.0f}</b><br>
            - Mục tiêu kỳ vọng (Target): <b style='color:#00E676'>{last['T1']:,.0f}</b></p>
            
            <div style='margin-top: 10px; font-style: italic; border-top: 1px dashed #555; padding-top: 5px;'>
                "Tuân thủ kỷ luật: Chỉ mua khi Nến Xanh + Mũi tên Báo Mua. Tuyệt đối không bắt đáy khi Nến Đỏ."
            </div>
        </div>
    </div>
    """
    return html

# ---------------------------------------------------------
# 4. GIAO DIỆN CHÍNH
# ---------------------------------------------------------
# --- LOGIN CHECK ---
if 'logged_in' not in st.session_state: st.session_state.logged_in = False
if st.session_state.logged_in and not db.check_token_valid(st.session_state.username, st.session_state.token):
    st.session_state.logged_in = False; st.rerun()

if not st.session_state.logged_in:
    # Màn hình đăng nhập
    c1, c2, c3 = st.columns([1, 1, 1])
    with c2:
        st.markdown("<br><h1 style='text-align: center; color: #d4af37;'>TAMDUY CAPITAL</h1>", unsafe_allow_html=True)
        with st.form("login"):
            u = st.text_input("User"); p = st.text_input("Pass", type="password")
            if st.form_submit_button("LOGIN"):
                res = db.login_user(u, p)
                if res["status"] == "success":
                    st.session_state.update(logged_in=True, username=u, name=res["name"], role=res["role"], token=res["token"])
                    st.rerun()
                else: st.error(res["msg"])
else:
    # --- DASHBOARD ---
    # Header & Input
    c1, c2, c3 = st.columns([1, 3, 1])
    with c1: st.markdown("### 🦅 PRO")
    with c2: 
        # Ô nhập mã + Tên công ty sẽ hiện bên dưới sau khi nhập
        symbol_input = st.text_input("MÃ CỔ PHIẾU", "", label_visibility="collapsed", placeholder="Nhập mã (VD: HPG)...").upper()
    with c3: 
        if st.button("LOGOUT"): st.session_state.logged_in = False; st.rerun()

    if symbol_input:
        data = get_stock_data(symbol_input)
        
        if not data["error"]:
            df = data["df"]
            # Tính toán Full Chỉ báo
            df = ind.calculate_full_indicators(df)
            last = df.iloc[-1]
            
            # --- TÊN CÔNG TY (HIỆN DƯỚI INPUT) ---
            st.markdown(f"<div style='text-align:center; color:#888; margin-top:-15px; margin-bottom:10px;'>{data['name']}</div>", unsafe_allow_html=True)

            # --- KHUNG NHẬN ĐỊNH (INSIGHT) ---
            st.markdown(render_insight_panel(df, symbol_input, data['name']), unsafe_allow_html=True)
            
            # --- 8 TABS PHÂN TÍCH ---
            # Danh sách 8 Tab như yêu cầu
            tab_names = [
                "TỔNG HỢP TÍN HIỆU", "TARGET/STOPLOSS", "VPA & TÍN HIỆU", 
                "TRENDLINE", "BOLLINGER BANDS", "ICHIMOKU", 
                "RSI & MACD", "TÀI CHÍNH & HỒ SƠ"
            ]
            tabs = st.tabs(tab_names)
            
            # === TAB 1: TỔNG HỢP (Nến Flower + Tín hiệu) ===
            with tabs[0]:
                fig = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[0.75, 0.25], vertical_spacing=0.02)
                
                # Logic màu nến Flower
                colors = ['#00E676' if x == 1 else '#FF1744' for x in df['trend_color']]
                
                # Vẽ nến (Dùng Loop để tô màu từng cây nến theo Trend Color thay vì giá đóng cửa)
                # Tuy nhiên để hiệu năng tốt, ta dùng trick: 
                # Vẽ 2 lớp nến: Lớp Xanh (cho trend tăng) và Lớp Đỏ (cho trend giảm)
                
                df_up = df[df['trend_color'] == 1]
                df_down = df[df['trend_color'] == -1]
                
                if not df_up.empty:
                    fig.add_trace(go.Candlestick(
                        x=df_up.index, open=df_up['open'], high=df_up['high'], low=df_up['low'], close=df_up['close'],
                        name='Trend Tăng', increasing_line_color='#00E676', decreasing_line_color='#006400'
                    ), row=1, col=1)
                    
                if not df_down.empty:
                    fig.add_trace(go.Candlestick(
                        x=df_down.index, open=df_down['open'], high=df_down['high'], low=df_down['low'], close=df_down['close'],
                        name='Trend Giảm', increasing_line_color='#B71C1C', decreasing_line_color='#FF1744'
                    ), row=1, col=1)
                
                # Mũi tên Mua (Breakout)
                buys = df[df['Breakout']]
                if not buys.empty:
                    fig.add_trace(go.Scatter(x=buys.index, y=buys['low']*0.98, mode='markers', marker=dict(symbol='triangle-up', size=15, color='cyan'), name='Breakout'), row=1, col=1)
                
                # Mũi tên Vàng (Pocket Pivot)
                pockets = df[df['Pocket_Pivot']]
                if not pockets.empty:
                    fig.add_trace(go.Scatter(x=pockets.index, y=pockets['low']*0.98, mode='markers', marker=dict(symbol='triangle-up', size=12, color='yellow'), name='Pocket Pivot'), row=1, col=1)

                # Volume
                fig.add_trace(go.Bar(x=df.index, y=df['volume'], marker_color=colors, name='Volume'), row=2, col=1)
                
                # Zoom 3 tháng
                if len(df) > 90:
                    fig.update_xaxes(range=[df.index[-90], df.index[-1]+timedelta(days=2)])
                    
                fig.update_layout(height=700, paper_bgcolor='#000', plot_bgcolor='#000', showlegend=False, xaxis_rangeslider_visible=False, margin=dict(l=0,r=50,t=10,b=0))
                st.plotly_chart(fig, use_container_width=True)

            # === CÁC TAB KHÁC (Placeholder - Bạn có thể yêu cầu code chi tiết từng tab sau) ===
            with tabs[1]: st.info("Biểu đồ Target/Stoploss đang cập nhật...")
            with tabs[2]: st.info("Biểu đồ VPA đang cập nhật...")
            with tabs[3]: st.info("Biểu đồ Trendline đang cập nhật...")
            with tabs[4]: st.info("Biểu đồ Bollinger Bands đang cập nhật...")
            with tabs[5]: st.info("Biểu đồ Ichimoku đang cập nhật...")
            with tabs[6]: st.info("Biểu đồ RSI/MACD đang cập nhật...")
            with tabs[7]: st.info(f"Hồ sơ tài chính của {data['name']} đang cập nhật...")

        else: st.error(data["error"])
