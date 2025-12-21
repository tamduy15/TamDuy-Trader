import streamlit as st
import pandas as pd
import uuid
from datetime import datetime

# Thay ID của bạn vào đây
SHEET_ID = "1rLautBfQowqcAw9gq2VCfK3UyqUIglnOzZQLqVHhvNs"
SHEET_URL = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/gviz/tq?tqx=out:csv"

def init_db():
    pass

def get_all_users():
    try:
        # Thêm uuid để buộc Google không lấy bản cũ (clear cache)
        final_url = f"{SHEET_URL}&cache={uuid.uuid4()}"
        df = pd.read_csv(final_url)
        # Loại bỏ khoảng trắng thừa ở tên cột
        df.columns = df.columns.str.strip().str.lower()
        return df
    except Exception as e:
        # Nếu lỗi, nó sẽ hiện thông báo đỏ trên web để bạn biết nguyên nhân
        st.error(f"⚠️ Lỗi kết nối Sheets: {e}")
        return pd.DataFrame()

def login_user(username, password):
    df = get_all_users()
    if df.empty: 
        return {"status": "fail", "msg": "Không thể kết nối dữ liệu Google Sheets"}

    # Lọc tìm user
    user_row = df[df['username'].astype(str) == str(username)]
    
    if not user_row.empty:
        row = user_row.iloc[0]
        
        # Kiểm tra mật khẩu
        if str(password) != str(row['password']):
            return {"status": "fail", "msg": "Mật khẩu không chính xác"}

        # Kiểm tra trạng thái Status (True/False)
        if str(row['status']).upper() != 'TRUE':
            return {"status": "fail", "msg": "Tài khoản đã bị khóa"}

        # Kiểm tra thời hạn
        try:
            open_date = pd.to_datetime(row['date_open'])
            duration = int(row['duration'])
            expiry_date = open_date + pd.DateOffset(months=duration)
            days_left = (expiry_date - datetime.now()).days
            
            if days_left <= 0:
                return {"status": "fail", "msg": "Tài khoản đã hết hạn sử dụng"}
            
            return {
                "status": "success", 
                "name": row['name'], 
                "role": row['role'], 
                "token": str(uuid.uuid4()),
                "msg": f"Hạn dùng còn {days_left} ngày" if days_left <= 7 else ""
            }
        except:
            return {"status": "fail", "msg": "Lỗi định dạng ngày trên Sheets (Yêu cầu YYYY-MM-DD)"}
            
    return {"status": "fail", "msg": "Tài khoản không tồn tại"}

def check_token_valid(username, current_token):
    return True

def create_user(u, p, n, r): pass
def toggle_user_status(u, s): pass
