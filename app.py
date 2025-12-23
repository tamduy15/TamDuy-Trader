import streamlit as st
import db_manager as db
import time
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import requests
import indicators as ind # Import file tính toán mới

# ---------------------------------------------------------
# 1. CẤU HÌNH
# ---------------------------------------------------------
st.set_page_config(page_title="TAMDUY TRADER PRO", layout="wide", page_icon="🦅", initial_sidebar_state="collapsed")
db.init_db()

# CSS Tùy chỉnh (Giữ nguyên style Dark Mode xịn xò)
st.markdown("""
<style>
    .stApp {background-color: #000000; color: #e0e0e0;}
    header[data-testid="stHeader"] {visibility: hidden; height: 0px;}
    .hud-box {background-color: #0d1117; border: 1px solid #333; padding: 10px; border-radius: 4px; text-align: center; border-top: 2px solid #d4af37;}
    .hud-val {font-family: 'Roboto Mono', monospace; font-size: 20px; font-weight: bold; color: #fff;}
    .hud-lbl {font-size: 11px; color: #888; text-transform: uppercase;}
    .stTabs [aria-selected="true"] {background-color: #d4af37 !important; color: #000 !important; font-weight: bold;}
</style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------
# 2. DATA ENGINE (DNSE API)
# ---------------------------------------------------------
@st.cache_data(ttl=5)
def get_data(symbol):
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
                return df[df['volume'] > 0], None
        return None, "Không có dữ liệu"
    except Exception as e: return None, str(e)

# ---------------------------------------------------------
# 3. GIAO DIỆN CHÍNH
# ---------------------------------------------------------
if 'logged_in' not in st.session_state: st.session_state.logged_in = False
if st.session_state.logged_in and not db.check_token_valid(st.session_state.username, st.session_state.token):
    st.session_state.logged_in = False; st.rerun()

# --- LOGIN FORM ---
if not st.session_state.logged_in:
    # (Phần code login giữ nguyên như cũ cho gọn)
    c1,c2,c3 = st.columns([1,1,1])
    with c2:
        st.title("TAMDUY CAPITAL")
        with st.form("login"):
            u = st.text_input("User"); p = st.text_input("Pass", type="password")
            if st.form_submit_button("LOGIN"):
                res = db.login_user(u, p)
                if res["status"] == "success":
                    st.session_state.update(logged_in=True, username=u, name=res["name"], role=res["role"], token=res["token"])
                    st.rerun()
                else: st.error(res["msg"])

# --- MAIN DASHBOARD ---
else:
    # Header
    c1, c2, c3, c4 = st.columns([1, 2, 4, 1])
    with c1: st.markdown("### 🦅 PRO")
    with c2: symbol = st.text_input("MÃ", "", label_visibility="collapsed", placeholder="Mã CK...").upper()
    with c4: 
        if st.button("EXIT"): st.session_state.logged_in = False; st.rerun()
    st.markdown("---")

    if symbol:
        df, err = get_data(symbol)
        if df is not None:
            # TÍNH TOÁN CHỈ BÁO (GỌI TỪ MODULE MỚI)
            df = ind.calculate_wyckoff_vsa(df)
            trend_color, trading_line, signal_line = ind.calculate_flower_indicator(df)
            last = df.iloc[-1]
            
            # --- HUD ---
            k1, k2, k3, k4 = st.columns(4)
            p_col = "#00E676" if last['close']>=last['open'] else "#FF5252"
            k1.markdown(f"<div class='hud-box'><div class='hud-val' style='color:{p_col}'>{last['close']:,.2f}</div><div class='hud-lbl'>GIÁ</div></div>", unsafe_allow_html=True)
            
            # Tín hiệu Flower
            flower_st = "TÍCH CỰC (XANH)" if trend_color[-1] == 1 else "TIÊU CỰC (ĐỎ)"
            f_col = "#00E676" if trend_color[-1] == 1 else "#FF5252"
            k2.markdown(f"<div class='hud-box'><div class='hud-val' style='color:{f_col}'>{flower_st}</div><div class='hud-lbl'>XU HƯỚNG FLOWER</div></div>", unsafe_allow_html=True)

            # --- TABS LAYOUT (7 TABS CHUẨN AMIBROKER) ---
            tabs = st.tabs([
                "TAB 1: TÍN HIỆU TỔNG HỢP", 
                "TAB 2: TARGET/STOPLOSS",
                "TAB 3: VPA VOLUME",
                "TAB 4: TRENDLINE",
                "TAB 5: BOLLINGER",
                "TAB 6: ICHIMOKU",
                "TAB 7: RSI-MACD"
            ])
            
            # === TAB 1: TỔNG HỢP (Nến Flower + Tín hiệu) ===
            with tabs[0]:
                fig = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[0.75, 0.25], vertical_spacing=0.02)
                
                # 1. Vẽ Nến Flower (Xanh/Đỏ theo xu hướng, KHÔNG theo giá tăng giảm)
                # Tách data thành 2 nhóm màu
                idx_green = np.where(trend_color == 1)[0]
                idx_red = np.where(trend_color == -1)[0]
                
                # Nến Xanh (Trend Tăng)
                if len(idx_green) > 0:
                    df_g = df.iloc[idx_green]
                    fig.add_trace(go.Candlestick(
                        x=df_g.index, open=df_g['open'], high=df_g['high'], low=df_g['low'], close=df_g['close'],
                        name='Trend Tăng',
                        increasing_line_color='#00E676', increasing_fillcolor='#00E676',
                        decreasing_line_color='#006400', decreasing_fillcolor='#006400' # Giảm trong trend tăng vẫn xanh đậm
                    ), row=1, col=1)
                
                # Nến Đỏ (Trend Giảm)
                if len(idx_red) > 0:
                    df_r = df.iloc[idx_red]
                    fig.add_trace(go.Candlestick(
                        x=df_r.index, open=df_r['open'], high=df_r['high'], low=df_r['low'], close=df_r['close'],
                        name='Trend Giảm',
                        increasing_line_color='#B71C1C', increasing_fillcolor='#B71C1C', # Tăng trong trend giảm vẫn đỏ đậm
                        decreasing_line_color='#FF1744', decreasing_fillcolor='#FF1744'
                    ), row=1, col=1)
                
                # 2. Vẽ Mũi tên Tín hiệu (Wyckoff & Pocket Pivot)
                buys = df[df['Signal_Wyckoff'] | df['Signal_Pocket']]
                if not buys.empty:
                    fig.add_trace(go.Scatter(
                        x=buys.index, y=buys['low']*0.98,
                        mode='markers+text', marker=dict(symbol='triangle-up', size=14, color='#FFFF00'),
                        text="MUA", textposition="bottom center", name='Signal'
                    ), row=1, col=1)
                
                # 3. Volume
                colors_vol = ['#00E676' if c==1 else '#FF5252' for c in trend_color]
                fig.add_trace(go.Bar(x=df.index, y=df['volume'], marker_color=colors_vol, name='Volume'), row=2, col=1)

                # Zoom 3 tháng
                if len(df) > 90:
                    fig.update_xaxes(range=[df.index[-90], df.index[-1]+timedelta(days=2)])

                fig.update_layout(height=700, paper_bgcolor='#000', plot_bgcolor='#000', showlegend=False, xaxis_rangeslider_visible=False, margin=dict(l=0,r=50,t=10,b=0))
                st.plotly_chart(fig, use_container_width=True)

            # === CÁC TAB KHÁC (Placeholder - Sẽ code tiếp) ===
            with tabs[1]: st.info("Đang xây dựng: Target / Stoploss Chart (Theo logic Trailing Stop)")
            with tabs[2]: st.info("Đang xây dựng: VPA Chart (Spread & Volume Analysis)")
            with tabs[3]: st.info("Đang xây dựng: Trendline Auto")
            with tabs[4]: st.info("Đang xây dựng: Bollinger + Keltner")
            with tabs[5]: st.info("Đang xây dựng: Ichimoku Full")
            with tabs[6]: st.info("Đang xây dựng: RSI / MACD / Gap")

        else: st.error(err)

