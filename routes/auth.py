"""
用户认证路由 - 注册(login)、登录(register)、登出(logout)、找回密码(reset_password)
"""

import os
import time
# 规避KMP库重复加载导致的崩溃
os.environ['KMP_DUPLICATE_LIB_OK'] = 'TRUE'

from flask import Blueprint, request, jsonify, g
from functools import wraps

from models.user import (
    create_user_table,
    register_user,
    login_user,
    reset_password_by_phone,
    get_user_by_id,
    update_avatar,
    get_db_connection,
)

bp = Blueprint('auth', __name__, url_prefix='/api/auth')

# Token过期时间（7天）
TOKEN_EXPIRY_SECONDS = 7 * 24 * 60 * 60


def init_token_table():
    """初始化token存储表"""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_tokens (
                id INT AUTO_INCREMENT PRIMARY KEY,
                token VARCHAR(64) UNIQUE NOT NULL,
                user_id VARCHAR(8) NOT NULL,
                created_at BIGINT NOT NULL,
                expires_at BIGINT NOT NULL,
                INDEX idx_token (token),
                INDEX idx_user_id (user_id)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """)
        conn.commit()
        print("[INFO] Token表初始化完成")
    except Exception as e:
        print(f"[WARN] Token表初始化: {e}")
        conn.rollback()
    finally:
        cursor.close()
        conn.close()


def save_token(token, user_id):
    """保存token到数据库"""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        current_time = int(time.time())
        expires_at = current_time + TOKEN_EXPIRY_SECONDS
        cursor.execute("""
            INSERT INTO user_tokens (token, user_id, created_at, expires_at)
            VALUES (%s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE expires_at = %s
        """, (token, str(user_id), current_time, expires_at, expires_at))
        conn.commit()
        return True
    except Exception as e:
        print(f"[ERROR] 保存token失败: {e}")
        conn.rollback()
        return False
    finally:
        cursor.close()
        conn.close()


def get_user_id_by_token(token):
    """从数据库获取token对应的用户ID"""
    if not token:
        return None
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        current_time = int(time.time())
        cursor.execute("""
            SELECT user_id, expires_at FROM user_tokens
            WHERE token = %s AND expires_at > %s
        """, (token, current_time))
        result = cursor.fetchone()
        if result:
            return result[0]
        return None
    except Exception as e:
        print(f"[ERROR] 查询token失败: {e}")
        return None
    finally:
        cursor.close()
        conn.close()


def delete_token(token):
    """从数据库删除token"""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM user_tokens WHERE token = %s", (token,))
        conn.commit()
        return True
    except Exception as e:
        print(f"[ERROR] 删除token失败: {e}")
        conn.rollback()
        return False
    finally:
        cursor.close()
        conn.close()


def cleanup_expired_tokens():
    """清理过期的token"""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        current_time = int(time.time())
        cursor.execute("DELETE FROM user_tokens WHERE expires_at <= %s", (current_time,))
        deleted = cursor.rowcount
        if deleted > 0:
            print(f"[INFO] 清理了 {deleted} 个过期token")
        conn.commit()
    except Exception as e:
        print(f"[ERROR] 清理过期token失败: {e}")
        conn.rollback()
    finally:
        cursor.close()
        conn.close()


# 初始化token表
try:
    init_token_table()
except:
    pass


def token_required(f):
    """验证token的装饰器"""
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get('Authorization', '').replace('Bearer ', '')
        
        if not token:
            return jsonify({'success': False, 'message': '请先登录'}), 401
        
        # 从数据库获取token对应的用户
        user_id = get_user_id_by_token(token)
        if not user_id:
            return jsonify({'success': False, 'message': 'token已过期，请重新登录'}), 401
        
        user = get_user_by_id(user_id)
        if not user:
            return jsonify({'success': False, 'message': '用户不存在'}), 401
        
        g.user_id = user_id
        g.user = user
        return f(*args, **kwargs)
    
    return decorated


# 数据库初始化（在模块加载时执行）
try:
    from models.user import create_user_table
    print("[INFO] 初始化用户表...")
    create_user_table()
except Exception as e:
    print(f"[WARN] 用户表初始化: {e}")


@bp.route('/register', methods=['POST'])
def register():
    """用户注册"""
    data = request.get_json()
    
    if not data:
        return jsonify({'success': False, 'message': '请提供注册信息'})
    
    username = data.get('username', '').strip()
    password = data.get('password', '')
    phone = data.get('phone', '').strip()
    avatar_url = data.get('avatar_url')
    
    # 验证必填字段
    if not username:
        return jsonify({'success': False, 'message': '用户名不能为空'})
    
    if len(password) < 6:
        return jsonify({'success': False, 'message': '密码至少6位'})
    
    if not phone or len(phone) != 11:
        return jsonify({'success': False, 'message': '请输入11位手机号'})
    
    # 验证手机号格式
    if not phone.isdigit():
        return jsonify({'success': False, 'message': '手机号必须为数字'})
    
    result = register_user(username, password, phone, avatar_url)
    
    if result['success']:
        return jsonify(result), 201
    return jsonify(result), 400


@bp.route('/login', methods=['POST'])
def login():
    """用户登录"""
    data = request.get_json()
    
    if not data:
        return jsonify({'success': False, 'message': '请提供登录信息'})
    
    username = data.get('username', '').strip()
    password = data.get('password', '')
    
    if not username or not password:
        return jsonify({'success': False, 'message': '用户名和密码不能为空'})
    
    result = login_user(username, password)
    
    if result['success']:
        # 保存token到数据库
        save_token(result['token'], result['user']['id'])
        return jsonify(result)
    return jsonify(result), 401


@bp.route('/logout', methods=['POST'])
@token_required
def logout():
    """用户登出"""
    token = request.headers.get('Authorization', '').replace('Bearer ', '')
    
    # 从数据库删除token
    delete_token(token)
    
    return jsonify({'success': True, 'message': '登出成功'})


@bp.route('/reset-password', methods=['POST'])
def reset_password():
    """通过手机号重置密码"""
    data = request.get_json()
    
    if not data:
        return jsonify({'success': False, 'message': '请提供信息'})
    
    phone = data.get('phone', '').strip()
    new_password = data.get('new_password', '')
    
    if not phone or len(phone) != 11:
        return jsonify({'success': False, 'message': '请输入11位手机号'})
    
    if len(new_password) < 6:
        return jsonify({'success': False, 'message': '新密码至少6位'})
    
    result = reset_password_by_phone(phone, new_password)
    
    if result['success']:
        return jsonify(result)
    return jsonify(result), 400


@bp.route('/profile', methods=['GET'])
@token_required
def get_profile():
    """获取用户信息"""
    return jsonify({
        'success': True,
        'user': g.user
    })


@bp.route('/avatar', methods=['PUT'])
@token_required
def update_user_avatar():
    """更新头像"""
    data = request.get_json()
    avatar_url = data.get('avatar_url')
    
    if not avatar_url:
        return jsonify({'success': False, 'message': '请提供头像URL'})
    
    result = update_avatar(g.user_id, avatar_url)
    
    if result['success']:
        return jsonify({
            'success': True,
            'message': '头像更新成功',
            'avatar_url': avatar_url
        })
    return jsonify(result), 400


@bp.route('/avatar/upload', methods=['POST'])
@token_required
def upload_avatar():
    """上传用户头像"""
    import uuid
    
    if 'avatar' not in request.files:
        return jsonify({'success': False, 'message': '没有上传文件'}), 400
    
    file = request.files['avatar']
    if file.filename == '':
        return jsonify({'success': False, 'message': '没有选择文件'}), 400
    
    # 获取文件扩展名
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in ['.jpg', '.jpeg', '.png', '.gif', '.webp']:
        return jsonify({'success': False, 'message': '不支持的图片格式'}), 400
    
    # 头像上传目录
    avatar_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'static', 'avatars')
    os.makedirs(avatar_dir, exist_ok=True)
    
    # 生成唯一文件名
    filename = f"{g.user_id}_{uuid.uuid4().hex}{ext}"
    filepath = os.path.join(avatar_dir, filename)
    
    try:
        file.save(filepath)
        # 生成访问URL
        avatar_url = f"/static/avatars/{filename}"
        
        # 更新数据库
        from models.user import update_avatar
        result = update_avatar(g.user_id, avatar_url)
        
        if result['success']:
            return jsonify({
                'success': True,
                'message': '头像上传成功',
                'avatar_url': avatar_url
            })
        return jsonify({'success': False, 'message': '更新头像失败'}), 500
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@bp.route('/check-username', methods=['GET'])
def check_username():
    """检查用户名是否可用"""
    username = request.args.get('username', '').strip()
    
    from models.user import get_db_connection
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("SELECT id FROM users WHERE username = %s", (username,))
    exists = cursor.fetchone() is not None
    cursor.close()
    conn.close()
    
    return jsonify({
        'success': True,
        'available': not exists
    })


@bp.route('/check-phone', methods=['GET'])
def check_phone():
    """检查手机号是否已注册"""
    phone = request.args.get('phone', '').strip()
    
    from models.user import get_db_connection
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("SELECT id FROM users WHERE phone = %s", (phone,))
    exists = cursor.fetchone() is not None
    cursor.close()
    conn.close()
    
    return jsonify({
        'success': True,
        'registered': exists
    })
