import pandas as pd
import numpy as np
import pandas_ta as ta

def calculate_flower_indicator(df, smoother=5):
    """
    Chỉ báo Flower (Hoa Loa Kèn) để tô màu nến xu hướng
    """
    df = df.copy()
    # HLC3
    hlc3 = (df['high'] + df['low'] + df['close']) / 3
    
    # EMA & StDev
    ema_hlc = ta.ema(hlc3, length=20)
    stdev_hlc = ta.stdev(hlc3, length=20)
    
    # Trading Line
    # Tránh chia cho 0
    stdev_hlc = stdev_hlc.replace(0, 0.0001)
    df['flower_trading'] = (hlc3 - ema_hlc) / stdev_hlc
    
    # Signal Line
    df['flower_signal'] = ta.ema(df['flower_trading'], length=smoother)
    
    # Trend Color: 1 (Green/Up), -1 (Red/Down)
    # Nguyên tắc: Trading > Signal => Uptrend (Xanh)
    df['trend_color'] = np.where(df['flower_trading'] > df['flower_signal'], 1, -1)
    
    return df

def calculate_wyckoff_vsa(df):
    """
    Tính toán tín hiệu Mua/Bán theo Wyckoff và VSA
    """
    df = df.copy()
    
    # 1. Các đường MA
    df['MA10'] = ta.sma(df['close'], length=10)
    df['MA20'] = ta.sma(df['close'], length=20)
    df['MA50'] = ta.sma(df['close'], length=50)
    df['MA150'] = ta.sma(df['close'], length=150)
    df['MA200'] = ta.sma(df['close'], length=200)
    df['AvgVol'] = ta.sma(df['volume'], length=50)
    
    # 2. Wyckoff: Nền giá chặt (Base Tight)
    period = 20
    df['HHV_20'] = df['high'].rolling(period).max().shift(1)
    df['LLV_20'] = df['low'].rolling(period).min()
    # Độ biến động nền < 15%
    base_change = (df['HHV_20'] - df['LLV_20']) / df['LLV_20']
    df['Base_Tight'] = np.where(df['LLV_20']>0, base_change < 0.15, False)
    
    # 3. Tín hiệu Breakout (Mũi tên Xanh)
    # Giá vượt đỉnh nền + Vol > 1.3 TB + Trend Tốt
    df['Breakout'] = (df['close'] > df['HHV_20']) & \
                     (df['volume'] > 1.3 * df['AvgVol']) & \
                     (df['close'] > df['MA50'])
                     
    # 4. Pocket Pivot (Mũi tên Vàng/Xanh dương - Mua sớm)
    # Vol > Max Vol giảm 10 phiên
    down_vol = np.where(df['close'] < df['close'].shift(1), df['volume'], 0)
    max_down_10 = pd.Series(down_vol, index=df.index).rolling(10).max().shift(1)
    df['Pocket_Pivot'] = (df['volume'] > max_down_10) & \
                         (df['close'] > df['close'].shift(1)) & \
                         (df['close'] > df['MA20'])

    # 5. Tín hiệu Bán (Mũi tên Đỏ)
    # Gãy MA20 hoặc Gãy nền
    df['Sell_Signal'] = (df['close'] < df['MA20']) & (df['close'].shift(1) >= df['MA20'].shift(1))
    
    # 6. Target / Stoploss (ATR)
    df['ATR'] = ta.atr(df['high'], df['low'], df['close'], length=14)
    # SL: Dưới MA20 một chút hoặc đáy gần nhất
    df['SL'] = df['close'] - (2 * df['ATR'])
    # Target: R:R = 1:2
    df['T1'] = df['close'] + (2 * 2 * df['ATR'])
    
    return df

def calculate_full_indicators(df):
    """
    Tính toán full chỉ báo cho 8 Tab
    """
    df = calculate_flower_indicator(df)
    df = calculate_wyckoff_vsa(df)
    
    # Bollinger Bands
    bb = ta.bbands(df['close'], length=20, std=2)
    if bb is not None:
        df['BB_Upper'] = bb['BBU_20_2.0']
        df['BB_Lower'] = bb['BBL_20_2.0']
        df['BB_Mid'] = bb['BBM_20_2.0']
        
    # Ichimoku
    ichi = ta.ichimoku(df['high'], df['low'], df['close'])[0]
    df['Tenkan'] = ichi['ITS_9']
    df['Kijun'] = ichi['IKS_26']
    df['SpanA'] = ichi['ISA_26']
    df['SpanB'] = ichi['ISB_26']
    
    # RSI & MACD
    df['RSI'] = ta.rsi(df['close'], length=14)
    macd = ta.macd(df['close'])
    df['MACD'] = macd['MACD_12_26_9']
    df['MACD_Signal'] = macd['MACDs_12_26_9']
    df['MACD_Hist'] = macd['MACDh_12_26_9']
    
    return df
