import streamlit as st
import gspread
from google.oauth2.service_account import Credentials

def get_sheet():
    # Streamlit sẽ tự động đọc mục [gcp_service_account] trong Secrets
    creds_info = st.secrets["gcp_service_account"]
    
    scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_info(creds_info, scopes=scope)
    client = gspread.authorize(creds)
    
    # Mở Sheets bằng ID
    return client.open_by_key("1rLautBfQowqcAw9gq2VCfK3UyqUIglnOzZQLqVHhvNs").sheet1
