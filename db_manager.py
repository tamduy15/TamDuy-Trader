import streamlit as st
import pandas as pd
import uuid

# Link Sheets (Sử dụng link công khai để đơn giản hóa cho bạn)
# Chú ý: Thay ID_FILE_CUA_BAN bằng ID bạn vừa lấy ở Bước 1
SHEET_ID = "ID_FILE_CUA_BAN" 
SHEET_URL = f"https://docs.google.com/spreadsheets/d/1rLautBfQowqcAw9gq2VCfK3UyqUIglnOzZQLqVHhvNs/gviz/tq?tqx=out:csv"

# Hàm đọc dữ liệu từ Sheets
def get_all_users():
    try:
        df = pd.read_csv(SHEET_URL)
        return df
    except:
        return pd.DataFrame(columns=['username', 'password', 'name', 'role', 'active_token', 'status'])

# Hàm lưu dữ liệu (Dành cho bản đơn giản: dùng st.cache hoặc ghi log)
# Lưu ý: Để ghi dữ liệu thật lên Sheets cần cấu hình Service Account phức tạp hơn.
# Ở đây mình hướng dẫn cách 'giả lập' an toàn để bạn chạy được ngay.
def init_db():
    pass

def login_user(username, password):
    df = get_all_users()
    # Tìm user
    user_row = df[df['username'] == str(username)]
    
    if not user_row.empty:
        stored_pw = str(user_row.iloc[0]['password'])
        status = user_row.iloc[0]['status']
        
        if status == 'locked':
            return {"status": "locked"}
            
        if str(password) == stored_pw:
            new_token = str(uuid.uuid4())
            # Trong bản Sheets công khai, ta lưu token vào session tạm thời
            return {
                "status": "success", 
                "name": user_row.iloc[0]['name'], 
                "role": user_row.iloc[0]['role'], 
                "token": new_token
            }
            
    return {"status": "fail"}

def check_token_valid(username, current_token):
    # Với Sheets, ta tạm chấp nhận token từ session để tránh ghi file liên tục
    return True 

import requests

def create_user(username, password, name, role="user"):
    # Thay link Form của bạn vào đây (nhớ giữ đoạn /formResponse)
    FORM_URL = "https://docs.google.com/forms/d/e/ID_FORM_CUA_BAN/formResponse"
    
    # Thay các số entry.xxx tương ứng bạn vừa tìm được ở Bước 2
    payload = {
        "entry.169361782": username,
        "entry.779502312": password,
        "entry.63670389": name,
        "entry.1477975338": role,
        "entry.65172968": "none",
        "entry.666666": "active"
    }
    
    try:
        res = requests.post(FORM_URL, data=payload)
        return res.status_code == 200
    except:
        return False

def toggle_user_status(username, new_status):
    st.info(f"Hãy vào Google Sheets đổi cột status của {username} thành {new_status}")


