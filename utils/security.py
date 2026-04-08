"""
安全工具模块 - 密码加密、Token管理等
"""

import hashlib
import secrets
from datetime import datetime, timedelta
from typing import Optional, Dict, Any

import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

try:
    from config import JWT_CONFIG
except ImportError:
    JWT_CONFIG = {
        'secret_key': 'your-secret-key-change-in-production',
        'token_expire_hours': 24,
    }

import jwt


def hash_password(password: str) -> str:
    """使用SHA256加密密码"""
    return hashlib.sha256(password.encode('utf-8')).hexdigest()


def verify_password(password: str, password_hash: str) -> bool:
    """验证密码是否正确"""
    return hash_password(password) == password_hash


def generate_token(user_id: int, username: str, extra_data: Dict = None) -> str:
    """生成JWT Token"""
    expire = datetime.utcnow() + timedelta(hours=JWT_CONFIG['token_expire_hours'])
    
    payload = {
        'user_id': user_id,
        'username': username,
        'exp': expire,
        'iat': datetime.utcnow(),
    }
    
    if extra_data:
        payload.update(extra_data)
    
    token = jwt.encode(
        payload,
        JWT_CONFIG['secret_key'],
        algorithm='HS256'
    )
    
    return token


def verify_token(token: str) -> Optional[Dict[str, Any]]:
    """验证JWT Token"""
    try:
        payload = jwt.decode(
            token,
            JWT_CONFIG['secret_key'],
            algorithms=['HS256']
        )
        return payload
    except jwt.ExpiredSignatureError:
        print("Token已过期")
        return None
    except jwt.InvalidTokenError:
        print("无效的Token")
        return None


def get_user_from_token(token: str) -> Optional[Dict[str, Any]]:
    """从Token中获取用户信息"""
    payload = verify_token(token)
    if payload:
        return {
            'user_id': payload.get('user_id'),
            'username': payload.get('username'),
        }
    return None


def token_required(f):
    """用于验证Token的装饰器"""
    from functools import wraps
    from flask import request, jsonify
    
    @wraps(f)
    def decorated(*args, **kwargs):
        token = None
        
        auth_header = request.headers.get('Authorization')
        if auth_header and auth_header.startswith('Bearer '):
            token = auth_header.split(' ')[1]
        
        if not token:
            return jsonify({'success': False, 'error': '缺少Token'}), 401
        
        user = get_user_from_token(token)
        if not user:
            return jsonify({'success': False, 'error': '无效的Token'}), 401
        
        return f(current_user=user, *args, **kwargs)
    
    return decorated


def success_response(data=None, message='操作成功', **kwargs):
    """成功响应格式"""
    response = {
        'success': True,
        'message': message,
    }
    if data is not None:
        response['data'] = data
    response.update(kwargs)
    return response


def error_response(message='操作失败', code=400, **kwargs):
    """错误响应格式"""
    response = {
        'success': False,
        'error': message,
    }
    response.update(kwargs)
    return response, code


def paginate(page: int, page_size: int, total: int) -> Dict:
    """生成分页信息"""
    total_pages = (total + page_size - 1) // page_size
    return {
        'page': page,
        'page_size': page_size,
        'total': total,
        'total_pages': total_pages,
        'has_next': page < total_pages,
        'has_prev': page > 1,
    }
