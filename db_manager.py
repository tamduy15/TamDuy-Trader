import streamlit as st
import psycopg2
import bcrypt
import uuid
import pandas as pd

# Hàm kết nối Database (Lấy link từ Secrets)
def get_connection():
    try:
        # Lấy đường dẫn kết nối từ cấu hình bảo mật
        db_url = st.secrets["DB_URL"]
        conn = psycopg2.connect(db_url)
        return conn
    except Exception as e:
        st.error(f"Lỗi kết nối Database: {e}")
        return None

# 1. Khởi tạo DB (Chỉ để tương thích, thực ra đã tạo trên Supabase rồi)
def init_db():
    pass 

# 2. Tạo User Mới
def create_user(username, password, name, role="user"):
    conn = get_connection()
    if not conn: return False
    cur = conn.cursor()
    hashed_pw = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8') # Decode để lưu dạng string
    
    try:
        cur.execute(
            "INSERT INTO users (username, password, name, role, active_token, status) VALUES (%s, %s, %s, %s, %s, %s)",
            (username, hashed_pw, name, role, "new", "active")
        )
        conn.commit()
        return True
    except:
        return False
    finally:
        cur.close()
        conn.close()

# 3. Đăng nhập
def login_user(username, password):
    conn = get_connection()
    if not conn: return {"status": "fail"}
    cur = conn.cursor()
    
    cur.execute("SELECT password, name, role, status FROM users WHERE username = %s", (username,))
    data = cur.fetchone()
    
    if data:
        stored_pw, name, role, status = data
        
        if status == 'locked':
            cur.close(); conn.close()
            return {"status": "locked"}
            
        # Kiểm tra pass (Encode lại pass nhập vào để so sánh với hash trong DB)
        if bcrypt.checkpw(password.encode('utf-8'), stored_pw.encode('utf-8')):
            new_token = str(uuid.uuid4())
            cur.execute("UPDATE users SET active_token = %s WHERE username = %s", (new_token, username))
            conn.commit()
            cur.close(); conn.close()
            return {"status": "success", "name": name, "role": role, "token": new_token}
            
    cur.close(); conn.close()
    return {"status": "fail"}

# 4. Kiểm tra Token (Check phiên làm việc)
def check_token_valid(username, current_token):
    conn = get_connection()
    if not conn: return False
    cur = conn.cursor()
    
    cur.execute("SELECT active_token, status FROM users WHERE username = %s", (username,))
    result = cur.fetchone()
    cur.close(); conn.close()
    
    if result:
        token_db, status = result
        if status == 'locked': return False
        if token_db == current_token: return True
    return False

# 5. ADMIN: Lấy danh sách user
def get_all_users():
    conn = get_connection()
    if not conn: return pd.DataFrame()
    
    # Dùng pandas đọc SQL trực tiếp
    df = pd.read_sql("SELECT username, name, role, status FROM users", conn)
    conn.close()
    return df

# 6. ADMIN: Khoá/Mở khoá
def toggle_user_status(username, new_status):
    conn = get_connection()
    if not conn: return
    cur = conn.cursor()
    cur.execute("UPDATE users SET status = %s WHERE username = %s", (new_status, username))
    conn.commit()
    cur.close()
    conn.close()
