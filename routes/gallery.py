"""
图库路由模块 - 花卉图库相关API
"""

import os
import urllib.parse
from flask import Blueprint, jsonify, send_file
import pymysql
from pymysql.cursors import DictCursor

from config import IMAGE_BASE_URL, DB_CONFIG

bp = Blueprint('gallery', __name__, url_prefix='/api/gallery')

# 内存缓存：从数据库加载的花卉映射
_FOLDER_CACHE = None
_FOLDER_TO_INFO = {}  # folder_name -> {id, latin_name, chinese_name, folder_name}


def load_flower_mapping():
    """从数据库加载花卉文件夹映射到内存"""
    global _FOLDER_CACHE, _FOLDER_TO_INFO
    
    if _FOLDER_CACHE is not None:
        return _FOLDER_CACHE
    
    try:
        conn = pymysql.connect(**DB_CONFIG)
        cursor = conn.cursor(DictCursor)
        
        cursor.execute("SELECT * FROM flower_mapping ORDER BY id")
        rows = cursor.fetchall()
        
        _FOLDER_CACHE = {}
        _FOLDER_TO_INFO = {}
        
        for row in rows:
            folder_name = row['folder_name']
            _FOLDER_CACHE[folder_name] = {
                'id': row['id'],
                'latin_name': row['latin_name'],
                'chinese_name': row['chinese_name'],
                'folder_name': folder_name,
                'family': row.get('family', ''),
                'genus': row.get('genus', '')
            }
            _FOLDER_TO_INFO[folder_name] = _FOLDER_CACHE[folder_name]
        
        cursor.close()
        conn.close()
        
        print(f"[INFO] 图库模块加载了 {len(_FOLDER_CACHE)} 个花卉文件夹映射")
        return _FOLDER_CACHE
        
    except Exception as e:
        print(f"[ERROR] 加载花卉映射失败: {e}")
        return {}


def get_flower_info_by_folder(folder_name):
    """根据文件夹名获取花卉信息"""
    if not _FOLDER_TO_INFO:
        load_flower_mapping()
    
    return _FOLDER_TO_INFO.get(folder_name)


def get_folder_by_name(search_name):
    """根据名称（中文/英文/拉丁名）查找文件夹名"""
    if not _FOLDER_TO_INFO:
        load_flower_mapping()
    
    # 1. 精确匹配文件夹名
    if search_name in _FOLDER_TO_INFO:
        return search_name
    
    # 2. 遍历查找匹配
    search_lower = search_name.lower()
    for info in _FOLDER_TO_INFO.values():
        if (search_lower == info['chinese_name'].lower() or 
            search_lower == info['latin_name'].lower() or
            search_lower == info['folder_name'].lower()):
            return info['folder_name']
    
    # 3. 模糊匹配
    for info in _FOLDER_TO_INFO.values():
        if (search_lower in info['chinese_name'].lower() or 
            search_lower in info['latin_name'].lower() or
            search_lower in info['folder_name'].lower()):
            return info['folder_name']
    
    # 4. 都找不到，返回原名称
    return search_name


# ============== 图库API ==============

@bp.route('/flowers', methods=['GET'])
def get_gallery_flowers():
    """获取所有花卉图库列表"""
    try:
        # 确保加载映射
        load_flower_mapping()
        
        flowers = []
        
        for folder_name in os.listdir(IMAGE_BASE_URL):
            folder_path = os.path.join(IMAGE_BASE_URL, folder_name)
            if os.path.isdir(folder_path):
                image_files = [f for f in os.listdir(folder_path) 
                              if f.lower().endswith(('.jpg', '.jpeg', '.png', '.gif', '.webp'))]
                
                if not image_files:
                    continue
                
                sample_image = f'/api/gallery/images/{folder_name}/{image_files[0]}'
                
                # 从数据库获取花卉信息
                flower_info = get_flower_info_by_folder(folder_name)
                
                if flower_info:
                    flowers.append({
                        'id': flower_info['id'],
                        'name': folder_name,  # 文件夹名
                        'name_en': flower_info['latin_name'],  # 拉丁名
                        'name_cn': flower_info['chinese_name'],  # 中文名
                        'family': flower_info.get('family', ''),
                        'image_count': len(image_files),
                        'sample_image': sample_image
                    })
                else:
                    # 找不到映射的文件夹也显示
                    flowers.append({
                        'id': 0,
                        'name': folder_name,
                        'name_en': folder_name,
                        'name_cn': folder_name,
                        'family': '',
                        'image_count': len(image_files),
                        'sample_image': sample_image
                    })
        
        # 按中文名排序
        flowers.sort(key=lambda x: x['name_cn'])
        
        return jsonify({
            'success': True,
            'data': {
                'flowers': flowers,
                'total': len(flowers)
            }
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500


@bp.route('/flower/<path:flower_name>', methods=['GET'])
def get_flower_images(flower_name):
    """获取指定花卉的所有图片"""
    try:
        # 确保加载映射
        load_flower_mapping()
        
        flower_name = urllib.parse.unquote(flower_name)
        
        # 从数据库查找文件夹名
        folder_name = get_folder_by_name(flower_name)
        folder_path = os.path.join(IMAGE_BASE_URL, folder_name)
        
        if not os.path.exists(folder_path):
            return jsonify({
                'success': False,
                'error': f'花卉 "{flower_name}" 不存在'
            }), 404
        
        image_files = sorted([f for f in os.listdir(folder_path) 
                             if f.lower().endswith(('.jpg', '.jpeg', '.png', '.gif', '.webp'))])
        
        images = [{
            'id': i + 1,
            'filename': filename,
            'url': f'/api/gallery/images/{folder_name}/{filename}'
        } for i, filename in enumerate(image_files)]
        
        # 获取花卉信息
        flower_info = get_flower_info_by_folder(folder_name)
        
        if flower_info:
            return jsonify({
                'success': True,
                'data': {
                    'id': flower_info['id'],
                    'name': folder_name,
                    'name_en': flower_info['latin_name'],
                    'name_cn': flower_info['chinese_name'],
                    'family': flower_info.get('family', ''),
                    'images': images,
                    'total': len(images)
                }
            })
        else:
            return jsonify({
                'success': True,
                'data': {
                    'id': 0,
                    'name': folder_name,
                    'name_en': folder_name,
                    'name_cn': folder_name,
                    'family': '',
                    'images': images,
                    'total': len(images)
                }
            })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500


@bp.route('/images/<path:filename>')
def serve_gallery_image(filename):
    """提供图库图片访问服务"""
    try:
        file_path = os.path.join(IMAGE_BASE_URL, filename)
        file_path = os.path.normpath(file_path)
        
        if not file_path.startswith(os.path.normpath(IMAGE_BASE_URL)):
            return 'Forbidden', 403
        
        if os.path.exists(file_path):
            ext = os.path.splitext(filename)[1].lower()
            mime_types = {
                '.jpg': 'image/jpeg',
                '.jpeg': 'image/jpeg',
                '.png': 'image/png',
                '.gif': 'image/gif',
                '.webp': 'image/webp'
            }
            mime_type = mime_types.get(ext, 'application/octet-stream')
            return send_file(file_path, mimetype=mime_type)
        else:
            return 'Image not found', 404
    except Exception as e:
        return str(e), 500


@bp.route('/search', methods=['GET'])
def search_gallery():
    """搜索花卉图库"""
    from flask import request
    
    try:
        # 确保加载映射
        load_flower_mapping()
        
        keyword = request.args.get('keyword', '').strip()
        
        if not keyword:
            return jsonify({
                'success': False,
                'error': '请提供搜索关键词'
            }), 400
        
        results = []
        keyword_lower = keyword.lower()
        
        for folder_name in os.listdir(IMAGE_BASE_URL):
            folder_path = os.path.join(IMAGE_BASE_URL, folder_name)
            if not os.path.isdir(folder_path):
                continue
            
            # 获取花卉信息
            flower_info = get_flower_info_by_folder(folder_name)
            
            # 匹配逻辑：文件夹名、中文名、拉丁名
            match = False
            if flower_info:
                if (keyword_lower in folder_name.lower() or
                    keyword_lower in flower_info['chinese_name'].lower() or
                    keyword_lower in flower_info['latin_name'].lower()):
                    match = True
            else:
                if keyword_lower in folder_name.lower():
                    match = True
            
            if match:
                image_files = [f for f in os.listdir(folder_path) 
                              if f.lower().endswith(('.jpg', '.jpeg', '.png', '.gif', '.webp'))]
                
                if not image_files:
                    continue
                
                sample_image = f'/api/gallery/images/{folder_name}/{image_files[0]}'
                
                if flower_info:
                    results.append({
                        'id': flower_info['id'],
                        'name': folder_name,
                        'name_en': flower_info['latin_name'],
                        'name_cn': flower_info['chinese_name'],
                        'family': flower_info.get('family', ''),
                        'image_count': len(image_files),
                        'sample_image': sample_image
                    })
                else:
                    results.append({
                        'id': 0,
                        'name': folder_name,
                        'name_en': folder_name,
                        'name_cn': folder_name,
                        'family': '',
                        'image_count': len(image_files),
                        'sample_image': sample_image
                    })
        
        return jsonify({
            'success': True,
            'data': {
                'flowers': results,
                'total': len(results),
                'keyword': keyword
            }
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500
