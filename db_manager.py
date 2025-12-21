import sqlite3
import bcrypt
import uuid
import pandas as pd

# 1. Khởi tạo Database (Thêm cột status)
def init_db():
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    # status: 'active' hoặc 'locked'
    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            username TEXT PRIMARY KEY,
            password TEXT NOT NULL,
            name TEXT,
            role TEXT,
            active_token TEXT,
            status TEXT DEFAULT 'active'
        )
    ''')
    conn.commit()
    conn.close()

# 2. Tạo User (Mặc định là active)
def create_user(username, password, name, role="user"):
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    hashed_pw = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())
    try:
        c.execute('INSERT INTO users (username, password, name, role, active_token, status) VALUES (?, ?, ?, ?, ?, ?)', 
                  (username, hashed_pw, name, role, "new", "active"))
        conn.commit()
        return True
    except:
        return False
    finally:
        conn.close()

# 3. Đăng nhập (Kiểm tra xem có bị KHOÁ không)
def login_user(username, password):
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute('SELECT password, name, role, status FROM users WHERE username = ?', (username,))
    data = c.fetchone()
    conn.close()
    
    if data:
        stored_pw, name, role, status = data
        
        # KIỂM TRA TRẠNG THÁI KHOÁ
        if status == 'locked':
            return {"status": "locked"}
            
        if bcrypt.checkpw(password.encode('utf-8'), stored_pw):
            new_token = str(uuid.uuid4())
            conn = sqlite3.connect('users.db')
            c = conn.cursor()
            c.execute('UPDATE users SET active_token = ? WHERE username = ?', (new_token, username))
            conn.commit()
            conn.close()
            return {"status": "success", "name": name, "role": role, "token": new_token}
            
    return {"status": "fail"}

# 4. Kiểm tra Token
def check_token_valid(username, current_token):
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute('SELECT active_token, status FROM users WHERE username = ?', (username,))
    result = c.fetchone()
    conn.close()
    
    if result:
        token_db, status = result
        if status == 'locked': return False # Bị khoá thì đá văng luôn
        if token_db == current_token: return True
    return False

# 5. ADMIN: Lấy danh sách user
def get_all_users():
    conn = sqlite3.connect('users.db')
    df = pd.read_sql_query("SELECT username, name, role, status FROM users", conn)
    conn.close()
    return df

# 6. ADMIN: Khoá/Mở khoá
def toggle_user_status(username, new_status):
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute('UPDATE users SET status = ? WHERE username = ?', (new_status, username))
    conn.commit()
    conn.close()