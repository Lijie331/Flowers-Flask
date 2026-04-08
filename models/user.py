"""
用户模块 - 用户注册、登录、找回密码
"""

import os
os.environ['KMP_DUPLICATE_LIB_OK'] = 'TRUE'

import hashlib
import secrets
import pymysql
from pymysql.cursors import DictCursor

try:
    from config import DB_CONFIG
except ImportError:
    DB_CONFIG = {
        'host': 'localhost',
        'port': 3306,
        'user': 'root',
        'password': '314331',
        'database': 'tlj',
        'charset': 'utf8mb4'
    }

SALT_LENGTH = 32


def get_db_connection():
    """获取数据库连接"""
    return pymysql.connect(**DB_CONFIG)


def generate_salt():
    """生成随机盐"""
    return secrets.token_hex(SALT_LENGTH)


def hash_password(password: str, salt: str) -> str:
    """使用SHA256加盐加密密码"""
    combined = salt + password
    return hashlib.sha256(combined.encode()).hexdigest()


def verify_password(password: str, salt: str, hashed: str) -> bool:
    """验证密码"""
    return hash_password(password, salt) == hashed


def generate_user_id() -> str:
    """生成唯一用户ID"""
    return secrets.token_hex(4).upper()


def create_user_table():
    """创建用户表"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    sql = """
    CREATE TABLE IF NOT EXISTS users (
        id VARCHAR(8) PRIMARY KEY COMMENT '用户ID',
        username VARCHAR(50) NOT NULL COMMENT '用户名',
        password_salt VARCHAR(64) NOT NULL COMMENT '密码盐',
        password_hash VARCHAR(64) NOT NULL COMMENT '密码哈希',
        phone VARCHAR(11) UNIQUE COMMENT '手机号',
        phone_encrypted TEXT COMMENT '加密手机号',
        avatar_url VARCHAR(500) DEFAULT NULL COMMENT '头像URL',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
        last_login TIMESTAMP NULL COMMENT '最后登录时间',
        is_active TINYINT(1) DEFAULT 1 COMMENT '是否激活',
        is_admin TINYINT(1) DEFAULT 0 COMMENT '是否管理员',
        INDEX idx_phone (phone(11)),
        INDEX idx_username (username)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='用户表'
    """
    
    try:
        cursor.execute(sql)
        conn.commit()
        print("[INFO] 用户表创建成功")
        return True
    except Exception as e:
        print(f"[ERROR] 创建用户表失败: {e}")
        return False
    finally:
        cursor.close()
        conn.close()


def encrypt_phone(phone: str) -> str:
    """加密手机号"""
    import base64
    return base64.b64encode(phone.encode()).decode()


def decrypt_phone(encrypted: str) -> str:
    """解密手机号"""
    import base64
    return base64.b64decode(encrypted.encode()).decode()


def register_user(username: str, password: str, phone: str, avatar_url: str = None) -> dict:
    """注册新用户"""
    conn = get_db_connection()
    cursor = conn.cursor(DictCursor)
    
    try:
        cursor.execute("SELECT id FROM users WHERE username = %s", (username,))
        if cursor.fetchone():
            return {'success': False, 'message': '用户名已存在'}
        
        cursor.execute("SELECT id FROM users WHERE phone = %s", (phone,))
        if cursor.fetchone():
            return {'success': False, 'message': '手机号已被注册'}
        
        user_id = generate_user_id()
        
        while True:
            cursor.execute("SELECT id FROM users WHERE id = %s", (user_id,))
            if not cursor.fetchone():
                break
            user_id = generate_user_id()
        
        salt = generate_salt()
        password_hash = hash_password(password, salt)
        phone_encrypted = encrypt_phone(phone)
        
        sql = """
        INSERT INTO users (id, username, password_salt, password_hash, phone, phone_encrypted, avatar_url)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        """
        cursor.execute(sql, (user_id, username, salt, password_hash, phone, phone_encrypted, avatar_url))
        conn.commit()
        
        return {
            'success': True,
            'message': '注册成功',
            'user': {
                'id': user_id,
                'username': username,
                'phone': phone[-4:].rjust(11, '*'),
                'avatar_url': avatar_url
            }
        }
        
    except Exception as e:
        conn.rollback()
        return {'success': False, 'message': f'注册失败: {str(e)}'}
    finally:
        cursor.close()
        conn.close()


def login_user(username: str, password: str) -> dict:
    """用户登录"""
    conn = get_db_connection()
    cursor = conn.cursor(DictCursor)
    
    try:
        cursor.execute("""
            SELECT id, username, password_salt, password_hash, phone, avatar_url, is_active, is_admin
            FROM users WHERE username = %s
        """, (username,))
        user = cursor.fetchone()
        
        if not user:
            return {'success': False, 'message': '用户名或密码错误'}
        
        if not user['is_active']:
            return {'success': False, 'message': '账号已被禁用'}
        
        if not verify_password(password, user['password_salt'], user['password_hash']):
            return {'success': False, 'message': '用户名或密码错误'}
        
        cursor.execute("UPDATE users SET last_login = NOW() WHERE id = %s", (user['id'],))
        conn.commit()
        
        import time
        token = hashlib.sha256(f"{user['id']}{user['username']}{time.time()}".encode()).hexdigest()
        
        phone_display = user['phone'][-4:].rjust(11, '*') if user['phone'] else None
        
        return {
            'success': True,
            'message': '登录成功',
            'token': token,
'user': {
                'id': user['id'],
                'username': user['username'],
                'phone': phone_display,
                'avatar_url': user['avatar_url'],
                'is_admin': user['is_admin']
            }
        }
        
    except Exception as e:
        return {'success': False, 'message': f'登录失败: {str(e)}'}
    finally:
        cursor.close()
        conn.close()


def reset_password_by_phone(phone: str, new_password: str) -> dict:
    """通过手机号重置密码"""
    conn = get_db_connection()
    cursor = conn.cursor(DictCursor)
    
    try:
        cursor.execute("SELECT id FROM users WHERE phone = %s", (phone,))
        user = cursor.fetchone()
        
        if not user:
            return {'success': False, 'message': '该手机号未注册'}
        
        salt = generate_salt()
        password_hash = hash_password(new_password, salt)
        
        cursor.execute("""
            UPDATE users SET password_salt = %s, password_hash = %s WHERE id = %s
        """, (salt, password_hash, user['id']))
        conn.commit()
        
        return {'success': True, 'message': '密码重置成功'}
        
    except Exception as e:
        conn.rollback()
        return {'success': False, 'message': f'密码重置失败: {str(e)}'}
    finally:
        cursor.close()
        conn.close()


def get_user_by_id(user_id: str) -> dict:
    """根据ID获取用户信息"""
    conn = get_db_connection()
    cursor = conn.cursor(DictCursor)
    
    try:
        cursor.execute("""
            SELECT id, username, phone, avatar_url, created_at, last_login, is_admin
            FROM users WHERE id = %s AND is_active = 1
        """, (user_id,))
        user = cursor.fetchone()
        
        if not user:
            return None
        
        if user['phone']:
            user['phone'] = user['phone'][:3] + '****' + user['phone'][-4:]
        
        return user
    finally:
        cursor.close()
        conn.close()


def update_avatar(user_id: str, avatar_url: str) -> dict:
    """更新用户头像"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute("UPDATE users SET avatar_url = %s WHERE id = %s", (avatar_url, user_id))
        conn.commit()
        return {'success': True, 'message': '头像更新成功'}
    except Exception as e:
        return {'success': False, 'message': str(e)}
    finally:
        cursor.close()
        conn.close()


if __name__ == '__main__':
    print("初始化用户表...")
    create_user_table()
