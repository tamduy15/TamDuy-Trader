import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import uuid
import pandas as pd
from datetime import datetime

# Kết nối Google Sheets bằng Service Account
def get_sheet():
    # Thông tin này lấy từ mục Secrets trên Streamlit Cloud
    creds_info = st.secrets["gcp_service_account"]
    scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_info(creds_info, scopes=scope)
    client = gspread.authorize(creds)
    # Thay ID của bạn vào đây
    return client.open_by_key("1rLautBfQowqcAw9gq2VCfK3UyqUIglnOzZQLqVHhvNs").sheet1

def check_token_valid(username, current_token):
    try:
        sheet = get_sheet()
        records = sheet.get_all_records()
        for row in records:
            if str(row['username']) == str(username):
                # So sánh token trong session web với token thực tế trên Sheets
                return str(row['active_token']) == str(current_token)
    except:
        return False
    return False
