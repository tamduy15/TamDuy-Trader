import streamlit as st
import pandas as pd
import uuid
from datetime import datetime, timedelta

# ID file Google Sheets của bạn
SHEET_ID = "ID_FILE_CUA_BAN" 
SHEET_URL = f"https://docs.google.com/spreadsheets/d/1rLautBfQowqcAw9gq2VCfK3UyqUIglnOzZQLqVHhvNs/gviz/tq?tqx=out:csv"

def get_all_users():
    try:
        # Thêm biến số ngẫu nhiên để tránh Google cache dữ liệu cũ
        url = f"{SHEET_URL}&cache={uuid.uuid4()}"
        df = pd.read_csv(url)
        return df
    except Exception as e:
        st.error(f"Lỗi đọc Sheets: {e}")
        return pd.DataFrame()

def login_user(username, password):
    df = get_all_users()
    if df.empty: return {"status": "fail", "msg": "Không thể kết nối dữ liệu"}

    # Tìm user (ép kiểu về string để so sánh)
    user_row = df[df['username'].astype(str) == str(username)]
    
    if not user_row.empty:
        row = user_row.iloc[0]
        
        # 1. Kiểm tra mật khẩu
        if str(password) != str(row['password']):
            return {"status": "fail", "msg": "Sai mật khẩu"}

        # 2. Kiểm tra trạng thái Status (Cột F)
        if str(row['status']).upper() != 'TRUE':
            return {"status": "fail", "msg": "Tài khoản đã bị khóa"}

        # 3. Kiểm tra thời hạn (Cột G và H)
        try:
            open_date = pd.to_datetime(row['date_open'])
            months = int(row['expiry_months'])
            # Tính ngày hết hạn (giả định 1 tháng = 30 ngày cho đơn giản)
            expiry_date = open_date + timedelta(days=months * 30)
            today = datetime.now()
            
            days_left = (expiry_date - today).days
            
            if days_left <= 0:
                return {"status": "fail", "msg": "Tài khoản đã hết hạn sử dụng"}
        except:
            return {"status": "fail", "msg": "Lỗi định dạng ngày tháng trên Sheets"}

        # 4. Xử lý Active Token (Chỉ cho phép 1 nơi đăng nhập)
        # Vì đây là bản Read-only, ta lưu token vào session của trình duyệt.
        # Muốn đá người cũ ra, bạn cần cấu hình quyền Ghi (Write) để cập nhật token lên Sheets.
        new_token = str(uuid.uuid4())
        
        msg_expiry = f"Thời hạn còn lại: {days_left} ngày." if days_left <= 7 else ""
        
        return {
            "status": "success", 
            "name": row['name'], 
            "role": row['role'], 
            "token": new_token,
            "msg": msg_expiry
        }
            
    return {"status": "fail", "msg": "Tài khoản không tồn tại"}

def check_token_valid(username, current_token):
    # Với bản Google Sheets Read-only, ta kiểm tra status còn True hay không
    df = get_all_users()
    user_row = df[df['username'].astype(str) == str(username)]
    if not user_row.empty:
        return str(user_row.iloc[0]['status']).upper() == 'TRUE'
    return False

# Các hàm Admin để tương thích với app.py cũ (Bạn nên sửa trên Sheets trực tiếp)
def toggle_user_status(username, status): pass
def create_user(u, p, n, r): pass
