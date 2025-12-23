import pandas as pd
import numpy as np
import pandas_ta as ta

def calculate_flower_indicator(df, smoother=5):
    """
    Chuyển đổi logic Nến Flower từ Amibroker:
    Màu xanh khi Trading > Signal, Đỏ khi Trading < Signal
    """
    df = df.copy()
    
    # HLC3
    hlc3 = (df['high'] + df['low'] + df['close']) / 3
    
    # EMA & StDev của HLC3 (Chu kỳ 20)
    ema_hlc = ta.ema(hlc3, length=20)
    stdev_hlc = ta.stdev(hlc3, length=20)
    
    # Trading Line
    stdev_hlc = stdev_hlc.replace(0, 0.0001)
    df['flower_trading'] = (hlc3 - ema_hlc) / stdev_hlc
    
    # Signal Line
    df['flower_signal'] = ta.ema(df['flower_trading'], length=smoother)
    
    # Trend Color: 1 (XANH), -1 (ĐỎ)
    df['trend_color'] = np.where(df['flower_trading'] > df['flower_signal'], 1, -1)
    
    return df

def calculate_wyckoff_vsa(df):
    """
    Tính toán các điểm mua/bán theo Wyckoff, VSA
    """
    df = df.copy()
    
    # Chỉ báo cơ bản
    df['MA10'] = ta.sma(df['close'], length=10)
    df['MA20'] = ta.sma(df['close'], length=20)
    df['MA50'] = ta.sma(df['close'], length=50)
    df['MA150'] = ta.sma(df['close'], length=150)
    df['MA200'] = ta.sma(df['close'], length=200)
    df['AvgVol'] = ta.sma(df['volume'], length=50)
    
    # 1. Wyckoff Base (Nền giá chặt)
    period = 25
    df['HHV_25'] = df['high'].rolling(period).max().shift(1)
    df['LLV_25'] = df['low'].rolling(period).min()
    
    # Fix chia cho 0
    with np.errstate(divide='ignore', invalid='ignore'):
        base_change = (df['HHV_25'] - df['LLV_25']) / df['LLV_25']
        df['Base_Tight'] = np.where(df['LLV_25'] > 0, base_change < 0.15, False)

    # 2. Tín hiệu Breakout
    df['Trend_Strong'] = (df['close'] > df['MA50']) & (df['MA50'] > df['MA150']) & (df['MA150'] > df['MA200'])
    df['Breakout'] = (df['close'] > df['HHV_25']) & (df['volume'] > 1.4 * df['AvgVol']) & df['Trend_Strong']
    
    # 3. Pocket Pivot
    down_vol_arr = np.where(df['close'] < df['close'].shift(1), df['volume'], 0)
    max_down_vol = pd.Series(down_vol_arr, index=df.index).rolling(10).max().shift(1)
    
    df['Pocket_Pivot'] = (df['volume'] > max_down_vol) & \
                         (df['close'] > df['close'].shift(1)) & \
                         (df['close'] > df['MA20'])

    # 4. Tín hiệu Bán
    df['Sell_Signal'] = (df['close'] < df['MA20']) & (df['close'].shift(1) >= df['MA20'].shift(1))
    
    # 5. Target / Stoploss (ATR)
    df['ATR'] = ta.atr(df['high'], df['low'], df['close'], length=14)
    df['SL'] = df['close'] - (2 * df['ATR'])
    df['T1'] = df['close'] + (4 * df['ATR'])
    
    return df

def calculate_full_indicators(df):
    """Tổng hợp tất cả chỉ báo cho 8 Tab"""
    df = calculate_flower_indicator(df)
    df = calculate_wyckoff_vsa(df)
    
    # Bollinger Bands (FIX LỖI KEYERROR)
    bb = ta.bbands(df['close'], length=20, std=2)
    if bb is not None:
        # Tự động tìm tên cột BBU (Upper) và BBL (Lower) bất kể version pandas_ta
        cols = bb.columns.tolist()
        upper_col = next((c for c in cols if c.startswith('BBU')), None)
        lower_col = next((c for c in cols if c.startswith('BBL')), None)
        mid_col = next((c for c in cols if c.startswith('BBM')), None)
        
        if upper_col and lower_col:
            df['BB_Upper'] = bb[upper_col]
            df['BB_Lower'] = bb[lower_col]
            if mid_col: df['BB_Mid'] = bb[mid_col]
        else:
            # Fallback nếu không tìm thấy
            df['BB_Upper'] = df['MA20'] + (2 * df['close'].rolling(20).std())
            df['BB_Lower'] = df['MA20'] - (2 * df['close'].rolling(20).std())
        
    # Ichimoku
    ichi = ta.ichimoku(df['high'], df['low'], df['close'])[0]
    df['Tenkan'] = ichi['ITS_9']
    df['Kijun'] = ichi['IKS_26']
    df['SpanA'] = ichi['ISA_26']
    df['SpanB'] = ichi['ISB_26']
    
    # RSI & MACD
    df['RSI'] = ta.rsi(df['close'], length=14)
    macd = ta.macd(df['close'])
    if macd is not None:
        df['MACD'] = macd['MACD_12_26_9']
        df['MACD_Signal'] = macd['MACDs_12_26_9']
        df['MACD_Hist'] = macd['MACDh_12_26_9']
    
    # ADX
    adx = ta.adx(df['high'], df['low'], df['close'])
    if adx is not None:
        df['ADX'] = adx['ADX_14']
    else: df['ADX'] = 0
    
    # Gap
    df['Gap_Up'] = df['low'] > df['high'].shift(1)
    df['Gap_Down'] = df['high'] < df['low'].shift(1)
        
    return df
