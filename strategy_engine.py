# strategy_engine.py
import pandas as pd
import pandas_ta as ta
import numpy as np

def calculate_datcap_logic(df):
    """
    Chuyển đổi logic AFL DATCAP sang Python.
    Output: DataFrame có thêm cột màu sắc (color), tín hiệu (signal), các đường chỉ báo.
    """
    if df.empty or len(df) < 50: return df
    df = df.copy()

    # 1. TÍNH TOÁN CHỈ BÁO CƠ BẢN (INDICATORS)
    # ----------------------------------------------------
    df['MA20'] = ta.sma(df['close'], length=20)
    df['MA50'] = ta.sma(df['close'], length=50)
    df['MA150'] = ta.sma(df['close'], length=150)
    df['MA200'] = ta.sma(df['close'], length=200)
    df['Vol_MA20'] = ta.sma(df['volume'], length=20)
    
    # RSI & MACD
    df['RSI'] = ta.rsi(df['close'], length=14)
    macd = ta.macd(df['close'])
    df['MACD'] = macd['MACD_12_26_9']
    df['MACD_Signal'] = macd['MACDs_12_26_9']

    # Bollinger Bands (cho Tab BB sau này)
    bb = ta.bbands(df['close'], length=20, std=2)
    df['BB_Upper'] = bb['BBU_20_2.0']
    df['BB_Lower'] = bb['BBL_20_2.0']

    # 2. LOGIC NỀN GIÁ CHẶT (BASE TIGHT) - QUAN TRỌNG
    # ----------------------------------------------------
    # Logic: Max High 25 phiên - Min Low 25 phiên < 15%
    period = 25
    df['HH_25'] = df['high'].rolling(period).max()
    df['LL_25'] = df['low'].rolling(period).min()
    df['Base_Tight'] = ((df['HH_25'] - df['LL_25']) / df['LL_25']) < 0.15

    # 3. MÔ PHỎNG TRẠNG THÁI (STATE MACHINE) ĐỂ TÔ MÀU NẾN
    # ----------------------------------------------------
    # Logic AmiBroker: 
    # Mua = Breakout hoặc Pocket Pivot
    # Giữ (Hold) = Giá > Trailing Stop (MA50 hoặc MA20)
    # Bán = Gãy Trend
    
    # Tạo các cột chứa trạng thái
    df['Status'] = 'NEUTRAL'   # NEUTRAL, BUY, HOLD, SELL
    df['BarColor'] = '#d1d4dc' # Màu xám mặc định (Neutral)
    
    # Biến trạng thái vòng lặp
    in_trade = False
    stop_loss = 0.0
    
    # Duyệt vòng lặp để mô phỏng thời gian thực (Giống AmiBroker Loop)
    # Lưu ý: Loop trong Python chậm hơn Vectorize, nhưng chính xác về logic giữ lệnh
    status_list = []
    color_list = []
    signal_list = [] # 1: Buy, -1: Sell, 0: None
    
    for i in range(len(df)):
        close = df['close'].iloc[i]
        vol = df['volume'].iloc[i]
        vol_avg = df['Vol_MA20'].iloc[i] if not pd.isna(df['Vol_MA20'].iloc[i]) else 0
        ma50 = df['MA50'].iloc[i]
        
        # Điều kiện MUA (Đơn giản hóa logic DATCAP để demo)
        # 1. Breakout Nền chặt + Vol to
        cond_breakout = (df['Base_Tight'].iloc[i]) and (close > df['HH_25'].iloc[i-1]) and (vol > 1.3 * vol_avg)
        # 2. Xu hướng dài hạn tốt
        cond_trend = close > ma50
        
        is_buy = cond_breakout and cond_trend and not in_trade
        
        # Điều kiện BÁN
        # Gãy MA50 hoặc Gãy MA20 (tùy setup, ở đây dùng MA50 cho Trend dài)
        is_sell = (close < ma50) and in_trade
        
        # XỬ LÝ TRẠNG THÁI
        current_status = 'NEUTRAL'
        current_color = '#787b86' # Xám (Neutral)
        current_signal = 0
        
        if is_buy:
            in_trade = True
            current_status = 'BUY'
            current_color = '#00E676' # Xanh lá (Điểm mua)
            current_signal = 1
            stop_loss = close * 0.93 # SL 7% từ điểm mua
            
        elif is_sell:
            in_trade = False
            current_status = 'SELL'
            current_color = '#FF5252' # Đỏ (Điểm bán)
            current_signal = -1
            
        elif in_trade:
            # Đang giữ lệnh -> Màu xanh hoặc Xanh nhạt
            current_status = 'HOLD'
            current_color = '#089981' # Xanh đậm (Đang giữ hàng)
            # Update SL (Trailing Stop) - Ví dụ dời lên đường MA50
            stop_loss = max(stop_loss, ma50)
            
        else:
            # Không có lệnh -> Màu xám hoặc Đỏ nhạt nếu đang Downtrend nặng
            if close < ma50:
                current_color = '#ef5350' # Đỏ nhạt (Downtrend)
            else:
                current_color = '#787b86' # Xám (Sideway)
        
        status_list.append(current_status)
        color_list.append(current_color)
        signal_list.append(current_signal)
    
    df['Status'] = status_list
    df['BarColor'] = color_list
    df['Signal_Point'] = signal_list
    
    return df
