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
    exp_value = EXP_CONFIG.get(action_type, 0)
    if exp_value == 0:
        return
    
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO experience_logs (user_id, action_type, exp_value, description)
            VALUES (%s, %s, %s, %s)
        """, (user_id, action_type, exp_value, description))
        
        # 使用 IGNORE 确保即使user_profiles表不存在对应记录也不会报错
        cursor.execute("""
            UPDATE user_profiles 
            SET experience = experience + %s
            WHERE user_id = %s
        """, (exp_value, user_id))
        
        conn.commit()
    except Exception as e:
        print(f"[WARN] 添加经验值失败: {e}")
        conn.rollback()
    finally:
        cursor.close()
        conn.close()


@bp.route('/profile', methods=['GET'])
@token_required
# 出错了 我不知道后面的函数有没有错，但是这个报错了
def get_my_profile():
    """获取我的资料"""
    from flask import g
    from datetime import date, timedelta  # 明确导入
    
    user_id = g.user_id
    today = date.today()  # 使用 date 而不是 datetime.date
    
    conn = get_db_connection()
    cursor = conn.cursor(DictCursor)
    
    try:
        # 1. 查询用户资料（统一字段）
        cursor.execute("""
            SELECT p.*, u.username, u.is_admin
            FROM user_profiles p
            JOIN users u ON p.user_id = u.id
            WHERE p.user_id = %s
        """, (user_id,))
        profile = cursor.fetchone()
        
        # 2. 如果没有资料，创建默认资料
        if not profile:
            default_nickname = f"FlowerUser{user_id}"
            cursor.execute("""
                INSERT INTO user_profiles (user_id, nickname, created_at) 
                VALUES (%s, %s, NOW())
            """, (user_id, default_nickname))
            conn.commit()
            
            # 重新查询（字段要和第一次一致！）
            cursor.execute("""
                SELECT p.*, u.username, u.is_admin
                FROM user_profiles p
                JOIN users u ON p.user_id = u.id
                WHERE p.user_id = %s
            """, (user_id,))
            profile = cursor.fetchone()
        
        # 3. 处理登录状态和经验（确保 profile 存在）
        if profile:
            # 获取当前登录信息
            cursor.execute("""
                SELECT last_login_date, login_streak 
                FROM user_profiles 
                WHERE user_id = %s
            """, (user_id,))
            login_info = cursor.fetchone()
            
            if login_info:
                last_login = login_info.get('last_login_date')
                current_streak = login_info.get('login_streak', 0) or 0
                
                # 确保 last_login 是 date 类型
                if last_login and hasattr(last_login, 'date'):
                    last_login = last_login.date()
                
                # 计算新的连续登录天数
                if last_login == today - timedelta(days=1):
                    new_streak = current_streak + 1
                elif last_login == today:
                    new_streak = current_streak  # 今天已经登录过
                else:
                    new_streak = 1  # 断签了，重新计算
                
                # 更新登录信息
                cursor.execute("""
                    UPDATE user_profiles 
                    SET login_streak = %s, last_login_date = %s
                    WHERE user_id = %s
                """, (new_streak, today, user_id))
                conn.commit()
                
                # 只有今天第一次登录才加经验
                if last_login != today:
                    add_experience(user_id, 'login', '每日登录')
        
        return jsonify({
            'success': True,
            'data': {'profile': profile}
        })
        
    except Exception as e:
        import traceback
        print(f"Error in get_my_profile: {str(e)}")
        print(traceback.format_exc())  # 打印完整堆栈到控制台
        return jsonify({'success': False, 'error': str(e)}), 500
        
    finally:
        cursor.close()
        conn.close()


@bp.route('/profile', methods=['PUT'])
@token_required
def update_profile():
    """更新个人资料 - 只更新user_profiles表，username保持不变"""
    from flask import g
    user_id = g.user_id
    data = request.get_json()
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # 检查记录是否存在
        cursor.execute("SELECT user_id FROM user_profiles WHERE user_id = %s", (user_id,))
        if not cursor.fetchone():
            # 如果记录不存在，先创建（nickname默认值为FlowerUser开头）
            default_nickname = f"FlowerUser{user_id}"
            cursor.execute("""
                INSERT INTO user_profiles (user_id, nickname, created_at)
                VALUES (%s, %s, NOW())
            """, (user_id, default_nickname))
        
        # 更新 user_profiles 表（不涉及users表）
        profile_updates = []
        profile_params = []
        
        for field in ['nickname', 'bio', 'gender', 'birthday', 'location', 'garden_visibility']:
            if field in data and data[field] is not None:
                profile_updates.append(f"{field} = %s")
                profile_params.append(data[field])
        
        if not profile_updates:
            return jsonify({'success': False, 'error': '没有要更新的字段'}), 400
        
        profile_params.append(user_id)
        cursor.execute(f"""
            UPDATE user_profiles SET {', '.join(profile_updates)} WHERE user_id = %s
        """, profile_params)
        
        conn.commit()
        
        return jsonify({'success': True, 'message': '资料更新成功'})
    except Exception as e:
        import traceback
        print(f"更新资料失败: {str(e)}")
        print(traceback.format_exc())
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
    
    # 先获取旧头像路径，稍后删除
    old_avatar_url = None
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT avatar_url FROM user_profiles WHERE user_id = %s", (user_id,))
        result = cursor.fetchone()
        if result:
            old_avatar_url = result[0]
    except:
        pass
    cursor.close()
    conn.close()
    
    # 生成新文件名（只保留最新头像）
    filename = f"{user_id}_{uuid.uuid4().hex[:8]}{ext}"
    filepath = os.path.join(AVATAR_DIR, filename)
    file.save(filepath)
    
    avatar_url = f"/static/avatars/{filename}"
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # 同时更新 users 和 user_profiles 两个表
        cursor.execute("""
            UPDATE user_profiles SET avatar_url = %s WHERE user_id = %s
        """, (avatar_url, user_id))
        cursor.execute("""
            UPDATE users SET avatar_url = %s WHERE id = %s
        """, (avatar_url, user_id))
        conn.commit()
        
        # 删除旧头像文件（如果存在且不是默认头像）
        if old_avatar_url and old_avatar_url.startswith('/static/avatars/'):
            old_filepath = os.path.join(os.path.dirname(os.path.dirname(__file__)), old_avatar_url.lstrip('/'))
            if os.path.exists(old_filepath):
                try:
                    os.remove(old_filepath)
                except Exception as e:
                    print(f"删除旧头像失败: {e}")
        
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


# ============== 通知功能 ==============

def init_notifications_table():
    """初始化通知表"""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        # 检查表是否存在
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_notifications (
                id INT AUTO_INCREMENT PRIMARY KEY,
                user_id VARCHAR(8) NOT NULL COMMENT '接收通知的用户ID',
                actor_id VARCHAR(8) COMMENT '触发通知的用户ID',
                actor_name VARCHAR(50) COMMENT '触发通知的用户名',
                actor_avatar VARCHAR(500) COMMENT '触发通知的用户头像',
                notification_type VARCHAR(20) DEFAULT 'system' COMMENT '通知类型: like/favorite/comment/follow/system',
                target_type VARCHAR(50) COMMENT '通知对象类型 post/comment/user',
                target_id INT COMMENT '通知对象ID',
                target_content TEXT COMMENT '通知对象内容摘要',
                is_read TINYINT(1) DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                INDEX idx_user_id (user_id),
                INDEX idx_is_read (is_read),
                INDEX idx_created_at (created_at)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='用户通知表'
        """)
        conn.commit()
        
        # 检查并更新 notification_type 字段类型（如果需要）
        try:
            cursor.execute("""
                ALTER TABLE user_notifications 
                MODIFY COLUMN notification_type VARCHAR(20) DEFAULT 'system'
                COMMENT '通知类型: like/favorite/comment/follow/system'
            """)
            conn.commit()
        except Exception as e:
            print(f"[INFO] 通知表字段更新: {e}")
        
        print("[INFO] 通知表初始化完成")
        return True
    except Exception as e:
        print(f"[ERROR] 通知表初始化失败: {e}")
        conn.rollback()
        return False
    finally:
        cursor.close()
        conn.close()

# 模块加载时初始化表
try:
    init_notifications_table()
except:
    pass


def create_notification(user_id, actor_id, actor_name, actor_avatar, notification_type, 
                       target_type=None, target_id=None, target_content=None):
    """创建通知"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO user_notifications 
            (user_id, actor_id, actor_name, actor_avatar, notification_type, 
             target_type, target_id, target_content)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """, (user_id, actor_id, actor_name, actor_avatar, notification_type,
              target_type, target_id, target_content))
        conn.commit()
        cursor.close()
        conn.close()
        return True
    except Exception as e:
        print(f"[ERROR] 创建通知失败: {e}")
        return False


@bp.route('/notifications', methods=['GET'])
@token_required
def get_notifications():
    """获取通知列表"""
    from flask import g
    user_id = g.user_id
    
    page = request.args.get('page', 1, type=int)
    page_size = request.args.get('page_size', 20, type=int)
    unread_only = request.args.get('unread_only', 'false').lower() == 'true'
    
    conn = get_db_connection()
    cursor = conn.cursor(DictCursor)
    
    try:
        # 构建查询条件
        where_clause = "WHERE user_id = %s"
        params = [user_id]
        
        if unread_only:
            where_clause += " AND is_read = 0"
        
        # 获取通知列表
        cursor.execute(f"""
            SELECT id, actor_id, actor_name, actor_avatar, notification_type,
                   target_type, target_id, target_content, is_read, created_at
            FROM user_notifications
            {where_clause}
            ORDER BY created_at DESC
            LIMIT %s OFFSET %s
        """, params + [page_size, (page - 1) * page_size])
        notifications = cursor.fetchall()
        
        # 获取未读数量
        cursor.execute("SELECT COUNT(*) as count FROM user_notifications WHERE user_id = %s AND is_read = 0", (user_id,))
        unread_count = cursor.fetchone()['count']
        
        # 转换通知类型为显示文本
        type_text_map = {
            'like': '点赞了你的帖子',
            'favorite': '收藏了你的帖子',
            'comment': '评论了你的帖子',
            'follow': '关注了你',
            'system': '系统通知'
        }
        for n in notifications:
            n['type_text'] = type_text_map.get(n['notification_type'], '有新通知')
        
        return jsonify({
            'success': True,
            'data': {
                'notifications': notifications,
                'unread_count': unread_count,
                'page': page,
                'page_size': page_size
            }
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        cursor.close()
        conn.close()


@bp.route('/notifications/<int:notification_id>/read', methods=['PUT'])
@token_required
def mark_notification_read(notification_id):
    """标记通知为已读"""
    from flask import g
    user_id = g.user_id
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute("""
            UPDATE user_notifications 
            SET is_read = 1 
            WHERE id = %s AND user_id = %s
        """, (notification_id, user_id))
        conn.commit()
        
        return jsonify({'success': True, 'message': '已标记为已读'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        cursor.close()
        conn.close()


@bp.route('/notifications/read-all', methods=['PUT'])
@token_required
def mark_all_notifications_read():
    """标记所有通知为已读"""
    from flask import g
    user_id = g.user_id
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute("""
            UPDATE user_notifications 
            SET is_read = 1 
            WHERE user_id = %s AND is_read = 0
        """, (user_id,))
        conn.commit()
        
        return jsonify({'success': True, 'message': '已全部标记为已读'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        cursor.close()
        conn.close()


@bp.route('/notifications/<int:notification_id>', methods=['DELETE'])
@token_required
def delete_notification(notification_id):
    """删除通知"""
    from flask import g
    user_id = g.user_id
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute("""
            DELETE FROM user_notifications 
            WHERE id = %s AND user_id = %s
        """, (notification_id, user_id))
        conn.commit()
        
        return jsonify({'success': True, 'message': '已删除'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        cursor.close()
        conn.close()


@bp.route('/notifications/unread-count', methods=['GET'])
@token_required
def get_unread_notification_count():
    """获取未读通知数量"""
    from flask import g
    user_id = g.user_id
    
    conn = get_db_connection()
    cursor = conn.cursor(DictCursor)
    
    try:
        cursor.execute("""
            SELECT COUNT(*) as count 
            FROM user_notifications 
            WHERE user_id = %s AND is_read = 0
        """, (user_id,))
        count = cursor.fetchone()['count']
        
        return jsonify({'success': True, 'unread_count': count})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        cursor.close()
        conn.close()
