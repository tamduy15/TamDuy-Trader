import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import uuid
import pandas as pd
from datetime import datetime

# Cấu hình quyền truy cập
def get_sheet():
    # Đọc thông tin từ mục [gcp_service_account] trong Secrets
    creds_info = st.secrets["gcp_service_account"]
    scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_info(creds_info, scopes=scope)
    client = gspread.authorize(creds)
    # ID file Sheets của bạn
    return client.open_by_key("1rLautBfQowqcAw9gq2VCfK3UyqUIglnOzZQLqVHhvNs").sheet1

def init_db():
    """Hàm khởi tạo để tránh lỗi AttributeError trong app.py"""
    pass

def login_user(username, password):
    try:
        sheet = get_sheet()
        data = sheet.get_all_records()
        
        for idx, row in enumerate(data):
            if str(row['username']).strip() == str(username).strip():
                if str(row['password']).strip() == str(password).strip():
                    if str(row['status']).upper() != 'TRUE':
                        return {"status": "fail", "msg": "Tài khoản đang bị khóa"}
                    
                    # 1. Kiểm tra thời hạn
                    open_date = pd.to_datetime(row['date_open'])
                    duration = int(row['duration'])
                    expiry_date = open_date + pd.DateOffset(months=duration)
                    days_left = (expiry_date - datetime.now()).days
                    
                    if days_left <= 0:
                        return {"status": "fail", "msg": "Tài khoản đã hết hạn"}

                    # 2. Tạo Token mới và GHI LÊN SHEETS (Cột E là cột số 5)
                    # idx + 2 vì: hàng 1 là tiêu đề, index mảng bắt đầu từ 0
                    new_token = str(uuid.uuid4())
                    sheet.update_cell(idx + 2, 5, new_token)
                    
                    return {
                        "status": "success", 
                        "name": row['name'], 
                        "role": row['role'], 
                        "token": new_token,
                        "days_left": days_left,
                        "expiry_date": expiry_date.strftime('%d/%m/%Y')
                    }
        return {"status": "fail", "msg": "Sai tài khoản hoặc mật khẩu"}
    except Exception as e:
        return {"status": "fail", "msg": f"Lỗi kết nối: {str(e)}"}

def check_token_valid(username, current_token):
    try:
        sheet = get_sheet()
        data = sheet.get_all_records()
        for row in data:
            if str(row['username']) == str(username):
                # Nếu token trên Sheet khác token máy đang dùng -> Bị đá ra
                return str(row['active_token']) == str(current_token)
    except:
        return False
    return False

# Các hàm giả lập để tương thích với app.py cũ
def create_user(u, p, n, r): pass
def toggle_user_status(u, s): pass
def get_all_users(): 
    sheet = get_sheet()
    return pd.DataFrame(sheet.get_all_records())
