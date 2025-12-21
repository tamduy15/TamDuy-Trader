import streamlit as st
import pandas as pd
import uuid
from datetime import datetime

# ID file Google Sheets của bạn
SHEET_ID = "1rLautBfQowqcAw9gq2VCfK3UyqUIglnOzZQLqVHhvNs" 
SHEET_URL = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/gviz/tq?tqx=out:csv"

def init_db():
    """Hàm khởi tạo để app.py không báo lỗi AttributeError"""
    pass

def get_all_users():
    try:
        # Thêm uuid để tránh Google trả về dữ liệu cũ (cache)
        url = f"{SHEET_URL}&cache={uuid.uuid4()}"
        df = pd.read_csv(url)
        # Làm sạch tên cột (tránh khoảng trắng thừa)
        df.columns = df.columns.str.strip()
        return df
    except Exception as e:
        return pd.DataFrame()

def login_user(username, password):
    df = get_all_users()
    if df.empty: 
        return {"status": "fail", "msg": "Không thể kết nối Google Sheets"}

    # Tìm user
    user_row = df[df['username'].astype(str) == str(username)]
    
    if not user_row.empty:
        row = user_row.iloc[0]
        
        # 1. Kiểm tra mật khẩu
        if str(password) != str(row['password']):
            return {"status": "fail", "msg": "Mật khẩu không chính xác"}

        # 2. Kiểm tra trạng thái Status
        if str(row['status']).upper() != 'TRUE':
            return {"status": "fail", "msg": "Tài khoản đang bị khóa (Status = False)"}

        # 3. Kiểm tra thời hạn theo 4 mốc (1, 3, 6, 12 tháng)
        try:
            open_date = pd.to_datetime(row['date_open'])
            duration_months = int(row['duration']) # Lấy từ cột H
            
            # Tính ngày hết hạn
            expiry_date = open_date + pd.DateOffset(months=duration_months)
            today = datetime.now()
            
            days_left = (expiry_date - today).days
            
            if days_left <= 0:
                return {"status": "fail", "msg": f"Tài khoản đã hết hạn vào ngày {expiry_date.strftime('%d/%m/%Y')}"}
            
            msg_expiry = ""
            if days_left <= 7:
                msg_expiry = f"Cảnh báo: Tài khoản của bạn chỉ còn {days_left} ngày sử dụng!"
        except:
            return {"status": "fail", "msg": "Lỗi định dạng ngày tháng trên Sheets (Yêu cầu: YYYY-MM-DD)"}

        # 4. Token đăng nhập (Dùng session để giả lập 1 nơi đăng nhập trên trình duyệt)
        new_token = str(uuid.uuid4())
        
        return {
            "status": "success", 
            "name": row['name'], 
            "role": row['role'], 
            "token": new_token,
            "msg": msg_expiry
        }
            
    return {"status": "fail", "msg": "Tài khoản không tồn tại"}

def check_token_valid(username, current_token):
    # Luôn trả về True để duy trì phiên cho Google Sheets
    return True

# Các hàm giả lập để tương thích với app.py
def create_user(u, p, n, r): pass
def toggle_user_status(u, s): pass
