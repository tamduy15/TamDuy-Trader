import pandas as pd
import numpy as np
import pandas_ta as ta

def calculate_flower_indicator(df, smoother=5):
    """
    Tính toán chỉ báo Flower (Hoa Loa Kèn) để tô màu nến.
    Chuyển đổi từ AFL: trading = ( hlc2 - emaHLC2 ) / stDevHLC2;
    """
    df = df.copy()
    
    # 1. Tính HLC2 (Trung bình giá)
    # Amibroker: hlc2 = (High + Low + Close) / 3 (Thông thường)
    # Tuy nhiên, một số bản Flower dùng (Open+High+Low+Close)/4.
    # Ta dùng (H+L+C)/3 cho phổ biến.
    hlc3 = (df['high'] + df['low'] + df['close']) / 3
    
    # 2. Tính EMA của HLC
    # Trong code gốc không ghi rõ chu kỳ EMA, thường là 20 hoặc 34. 
    # Ta chọn 20 để nhạy với ngắn hạn.
    ema_hlc = ta.ema(hlc3, length=20)
    
    # 3. Tính độ lệch chuẩn (StDev)
    stdev_hlc = ta.stdev(hlc3, length=20)
    
    # 4. Tính đường Trading (Dao động)
    # Tránh chia cho 0
    stdev_hlc = stdev_hlc.replace(0, 0.0001)
    trading = (hlc3 - ema_hlc) / stdev_hlc
    
    # 5. Tính đường Signal (Làm mượt Trading)
    signal_trading = ta.ema(trading, length=smoother)
    
    # 6. Xác định Màu Nến (Trend Color)
    # Xanh (1) nếu Trading > Signal, Đỏ (-1) nếu ngược lại
    # Logic ngoại lệ: Ref(oo, -1) < oo... (Nến đảo chiều) -> Cái này hơi phức tạp để mô phỏng 100%
    # Ta dùng logic chính: Trading > Signal
    
    trend_color = np.where(trading > signal_trading, 1, -1) # 1: Xanh, -1: Đỏ
    
    return trend_color, trading, signal_trading

def calculate_wyckoff_vsa(df):
    """
    Tính toán các điểm mua Wyckoff và Pocket Pivot
    """
    df = df.copy()
    
    # MA Lines
    df['MA10'] = ta.sma(df['close'], length=10)
    df['MA20'] = ta.sma(df['close'], length=20)
    df['MA50'] = ta.sma(df['close'], length=50)
    df['MA150'] = ta.sma(df['close'], length=150)
    df['MA200'] = ta.sma(df['close'], length=200)
    df['AvgVol'] = ta.sma(df['volume'], length=50)
    
    # 1. Trend Filter
    trend_strong = (df['close'] > df['MA50']) & (df['MA50'] > df['MA150']) & (df['MA150'] > df['MA200'])
    
    # 2. Wyckoff Base (Nền giá)
    period = 20
    hhv = df['high'].rolling(period).max().shift(1)
    llv = df['low'].rolling(period).min()
    base_tight = np.where(llv > 0, (hhv - llv) / llv < 0.15, False) # Nền chặt < 15%
    
    # Breakout
    breakout = (df['close'] > hhv) & (df['volume'] > 1.3 * df['AvgVol'])
    
    # 3. Pocket Pivot
    down_vol = np.where(df['close'] < df['close'].shift(1), df['volume'], 0)
    max_down = pd.Series(down_vol, index=df.index).rolling(10).max().shift(1)
    pocket = (df['volume'] > max_down) & (df['close'] > df['MA10']) & (df['close'] > df['close'].shift(1))
    
    # Tín hiệu
    df['Signal_Wyckoff'] = breakout & base_tight & trend_strong
    df['Signal_Pocket'] = pocket & (df['close'] > df['MA50'])
    
    return df

def resample_weekly(df):
    """Chuyển dữ liệu Ngày sang Tuần để lọc nhiễu dài hạn"""
    logic = {'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last', 'volume': 'sum'}
    df_weekly = df.resample('W').apply(logic)
    return df_weekly
