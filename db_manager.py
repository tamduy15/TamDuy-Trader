import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import uuid
import pandas as pd
from datetime import datetime

# Cấu hình quyền truy cập
scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=scope)
client = gspread.authorize(creds)
sheet = client.open_by_key("1rLautBfQowqcAw9gq2VCfK3UyqUIglnOzZQLqVHhvNs").sheet1

def login_user(username, password):
    data = sheet.get_all_records()
    df = pd.DataFrame(data)
    
    # Tìm dòng của user (Index trong gspread bắt đầu từ 2 vì hàng 1 là tiêu đề)
    for idx, row in enumerate(data):
        if str(row['username']) == str(username):
            if str(row['password']) == str(password):
                if str(row['status']).upper() != 'TRUE':
                    return {"status": "fail", "msg": "Tài khoản bị khóa"}
                
                # Tạo Token mới và GHI VÀO SHEETS (Cột E là cột 5)
                new_token = str(uuid.uuid4())
                sheet.update_cell(idx + 2, 5, new_token) 
                
                # Tính toán ngày hết hạn (giống code cũ)
                # ... (phần tính days_left giữ nguyên)
                
                return {
                    "status": "success", "name": row['name'], "role": row['role'],
                    "token": new_token, "days_left": days_left, "expiry_date": expiry
                }
    return {"status": "fail", "msg": "Sai tài khoản hoặc mật khẩu"}

def check_token_valid(username, current_token):
    # Kiểm tra xem Token hiện tại có khớp với Token trên Sheets không
    data = sheet.get_all_records()
    for row in data:
        if str(row['username']) == str(username):
            return str(row['active_token']) == str(current_token)
    return False
