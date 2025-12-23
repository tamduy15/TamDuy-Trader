import streamlit as st
import db_manager as db
import time
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timedelta
import requests
import indicators as ind # Import file indicators.py

# ---------------------------------------------------------
# 1. KẾT NỐI API & CẤU HÌNH
# ---------------------------------------------------------
st.set_page_config(page_title="TAMDUY TRADER PRO", layout="wide", page_icon="🦅", initial_sidebar_state="collapsed")
db.init_db()

# --- CSS: PRO TRADING TERMINAL ---
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

    /* HUD Metrics */
    .hud-box {
        background-color: #0d1117; border: 1px solid #333;
        padding: 8px; border-radius: 4px; text-align: center;
        border-top: 2px solid #d4af37; margin-bottom: 5px;
    }
    .hud-val {font-family: 'Roboto Mono', monospace; font-size: 18px; font-weight: bold; color: #fff;}
    .hud-lbl {font-size: 10px; color: #888; text-transform: uppercase;}
    
    /* Insight Panel Style */
    .insight-container {
        background-color: #161b22; 
        border: 1px solid #30363d; 
        border-left: 5px solid #d4af37;
        padding: 20px; 
        border-radius: 5px;
        margin-bottom: 10px;
        height: 100%;
    }
    .insight-title {color: #d4af37; font-weight: bold; font-size: 18px; margin-bottom: 10px; text-transform: uppercase; border-bottom: 1px solid #333; padding-bottom: 5px;}
    .insight-text {font-size: 13px; line-height: 1.6; color: #c9d1d9;}
    .insight-highlight {color: #fff; font-weight: bold;}
    
    /* Tabs */
    .stTabs [data-baseweb="tab-list"] {gap: 2px;}
    .stTabs [data-baseweb="tab"] {background-color: #111; border: 1px solid #333; color: #888; font-size: 11px; padding: 5px 10px;}
    .stTabs [aria-selected="true"] {background-color: #d4af37 !important; color: #000 !important; font-weight: bold;}
</style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------
# 2. DATA ENGINE
# ---------------------------------------------------------
@st.cache_data(ttl=5)
def get_stock_data(symbol):
    """Lấy dữ liệu giá và thông tin doanh nghiệp"""
    data = {"df": None, "name": symbol, "error": ""}
    
    # 1. Lấy Tên Công Ty (Dùng API Finfo VNDirect vì nó free và có tên)
    try:
        url_profile = f"https://finfo-api.vndirect.com.vn/v4/stocks?q=code:{symbol}"
        res_p = requests.get(url_profile, headers={'User-Agent': 'Mozilla/5.0'}, timeout=5)
        if res_p.status_code == 200:
            json_data = res_p.json()
            if len(json_data['data']) > 0:
                data["name"] = json_data['data'][0]['companyName']
    except: pass # Nếu lỗi thì dùng tạm mã CK

    # 2. Lấy Dữ Liệu Giá (Entrade/DNSE cho nhanh)
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
            else: data["error"] = f"Mã {symbol} không có dữ liệu."
        else: data["error"] = "Lỗi kết nối API giá."
    except Exception as e: data["error"] = str(e)
    
    return data

# ---------------------------------------------------------
# 3. RENDER INSIGHT PANEL (NHẬN ĐỊNH THÔNG MINH)
# ---------------------------------------------------------
def render_insight_panel(df, symbol, company_name):
    last = df.iloc[-1]
    
    # 1. Trạng thái Xu hướng (Dựa trên màu nến Flower)
    trend_color = last['trend_color'] # 1: Xanh, -1: Đỏ
    if trend_color == 1:
        trend_st = "TÍCH CỰC (MÀU XANH)"
        trend_desc = "Phe Mua đang kiểm soát. Ưu tiên Nắm giữ hoặc Canh mua."
        trend_css = "color: #00E676;"
    else:
        trend_st = "TIÊU CỰC (MÀU ĐỎ)"
        trend_desc = "Phe Bán đang chiếm ưu thế. Hạn chế mua mới, ưu tiên quản trị rủi ro."
        trend_css = "color: #FF5252;"

    # 2. Tín hiệu Mua/Bán
    signal = "QUAN SÁT"
    sig_color = "#888"
    
    if last['Breakout']: 
        signal = "MUA GIA TĂNG (BREAKOUT)"
        sig_desc = "Giá vượt đỉnh nền tảng với khối lượng lớn."
        sig_color = "#00E676"
    elif last['Pocket_Pivot']:
        signal = "MUA SỚM (POCKET PIVOT)"
        sig_desc = "Dòng tiền lớn tham gia ngay trong nền giá."
        sig_color = "#FFD600"
    elif last['Sell_Signal']:
        signal = "BÁN / HẠ TỶ TRỌNG"
        sig_desc = "Giá gãy đường xu hướng ngắn hạn MA20."
        sig_color = "#FF5252"
    else:
        sig_desc = "Chưa có tín hiệu đặc biệt trong phiên nay."

    # 3. Vùng Giá
    p_change = (last['close'] - df.iloc[-2]['close']) / df.iloc[-2]['close'] * 100
    p_color = "#00E676" if p_change >= 0 else "#FF5252"

    html = f"""
    <div class='insight-container'>
        <div class='insight-title'>🦅 NHẬN ĐỊNH CỔ PHIẾU: {symbol}</div>
        <div style='font-size: 16px; font-weight: bold; margin-bottom: 15px; color: #FFF; border-bottom: 1px solid #333; padding-bottom: 5px;'>
            {company_name}
        </div>
        
        <div class='insight-text'>
            <p><b>1. TRẠNG THÁI XU HƯỚNG (FLOWER):</b><br>
            Hiện tại: <span style='{trend_css} font-weight:bold; font-size: 15px;'>{trend_st}</span><br>
            <i>"{trend_desc}"</i></p>
            
            <p><b>2. TÍN HIỆU HỆ THỐNG:</b><br>
            Khuyến nghị: <span style='color:{sig_color}; font-weight:bold; font-size: 15px;'>{signal}</span><br>
            Lý do: {sig_desc}<br>
            Giá hiện tại: <span style='{p_color}'><b>{last['close']:,.2f} ({p_change:+.2f}%)</b></span></p>
            
            <p><b>3. VÙNG HÀNH ĐỘNG:</b><br>
            • Hỗ trợ cứng (SL): <b style='color:#FF5252'>{last['SL']:,.2f}</b><br>
            • Mục tiêu (Target): <b style='color:#00E676'>{last['T1']:,.2f}</b></p>
            
            <div style='margin-top: 15px; background-color: #000; padding: 10px; border-radius: 4px; font-style: italic; border-left: 3px solid #d4af37;'>
                "Nguyên tắc: Chỉ mua khi Nến chuyển Xanh và có Mũi tên báo Mua. Kiên quyết cắt lỗ khi Nến chuyển Đỏ hoặc gãy MA20."
            </div>
        </div>
    </div>
    """
    return html

# ---------------------------------------------------------
# 4. GIAO DIỆN CHÍNH
# ---------------------------------------------------------
if 'logged_in' not in st.session_state: st.session_state.logged_in = False
if st.session_state.logged_in and not db.check_token_valid(st.session_state.username, st.session_state.token):
    st.session_state.logged_in = False; st.rerun()

# --- LOGIN ---
if not st.session_state.logged_in:
    c1, c2, c3 = st.columns([1, 1, 1])
    with c2:
        st.markdown("<br><h1 style='text-align: center; color: #d4af37;'>TAMDUY CAPITAL</h1>", unsafe_allow_html=True)
        with st.form("login_form"):
            u = st.text_input("Username"); p = st.text_input("Password", type="password")
            if st.form_submit_button("LOGIN"):
                res = db.login_user(u, p)
                if res["status"] == "success":
                    st.session_state.update(logged_in=True, username=u, name=res["name"], role=res["role"], token=res["token"])
                    st.rerun()
                else: st.error(res["msg"])

# --- DASHBOARD ---
else:
    c1, c2, c3 = st.columns([1, 3, 1])
    with c1: st.markdown("### 🦅 PRO")
    with c2: 
        symbol = st.text_input("MÃ CK", "", label_visibility="collapsed", placeholder="Nhập mã (VD: HPG)...").upper()
    with c3: 
        if st.button("LOGOUT"): st.session_state.logged_in = False; st.rerun()

    if symbol:
        data = get_stock_data(symbol)
        
        if not data["error"]:
            df = data["df"]
            df = ind.calculate_full_indicators(df) # Gọi hàm tính toán
            last = df.iloc[-1]
            
            # --- HIỂN TÊN CÔNG TY ---
            st.markdown(f"<div style='text-align:center; color:#888; margin-top:-15px; margin-bottom:10px; font-style:italic;'>{data['name']}</div>", unsafe_allow_html=True)

            # --- LAYOUT CHÍNH: CHART TRÁI - INSIGHT PHẢI ---
            col_chart, col_insight = st.columns([3, 1])
            
            with col_insight:
                st.markdown(render_insight_panel(df, symbol, data['name']), unsafe_allow_html=True)

            with col_chart:
                # --- 8 TABS CHUẨN AMIBROKER ---
                tabs = st.tabs([
                    "TAB 1: TÍN HIỆU MUA/BÁN", 
                    "TAB 2: TARGET/STOPLOSS",
                    "TAB 3: VPA VOLUME",
                    "TAB 4: TRENDLINE",
                    "TAB 5: BOLLINGER",
                    "TAB 6: ICHIMOKU",
                    "TAB 7: RSI-MACD-GAP",
                    "TAB 8: TÀI CHÍNH & HỒ SƠ"
                ])
                
                # === TAB 1: TỔNG HỢP (Nến Flower) ===
                with tabs[0]:
                    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[0.75, 0.25], vertical_spacing=0.02)
                    
                    # Logic màu nến Flower (Xanh/Đỏ theo xu hướng)
                    df_up = df[df['trend_color'] == 1]
                    df_down = df[df['trend_color'] == -1]
                    
                    if not df_up.empty:
                        fig.add_trace(go.Candlestick(
                            x=df_up.index, open=df_up['open'], high=df_up['high'], low=df_up['low'], close=df_up['close'],
                            name='Uptrend', increasing_line_color='#00E676', increasing_fillcolor='#00E676',
                            decreasing_line_color='#006400', decreasing_fillcolor='#006400'
                        ), row=1, col=1)
                        
                    if not df_down.empty:
                        fig.add_trace(go.Candlestick(
                            x=df_down.index, open=df_down['open'], high=df_down['high'], low=df_down['low'], close=df_down['close'],
                            name='Downtrend', increasing_line_color='#B71C1C', increasing_fillcolor='#B71C1C',
                            decreasing_line_color='#FF1744', decreasing_fillcolor='#FF1744'
                        ), row=1, col=1)
                    
                    # Mũi tên Breakout
                    buys = df[df['Breakout']]
                    if not buys.empty:
                        fig.add_trace(go.Scatter(x=buys.index, y=buys['low']*0.98, mode='markers', marker=dict(symbol='triangle-up', size=15, color='cyan'), name='Breakout'), row=1, col=1)
                    
                    # Mũi tên Pocket
                    pockets = df[df['Pocket_Pivot']]
                    if not pockets.empty:
                        fig.add_trace(go.Scatter(x=pockets.index, y=pockets['low']*0.98, mode='markers', marker=dict(symbol='triangle-up', size=12, color='yellow'), name='Pocket Pivot'), row=1, col=1)
                    
                    # Volume
                    colors_vol = ['#00E676' if x == 1 else '#FF1744' for x in df['trend_color']]
                    fig.add_trace(go.Bar(x=df.index, y=df['volume'], marker_color=colors_vol, name='Volume'), row=2, col=1)

                    # Zoom
                    if len(df) > 90:
                        fig.update_xaxes(range=[df.index[-90], df.index[-1]+timedelta(days=2)])

                    fig.update_layout(height=700, paper_bgcolor='#000', plot_bgcolor='#000', showlegend=False, xaxis_rangeslider_visible=False, margin=dict(l=0,r=50,t=10,b=0))
                    st.plotly_chart(fig, use_container_width=True, config={'scrollZoom': True})

                # === CÁC TAB KHÁC (Placeholder) ===
                with tabs[1]: 
                    st.info("Biểu đồ Target/Stoploss (Trailing Stop)")
                    # Code vẽ chart SL/Target sẽ nằm ở đây...
                with tabs[2]: st.info("Biểu đồ VPA Analysis")
                with tabs[3]: st.info("Biểu đồ Trendline")
                with tabs[4]: st.info("Biểu đồ Bollinger Bands")
                with tabs[5]: st.info("Biểu đồ Ichimoku")
                with tabs[6]: st.info("Biểu đồ RSI - MACD - GAP")
                with tabs[7]: st.info("Hồ sơ & Tài chính")

        else: st.error(data["error"])
