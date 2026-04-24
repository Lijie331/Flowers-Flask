from flask import Blueprint, request, jsonify, g
import pymysql
from functools import wraps
from config import DB_CONFIG
from routes.auth import token_required

admin_bp = Blueprint('admin', __name__, url_prefix='/api/admin')

def admin_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        user_id = g.user_id
        if not user_id:
            return jsonify({'success': False, 'error': '未登录'}), 401
        
        conn = pymysql.connect(**DB_CONFIG)
        cursor = conn.cursor()
        cursor.execute("SELECT is_admin FROM users WHERE id = %s", (user_id,))
        result = cursor.fetchone()
        cursor.close()
        conn.close()
        
        if not result or result[0] != 1:
            return jsonify({'success': False, 'error': '无权限'}), 403

        return f(*args, **kwargs)
    return wrapper

#用户管理接口
@admin_bp.route('/users', methods=['GET'])
@token_required
@admin_required
def get_users():
    keyword = request.args.get('keyword', '').strip()
    conn = pymysql.connect(**DB_CONFIG)
    cursor = conn.cursor(pymysql.cursors.DictCursor)

    if keyword:
        # 模糊查找：支持ID和用户名模糊匹配
        where_clause = "WHERE id LIKE %s OR username LIKE %s"
        params = [f'%{keyword}%', f'%{keyword}%']
        cursor.execute(f"SELECT id, username, phone, is_admin, is_active, created_at FROM users {where_clause} ORDER BY id DESC", params)
    else:
        cursor.execute("SELECT id, username, phone, is_admin, is_active, created_at FROM users ORDER BY id DESC")

    users = cursor.fetchall()
    cursor.close()
    conn.close()
    return jsonify({'success': True, 'users': users})

#禁用/恢复账号
@admin_bp.route('/user/status/<user_id>', methods=['POST'])
@token_required
@admin_required
def toggle_status(user_id):
    data = request.get_json()
    is_active = data.get('is_active')
    conn = pymysql.connect(**DB_CONFIG)
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET is_active=%s WHERE id=%s", (is_active, user_id))
    conn.commit()
    cursor.close()
    conn.close()
    return jsonify({'success': True})

#删除用户
@admin_bp.route('/user/<user_id>', methods=['DELETE'])
@token_required
@admin_required
def delete_user(user_id):
    conn = pymysql.connect(**DB_CONFIG)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM users WHERE id=%s", (user_id,))
    conn.commit()
    cursor.close()
    conn.close()
    return jsonify({'success': True})

#获取识别记录
@admin_bp.route('/history', methods=['GET'])
@token_required
@admin_required
def get_history_admin():
    page = int(request.args.get('page', 1))
    page_size = int(request.args.get('page_size', 10))
    user_id = request.args.get('user_id', '')
    offset = (page - 1) * page_size

    conn = pymysql.connect(**DB_CONFIG)
    cursor = conn.cursor(pymysql.cursors.DictCursor)

    where_clause = ""
    params = []
    if user_id:
        # 支持模糊搜索用户ID
        where_clause = "WHERE user_id LIKE %s"
        params.append(f'%{user_id}%')

    count_sql = f"SELECT COUNT(*) as total FROM identify_history {where_clause}"
    cursor.execute(count_sql, params)
    total = cursor.fetchone()['total']

    data_sql = f"""
        SELECT id, user_id, model_name, predicted_class_name, predicted_class_en, confidence, created_at
        FROM identify_history {where_clause} ORDER BY id DESC LIMIT %s OFFSET %s
    """
    cursor.execute(data_sql, params + [page_size, offset])
    history = cursor.fetchall()

    cursor.close()
    conn.close()
    return jsonify({'success': True, 'history': history, 'total': total})

#删除识别记录
@admin_bp.route('/history/<int:record_id>', methods=['DELETE'])
@token_required
@admin_required
def delete_history(record_id):
    conn = pymysql.connect(**DB_CONFIG)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM identify_history WHERE id=%s", (record_id,))
    conn.commit()
    cursor.close()
    conn.close()
    return jsonify({'success': True})

#获取统计数据
@admin_bp.route('/stats', methods=['GET'])
@token_required
@admin_required
def get_stats():
    conn = pymysql.connect(**DB_CONFIG)
    cursor = conn.cursor(pymysql.cursors.DictCursor)
    cursor.execute("""
        SELECT predicted_class_name as label, COUNT(*) as value
        FROM identify_history GROUP BY predicted_class_name ORDER BY value DESC LIMIT 10
    """)
    stats = cursor.fetchall()
    cursor.close()
    conn.close()
    labels = [s['label'] for s in stats]
    values = [s['value'] for s in stats]
    return jsonify({'success': True, 'data': {'labels': labels, 'values': values}})

# ============ 模型管理 ============

# 模型配置（备用，不从数据库读）
MODEL_CONFIG = {
    'clip_rn50': {'name': 'ResNet50', 'badge': '快速'},
    'clip_rn101': {'name': 'ResNet101', 'badge': '平衡'},
    'clip_vit_b16': {'name': 'ViT-B/16', 'badge': '高精度(速度较慢)'},
    'clip_vit_l14': {'name': 'ViT-L/14', 'badge': '最高精度(速度慢)'},
}

# 获取所有模型状态（从数据库）
@admin_bp.route('/models', methods=['GET'])
@token_required
@admin_required
def get_models():
    conn = pymysql.connect(**DB_CONFIG)
    cursor = conn.cursor(pymysql.cursors.DictCursor)
    cursor.execute("SELECT model_id as id, name, badge, enabled FROM model_status ORDER BY model_id")
    models = cursor.fetchall()
    cursor.close()
    conn.close()
    return jsonify({'success': True, 'models': models})

# 禁用/恢复模型（存入数据库）
@admin_bp.route('/model/toggle', methods=['POST'])
@token_required
@admin_required
def toggle_model():
    data = request.get_json()
    model_id = data.get('model_id')
    enabled = data.get('enabled')

    conn = pymysql.connect(**DB_CONFIG)
    cursor = conn.cursor()
    cursor.execute("UPDATE model_status SET enabled=%s WHERE model_id=%s", (1 if enabled else 0, model_id))
    conn.commit()
    cursor.close()
    conn.close()

    return jsonify({'success': True, 'enabled': enabled})


# ============ 反馈管理 ============

@admin_bp.route('/feedbacks', methods=['GET'])
@token_required
@admin_required
def get_feedbacks():
    """获取反馈列表"""
    page = int(request.args.get('page', 1))
    page_size = int(request.args.get('page_size', 10))
    status = request.args.get('status', '')
    offset = (page - 1) * page_size

    conn = pymysql.connect(**DB_CONFIG)
    cursor = conn.cursor(pymysql.cursors.DictCursor)

    where_clause = ""
    params = []
    if status:
        where_clause = "WHERE f.status = %s"
        params.append(status)

    cursor.execute(f"SELECT COUNT(*) as total FROM feedbacks f {where_clause}", params)
    total = cursor.fetchone()['total']

    cursor.execute(f"""
        SELECT f.id, f.user_id, f.type, f.description, f.contact, f.image_path,
               f.plant_name, f.model_name, f.status, f.admin_note, f.created_at,
               u.username
        FROM feedbacks f
        LEFT JOIN users u ON f.user_id = u.id
        {where_clause}
        ORDER BY f.created_at DESC
        LIMIT %s OFFSET %s
    """, params + [page_size, offset])

    feedbacks = cursor.fetchall()
    cursor.close()
    conn.close()

    for f in feedbacks:
        if f['created_at']:
            f['created_at'] = f['created_at'].strftime('%Y-%m-%d %H:%M:%S')

    return jsonify({
        'success': True,
        'feedbacks': feedbacks,
        'total': total,
        'page': page,
        'page_size': page_size
    })


@admin_bp.route('/feedbacks/<int:feedback_id>', methods=['PUT'])
@token_required
@admin_required
def update_feedback(feedback_id):
    """处理反馈（更新状态和备注）"""
    data = request.get_json()
    status = data.get('status')
    admin_note = data.get('admin_note', '')

    conn = pymysql.connect(**DB_CONFIG)
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE feedbacks
        SET status = %s, admin_note = %s, updated_at = NOW()
        WHERE id = %s
    """, (status, admin_note, feedback_id))
    conn.commit()
    cursor.close()
    conn.close()

    return jsonify({'success': True})


@admin_bp.route('/feedbacks/<int:feedback_id>', methods=['DELETE'])
@token_required
@admin_required
def delete_feedback(feedback_id):
    """删除反馈"""
    conn = pymysql.connect(**DB_CONFIG)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM feedbacks WHERE id = %s", (feedback_id,))
    conn.commit()
    cursor.close()
    conn.close()
    return jsonify({'success': True})


@admin_bp.route('/feedback/<int:feedback_id>/process', methods=['POST'])
@token_required
@admin_required
def process_feedback(feedback_id):
    """处理反馈弹窗接口

    action 可选值:
    - 'add_training': 添加到扩展训练数据（需同时传 label, name_cn）
    - 'mark_correct': 标记为正确预测
    - 'dismiss': 无需处理
    """
    data = request.get_json() or {}
    action = data.get('action', '')
    admin_note = data.get('note', '')

    conn = pymysql.connect(**DB_CONFIG)
    cursor = conn.cursor()

    if action == 'add_training':
        label = data.get('label', '')
        name_cn = data.get('name_cn', '')

        if not label or not name_cn:
            conn.close()
            return jsonify({'success': False, 'error': '花卉label和中文名称不能为空'}), 400

        # 获取反馈中的图片路径
        cursor.execute("SELECT image_path FROM feedbacks WHERE id = %s", (feedback_id,))
        feedback = cursor.fetchone()
        image_path = feedback[0] if feedback else None

        # 创建扩展训练数据记录
        cursor.execute("""
            INSERT INTO extended_training_data
            (image_path, flower_label, flower_name_cn, source_feedback_id, created_by)
            VALUES (%s, %s, %s, %s, %s)
        """, (image_path, label, name_cn, feedback_id, None))

        # 更新反馈状态为已处理
        cursor.execute("""
            UPDATE feedbacks
            SET status = 'processed', admin_note = %s, updated_at = NOW()
            WHERE id = %s
        """, (admin_note, feedback_id))
        conn.commit()
        conn.close()
        return jsonify({'success': True, 'message': '已添加到扩展训练数据'})

    elif action == 'mark_correct':
        cursor.execute("""
            UPDATE feedbacks
            SET status = 'processed', admin_note = %s, updated_at = NOW()
            WHERE id = %s
        """, (admin_note, feedback_id))
        conn.commit()
        conn.close()
        return jsonify({'success': True, 'message': '已标记为正确预测'})

    elif action == 'dismiss':
        cursor.execute("""
            UPDATE feedbacks
            SET status = 'rejected', admin_note = %s, updated_at = NOW()
            WHERE id = %s
        """, (admin_note, feedback_id))
        conn.commit()
        conn.close()
        return jsonify({'success': True, 'message': '已标记为无需处理'})

    else:
        conn.close()
        return jsonify({'success': False, 'error': '无效的操作类型'}), 400


# ============ 扩展训练数据管理 ============

@admin_bp.route('/extended-data', methods=['GET'])
@token_required
@admin_required
def get_extended_data():
    """获取扩展训练数据列表"""
    page = int(request.args.get('page', 1))
    page_size = int(request.args.get('page_size', 10))
    offset = (page - 1) * page_size

    conn = pymysql.connect(**DB_CONFIG)
    cursor = conn.cursor(pymysql.cursors.DictCursor)

    cursor.execute("SELECT COUNT(*) as total FROM extended_training_data")
    total = cursor.fetchone()['total']

    cursor.execute("""
        SELECT e.id, e.image_path, e.flower_label, e.flower_name_cn,
               e.source_feedback_id, e.created_by, e.created_at,
               u.username, f.plant_name as source_plant
        FROM extended_training_data e
        LEFT JOIN users u ON e.created_by = u.id
        LEFT JOIN feedbacks f ON e.source_feedback_id = f.id
        ORDER BY e.created_at DESC
        LIMIT %s OFFSET %s
    """, (page_size, offset))

    data_list = cursor.fetchall()
    cursor.close()
    conn.close()

    for item in data_list:
        if item['created_at']:
            item['created_at'] = item['created_at'].strftime('%Y-%m-%d %H:%M:%S')

    return jsonify({
        'success': True,
        'data_list': data_list,
        'total': total,
        'page': page,
        'page_size': page_size
    })


@admin_bp.route('/extended-data', methods=['POST'])
@token_required
@admin_required
def create_extended_data():
    """添加扩展训练数据"""
    from flask import g

    data = request.get_json()
    image_path = data.get('image_path')
    flower_label = data.get('flower_label')
    flower_name_cn = data.get('flower_name_cn')
    source_feedback_id = data.get('source_feedback_id')

    conn = pymysql.connect(**DB_CONFIG)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO extended_training_data
        (image_path, flower_label, flower_name_cn, source_feedback_id, created_by)
        VALUES (%s, %s, %s, %s, %s)
    """, (image_path, flower_label, flower_name_cn,
          source_feedback_id if source_feedback_id else None, g.user_id))
    conn.commit()
    new_id = cursor.lastrowid
    cursor.close()
    conn.close()

    return jsonify({'success': True, 'id': new_id})


@admin_bp.route('/extended-data/<int:data_id>', methods=['DELETE'])
@token_required
@admin_required
def delete_extended_data(data_id):
    """删除扩展训练数据"""
    conn = pymysql.connect(**DB_CONFIG)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM extended_training_data WHERE id = %s", (data_id,))
    conn.commit()
    cursor.close()
    conn.close()
    return jsonify({'success': True})