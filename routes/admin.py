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
    conn = pymysql.connect(**DB_CONFIG)
    cursor = conn.cursor(pymysql.cursors.DictCursor)
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
        where_clause = "WHERE user_id = %s"
        params.append(user_id)
    
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