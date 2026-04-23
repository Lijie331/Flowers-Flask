"""
社区路由模块 - 收藏、花园、养护提醒、花友圈
"""

import os
import json
import uuid
from flask import Blueprint, request, jsonify, current_app
import pymysql
from pymysql.cursors import DictCursor
from datetime import datetime
from config import DB_CONFIG
from routes.auth import token_required

bp = Blueprint('community', __name__, url_prefix='/api/community')

# 导入经验值函数
from routes.user import add_experience

# 图片上传目录
GARDEN_PHOTOS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'static', 'garden_photos')

# 帖子图片和视频上传目录
POST_IMAGES_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'static', 'post_images')
POST_VIDEOS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'static', 'post_videos')

# 确保目录存在
os.makedirs(GARDEN_PHOTOS_DIR, exist_ok=True)
os.makedirs(POST_IMAGES_DIR, exist_ok=True)
os.makedirs(POST_VIDEOS_DIR, exist_ok=True)


# ============== 数据库辅助函数 ==============

def get_db_connection():
    """获取数据库连接"""
    return pymysql.connect(**DB_CONFIG)


def create_notification(user_id, actor_id, actor_name, actor_avatar, notification_type, target_type=None, target_id=None, target_content=None):
    """创建用户通知"""
    # 不给自己发通知
    if str(user_id) == str(actor_id):
        return False
    
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        # 确保表存在
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_notifications (
                id INT AUTO_INCREMENT PRIMARY KEY,
                user_id VARCHAR(8) NOT NULL,
                actor_id VARCHAR(8),
                actor_name VARCHAR(50),
                actor_avatar VARCHAR(500),
                notification_type VARCHAR(20) DEFAULT 'system',
                target_type VARCHAR(50),
                target_id INT,
                target_content TEXT,
                is_read TINYINT(1) DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                INDEX idx_user_id (user_id),
                INDEX idx_is_read (is_read)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """)
        
        cursor.execute("""
            INSERT INTO user_notifications 
            (user_id, actor_id, actor_name, actor_avatar, notification_type, target_type, target_id, target_content)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """, (user_id, actor_id, actor_name, actor_avatar, notification_type, target_type, target_id, target_content))
        conn.commit()
        print(f"[INFO] 发送通知成功: {actor_name} -> {user_id}, 类型: {notification_type}")
        return True
    except Exception as e:
        print(f"[ERROR] 创建通知失败: {e}")
        conn.rollback()
        return False
    finally:
        cursor.close()
        conn.close()


# ============== 文件上传 API ==============

@bp.route('/upload/image', methods=['POST'])
@token_required
def upload_post_image():
    """上传帖子图片"""
    from flask import g
    if 'image' not in request.files:
        return jsonify({'success': False, 'error': '没有上传文件'}), 400
    
    file = request.files['image']
    if file.filename == '':
        return jsonify({'success': False, 'error': '没有选择文件'}), 400
    
    # 获取文件扩展名
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in ['.jpg', '.jpeg', '.png', '.gif', '.webp']:
        return jsonify({'success': False, 'error': '不支持的图片格式'}), 400
    
    # 生成唯一文件名
    filename = f"{uuid.uuid4().hex}{ext}"
    filepath = os.path.join(POST_IMAGES_DIR, filename)
    
    try:
        file.save(filepath)
        url = f"/static/post_images/{filename}"
        return jsonify({'success': True, 'url': url, 'filename': filename})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@bp.route('/upload/video', methods=['POST'])
@token_required
def upload_post_video():
    """上传帖子视频"""
    from flask import g
    if 'video' not in request.files:
        return jsonify({'success': False, 'error': '没有上传文件'}), 400
    
    file = request.files['video']
    if file.filename == '':
        return jsonify({'success': False, 'error': '没有选择文件'}), 400
    
    # 获取文件扩展名
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in ['.mp4', '.avi', '.mov', '.wmv', '.flv']:
        return jsonify({'success': False, 'error': '不支持的视频格式'}), 400
    
    # 检查文件大小 (限制100MB)
    file.seek(0, 2)
    size = file.tell()
    file.seek(0)
    if size > 100 * 1024 * 1024:
        return jsonify({'success': False, 'error': '视频文件不能超过100MB'}), 400
    
    # 生成唯一文件名
    filename = f"{uuid.uuid4().hex}{ext}"
    filepath = os.path.join(POST_VIDEOS_DIR, filename)
    
    try:
        file.save(filepath)
        url = f"/static/post_videos/{filename}"
        return jsonify({'success': True, 'url': url, 'filename': filename})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# ============== 收藏功能 API ==============

@bp.route('/favorites', methods=['GET'])
@token_required
def get_favorites():
    """获取用户收藏列表"""
    from flask import g
    user_id = g.user_id
    
    conn = get_db_connection()
    cursor = conn.cursor(DictCursor)
    
    try:
        cursor.execute("""
            SELECT id, flower_id, folder_name, latin_name, chinese_name, created_at
            FROM user_favorites
            WHERE user_id = %s
            ORDER BY created_at DESC
        """, (user_id,))
        
        favorites = cursor.fetchall()
        
        return jsonify({
            'success': True,
            'data': {
                'favorites': favorites,
                'total': len(favorites)
            }
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        cursor.close()
        conn.close()


@bp.route('/favorites/posts', methods=['GET'])
@token_required
def get_favorite_posts():
    """获取用户收藏的社区帖子列表"""
    from flask import g
    user_id = g.user_id
    
    conn = get_db_connection()
    cursor = conn.cursor(DictCursor)
    
    try:
        cursor.execute("""
            SELECT p.*, 
                   1 as is_favorited,
                   (SELECT COUNT(*) FROM likes WHERE post_id = p.id) as likes_count,
                   (SELECT COUNT(*) FROM comments WHERE post_id = p.id) as comments_count
            FROM post_favorites pf
            JOIN posts p ON pf.post_id = p.id
            WHERE pf.user_id = %s
            ORDER BY pf.created_at DESC
        """, (user_id,))
        
        favorites = cursor.fetchall()
        
        # 解析 images JSON
        for post in favorites:
            if post.get('images'):
                try:
                    post['images'] = json.loads(post['images'])
                except:
                    post['images'] = []
            if post.get('topics'):
                try:
                    post['topics'] = json.loads(post['topics'])
                except:
                    post['topics'] = []
            if post.get('mentions'):
                try:
                    post['mentions'] = json.loads(post['mentions'])
                except:
                    post['mentions'] = []
        
        return jsonify({
            'success': True,
            'data': {
                'favorites': favorites,
                'total': len(favorites)
            }
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        cursor.close()
        conn.close()


@bp.route('/favorites', methods=['POST'])
@token_required
def add_favorite():
    """添加收藏"""
    from flask import g
    user_id = g.user_id
    data = request.get_json()
    
    flower_id = data.get('flower_id')
    folder_name = data.get('folder_name')
    latin_name = data.get('latin_name', '')
    chinese_name = data.get('chinese_name', '')
    
    if not folder_name:
        return jsonify({'success': False, 'error': '缺少花卉名称'}), 400
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # 检查是否已收藏
        cursor.execute("""
            SELECT id FROM user_favorites WHERE user_id = %s AND folder_name = %s
        """, (user_id, folder_name))
        if cursor.fetchone():
            return jsonify({'success': False, 'error': '已收藏过该花卉'}), 400
        
        cursor.execute("""
            INSERT INTO user_favorites (user_id, flower_id, folder_name, latin_name, chinese_name)
            VALUES (%s, %s, %s, %s, %s)
        """, (user_id, flower_id, folder_name, latin_name, chinese_name))
        conn.commit()
        
        return jsonify({'success': True, 'message': '收藏成功'})
    except Exception as e:
        conn.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        cursor.close()
        conn.close()


@bp.route('/favorites/<int:favorite_id>', methods=['DELETE'])
@token_required
def remove_favorite(favorite_id):
    """取消收藏"""
    from flask import g
    user_id = g.user_id
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute("""
            DELETE FROM user_favorites WHERE id = %s AND user_id = %s
        """, (favorite_id, user_id))
        conn.commit()
        
        if cursor.rowcount == 0:
            return jsonify({'success': False, 'error': '收藏不存在'}), 404
        
        return jsonify({'success': True, 'message': '已取消收藏'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        cursor.close()
        conn.close()


@bp.route('/favorites/check', methods=['GET'])
@token_required
def check_favorite():
    """检查是否已收藏"""
    from flask import g
    user_id = g.user_id
    folder_name = request.args.get('folder_name', '')
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute("""
            SELECT id FROM user_favorites WHERE user_id = %s AND folder_name = %s
        """, (user_id, folder_name))
        
        exists = cursor.fetchone() is not None
        
        return jsonify({'success': True, 'is_favorited': exists})
    finally:
        cursor.close()
        conn.close()


# ============== 我的花园 API ==============

@bp.route('/garden', methods=['GET'])
@token_required
def get_garden():
    """获取用户花园"""
    from flask import g
    user_id = g.user_id
    
    conn = get_db_connection()
    cursor = conn.cursor(DictCursor)
    
    try:
        cursor.execute("""
            SELECT * FROM user_garden WHERE user_id = %s ORDER BY created_at DESC
        """, (user_id,))
        
        plants = cursor.fetchall()
        
        return jsonify({
            'success': True,
            'data': {
                'plants': plants,
                'total': len(plants)
            }
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        cursor.close()
        conn.close()


@bp.route('/garden/<int:plant_id>', methods=['GET'])
@token_required
def get_garden_plant(plant_id):
    """获取单个植物详情（支持查看他人花园）"""
    from flask import g
    user_id = g.user_id
    
    conn = get_db_connection()
    cursor = conn.cursor(DictCursor)
    
    try:
        # 先获取植物信息
        cursor.execute("""
            SELECT g.*, u.username, u.is_admin
            FROM user_garden g
            JOIN users u ON g.user_id = u.id
            WHERE g.id = %s
        """, (plant_id,))
        
        plant = cursor.fetchone()
        
        if not plant:
            return jsonify({'success': False, 'error': '植物不存在'}), 404
        
        # 检查是否是本人的植物
        is_owner = str(plant['user_id']) == str(user_id)
        
        # 如果不是本人，检查隐私设置
        if not is_owner:
            # 获取主人的隐私设置
            cursor.execute("""
                SELECT garden_visibility FROM user_profiles WHERE user_id = %s
            """, (plant['user_id'],))
            profile = cursor.fetchone()
            
            visibility = profile['garden_visibility'] if profile else 'public'
            
            if visibility == 'private':
                return jsonify({'success': False, 'error': '对方花园不可见哦~'}), 403
            
            # 检查是否在黑名单
            cursor.execute("""
                SELECT id FROM user_blacklist 
                WHERE user_id = %s AND blocked_user_id = %s
            """, (plant['user_id'], user_id))
            if cursor.fetchone():
                return jsonify({'success': False, 'error': '对方花园不可见哦~'}), 403
        
        return jsonify({
            'success': True,
            'data': {
                'plant': plant,
                'is_owner': is_owner
            }
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        cursor.close()
        conn.close()


@bp.route('/garden', methods=['POST'])
@token_required
def add_to_garden():
    """添加到花园"""
    from flask import g
    user_id = g.user_id
    data = request.get_json()
    
    flower_id = data.get('flower_id')
    flower_name = data.get('flower_name')
    latin_name = data.get('latin_name', '')
    chinese_name = data.get('chinese_name', '')
    nickname = data.get('nickname', '')
    location = data.get('location', '')
    acquired_date = data.get('acquired_date')
    status = data.get('status', 'healthy')
    notes = data.get('notes', '')
    
    if not flower_name:
        return jsonify({'success': False, 'error': '缺少花卉名称'}), 400
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute("""
            INSERT INTO user_garden 
            (user_id, flower_id, flower_name, latin_name, chinese_name, 
             nickname, location, acquired_date, status, notes)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (user_id, flower_id, flower_name, latin_name, chinese_name,
              nickname, location, acquired_date, status, notes))
        conn.commit()
        
        return jsonify({'success': True, 'message': '已添加到花园'})
    except Exception as e:
        conn.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        cursor.close()
        conn.close()


@bp.route('/garden/<int:plant_id>', methods=['PUT'])
@token_required
def update_garden_plant(plant_id):
    """更新花园植物"""
    from flask import g
    user_id = g.user_id
    data = request.get_json()
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # 构建更新语句
        updates = []
        params = []
        
        for field in ['nickname', 'location', 'status', 'notes', 'water_frequency', 'fertilize_frequency']:
            if field in data:
                updates.append(f"{field} = %s")
                params.append(data[field])
        
        if not updates:
            return jsonify({'success': False, 'error': '没有要更新的字段'}), 400
        
        params.extend([plant_id, user_id])
        
        cursor.execute(f"""
            UPDATE user_garden SET {', '.join(updates)}
            WHERE id = %s AND user_id = %s
        """, params)
        conn.commit()
        
        if cursor.rowcount == 0:
            return jsonify({'success': False, 'error': '植物不存在'}), 404
        
        return jsonify({'success': True, 'message': '更新成功'})
    except Exception as e:
        conn.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        cursor.close()
        conn.close()


@bp.route('/garden/<int:plant_id>', methods=['DELETE'])
@token_required
def remove_from_garden(plant_id):
    """从花园移除"""
    from flask import g
    user_id = g.user_id
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute("""
            DELETE FROM user_garden WHERE id = %s AND user_id = %s
        """, (plant_id, user_id))
        conn.commit()
        
        if cursor.rowcount == 0:
            return jsonify({'success': False, 'error': '植物不存在'}), 404
        
        return jsonify({'success': True, 'message': '已从花园移除'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        cursor.close()
        conn.close()


# ============== 养护提醒 API ==============

@bp.route('/reminders', methods=['GET'])
@token_required
def get_reminders():
    """获取养护提醒列表"""
    from flask import g
    user_id = g.user_id
    
    conn = get_db_connection()
    cursor = conn.cursor(DictCursor)
    
    try:
        cursor.execute("""
            SELECT * FROM care_reminders 
            WHERE user_id = %s AND is_active = 1
            ORDER BY next_reminder ASC
        """, (user_id,))
        
        reminders = cursor.fetchall()
        
        # 转换提醒类型为中文
        type_map = {
            'water': '浇水',
            'fertilize': '施肥',
            'prune': '修剪',
            'repot': '换盆',
            'other': '其他'
        }
        for r in reminders:
            r['type_name'] = type_map.get(r['reminder_type'], '其他')
        
        return jsonify({
            'success': True,
            'data': {
                'reminders': reminders,
                'total': len(reminders)
            }
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        cursor.close()
        conn.close()


@bp.route('/reminders/today', methods=['GET'])
@token_required
def get_today_reminders():
    """获取今日提醒"""
    from flask import g
    user_id = g.user_id
    
    conn = get_db_connection()
    cursor = conn.cursor(DictCursor)
    
    try:
        cursor.execute("""
            SELECT * FROM care_reminders 
            WHERE user_id = %s AND is_active = 1 
            AND next_reminder <= CURDATE() + INTERVAL 1 DAY
            ORDER BY next_reminder ASC
        """, (user_id,))
        
        reminders = cursor.fetchall()
        
        type_map = {
            'water': '浇水',
            'fertilize': '施肥',
            'prune': '修剪',
            'repot': '换盆',
            'other': '其他'
        }
        for r in reminders:
            r['type_name'] = type_map.get(r['reminder_type'], '其他')
        
        return jsonify({
            'success': True,
            'data': {
                'reminders': reminders,
                'total': len(reminders)
            }
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        cursor.close()
        conn.close()


@bp.route('/reminders', methods=['POST'])
@token_required
def add_reminder():
    """添加养护提醒"""
    from flask import g
    user_id = g.user_id
    data = request.get_json()
    
    flower_id = data.get('flower_id')
    flower_name = data.get('flower_name', '')
    reminder_type = data.get('reminder_type', 'water')
    frequency_days = data.get('frequency_days', 7)
    next_reminder = data.get('next_reminder')
    notes = data.get('notes', '')
    
    if not flower_name:
        return jsonify({'success': False, 'error': '缺少花卉名称'}), 400
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute("""
            INSERT INTO care_reminders 
            (user_id, flower_id, flower_name, reminder_type, frequency_days, next_reminder, notes)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (user_id, flower_id, flower_name, reminder_type, frequency_days, next_reminder, notes))
        conn.commit()
        
        return jsonify({'success': True, 'message': '提醒已添加'})
    except Exception as e:
        conn.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        cursor.close()
        conn.close()


@bp.route('/reminders/<int:reminder_id>/done', methods=['POST'])
@token_required
def mark_reminder_done(reminder_id):
    """标记提醒完成"""
    from flask import g
    user_id = g.user_id
    
    conn = get_db_connection()
    cursor = conn.cursor(DictCursor)
    
    try:
        cursor.execute("""
            SELECT * FROM care_reminders WHERE id = %s AND user_id = %s
        """, (reminder_id, user_id))
        reminder = cursor.fetchone()
        
        if not reminder:
            return jsonify({'success': False, 'error': '提醒不存在'}), 404
        
        # 更新完成日期和下次提醒日期
        import datetime
        next_date = datetime.date.today() + datetime.timedelta(days=reminder['frequency_days'])
        
        cursor.execute("""
            UPDATE care_reminders 
            SET last_done = CURDATE(), next_reminder = %s
            WHERE id = %s
        """, (next_date, reminder_id))
        conn.commit()
        
        return jsonify({'success': True, 'message': '已完成，下次提醒已更新'})
    except Exception as e:
        conn.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        cursor.close()
        conn.close()


@bp.route('/reminders/<int:reminder_id>', methods=['DELETE'])
@token_required
def delete_reminder(reminder_id):
    """删除提醒"""
    from flask import g
    user_id = g.user_id
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute("""
            DELETE FROM care_reminders WHERE id = %s AND user_id = %s
        """, (reminder_id, user_id))
        conn.commit()
        
        if cursor.rowcount == 0:
            return jsonify({'success': False, 'error': '提醒不存在'}), 404
        
        return jsonify({'success': True, 'message': '已删除'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        cursor.close()
        conn.close()


# ============== 花友圈 API ==============

@bp.route('/posts', methods=['GET'])
def get_posts():
    """获取帖子列表"""
    page = int(request.args.get('page', 1))
    page_size = int(request.args.get('page_size', 10))
    user_id = request.args.get('user_id')  # 可选：只看某用户的帖子

    conn = get_db_connection()
    cursor = conn.cursor(DictCursor)

    try:
        # 获取当前登录用户的ID和是否管理员
        from routes.auth import get_user_id_by_token
        token = request.headers.get('Authorization', '').replace('Bearer ', '')
        current_user_id = get_user_id_by_token(token) if token else None
        query_user_id = current_user_id if current_user_id else request.headers.get('X-User-Id', '')

        # 检查是否为管理员
        is_admin = False
        if current_user_id:
            cursor.execute("SELECT is_admin FROM users WHERE id = %s", (current_user_id,))
            result = cursor.fetchone()
            is_admin = result and result.get('is_admin', 0) == 1

        # 所有人都只能看到已通过的帖子，待审核帖子只能在审核列表查看
        where = "WHERE p.status = 'approved'"
        params = []
        if user_id:
            where += " AND p.user_id = %s"
            params.append(user_id)

        # 查询总数
        cursor.execute(f"SELECT COUNT(*) as total FROM posts p {where}", params)
        total = cursor.fetchone()['total']

        # 分页查询 - 使用 user_profiles 的 nickname 和 avatar_url
        offset = (page - 1) * page_size

        cursor.execute(f"""
            SELECT p.id, p.user_id, p.content, p.images, p.video_url, p.flower_id, p.flower_name,
                   p.topics, p.mentions, p.likes_count, p.comments_count, p.favorites_count,
                   p.is_top, p.status, p.created_at, p.updated_at,
                   CASE WHEN l.id IS NOT NULL THEN 1 ELSE 0 END as is_liked,
                   CASE WHEN f.id IS NOT NULL THEN 1 ELSE 0 END as is_favorited,
                   COALESCE(NULLIF(pf.nickname, ''), u.username, p.username) as username,
                   COALESCE(NULLIF(pf.avatar_url, ''), p.user_avatar, NULLIF(u.avatar_url, '')) as user_avatar
            FROM posts p
            LEFT JOIN users u ON p.user_id = u.id
            LEFT JOIN user_profiles pf ON p.user_id = pf.user_id
            LEFT JOIN likes l ON p.id = l.post_id AND l.user_id = %s
            LEFT JOIN post_favorites f ON p.id = f.post_id AND f.user_id = %s
            {where}
            ORDER BY p.is_top DESC, p.created_at DESC
            LIMIT %s OFFSET %s
        """, [query_user_id, query_user_id] + params + [page_size, offset])
        
        posts = cursor.fetchall()
        
        # 解析 images JSON
        for post in posts:
            if post['images']:
                try:
                    post['images'] = json.loads(post['images'])
                except:
                    post['images'] = []
            if post.get('topics'):
                try:
                    post['topics'] = json.loads(post['topics'])
                except:
                    post['topics'] = []
            if post.get('mentions'):
                try:
                    post['mentions'] = json.loads(post['mentions'])
                except:
                    post['mentions'] = []
        
        return jsonify({
            'success': True,
            'data': {
                'posts': posts,
                'total': total,
                'page': page,
                'page_size': page_size,
                'total_pages': (total + page_size - 1) // page_size
            }
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        cursor.close()
        conn.close()


@bp.route('/posts', methods=['POST'])
@token_required
def create_post():
    """发布帖子 - 带AI内容审核"""
    from flask import g
    user_id = g.user_id

    conn = get_db_connection()
    cursor = conn.cursor(DictCursor)

    # 从 user_profiles 获取 nickname 和 avatar_url
    cursor.execute("SELECT nickname, avatar_url FROM user_profiles WHERE user_id = %s", (user_id,))
    profile = cursor.fetchone()

    username = profile['nickname'] if profile and profile['nickname'] else g.user.get('username', '匿名用户')
    user_avatar = profile['avatar_url'] if profile and profile['avatar_url'] else g.user.get('avatar_url', '')
    cursor.close()

    data = request.get_json()

    content = data.get('content', '').strip()
    images = data.get('images', [])
    video_url = data.get('video_url')
    flower_id = data.get('flower_id')
    flower_name = data.get('flower_name')
    topics = data.get('topics', [])
    mentions = data.get('mentions', [])

    if not content:
        conn.close()
        return jsonify({'success': False, 'error': '内容不能为空'}), 400

    # ========== AI内容审核 ==========
    from utils.content_moderation import moderate_post

    try:
        moderation_result = moderate_post(content, images, video_url)
        print(f"[INFO] AI审核结果: {moderation_result}")

        # 根据审核结果确定帖子状态和审核信息
        if moderation_result['suggestion'] == 'block':
            # P0文本/图片违规，进入人工审核
            post_status = 'pending'
            is_auto_passed = 0
            risk_level = 'P0'
            # 区分文本和图片的标签
            text_labels = moderation_result.get('details', {}).get('text', {}).get('labels', [])
            image_labels = []
            for img_result in moderation_result.get('details', {}).get('images', []):
                image_labels.extend(img_result.get('labels', []))
            all_labels = list(set(text_labels + image_labels))  # 合并所有标签
            display_labels = moderation_result.get('labels_display', [])
            audit_info = json.dumps({
                'risk_level': moderation_result['risk_level'],
                'labels': all_labels,  # 合并的标签（兼容旧数据）
                'labels_display': display_labels,  # 中文显示标签
                'text_labels': text_labels,  # 文本违规标签
                'image_labels': image_labels,  # 图片违规标签
                'max_score': moderation_result['max_score'],
                'audit_type': 'ai_block_pending',
                'ai_review_time': datetime.now().isoformat()
            }, ensure_ascii=False)

        elif moderation_result['suggestion'] == 'review':
            # P1进入人工审核
            post_status = 'pending'
            is_auto_passed = 0
            risk_level = 'P1'
            text_labels = moderation_result.get('details', {}).get('text', {}).get('labels', [])
            image_labels = []
            for img_result in moderation_result.get('details', {}).get('images', []):
                image_labels.extend(img_result.get('labels', []))
            all_labels = list(set(text_labels + image_labels))
            display_labels = moderation_result.get('labels_display', [])
            audit_info = json.dumps({
                'risk_level': moderation_result['risk_level'],
                'labels': all_labels,
                'labels_display': display_labels,
                'text_labels': text_labels,
                'image_labels': image_labels,
                'max_score': moderation_result['max_score'],
                'audit_type': 'ai_pending',
                'ai_review_time': datetime.now().isoformat()
            }, ensure_ascii=False)
        else:
            # P2或无风险，直接通过
            post_status = 'approved'
            admin_status = 'auto_pass'  # AI自动通过，无需管理员处理
            is_auto_passed = 1
            risk_level = moderation_result.get('risk_level', 'none')
            audit_info = json.dumps({
                'risk_level': moderation_result['risk_level'],
                'labels': moderation_result['labels'],
                'max_score': moderation_result['max_score'],
                'audit_type': 'ai_auto_pass',
                'ai_review_time': datetime.now().isoformat()
            }, ensure_ascii=False) if moderation_result['labels'] else None

    except Exception as e:
        import traceback
        traceback.print_exc()
        # 审核异常时，保守起见进入人工审核
        post_status = 'pending'
        admin_status = None
        risk_level = 'P1'
        audit_info = json.dumps({
            'risk_level': 'P1',
            'labels': ['audit_error'],
            'error': str(e),
            'audit_type': 'ai_error'
        }, ensure_ascii=False)

    cursor = conn.cursor()

    # 如果是pending状态，admin_status保持为NULL（待处理）
    if 'admin_status' not in dir():
        admin_status = None
    # 默认 is_auto_passed = 0
    if 'is_auto_passed' not in dir():
        is_auto_passed = 0
    # 默认 risk_level
    if 'risk_level' not in dir():
        risk_level = None

    try:
        cursor.execute("""
            INSERT INTO posts
            (user_id, username, user_avatar, content, images, video_url, flower_id, flower_name, topics, mentions, status, admin_status, audit_info, is_auto_passed, risk_level)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (user_id, username, user_avatar, content,
              json.dumps(images, ensure_ascii=False) if images else None,
              video_url, flower_id, flower_name,
              json.dumps(topics, ensure_ascii=False) if topics else None,
              json.dumps(mentions, ensure_ascii=False) if mentions else None,
              post_status, admin_status, audit_info, is_auto_passed, risk_level))
        conn.commit()

        post_id = cursor.lastrowid

        # 如果是AI审核进入pending状态，发送通知给用户和所有管理员
        if post_status == 'pending':
            # 通知用户
            try:
                create_notification(
                    user_id=user_id,
                    actor_id='system',
                    actor_name='系统',
                    actor_avatar='',
                    notification_type='system',
                    target_type='post',
                    target_id=post_id,
                    target_content='您的帖子正在等待人工审核'
                )
            except Exception as notif_err:
                print(f"[WARN] 发送审核通知失败: {notif_err}")

            # 通知所有管理员
            try:
                cursor.execute("SELECT id FROM users WHERE is_admin = 1")
                admins = cursor.fetchall()
                for admin in admins:
                    create_notification(
                        user_id=admin['id'],
                        actor_id='system',
                        actor_name='系统',
                        actor_avatar='',
                        notification_type='system',
                        target_type='post',
                        target_id=post_id,
                        target_content=f'有新的帖子待审核（ID: {post_id}）'
                    )
                if admins:
                    print(f"[INFO] 已通知 {len(admins)} 位管理员有新帖子待审核")
            except Exception as notif_err:
                print(f"[WARN] 发送管理员通知失败: {notif_err}")

        # 更新用户发帖数（只有审核通过的才增加）
        if post_status == 'approved':
            cursor.execute("UPDATE user_profiles SET posts_count = posts_count + 1 WHERE user_id = %s", (user_id,))
            conn.commit()
            # 添加经验值：发布内容+10
            add_experience(user_id, 'post', '发布帖子')
            message = '发布成功'
        else:
            message = '发布成功，内容正在审核中'

        return jsonify({
            'success': True,
            'message': message,
            'post_id': post_id,
            'status': post_status,
            'need_manual_review': post_status == 'pending',
            'audit': {
                'risk_level': moderation_result.get('risk_level', 'none') if 'moderation_result' in dir() else 'none',
                'suggestion': moderation_result.get('suggestion', 'pass') if 'moderation_result' in dir() else 'pass'
            }
        })
    except Exception as e:
        conn.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        cursor.close()
        conn.close()


# ============== 内容审核 API ==============

@bp.route('/audit/list', methods=['GET'])
@token_required
def get_audit_list():
    """获取审核列表"""
    from flask import g

    # 检查管理员权限
    if not g.user.get('is_admin'):
        return jsonify({'success': False, 'error': '需要管理员权限'}), 403

    page = int(request.args.get('page', 1))
    page_size = int(request.args.get('page_size', 10))
    status = request.args.get('status', 'pending')
    risk_level = request.args.get('risk_level')

    if status not in ['pending', 'approved', 'rejected']:
        status = 'pending'

    conn = get_db_connection()
    cursor = conn.cursor(DictCursor)

    try:
        offset = (page - 1) * page_size

        # 构建查询条件
        where_sql = "p.status = %s"
        params = [status]

        if risk_level:
            where_sql += " AND JSON_EXTRACT(p.audit_info, '$.risk_level') = %s"
            params.append(risk_level)

        cursor.execute(f"""
            SELECT COUNT(*) as total FROM posts p WHERE {where_sql}
        """, params)
        total = cursor.fetchone()['total']

        cursor.execute(f"""
            SELECT p.*, u.username as author_name
            FROM posts p
            LEFT JOIN users u ON p.user_id = u.id
            WHERE {where_sql}
            ORDER BY
                CASE WHEN p.status = 'pending' THEN 0 ELSE 1 END,
                p.created_at DESC
            LIMIT %s OFFSET %s
        """, params + [page_size, offset])

        posts = cursor.fetchall()

        for post in posts:
            if post['images']:
                try:
                    post['images'] = json.loads(post['images'])
                except:
                    post['images'] = []
            if post.get('topics'):
                try:
                    post['topics'] = json.loads(post['topics'])
                except:
                    post['topics'] = []
            if post.get('audit_info'):
                try:
                    post['audit_info'] = json.loads(post['audit_info'])
                except:
                    post['audit_info'] = {}

        return jsonify({
            'success': True,
            'data': {
                'posts': posts,
                'total': total,
                'page': page,
                'page_size': page_size,
                'total_pages': (total + page_size - 1) // page_size if total > 0 else 0
            }
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        cursor.close()
        conn.close()


# 保留旧接口兼容
@bp.route('/audit/pending', methods=['GET'])
@token_required
def get_pending_posts():
    """获取待审核帖子（兼容旧接口）"""
    return get_audit_list()


@bp.route('/audit/processed', methods=['GET'])
@token_required
def get_processed_posts():
    """获取已处理过的帖子（管理员查看）"""
    from flask import g

    if not g.user.get('is_admin'):
        return jsonify({'success': False, 'error': '需要管理员权限'}), 403

    page = int(request.args.get('page', 1))
    page_size = int(request.args.get('page_size', 10))
    admin_status = request.args.get('admin_status')  # approved/rejected/auto_pass

    conn = get_db_connection()
    cursor = conn.cursor(DictCursor)

    try:
        offset = (page - 1) * page_size

        # 构建查询条件
        where_clauses = ["p.admin_status IS NOT NULL"]
        params = []

        if admin_status == 'auto_pass':
            # AI自动通过的帖子用 is_auto_passed 字段判断
            where_clauses.append("p.is_auto_passed = 1")
        elif admin_status:
            where_clauses.append("p.admin_status = %s")
            params.append(admin_status)

        where_sql = " AND ".join(where_clauses)

        # 查询总数
        cursor.execute(f"SELECT COUNT(*) as total FROM posts p WHERE {where_sql}", params)
        total = cursor.fetchone()['total']

        # 查询列表
        cursor.execute(f"""
            SELECT p.*, u.username as author_name
            FROM posts p
            LEFT JOIN users u ON p.user_id = u.id
            WHERE {where_sql}
            ORDER BY p.updated_at DESC
            LIMIT %s OFFSET %s
        """, params + [page_size, offset])

        posts = cursor.fetchall()

        for post in posts:
            if post['images']:
                try:
                    post['images'] = json.loads(post['images'])
                except:
                    post['images'] = []
            if post.get('topics'):
                try:
                    post['topics'] = json.loads(post['topics'])
                except:
                    post['topics'] = []
            if post.get('audit_info'):
                try:
                    post['audit_info'] = json.loads(post['audit_info'])
                except:
                    post['audit_info'] = {}

        return jsonify({
            'success': True,
            'data': {
                'posts': posts,
                'total': total,
                'page': page,
                'page_size': page_size,
                'total_pages': (total + page_size - 1) // page_size if total > 0 else 0
            }
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        cursor.close()
        conn.close()


@bp.route('/audit/<int:post_id>/approve', methods=['POST'])
@token_required
def approve_post(post_id):
    """审核通过帖子"""
    from flask import g
    from datetime import datetime

    if not g.user.get('is_admin'):
        return jsonify({'success': False, 'error': '需要管理员权限'}), 403

    conn = get_db_connection()
    cursor = conn.cursor(DictCursor)

    try:
        # 获取帖子信息
        cursor.execute("""
            SELECT p.*, u.username as author_name
            FROM posts p
            LEFT JOIN users u ON p.user_id = u.id
            WHERE p.id = %s
        """, (post_id,))
        post = cursor.fetchone()

        if not post:
            return jsonify({'success': False, 'error': '帖子不存在'}), 404

        if post['status'] == 'approved':
            return jsonify({'success': False, 'error': '帖子已审核通过'}), 400

        # 更新帖子状态
        cursor.execute("""
            UPDATE posts
            SET status = 'approved',
                admin_status = 'approved',
                audit_info = JSON_SET(COALESCE(audit_info, '{}'),
                    '$.manual_review_time', %s,
                    '$.manual_reviewer_id', %s,
                    '$.audit_type', 'manual_review')
            WHERE id = %s
        """, (datetime.now().isoformat(), g.user_id, post_id))
        conn.commit()

        # 更新用户发帖数
        cursor.execute("UPDATE user_profiles SET posts_count = posts_count + 1 WHERE user_id = %s", (post['user_id'],))
        conn.commit()

        # 添加经验值
        try:
            add_experience(post['user_id'], 'post', '发布帖子')
        except:
            pass

        # 发送审核通过通知
        create_notification(
            user_id=post['user_id'],
            actor_id='system',
            actor_name='系统',
            actor_avatar='',
            notification_type='system',
            target_type='post',
            target_id=post_id,
            target_content='您的帖子已审核通过'
        )

        return jsonify({'success': True, 'message': '审核通过'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        cursor.close()
        conn.close()


@bp.route('/audit/<int:post_id>/reject', methods=['POST'])
@token_required
def reject_post(post_id):
    """审核拒绝帖子"""
    from flask import g
    from datetime import datetime

    if not g.user.get('is_admin'):
        return jsonify({'success': False, 'error': '需要管理员权限'}), 403

    data = request.get_json() or {}
    reason = data.get('reason', '')

    conn = get_db_connection()
    cursor = conn.cursor(DictCursor)

    try:
        # 获取帖子信息
        cursor.execute("""
            SELECT p.*, u.username as author_name
            FROM posts p
            LEFT JOIN users u ON p.user_id = u.id
            WHERE p.id = %s
        """, (post_id,))
        post = cursor.fetchone()

        if not post:
            return jsonify({'success': False, 'error': '帖子不存在'}), 404

        if post['status'] == 'rejected':
            return jsonify({'success': False, 'error': '帖子已审核拒绝'}), 400

        # 更新帖子状态
        cursor.execute("""
            UPDATE posts
            SET status = 'rejected',
                admin_status = 'rejected',
                audit_info = JSON_SET(COALESCE(audit_info, '{}'),
                    '$.manual_review_time', %s,
                    '$.manual_reviewer_id', %s,
                    '$.audit_type', 'manual_review',
                    '$.reject_reason', %s)
            WHERE id = %s
        """, (datetime.now().isoformat(), g.user_id, reason, post_id))
        conn.commit()

        # 发送审核拒绝通知
        notification_content = f'您的帖子未通过审核，原因：{reason}' if reason else '您的帖子未通过审核'
        create_notification(
            user_id=post['user_id'],
            actor_id='system',
            actor_name='系统',
            actor_avatar='',
            notification_type='system',
            target_type='post',
            target_id=post_id,
            target_content=notification_content
        )

        return jsonify({'success': True, 'message': '已拒绝'})
    except Exception as e:
        conn.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        cursor.close()
        conn.close()


@bp.route('/audit/<int:post_id>/block', methods=['POST'])
@token_required
def block_post(post_id):
    """禁止帖子"""
    from flask import g
    from datetime import datetime

    if not g.user.get('is_admin'):
        return jsonify({'success': False, 'error': '需要管理员权限'}), 403

    conn = get_db_connection()
    cursor = conn.cursor(DictCursor)

    try:
        cursor.execute("""
            SELECT p.*, u.username as author_name
            FROM posts p
            LEFT JOIN users u ON p.user_id = u.id
            WHERE p.id = %s
        """, (post_id,))
        post = cursor.fetchone()

        if not post:
            return jsonify({'success': False, 'error': '帖子不存在'}), 404

        if post['status'] == 'rejected':
            return jsonify({'success': False, 'error': '帖子已被禁止'}), 400

        cursor.execute("""
            UPDATE posts
            SET status = 'rejected',
                admin_status = 'rejected',
                audit_info = JSON_SET(COALESCE(audit_info, '{}'),
                    '$.manual_review_time', %s,
                    '$.manual_reviewer_id', %s,
                    '$.audit_type', 'admin_block')
            WHERE id = %s
        """, (datetime.now().isoformat(), g.user_id, post_id))
        conn.commit()

        create_notification(
            user_id=post['user_id'],
            actor_id='system',
            actor_name='系统',
            actor_avatar='',
            notification_type='system',
            target_type='post',
            target_id=post_id,
            target_content='您的帖子已被管理员禁止发布'
        )

        return jsonify({'success': True, 'message': '已禁止'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        cursor.close()
        conn.close()


@bp.route('/audit/<int:post_id>/allow', methods=['POST'])
@token_required
def allow_post(post_id):
    """允许被禁止的帖子"""
    from flask import g
    from datetime import datetime

    if not g.user.get('is_admin'):
        return jsonify({'success': False, 'error': '需要管理员权限'}), 403

    conn = get_db_connection()
    cursor = conn.cursor(DictCursor)

    try:
        cursor.execute("""
            SELECT p.*, u.username as author_name
            FROM posts p
            LEFT JOIN users u ON p.user_id = u.id
            WHERE p.id = %s
        """, (post_id,))
        post = cursor.fetchone()

        if not post:
            return jsonify({'success': False, 'error': '帖子不存在'}), 404

        if post['status'] != 'rejected':
            return jsonify({'success': False, 'error': '只能恢复已拒绝的帖子'}), 400

        cursor.execute("""
            UPDATE posts
            SET status = 'approved',
                admin_status = 'auto_pass',
                is_auto_passed = 1,
                audit_info = JSON_SET(COALESCE(audit_info, '{}'),
                    '$.manual_review_time', %s,
                    '$.manual_reviewer_id', %s,
                    '$.audit_type', 'admin_allow')
            WHERE id = %s
        """, (datetime.now().isoformat(), g.user_id, post_id))
        conn.commit()

        create_notification(
            user_id=post['user_id'],
            actor_id='system',
            actor_name='系统',
            actor_avatar='',
            notification_type='system',
            target_type='post',
            target_id=post_id,
            target_content='您的帖子已恢复在社区展示'
        )

        return jsonify({'success': True, 'message': '已恢复'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        cursor.close()
        conn.close()


@bp.route('/posts/<int:post_id>', methods=['DELETE'])
@token_required
def delete_post(post_id):
    """删除帖子"""
    from flask import g
    user_id = g.user_id
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute("""
            DELETE FROM posts WHERE id = %s AND user_id = %s
        """, (post_id, user_id))
        conn.commit()
        
        if cursor.rowcount == 0:
            return jsonify({'success': False, 'error': '帖子不存在或无权删除'}), 404
        
        return jsonify({'success': True, 'message': '已删除'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        cursor.close()
        conn.close()


@bp.route('/posts/<int:post_id>/like', methods=['POST'])
@token_required
def toggle_like(post_id):
    """点赞/取消点赞"""
    from flask import g
    user_id = g.user_id
    
    conn = get_db_connection()
    cursor = conn.cursor(DictCursor)
    
    # 从 user_profiles 获取 nickname 和 avatar_url
    cursor.execute("SELECT nickname, avatar_url FROM user_profiles WHERE user_id = %s", (user_id,))
    profile = cursor.fetchone()
    username = profile['nickname'] if profile and profile['nickname'] else g.user.get('username', '匿名用户')
    user_avatar = profile['avatar_url'] if profile and profile['avatar_url'] else g.user.get('avatar_url', '')
    
    try:
        # 获取帖子作者信息
        cursor.execute("SELECT user_id, content FROM posts WHERE id = %s", (post_id,))
        post = cursor.fetchone()
        if not post:
            return jsonify({'success': False, 'error': '帖子不存在'}), 404
        
        post_author_id = post['user_id']
        post_content = ((post['content'] or '')[:50]) if post['content'] else '帖子'
        
        # 不给自己点赞时不发送通知
        if str(post_author_id) == str(user_id):
            send_notification = False
        else:
            send_notification = True
        
        # 检查是否已点赞
        cursor.execute("""
            SELECT id FROM likes WHERE post_id = %s AND user_id = %s
        """, (post_id, user_id))
        existing = cursor.fetchone()
        
        if existing:
            # 取消点赞
            cursor.execute("""
                DELETE FROM likes WHERE post_id = %s AND user_id = %s
            """, (post_id, user_id))
            cursor.execute("""
                UPDATE posts SET likes_count = likes_count - 1 WHERE id = %s
            """, (post_id,))
            conn.commit()
            liked = False
            
            # 取消点赞时删除之前的通知
            if send_notification:
                try:
                    cursor.execute("""
                        DELETE FROM user_notifications 
                        WHERE actor_id = %s AND target_id = %s AND target_type = 'post' AND notification_type = 'like'
                    """, (user_id, post_id))
                    conn.commit()
                except Exception as e:
                    print(f"[WARN] 删除通知失败: {e}")
        else:
            # 添加点赞
            cursor.execute("""
                INSERT INTO likes (post_id, user_id) VALUES (%s, %s)
            """, (post_id, user_id))
            cursor.execute("""
                UPDATE posts SET likes_count = likes_count + 1 WHERE id = %s
            """, (post_id,))
            conn.commit()
            liked = True
            
            # 添加经验值：点赞+1（使用独立连接，不影响主事务）
            try:
                add_experience(user_id, 'like', '点赞帖子')
            except Exception as e:
                print(f"[WARN] 添加经验值失败: {e}")
            
            # 发送点赞通知（使用独立连接，不影响主事务）
            # 检查是否已经发送过该通知（防止重复发送）
            if send_notification:
                try:
                    cursor.execute("""
                        SELECT id FROM user_notifications 
                        WHERE actor_id = %s AND target_id = %s AND target_type = 'post' AND notification_type = 'like'
                    """, (user_id, post_id))
                    existing_notification = cursor.fetchone()
                    
                    if not existing_notification:
                        print(f"[INFO] 发送点赞通知: {username} 点赞了帖子 {post_id}")
                        create_notification(
                            user_id=post_author_id,
                            actor_id=user_id,
                            actor_name=username,
                            actor_avatar=user_avatar,
                            notification_type='like',
                            target_type='post',
                            target_id=post_id,
                            target_content=post_content
                        )
                    else:
                        print(f"[INFO] 点赞通知已存在，跳过")
                except Exception as e:
                    print(f"[WARN] 创建点赞通知失败: {e}")
        
        # 获取最新点赞数
        cursor.execute("SELECT likes_count FROM posts WHERE id = %s", (post_id,))
        likes_count = cursor.fetchone()['likes_count']
        
        return jsonify({
            'success': True,
            'liked': liked,
            'likes_count': likes_count
        })
    except Exception as e:
        conn.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        cursor.close()
        conn.close()


@bp.route('/posts/<int:post_id>/favorite', methods=['POST'])
@token_required
def toggle_favorite(post_id):
    """收藏/取消收藏帖子"""
    from flask import g
    user_id = g.user_id
    
    conn = get_db_connection()
    cursor = conn.cursor(DictCursor)
    
    # 从 user_profiles 获取 nickname 和 avatar_url
    cursor.execute("SELECT nickname, avatar_url FROM user_profiles WHERE user_id = %s", (user_id,))
    profile = cursor.fetchone()
    username = profile['nickname'] if profile and profile['nickname'] else g.user.get('username', '匿名用户')
    user_avatar = profile['avatar_url'] if profile and profile['avatar_url'] else g.user.get('avatar_url', '')
    
    try:
        # 检查帖子是否存在
        cursor.execute("SELECT user_id, content FROM posts WHERE id = %s", (post_id,))
        post = cursor.fetchone()
        if not post:
            return jsonify({'success': False, 'error': '帖子不存在'}), 404
        
        post_author_id = post['user_id']
        post_content = ((post['content'] or '')[:50]) if post['content'] else '帖子'
        
        # 不给自己收藏时不发送通知
        if str(post_author_id) == str(user_id):
            send_notification = False
        else:
            send_notification = True
        
        # 检查是否已收藏
        cursor.execute("""
            SELECT id FROM post_favorites WHERE post_id = %s AND user_id = %s
        """, (post_id, user_id))
        existing = cursor.fetchone()
        
        if existing:
            # 取消收藏
            cursor.execute("""
                DELETE FROM post_favorites WHERE post_id = %s AND user_id = %s
            """, (post_id, user_id))
            cursor.execute("""
                UPDATE posts SET favorites_count = favorites_count - 1 WHERE id = %s
            """, (post_id,))
            conn.commit()
            favorited = False
            
            # 取消收藏时删除之前的通知
            if send_notification:
                try:
                    cursor.execute("""
                        DELETE FROM user_notifications 
                        WHERE actor_id = %s AND target_id = %s AND target_type = 'post' AND notification_type = 'favorite'
                    """, (user_id, post_id))
                    conn.commit()
                except Exception as e:
                    print(f"[WARN] 删除通知失败: {e}")
        else:
            # 添加收藏
            cursor.execute("""
                INSERT INTO post_favorites (post_id, user_id) VALUES (%s, %s)
            """, (post_id, user_id))
            cursor.execute("""
                UPDATE posts SET favorites_count = favorites_count + 1 WHERE id = %s
            """, (post_id,))
            conn.commit()
            favorited = True
            
            # 添加经验值：收藏+2
            add_experience(user_id, 'like', '收藏帖子')
            
            # 发送收藏通知（使用正确的通知类型）
            if send_notification:
                try:
                    cursor.execute("""
                        SELECT id FROM user_notifications 
                        WHERE actor_id = %s AND target_id = %s AND target_type = 'post' AND notification_type = 'favorite'
                    """, (user_id, post_id))
                    existing_notification = cursor.fetchone()
                    
                    if not existing_notification:
                        print(f"[INFO] 发送收藏通知: {username} 收藏了帖子 {post_id}")
                        create_notification(
                            user_id=post_author_id,
                            actor_id=user_id,
                            actor_name=username,
                            actor_avatar=user_avatar,
                            notification_type='favorite',
                            target_type='post',
                            target_id=post_id,
                            target_content=post_content
                        )
                    else:
                        print(f"[INFO] 收藏通知已存在，跳过")
                except Exception as e:
                    print(f"[WARN] 创建收藏通知失败: {e}")
        
        # 获取最新收藏数
        cursor.execute("SELECT favorites_count FROM posts WHERE id = %s", (post_id,))
        result = cursor.fetchone()
        favorites_count = result['favorites_count'] if result else 0
        
        return jsonify({
            'success': True,
            'favorited': favorited,
            'favorites_count': favorites_count
        })
    except Exception as e:
        conn.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        cursor.close()
        conn.close()


# ============== 评论 API ==============

@bp.route('/posts/<int:post_id>/comments', methods=['GET'])
def get_comments(post_id):
    """获取评论列表"""
    conn = get_db_connection()
    cursor = conn.cursor(DictCursor)
    
    try:
        # JOIN user_profiles 获取 nickname 和 avatar_url（显式列出需要的字段）
        cursor.execute("""
            SELECT c.id, c.post_id, c.user_id, c.content, c.created_at, c.updated_at,
                   COALESCE(NULLIF(pf.nickname, ''), c.username) as username, 
                   COALESCE(NULLIF(pf.avatar_url, ''), c.user_avatar) as user_avatar
            FROM comments c
            LEFT JOIN user_profiles pf ON c.user_id = pf.user_id
            WHERE c.post_id = %s ORDER BY c.created_at ASC
        """, (post_id,))
        
        comments = cursor.fetchall()
        
        return jsonify({
            'success': True,
            'data': {
                'comments': comments,
                'total': len(comments)
            }
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        cursor.close()
        conn.close()


@bp.route('/posts/<int:post_id>/comments', methods=['POST'])
@token_required
def add_comment(post_id):
    """添加评论"""
    from flask import g
    user_id = g.user_id
    
    conn = get_db_connection()
    cursor = conn.cursor(DictCursor)
    
    # 从 user_profiles 获取 nickname 和 avatar_url
    cursor.execute("SELECT nickname, avatar_url FROM user_profiles WHERE user_id = %s", (user_id,))
    profile = cursor.fetchone()
    username = profile['nickname'] if profile and profile['nickname'] else g.user.get('username', '匿名用户')
    user_avatar = profile['avatar_url'] if profile and profile['avatar_url'] else g.user.get('avatar_url', '')
    
    data = request.get_json()
    content = data.get('content', '').strip()
    
    if not content:
        cursor.close()
        conn.close()
        return jsonify({'success': False, 'error': '评论内容不能为空'}), 400
    
    try:
        # 获取帖子作者信息
        cursor.execute("SELECT user_id, content FROM posts WHERE id = %s", (post_id,))
        post = cursor.fetchone()
        if not post:
            return jsonify({'success': False, 'error': '帖子不存在'}), 404
        
        post_author_id = post['user_id']
        post_content = ((post['content'] or '')[:50]) if post['content'] else '帖子'
        
        cursor.execute("""
            INSERT INTO comments (post_id, user_id, username, user_avatar, content)
            VALUES (%s, %s, %s, %s, %s)
        """, (post_id, user_id, username, user_avatar, content))
        
        # 更新评论数
        cursor.execute("""
            UPDATE posts SET comments_count = comments_count + 1 WHERE id = %s
        """, (post_id,))
        
        conn.commit()
        
        # 添加经验值：评论+2
        add_experience(user_id, 'comment', '评论帖子')
        
        # 发送评论通知
        create_notification(
            user_id=post_author_id,
            actor_id=user_id,
            actor_name=username,
            actor_avatar=user_avatar,
            notification_type='comment',
            target_type='post',
            target_id=post_id,
            target_content=post_content
        )
        
        return jsonify({'success': True, 'message': '评论成功'})
    except Exception as e:
        conn.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        cursor.close()
        conn.close()


# ============== 花园照片记录 API ==============

@bp.route('/garden/<int:plant_id>/photos', methods=['GET'])
@token_required
def get_garden_photos(plant_id):
    """获取花园植物的照片记录"""
    from flask import g, request
    user_id = g.user_id
    
    conn = get_db_connection()
    cursor = conn.cursor(DictCursor)
    
    try:
        # 验证植物属于当前用户
        cursor.execute("SELECT * FROM user_garden WHERE id = %s AND user_id = %s", (plant_id, user_id))
        plant = cursor.fetchone()
        if not plant:
            return jsonify({'success': False, 'error': '植物不存在'}), 404
        
        # 获取照片记录
        cursor.execute("""
            SELECT id, garden_id, user_id, image_url, notes, recorded_date, created_at
            FROM garden_photos
            WHERE garden_id = %s
            ORDER BY recorded_date DESC, created_at DESC
        """, (plant_id,))
        photos = cursor.fetchall()

        # 处理日期字段和图片URL
        base_url = request.host_url.rstrip('/')
        for photo in photos:
            if photo.get('recorded_date'):
                photo['recorded_date'] = str(photo['recorded_date'])
            if photo.get('created_at'):
                photo['created_at'] = photo['created_at'].isoformat()
            if photo.get('image_url') and not photo['image_url'].startswith('http'):
                photo['image_url'] = base_url + photo['image_url']
        
        return jsonify({
            'success': True,
            'data': {
                'plant': plant,
                'photos': photos,
                'total': len(photos)
            }
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        cursor.close()
        conn.close()


@bp.route('/garden/<int:plant_id>/photos', methods=['POST'])
@token_required
def add_garden_photo(plant_id):
    """添加花园植物的照片记录"""
    from flask import g, url_for
    user_id = g.user_id
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # 验证植物属于当前用户
        cursor.execute("SELECT * FROM user_garden WHERE id = %s AND user_id = %s", (plant_id, user_id))
        if not cursor.fetchone():
            return jsonify({'success': False, 'error': '植物不存在'}), 404
        
        # 获取表单数据
        notes = request.form.get('notes', '')
        recorded_date = request.form.get('recorded_date')
        
        if not recorded_date:
            import datetime
            recorded_date = datetime.date.today().isoformat()
        
        image_url = ''
        
        # 处理图片上传
        if 'image' in request.files:
            file = request.files['image']
            if file and file.filename:
                # 获取文件扩展名
                ext = os.path.splitext(file.filename)[1].lower()
                if ext not in ['.jpg', '.jpeg', '.png', '.gif', '.webp']:
                    ext = '.jpg'
                
                # 生成唯一文件名
                filename = f"{uuid.uuid4().hex}{ext}"
                filepath = os.path.join(GARDEN_PHOTOS_DIR, filename)
                
                # 保存文件
                file.save(filepath)
                
                # 生成URL
                image_url = f"/static/garden_photos/{filename}"
        
        cursor.execute("""
            INSERT INTO garden_photos (garden_id, user_id, image_url, notes, recorded_date)
            VALUES (%s, %s, %s, %s, %s)
        """, (plant_id, user_id, image_url, notes, recorded_date))
        conn.commit()
        
        photo_id = cursor.lastrowid
        
        return jsonify({
            'success': True, 
            'message': '照片记录已添加',
            'photo_id': photo_id,
            'image_url': image_url
        })
    except Exception as e:
        conn.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        cursor.close()
        conn.close()


@bp.route('/garden/photos/<int:photo_id>', methods=['DELETE'])
@token_required
def delete_garden_photo(photo_id):
    """删除花园植物的照片记录"""
    from flask import g
    user_id = g.user_id
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute("""
            DELETE FROM garden_photos WHERE id = %s AND user_id = %s
        """, (photo_id, user_id))
        conn.commit()
        
        if cursor.rowcount == 0:
            return jsonify({'success': False, 'error': '照片记录不存在'}), 404
        
        return jsonify({'success': True, 'message': '已删除'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        cursor.close()
        conn.close()


# ============== 花园日志 API ==============

@bp.route('/garden/<int:plant_id>/diary', methods=['GET'])
@token_required
def get_diary_entries(plant_id):
    """获取花园植物的日志记录"""
    from flask import g, request
    user_id = g.user_id
    
    conn = get_db_connection()
    cursor = conn.cursor(DictCursor)
    
    try:
        # 验证植物属于当前用户
        cursor.execute("SELECT * FROM user_garden WHERE id = %s AND user_id = %s", (plant_id, user_id))
        if not cursor.fetchone():
            return jsonify({'success': False, 'error': '植物不存在'}), 404
        
        # 获取日志记录
        cursor.execute("""
            SELECT id, garden_id, user_id, diary_date, content, mood, weather, image_url, created_at, updated_at
            FROM garden_diary_entries
            WHERE garden_id = %s
            ORDER BY diary_date DESC, created_at DESC
        """, (plant_id,))
        entries = cursor.fetchall()

        # 处理日期字段和图片URL
        base_url = request.host_url.rstrip('/')
        for entry in entries:
            # 转换 diary_date 为字符串
            if entry.get('diary_date'):
                entry['diary_date'] = str(entry['diary_date'])
            if entry.get('created_at'):
                entry['created_at'] = entry['created_at'].isoformat()
            if entry.get('updated_at'):
                entry['updated_at'] = entry['updated_at'].isoformat()
            if entry.get('image_url') and not entry['image_url'].startswith('http'):
                entry['image_url'] = base_url + entry['image_url']
        
        return jsonify({
            'success': True,
            'data': {
                'entries': entries,
                'total': len(entries)
            }
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        cursor.close()
        conn.close()


@bp.route('/garden/<int:plant_id>/diary', methods=['POST'])
@token_required
def add_diary_entry(plant_id):
    """添加花园日志（支持图片）"""
    from flask import g, request
    user_id = g.user_id
    
    # 支持表单数据和JSON
    if request.content_type and 'multipart/form-data' in request.content_type:
        diary_date = request.form.get('diary_date')
        content = request.form.get('content', '').strip()
        mood = request.form.get('mood', 'normal')
        weather = request.form.get('weather', '')
    else:
        data = request.get_json() or {}
        diary_date = data.get('diary_date')
        content = data.get('content', '').strip()
        mood = data.get('mood', 'normal')
        weather = data.get('weather', '')
    
    if not diary_date or not content:
        return jsonify({'success': False, 'error': '日期和内容不能为空'}), 400
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # 验证植物属于当前用户
        cursor.execute("SELECT * FROM user_garden WHERE id = %s AND user_id = %s", (plant_id, user_id))
        if not cursor.fetchone():
            return jsonify({'success': False, 'error': '植物不存在'}), 404
        
        image_url = ''
        # 处理图片上传
        if request.content_type and 'multipart/form-data' in request.content_type:
            if 'image' in request.files:
                file = request.files['image']
                if file and file.filename:
                    ext = os.path.splitext(file.filename)[1].lower()
                    if ext not in ['.jpg', '.jpeg', '.png', '.gif', '.webp']:
                        ext = '.jpg'
                    filename = f"{uuid.uuid4().hex}{ext}"
                    filepath = os.path.join(GARDEN_PHOTOS_DIR, filename)
                    file.save(filepath)
                    image_url = f"/static/garden_photos/{filename}"
        
        cursor.execute("""
            INSERT INTO garden_diary_entries (garden_id, user_id, diary_date, content, mood, weather, image_url)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (plant_id, user_id, diary_date, content, mood, weather, image_url))
        conn.commit()
        
        entry_id = cursor.lastrowid
        
        return jsonify({
            'success': True,
            'message': '日志已添加',
            'entry_id': entry_id
        })
    except Exception as e:
        conn.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        cursor.close()
        conn.close()


@bp.route('/diary/<int:entry_id>', methods=['PUT'])
@token_required
def update_diary_entry(entry_id):
    """更新日志"""
    from flask import g
    user_id = g.user_id
    data = request.get_json()
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute("""
            UPDATE garden_diary_entries 
            SET content = %s, mood = %s, weather = %s
            WHERE id = %s AND user_id = %s
        """, (data.get('content', ''), data.get('mood', 'normal'), 
              data.get('weather', ''), entry_id, user_id))
        conn.commit()
        
        if cursor.rowcount == 0:
            return jsonify({'success': False, 'error': '日志不存在或无权修改'}), 404
        
        return jsonify({'success': True, 'message': '日志已更新'})
    except Exception as e:
        conn.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        cursor.close()
        conn.close()


@bp.route('/diary/<int:entry_id>', methods=['DELETE'])
@token_required
def delete_diary_entry(entry_id):
    """删除日志"""
    from flask import g
    user_id = g.user_id
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute("""
            DELETE FROM garden_diary_entries WHERE id = %s AND user_id = %s
        """, (entry_id, user_id))
        conn.commit()
        
        if cursor.rowcount == 0:
            return jsonify({'success': False, 'error': '日志不存在'}), 404
        
        return jsonify({'success': True, 'message': '已删除'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        cursor.close()
        conn.close()


# ============== 养护计划 API ==============

@bp.route('/garden/<int:plant_id>/schedules', methods=['GET'])
@token_required
def get_care_schedules(plant_id):
    """获取养护计划列表"""
    from flask import g
    user_id = g.user_id
    
    conn = get_db_connection()
    cursor = conn.cursor(DictCursor)

    try:
        # 确保表存在
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS garden_care_schedules (
                id INT AUTO_INCREMENT PRIMARY KEY,
                garden_id INT NOT NULL,
                user_id VARCHAR(8) NOT NULL,
                care_type VARCHAR(20) NOT NULL DEFAULT 'water',
                frequency_days INT NOT NULL DEFAULT 7,
                next_due DATE,
                last_done DATE,
                notes TEXT,
                is_active TINYINT(1) DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                INDEX idx_garden_id (garden_id),
                INDEX idx_user_id (user_id),
                INDEX idx_next_due (next_due)
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS garden_care_logs (
                id INT AUTO_INCREMENT PRIMARY KEY,
                schedule_id INT NOT NULL,
                garden_id INT NOT NULL,
                user_id VARCHAR(8) NOT NULL,
                care_type VARCHAR(20) NOT NULL,
                care_date DATE NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                INDEX idx_schedule_id (schedule_id),
                INDEX idx_garden_id (garden_id)
            )
        """)
        conn.commit()

        cursor.execute("SELECT * FROM user_garden WHERE id = %s AND user_id = %s", (plant_id, user_id))
        if not cursor.fetchone():
            return jsonify({'success': False, 'error': '植物不存在'}), 404

        cursor.execute("""
            SELECT id, garden_id, user_id, care_type, frequency_days, next_due, last_done, notes, is_active, created_at
            FROM garden_care_schedules
            WHERE garden_id = %s AND is_active = 1
            ORDER BY next_due ASC
        """, (plant_id,))
        schedules = cursor.fetchall()

        # 转换日期字段为字符串
        for schedule in schedules:
            if schedule.get('next_due'):
                schedule['next_due'] = str(schedule['next_due'])
            if schedule.get('last_done'):
                schedule['last_done'] = str(schedule['last_done'])
            if schedule.get('created_at'):
                schedule['created_at'] = schedule['created_at'].isoformat()

        return jsonify({
            'success': True,
            'data': {'schedules': schedules}
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        cursor.close()
        conn.close()


@bp.route('/garden/<int:plant_id>/schedules', methods=['POST'])
@token_required
def add_care_schedule(plant_id):
    """添加养护计划"""
    from flask import g
    user_id = g.user_id
    data = request.get_json()
    
    care_type = data.get('care_type', 'water')  # water/fertilize/prune/repot/other
    frequency_days = data.get('frequency_days', 7)
    notes = data.get('notes', '')
    
    if care_type not in ['water', 'fertilize', 'prune', 'repot', 'other']:
        return jsonify({'success': False, 'error': '无效的养护类型'}), 400
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute("SELECT * FROM user_garden WHERE id = %s AND user_id = %s", (plant_id, user_id))
        if not cursor.fetchone():
            return jsonify({'success': False, 'error': '植物不存在'}), 404
        
        import datetime
        today = datetime.date.today()
        next_due = today + datetime.timedelta(days=frequency_days)
        
        cursor.execute("""
            INSERT INTO garden_care_schedules 
            (garden_id, user_id, care_type, frequency_days, next_due, notes)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (plant_id, user_id, care_type, frequency_days, next_due, notes))
        conn.commit()
        
        schedule_id = cursor.lastrowid
        
        # 生成通知
        _generate_care_notification(user_id, plant_id, care_type, next_due, notes)
        
        return jsonify({
            'success': True,
            'message': '计划已添加',
            'schedule_id': schedule_id
        })
    except Exception as e:
        conn.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        cursor.close()
        conn.close()


@bp.route('/schedules/<int:schedule_id>/complete', methods=['POST'])
@token_required
def complete_care(schedule_id):
    """完成一次养护"""
    from flask import g
    user_id = g.user_id
    
    conn = get_db_connection()
    cursor = conn.cursor(DictCursor)
    
    try:
        cursor.execute("""
            SELECT * FROM garden_care_schedules WHERE id = %s AND user_id = %s
        """, (schedule_id, user_id))
        schedule = cursor.fetchone()
        
        if not schedule:
            return jsonify({'success': False, 'error': '计划不存在'}), 404
        
        import datetime
        today = datetime.date.today()
        
        # 更新计划
        cursor.execute("""
            UPDATE garden_care_schedules 
            SET last_done = %s, next_due = DATE_ADD(%s, INTERVAL frequency_days DAY)
            WHERE id = %s
        """, (today, today, schedule_id))
        
        # 记录历史
        cursor.execute("""
            INSERT INTO garden_care_logs (schedule_id, garden_id, user_id, care_type, care_date)
            VALUES (%s, %s, %s, %s, %s)
        """, (schedule_id, schedule['garden_id'], user_id, schedule['care_type'], today))
        
        # 更新植物上次养护时间
        if schedule['care_type'] == 'water':
            cursor.execute("""
                UPDATE user_garden SET last_watered = %s WHERE id = %s
            """, (today, schedule['garden_id']))
        elif schedule['care_type'] == 'fertilize':
            cursor.execute("""
                UPDATE user_garden SET last_fertilized = %s WHERE id = %s
            """, (today, schedule['garden_id']))
        
        conn.commit()
        
        return jsonify({'success': True, 'message': '养护完成'})
    except Exception as e:
        conn.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        cursor.close()
        conn.close()


@bp.route('/schedules/<int:schedule_id>', methods=['DELETE'])
@token_required
def delete_schedule(schedule_id):
    """删除养护计划"""
    from flask import g
    user_id = g.user_id
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute("""
            UPDATE garden_care_schedules SET is_active = 0 WHERE id = %s AND user_id = %s
        """, (schedule_id, user_id))
        conn.commit()
        
        return jsonify({'success': True, 'message': '计划已删除'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        cursor.close()
        conn.close()


@bp.route('/schedules/all', methods=['GET'])
@token_required
def get_all_schedules():
    """获取用户所有养护计划"""
    from flask import g
    user_id = g.user_id
    
    conn = get_db_connection()
    cursor = conn.cursor(DictCursor)
    
    try:
        cursor.execute("""
            SELECT s.*, g.nickname, g.flower_name, g.latin_name
            FROM garden_care_schedules s
            JOIN user_garden g ON s.garden_id = g.id
            WHERE s.user_id = %s AND s.is_active = 1
            ORDER BY s.next_due ASC
        """, (user_id,))
        schedules = cursor.fetchall()
        
        return jsonify({
            'success': True,
            'data': {'schedules': schedules}
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        cursor.close()
        conn.close()


def _generate_care_notification(user_id, garden_id, care_type, due_date, notes=''):
    """生成养护通知"""
    care_type_names = {
        'water': '浇水',
        'fertilize': '施肥',
        'prune': '修剪',
        'repot': '换盆',
        'other': '养护'
    }
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        title = f"🌱 {care_type_names.get(care_type, '养护')}提醒"
        content = f"您的植物需要在 {due_date} 进行{care_type_names.get(care_type, '养护')}"
        if notes:
            content += f"（{notes}）"
        
        cursor.execute("""
            INSERT INTO care_notifications 
            (user_id, garden_id, notification_type, title, content, due_date)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (user_id, garden_id, care_type, title, content, due_date))
        conn.commit()
    except Exception:
        pass
    finally:
        cursor.close()
        conn.close()


# ============== 消息通知 API ==============

@bp.route('/notifications', methods=['GET'])
@token_required
def get_notifications():
    """获取消息通知列表（仅返回当天到期的养护通知）"""
    from flask import g
    import datetime
    user_id = g.user_id
    
    conn = get_db_connection()
    cursor = conn.cursor(DictCursor)
    
    try:
        today = datetime.date.today().isoformat()
        
        # 先检查是否有当天到期的养护计划需要生成通知
        cursor.execute("""
            SELECT s.*, g.nickname, g.flower_name
            FROM garden_care_schedules s
            JOIN user_garden g ON s.garden_id = g.id
            WHERE s.user_id = %s AND s.is_active = 1 AND s.next_due = %s
        """, (user_id, today))
        due_schedules = cursor.fetchall()
        
        care_type_names = {
            'water': '浇水',
            'fertilize': '施肥',
            'prune': '修剪',
            'repot': '换盆',
            'other': '养护'
        }
        
        # 为当天到期的计划生成通知
        for schedule in due_schedules:
            plant_name = schedule['nickname'] or schedule['flower_name']
            care_name = care_type_names.get(schedule['care_type'], '养护')
            
            # 检查是否已存在相同通知
            cursor.execute("""
                SELECT id FROM care_notifications 
                WHERE user_id = %s AND garden_id = %s AND notification_type = %s AND due_date = %s
            """, (user_id, schedule['garden_id'], schedule['care_type'], today))
            
            if not cursor.fetchone():
                title = f"🌱 {care_name}提醒"
                content = f"您的「{plant_name}」今天需要{care_name}"
                if schedule.get('notes'):
                    content += f"（{schedule['notes']}）"
                
                cursor.execute("""
                    INSERT INTO care_notifications 
                    (user_id, garden_id, notification_type, title, content, due_date)
                    VALUES (%s, %s, %s, %s, %s, %s)
                """, (user_id, schedule['garden_id'], schedule['care_type'], title, content, today))
        
        conn.commit()
        
        # 获取当天到期的通知
        cursor.execute("""
            SELECT n.*, g.nickname, g.flower_name
            FROM care_notifications n
            LEFT JOIN user_garden g ON n.garden_id = g.id
            WHERE n.user_id = %s AND n.is_dismissed = 0 AND n.due_date = %s
            ORDER BY n.created_at DESC
            LIMIT 50
        """, (user_id, today))
        notifications = cursor.fetchall()
        
        # 统计未读数（仅当天）
        cursor.execute("""
            SELECT COUNT(*) as unread_count FROM care_notifications
            WHERE user_id = %s AND is_read = 0 AND is_dismissed = 0 AND due_date = %s
        """, (user_id, today))
        unread_count = cursor.fetchone()['unread_count']
        
        return jsonify({
            'success': True,
            'data': {
                'notifications': notifications,
                'unread_count': unread_count,
                'date': today
            }
        })
    except Exception as e:
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
            UPDATE care_notifications SET is_read = 1 WHERE id = %s AND user_id = %s
        """, (notification_id, user_id))
        conn.commit()
        
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        cursor.close()
        conn.close()


@bp.route('/notifications/read-all', methods=['PUT'])
@token_required
def mark_all_read():
    """标记所有通知为已读"""
    from flask import g
    user_id = g.user_id
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute("""
            UPDATE care_notifications SET is_read = 1 WHERE user_id = %s AND is_read = 0
        """, (user_id,))
        conn.commit()
        
        return jsonify({'success': True, 'message': '全部已读'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        cursor.close()
        conn.close()


@bp.route('/notifications/<int:notification_id>', methods=['DELETE'])
@token_required
def dismiss_notification(notification_id):
    """忽略通知"""
    from flask import g
    user_id = g.user_id
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute("""
            UPDATE care_notifications SET is_dismissed = 1 WHERE id = %s AND user_id = %s
        """, (notification_id, user_id))
        conn.commit()
        
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        cursor.close()
        conn.close()
