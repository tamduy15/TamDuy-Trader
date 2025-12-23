import pandas as pd
import numpy as np
import pandas_ta as ta

def calculate_flower_indicator(df, smoother=5):
    """
    Chuyển đổi logic Nến Flower từ Amibroker:
    trading = ( hlc2 - emaHLC2 ) / stDevHLC2;
    Màu xanh khi Trading > Signal, Đỏ khi Trading < Signal
    """
    df = df.copy()
    
    # 1. HLC3 (Giá trung bình)
    # Trong Ami: hlc2 thường là (H+L+C)/3 hoặc (O+H+L+C)/4. Ta dùng HLC3 chuẩn.
    hlc3 = (df['high'] + df['low'] + df['close']) / 3
    
    # 2. EMA & StDev của HLC3 (Chu kỳ 20)
    ema_hlc = ta.ema(hlc3, length=20)
    stdev_hlc = ta.stdev(hlc3, length=20)
    
    # 3. Trading Line (Dao động)
    # Tránh chia cho 0
    stdev_hlc = stdev_hlc.replace(0, 0.0001)
    df['flower_trading'] = (hlc3 - ema_hlc) / stdev_hlc
    
    # 4. Signal Line (Làm mượt)
    df['flower_signal'] = ta.ema(df['flower_trading'], length=smoother)
    
    # 5. Trend Color: 1 (XANH - Tăng), -1 (ĐỎ - Giảm)
    df['trend_color'] = np.where(df['flower_trading'] > df['flower_signal'], 1, -1)
    
    return df

def calculate_wyckoff_vsa(df):
    """
    Tính toán các điểm mua/bán theo Wyckoff, VSA và Robot 3in1
    """
    df = df.copy()
    
    # --- CHỈ BÁO CƠ BẢN ---
    df['MA10'] = ta.sma(df['close'], length=10)
    df['MA20'] = ta.sma(df['close'], length=20)
    df['MA50'] = ta.sma(df['close'], length=50)
    df['MA150'] = ta.sma(df['close'], length=150)
    df['MA200'] = ta.sma(df['close'], length=200)
    df['AvgVol'] = ta.sma(df['volume'], length=50)
    
    # --- 1. WYCKOFF BASE (Dải màu xanh - Nền chặt) ---
    period = 25
    df['HHV_25'] = df['high'].rolling(period).max().shift(1)
    df['LLV_25'] = df['low'].rolling(period).min()
    # Biên độ nền < 15%
    base_change = (df['HHV_25'] - df['LLV_25']) / df['LLV_25']
    df['Base_Tight'] = np.where(df['LLV_25']>0, base_change < 0.15, False)

    # --- 2. TÍN HIỆU MUA (Mũi tên Xanh - Breakout) ---
    # Giá vượt đỉnh nền + Vol nổ > 1.4 lần TB + Trend Tốt
    df['Trend_Strong'] = (df['close'] > df['MA50']) & (df['MA50'] > df['MA150']) & (df['MA150'] > df['MA200'])
    df['Breakout'] = (df['close'] > df['HHV_25']) & (df['volume'] > 1.4 * df['AvgVol']) & df['Trend_Strong']
    
    # --- 3. POCKET PIVOT (Mũi tên Vàng - Mua sớm) ---
    # Vol lớn hơn Max Vol của các phiên GIẢM trong 10 ngày qua
    down_vol_arr = np.where(df['close'] < df['close'].shift(1), df['volume'], 0)
    down_vol_series = pd.Series(down_vol_arr, index=df.index)
    max_down_vol = down_vol_series.rolling(10).max().shift(1)
    
    df['Pocket_Pivot'] = (df['volume'] > max_down_vol) & \
                         (df['close'] > df['close'].shift(1)) & \
                         (df['close'] > df['MA20'])

    # --- 4. TÍN HIỆU BÁN (Mũi tên Đỏ) ---
    # Gãy MA20
    df['Sell_Signal'] = (df['close'] < df['MA20']) & (df['close'].shift(1) >= df['MA20'].shift(1))
    
    # --- 5. TARGET / STOPLOSS (ATR) ---
    df['ATR'] = ta.atr(df['high'], df['low'], df['close'], length=14)
    # SL: MA50 hoặc Kijun hoặc Đáy gần nhất (Low - 2ATR)
    df['SL'] = df['close'] - (2 * df['ATR'])
    # Target R:R 1:2
    df['T1'] = df['close'] + (2 * (df['close'] - df['SL']))
    
    return df

def calculate_full_indicators(df):
    """Tổng hợp tất cả chỉ báo cho 8 Tab"""
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
    
    # ADX
    adx = ta.adx(df['high'], df['low'], df['close'])
    if adx is not None:
        df['ADX'] = adx['ADX_14']
    else: df['ADX'] = 0
        
    return df
