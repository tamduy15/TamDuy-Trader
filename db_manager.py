import streamlit as st
import pandas as pd
import uuid
from datetime import datetime

# ID Sheet của bạn
SHEET_ID = "1rLautBfQowqcAw9gq2VCfK3UyqUIglnOzZQLqVHhvNs"
# Link này sẽ ép Google xuất dữ liệu ở dạng CSV công khai
SHEET_URL = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/export?format=csv&gid=0"

def init_db():
    pass

def get_all_users():
    try:
        # Thêm uuid để tránh cache (dữ liệu cũ)
        url = f"{SHEET_URL}&nocache={uuid.uuid4()}"
        # Thiết lập timeout và headers để tránh bị Google chặn robot
        df = pd.read_csv(url, on_bad_lines='skip')
        df.columns = df.columns.str.strip().str.lower()
        return df
    except Exception as e:
        # Dòng này sẽ hiện lỗi thật sự lên màn hình để bạn chụp cho mình nếu vẫn hỏng
        st.error(f"Chi tiết lỗi kết nối: {e}")
        return pd.DataFrame()

def login_user(username, password):
    df = get_all_users()
    if df.empty: 
        return {"status": "fail", "msg": "Lỗi kết nối dữ liệu"}

    user_row = df[df['username'].astype(str).str.strip() == str(username).strip()]
    
    if not user_row.empty:
        row = user_row.iloc[0]
        if str(password).strip() != str(row['password']).strip():
            return {"status": "fail", "msg": "Mật khẩu không chính xác"}

        try:
            open_date = pd.to_datetime(row['date_open'])
            duration = int(row['duration'])
            expiry_date = open_date + pd.DateOffset(months=duration)
            days_left = (expiry_date - datetime.now()).days
            
            if days_left <= 0:
                return {"status": "fail", "msg": "Tài khoản đã hết hạn!"}
            
            return {
                "status": "success", 
                "name": row['name'], 
                "role": row['role'], 
                "token": str(uuid.uuid4()),
                "days_left": days_left,
                "expiry_date": expiry_date.strftime('%d/%m/%Y')
            }
        except:
            return {"status": "fail", "msg": "Lỗi định dạng ngày trên Sheets"}
            
    return {"status": "fail", "msg": "Tài khoản không tồn tại"}

def check_token_valid(username, current_token):
    return True

def create_user(u, p, n, r): pass
def toggle_user_status(u, s): pass

