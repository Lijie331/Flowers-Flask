"""
反馈管理路由模块
"""

import os
import uuid
import datetime
from functools import wraps
from flask import Blueprint, request, jsonify, g
import pymysql
from pymysql.cursors import DictCursor

from config import DB_CONFIG


# 可选token验证（不强制要求登录）
def optional_token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        g.user_id = None
        g.user = None

        auth_header = request.headers.get('Authorization', '')
        if auth_header.startswith('Bearer '):
            token = auth_header[7:]
            try:
                from routes.auth import get_user_id_by_token, get_user_by_id
                user_id = get_user_id_by_token(token)
                if user_id:
                    g.user_id = user_id
                    g.user = get_user_by_id(user_id)
            except Exception as e:
                print(f"[WARN] Token验证失败: {e}")
                pass
        return f(*args, **kwargs)
    return decorated

bp = Blueprint('feedback', __name__, url_prefix='/api')

# 反馈图片存储目录
FEEDBACK_IMAGE_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'static', 'feedback_images')
os.makedirs(FEEDBACK_IMAGE_DIR, exist_ok=True)


def get_db_connection():
    return pymysql.connect(**DB_CONFIG)


@bp.route('/feedback', methods=['POST'])
@optional_token_required
def submit_feedback():
    """提交反馈接口 - 支持图片上传"""
    from flask import g

    user_id = g.user_id

    try:
        # 获取表单数据
        feedback_type = request.form.get('type', 'incorrect')
        description = request.form.get('description', '')
        contact = request.form.get('contact', '')
        plant_name = request.form.get('plant_name', '')
        model_name = request.form.get('model_name', '')
        history_id = request.form.get('history_id')

        # 处理图片
        image_path = None
        if 'image' in request.files:
            image_file = request.files['image']
            if image_file and image_file.filename:
                # 生成唯一文件名
                ext = os.path.splitext(image_file.filename)[1] or '.jpg'
                filename = f"{uuid.uuid4().hex}{ext}"
                filepath = os.path.join(FEEDBACK_IMAGE_DIR, filename)
                image_file.save(filepath)
                image_path = f"/static/feedback_images/{filename}"

        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO feedbacks (user_id, type, description, contact, image_path,
                                  plant_name, model_name, history_id, status)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'pending')
        """, (user_id, feedback_type, description, contact, image_path,
              plant_name, model_name, history_id if history_id else None))

        feedback_id = cursor.lastrowid
        conn.commit()
        cursor.close()
        conn.close()

        return jsonify({
            'success': True,
            'message': '反馈提交成功',
            'feedback_id': feedback_id
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@bp.route('/feedback/history', methods=['GET'])
@optional_token_required
def get_my_feedbacks():
    """获取我的反馈历史"""
    from flask import g

    user_id = g.user_id
    if not user_id:
        return jsonify({
            'success': True,
            'feedbacks': [],
            'total': 0
        })

    try:
        page = int(request.args.get('page', 1))
        page_size = int(request.args.get('page_size', 10))
        page = max(page, 1)
        page_size = min(max(page_size, 1), 50)
        offset = (page - 1) * page_size

        conn = get_db_connection()
        cursor = conn.cursor(DictCursor)

        cursor.execute("SELECT COUNT(*) as total FROM feedbacks WHERE user_id = %s", (user_id,))
        total = cursor.fetchone()['total']

        cursor.execute("""
            SELECT id, type, description, image_path, plant_name, model_name,
                   status, admin_note, created_at
            FROM feedbacks
            WHERE user_id = %s
            ORDER BY created_at DESC
            LIMIT %s OFFSET %s
        """, (user_id, page_size, offset))

        feedbacks = cursor.fetchall()
        cursor.close()
        conn.close()

        # 转换日期格式
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

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500
