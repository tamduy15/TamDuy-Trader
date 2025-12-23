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
    df['MA20'] = ta.sma(df['close'], length=20)
    df['MA50'] = ta.sma(df['close'], length=50)
    df['MA150'] = ta.sma(df['close'], length=150)
    df['MA200'] = ta.sma(df['close'], length=200)
    df['Vol_MA20'] = ta.sma(df['volume'], length=20)
    
    # RSI & MACD
    df['RSI'] = ta.rsi(df['close'], length=14)
    macd = ta.macd(df['close'])
    # Pandas TA trả về tên cột có thể khác nhau, ta lấy theo index hoặc tên chuẩn
    # MACD thường trả về: MACD_12_26_9, MACDh_12_26_9 (hist), MACDs_12_26_9 (signal)
    df['MACD'] = macd['MACD_12_26_9']
    df['MACD_Signal'] = macd['MACDs_12_26_9']

    # Bollinger Bands
    bb = ta.bbands(df['close'], length=20, std=2)
    df['BB_Upper'] = bb['BBU_20_2.0']
    df['BB_Lower'] = bb['BBL_20_2.0']

    # 2. LOGIC NỀN GIÁ CHẶT (BASE TIGHT)
    period = 25
    df['HH_25'] = df['high'].rolling(period).max()
    df['LL_25'] = df['low'].rolling(period).min()
    df['Base_Tight'] = ((df['HH_25'] - df['LL_25']) / df['LL_25']) < 0.15

    # 3. MÔ PHỎNG TRẠNG THÁI (STATE MACHINE)
    df['Status'] = 'NEUTRAL'
    df['BarColor'] = '#d1d4dc' # Màu xám
    
    in_trade = False
    stop_loss = 0.0
    
    status_list = []
    color_list = []
    signal_list = [] # 1: Buy, -1: Sell, 0: None
    
    # Chuyển dữ liệu sang numpy array để loop nhanh hơn hoặc dùng itertuples
    # Để đơn giản và an toàn logic, dùng loop cơ bản
    for i in range(len(df)):
        close = df['close'].iloc[i]
        vol = df['volume'].iloc[i]
        # Xử lý NaN ở những dòng đầu
        vol_avg = df['Vol_MA20'].iloc[i] if not pd.isna(df['Vol_MA20'].iloc[i]) else 0
        ma50 = df['MA50'].iloc[i]
        
        # Logic mua đơn giản hóa
        cond_breakout = (df['Base_Tight'].iloc[i]) and (close > df['HH_25'].iloc[i-1]) and (vol > 1.3 * vol_avg)
        cond_trend = close > ma50 if not pd.isna(ma50) else False
        
        is_buy = cond_breakout and cond_trend and not in_trade
        is_sell = (close < ma50) and in_trade
        
        current_status = 'NEUTRAL'
        current_color = '#787b86' 
        current_signal = 0
        
        if is_buy:
            in_trade = True
            current_status = 'BUY'
            current_color = '#00E676' # Xanh lá
            current_signal = 1
            stop_loss = close * 0.93
            
        elif is_sell:
            in_trade = False
            current_status = 'SELL'
            current_color = '#FF5252' # Đỏ
            current_signal = -1
            
        elif in_trade:
            current_status = 'HOLD'
            current_color = '#089981' # Xanh đậm giữ lệnh
            stop_loss = max(stop_loss, ma50 if not pd.isna(ma50) else 0)
            
        else:
            if not pd.isna(ma50) and close < ma50:
                current_color = '#ef5350' # Đỏ nhạt downtrend
            else:
                current_color = '#787b86' # Xám sideway
        
        status_list.append(current_status)
        color_list.append(current_color)
        signal_list.append(current_signal)
    
    df['Status'] = status_list
    df['BarColor'] = color_list
    df['Signal_Point'] = signal_list
    
    return df
