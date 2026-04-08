"""
用户资料路由模块 - 个人资料、成长体系、认证
"""

import os
import uuid
import datetime
from flask import Blueprint, request, jsonify
import pymysql
from pymysql.cursors import DictCursor

from config import DB_CONFIG
from routes.auth import token_required

bp = Blueprint('user', __name__, url_prefix='/api/user')

# 头像上传目录
AVATAR_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'static', 'avatars')
os.makedirs(AVATAR_DIR, exist_ok=True)

# 经验值配置
EXP_CONFIG = {
    'post': 10,
    'comment': 2,
    'like': 1,
    'identify': 3,
    'login': 5,
    'streak': 10,
}


def get_db_connection():
    return pymysql.connect(**DB_CONFIG)


def add_experience(user_id, action_type, description=''):
    """添加经验值"""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        exp_value = EXP_CONFIG.get(action_type, 0)
        if exp_value == 0:
            return
        
        cursor.execute("""
            INSERT INTO experience_logs (user_id, action_type, exp_value, description)
            VALUES (%s, %s, %s, %s)
        """, (user_id, action_type, exp_value, description))
        
        cursor.execute("""
            UPDATE user_profiles 
            SET experience = experience + %s
            WHERE user_id = %s
        """, (exp_value, user_id))
        
        conn.commit()
    except Exception:
        conn.rollback()
    finally:
        cursor.close()
        conn.close()


@bp.route('/profile', methods=['GET'])
@token_required
def get_my_profile():
    """获取我的资料"""
    from flask import g
    user_id = g.user_id
    
    conn = get_db_connection()
    cursor = conn.cursor(DictCursor)
    
    try:
        cursor.execute("""
            SELECT p.*, u.username, u.email, u.is_admin
            FROM user_profiles p
            JOIN users u ON p.user_id = u.id
            WHERE p.user_id = %s
        """, (user_id,))
        profile = cursor.fetchone()
        
        if not profile:
            cursor.execute("""
                INSERT INTO user_profiles (user_id, nickname) VALUES (%s, %s)
            """, (user_id, f"FlowerUser{user_id}"))
            conn.commit()
            
            cursor.execute("""
                SELECT p.*, u.username, u.email, u.is_admin
                FROM user_profiles p
                JOIN users u ON p.user_id = u.id
                WHERE p.user_id = %s
            """, (user_id,))
            profile = cursor.fetchone()
        
        # 更新登录状态和经验
        today = datetime.date.today()
        cursor.execute("""
            SELECT last_login_date, login_streak FROM user_profiles WHERE user_id = %s
        """, (user_id,))
        login_info = cursor.fetchone()
        
        if login_info:
            last_login = login_info['last_login_date']
            if last_login:
                if last_login == today - datetime.timedelta(days=1):
                    new_streak = login_info['login_streak'] + 1
                    cursor.execute("""
                        UPDATE user_profiles SET login_streak = %s, last_login_date = %s
                        WHERE user_id = %s
                    """, (new_streak, today, user_id))
                elif last_login != today:
                    cursor.execute("""
                        UPDATE user_profiles SET login_streak = 1, last_login_date = %s
                        WHERE user_id = %s
                    """, (today, user_id))
            else:
                cursor.execute("""
                    UPDATE user_profiles SET login_streak = 1, last_login_date = %s
WHERE user_id = %s
                """, (today, user_id))
            
            conn.commit()
            add_experience(user_id, 'login', '每日登录')
        
        return jsonify({
            'success': True,
            'data': {'profile': profile}
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        cursor.close()
        conn.close()


@bp.route('/profile', methods=['PUT'])
@token_required
def update_profile():
    """更新个人资料"""
    from flask import g
    user_id = g.user_id
    data = request.get_json()
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        updates = []
        params = []
        
        for field in ['nickname', 'bio', 'gender', 'birthday', 'location', 'garden_visibility']:
            if field in data:
                updates.append(f"{field} = %s")
                params.append(data[field])
        
        if not updates:
            return jsonify({'success': False, 'error': '没有要更新的字段'}), 400
        
        params.append(user_id)
        cursor.execute(f"""
            UPDATE user_profiles SET {', '.join(updates)} WHERE user_id = %s
        """, params)
        conn.commit()
        
        return jsonify({'success': True, 'message': '资料更新成功'})
    except Exception as e:
        conn.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        cursor.close()
        conn.close()


@bp.route('/avatar', methods=['POST'])
@token_required
def upload_avatar():
    """上传头像"""
    from flask import g
    user_id = g.user_id
    
    if 'avatar' not in request.files:
        return jsonify({'success': False, 'error': '没有上传文件'}), 400
    
    file = request.files['avatar']
    if not file.filename:
        return jsonify({'success': False, 'error': '没有选择文件'}), 400
    
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in ['.jpg', '.jpeg', '.png', '.gif', '.webp']:
        ext = '.jpg'
    
    filename = f"{user_id}_{uuid.uuid4().hex[:8]}{ext}"
    filepath = os.path.join(AVATAR_DIR, filename)
    file.save(filepath)
    
    avatar_url = f"/static/avatars/{filename}"
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute("""
            UPDATE user_profiles SET avatar_url = %s WHERE user_id = %s
        """, (avatar_url, user_id))
        conn.commit()
        
        return jsonify({
            'success': True,
            'message': '头像上传成功',
            'avatar_url': avatar_url
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        cursor.close()
        conn.close()


@bp.route('/profile/<target_id>', methods=['GET'])
@token_required
def get_user_profile(target_id):
    """查看其他用户资料"""
    from flask import g
    user_id = g.user_id
    
    conn = get_db_connection()
    cursor = conn.cursor(DictCursor)
    
    try:
        cursor.execute("""
            SELECT id FROM user_blacklist 
            WHERE user_id = %s AND blocked_user_id = %s
        """, (target_id, user_id))
        if cursor.fetchone():
            return jsonify({'success': False, 'error': '无法查看该用户'}), 403
        
        cursor.execute("""
            SELECT p.user_id, p.nickname, p.avatar_url, p.bio, p.level, p.title,
                   p.followers_count, p.following_count, p.posts_count,
                   (SELECT COUNT(*) FROM user_follows WHERE follower_id = %s AND following_id = p.user_id) as is_following
            FROM user_profiles p
            WHERE p.user_id = %s
        """, (user_id, target_id))
        profile = cursor.fetchone()
        
        if not profile:
            return jsonify({'success': False, 'error': '用户不存在'}), 404
        
        return jsonify({
            'success': True,
            'data': {'profile': profile}
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        cursor.close()
        conn.close()


@bp.route('/follow/<target_id>', methods=['POST'])
@token_required
def toggle_follow(target_id):
    """关注/取消关注"""
    from flask import g
    user_id = g.user_id
    
    if user_id == target_id:
        return jsonify({'success': False, 'error': '不能关注自己'}), 400
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute("""
            SELECT id FROM user_follows WHERE follower_id = %s AND following_id = %s
        """, (user_id, target_id))
        
        if cursor.fetchone():
            cursor.execute("DELETE FROM user_follows WHERE follower_id = %s AND following_id = %s", (user_id, target_id))
            cursor.execute("UPDATE user_profiles SET following_count = following_count - 1 WHERE user_id = %s", (user_id,))
            cursor.execute("UPDATE user_profiles SET followers_count = followers_count - 1 WHERE user_id = %s", (target_id,))
            conn.commit()
            return jsonify({'success': True, 'following': False, 'message': '已取消关注'})
        else:
            cursor.execute("INSERT INTO user_follows (follower_id, following_id) VALUES (%s, %s)", (user_id, target_id))
            cursor.execute("UPDATE user_profiles SET following_count = following_count + 1 WHERE user_id = %s", (user_id,))
            cursor.execute("UPDATE user_profiles SET followers_count = followers_count + 1 WHERE user_id = %s", (target_id,))
            conn.commit()
            return jsonify({'success': True, 'following': True, 'message': '已关注'})
    except Exception as e:
        conn.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        cursor.close()
        conn.close()


@bp.route('/levels', methods=['GET'])
def get_levels():
    """获取等级信息"""
    conn = get_db_connection()
    cursor = conn.cursor(DictCursor)
    
    try:
        cursor.execute("""
            SELECT level, min_experience, max_experience, title, icon
            FROM experience_levels ORDER BY level ASC
        """)
        levels = cursor.fetchall()
        
        return jsonify({
            'success': True,
            'data': {'levels': levels}
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        cursor.close()
        conn.close()


@bp.route('/experience/logs', methods=['GET'])
@token_required
def get_experience_logs():
    """获取经验值记录"""
    from flask import g
    user_id = g.user_id
    
    page = request.args.get('page', 1, type=int)
    page_size = request.args.get('page_size', 20, type=int)
    
    conn = get_db_connection()
    cursor = conn.cursor(DictCursor)
    
    try:
        cursor.execute("""
            SELECT action_type, exp_value, description, created_at
            FROM experience_logs
            WHERE user_id = %s
            ORDER BY created_at DESC
            LIMIT %s OFFSET %s
        """, (user_id, page_size, (page - 1) * page_size))
        logs = cursor.fetchall()
        
        cursor.execute("SELECT COUNT(*) as total FROM experience_logs WHERE user_id = %s", (user_id,))
        total = cursor.fetchone()['total']
        
        return jsonify({
            'success': True,
            'data': {
                'logs': logs,
                'total': total,
                'page': page,
                'page_size': page_size
            }
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        cursor.close()
        conn.close()
