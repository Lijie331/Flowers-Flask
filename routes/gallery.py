"""
图库路由模块 - 花卉图库相关API
"""

import os
import urllib.parse
from flask import Blueprint, jsonify, send_file, request, g
import pymysql
from pymysql.cursors import DictCursor

from config import IMAGE_BASE_URL, DB_CONFIG

bp = Blueprint('gallery', __name__, url_prefix='/api/gallery')

# 导入认证装饰器
from routes.auth import token_required


# ============== 数据库辅助函数 ==============

def get_db_connection():
    """获取数据库连接"""
    return pymysql.connect(**DB_CONFIG)


# ============== 图库收藏表初始化 ==============

def init_gallery_favorites_table():
    """初始化图库收藏表"""
    conn = get_db_connection()
    if conn is None:
        return False
    cursor = conn.cursor()
    try:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS gallery_favorites (
                id INT AUTO_INCREMENT PRIMARY KEY,
                user_id VARCHAR(8) NOT NULL,
                flower_id INT NOT NULL DEFAULT 0,
                folder_name VARCHAR(200) NOT NULL,
                chinese_name VARCHAR(200) DEFAULT '',
                latin_name VARCHAR(200) DEFAULT '',
                sample_image VARCHAR(500) DEFAULT '',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE KEY uk_user_folder (user_id, folder_name),
                INDEX idx_user_id (user_id)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='图库收藏表'
        """)
        conn.commit()
        print("[INFO] 图库收藏表初始化完成")
        return True
    except Exception as e:
        print(f"[ERROR] 图库收藏表初始化失败: {e}")
        conn.rollback()
        return False
    finally:
        cursor.close()
        conn.close()

# 模块加载时初始化表
try:
    init_gallery_favorites_table()
except:
    pass

# 内存缓存：从数据库加载的花卉映射
_FOLDER_CACHE = None
_FOLDER_TO_INFO = {}  # folder_name -> {id, latin_name, chinese_name, folder_name}


def load_flower_mapping():
    """从数据库 flowers_2 表加载花卉文件夹映射到内存"""
    global _FOLDER_CACHE, _FOLDER_TO_INFO
    
    if _FOLDER_CACHE is not None:
        return _FOLDER_CACHE
    
    try:
        conn = pymysql.connect(**DB_CONFIG)
        cursor = conn.cursor(DictCursor)
        
        # 直接从 flowers_2 表加载
        cursor.execute("SELECT id, chinese_name, latin_name, family, genus FROM flowers ORDER BY id")
        rows = cursor.fetchall()
        
        _FOLDER_CACHE = {}
        _FOLDER_TO_INFO = {}
        
        for row in rows:
            chinese_name = row['chinese_name']
            _FOLDER_CACHE[chinese_name] = {
                'id': row['id'],
                'latin_name': row['latin_name'],
                'chinese_name': row['chinese_name'],
                'folder_name': row['chinese_name'],
                'family': row.get('family', ''),
                'genus': row.get('genus', '')
            }
            _FOLDER_TO_INFO[chinese_name] = _FOLDER_CACHE[chinese_name]
            
            # 也用 latin_name 作为 key
            if row['latin_name']:
                _FOLDER_TO_INFO[row['latin_name']] = _FOLDER_CACHE[chinese_name]
        
        cursor.close()
        conn.close()
        
        print(f"[INFO] 图库模块加载了 {len(_FOLDER_CACHE)} 个花卉映射 (来自flowers_2表)")
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
    
    # 2. 遍历查找匹配（优先返回folder_mapping，如果存在的话）
    search_lower = search_name.lower()
    for info in _FOLDER_TO_INFO.values():
        if (search_lower == info['chinese_name'].lower() or 
            search_lower == info['latin_name'].lower() or
            search_lower == info['folder_name'].lower()):
            # 优先返回folder_mapping（实际目录名），否则返回folder_name
            return info.get('folder_mapping') or info['folder_name']
    
    # 3. 模糊匹配
    for info in _FOLDER_TO_INFO.values():
        if (search_lower in info['chinese_name'].lower() or 
            search_lower in info['latin_name'].lower() or
            search_lower in info['folder_name'].lower()):
            # 优先返回folder_mapping（实际目录名），否则返回folder_name
            return info.get('folder_mapping') or info['folder_name']
    
    # 4. 都找不到，返回原名称
    return search_name


# ============== 图库API ==============

@bp.route('/flowers', methods=['GET'])
def get_gallery_flowers():
    """获取所有花卉图库列表 - 直接从flowers表读取image_url"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor(DictCursor)

        # 直接从flowers_2表获取所有花卉
        cursor.execute("""
            SELECT id, chinese_name, latin_name, family, genus, image_url 
            FROM flowers 
            WHERE image_url IS NOT NULL AND image_url != '' AND image_url != '[]'
            ORDER BY chinese_name
        """)

        import json
        flowers = []
        for row in cursor.fetchall():
            image_url = row.get('image_url') or ''
            
            # 解析 image_url JSON
            sample_image = ''
            image_count = 0
            images = []
            
            if image_url:
                try:
                    image_data = json.loads(image_url)
                    image_count = image_data.get('count', 0)
                    
                    if 'images' in image_data:
                        for img in image_data['images']:
                            if isinstance(img, dict) and 'relative_path' in img:
                                rel_path = img['relative_path']
                                # 使用第一张图片作为封面
                                if not sample_image:
                                    sample_image = f'/api/encyclopedia/images/{rel_path}'
                                images.append(rel_path)
                            elif isinstance(img, str):
                                if not sample_image:
                                    sample_image = f'/api/encyclopedia/images/{img}'
                                images.append(img)
                    
                    # 如果没有count字段，从images列表计算
                    if image_count == 0 and images:
                        image_count = len(images)
                        
                except json.JSONDecodeError:
                    pass
            
            # 只有有图片的花卉才显示
            if image_count > 0:
                flowers.append({
                    'id': row['id'],
                    'name': row['chinese_name'],
                    'name_en': row['latin_name'] or '',
                    'name_cn': row['chinese_name'],
                    'family': row['family'] or '',
                    'genus': row['genus'] or '',
                    'image_count': image_count,
                    'sample_image': sample_image
                })

        cursor.close()
        conn.close()

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
    """获取指定花卉的所有图片 - 直接从flowers表读取image_url"""
    try:
        flower_name = urllib.parse.unquote(flower_name)
        
        conn = get_db_connection()
        cursor = conn.cursor(DictCursor)
        
        # 直接从flowers_2表查找
        cursor.execute("""
            SELECT id, chinese_name, latin_name, family, image_url 
            FROM flowers 
            WHERE chinese_name = %s OR latin_name = %s
        """, (flower_name, flower_name))
        
        flower = cursor.fetchone()
        cursor.close()
        conn.close()
        
        if not flower:
            return jsonify({
                'success': False,
                'error': f'花卉 "{flower_name}" 不存在'
            }), 404
        
        # 解析 image_url JSON
        import json
        images = []
        if flower.get('image_url'):
            try:
                image_data = json.loads(flower['image_url'])
                if 'images' in image_data:
                    for img in image_data['images']:
                        if isinstance(img, dict) and 'relative_path' in img:
                            # 直接使用 relative_path 构建URL
                            images.append({
                                'id': len(images) + 1,
                                'filename': img.get('filename', img['relative_path'].split('/')[-1]),
                                'url': f'/api/encyclopedia/images/{img["relative_path"]}'
                            })
                        elif isinstance(img, str):
                            # 直接是相对路径字符串
                            images.append({
                                'id': len(images) + 1,
                                'filename': img.split('/')[-1],
                                'url': f'/api/encyclopedia/images/{img}'
                            })
            except json.JSONDecodeError:
                pass
        
        return jsonify({
            'success': True,
            'data': {
                'id': flower['id'],
                'name': flower['chinese_name'],
                'name_en': flower['latin_name'] or '',
                'name_cn': flower['chinese_name'],
                'family': flower.get('family', ''),
                'images': images,
                'total': len(images)
            }
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500


# encyclopedia.py 中已有 /api/encyclopedia/images/<path> 服务图片，使用那个即可


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

        # 遍历图片目录
        if not os.path.exists(IMAGE_BASE_URL):
            return jsonify({
                'success': False,
                'error': '图片目录不存在'
            }), 500

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

                sample_image = f'/api/encyclopedia/images/{folder_name}/{image_files[0]}'

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


# ============== 图库收藏API ==============

@bp.route('/favorites', methods=['GET'])
@token_required
def get_gallery_favorites():
    """获取用户的图库收藏列表"""
    user_id = g.user_id
    
    conn = get_db_connection()
    if conn is None:
        return jsonify({'success': False, 'error': '数据库连接失败'}), 500
    
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT id, flower_id, folder_name, chinese_name, latin_name, 
                   sample_image, created_at
            FROM gallery_favorites
            WHERE user_id = %s
            ORDER BY created_at DESC
        """, (user_id,))
        
        favorites = []
        for row in cursor.fetchall():
            favorites.append({
                'id': row[0],
                'flower_id': row[1],
                'folder_name': row[2],
                'chinese_name': row[3],
                'latin_name': row[4],
                'sample_image': row[5],
                'created_at': row[6].isoformat() if row[6] else None
            })
        
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
def add_gallery_favorite():
    """添加图库收藏"""
    user_id = g.user_id
    data = request.get_json()
    
    folder_name = data.get('folder_name')
    flower_id = data.get('flower_id', 0)
    chinese_name = data.get('chinese_name', '')
    latin_name = data.get('latin_name', '')
    sample_image = data.get('sample_image', '')
    
    if not folder_name:
        return jsonify({'success': False, 'error': '缺少文件夹名称'}), 400
    
    conn = get_db_connection()
    if conn is None:
        return jsonify({'success': False, 'error': '数据库连接失败'}), 500
    
    cursor = conn.cursor()
    try:
        # 检查是否已收藏
        cursor.execute("""
            SELECT id FROM gallery_favorites WHERE user_id = %s AND folder_name = %s
        """, (user_id, folder_name))
        if cursor.fetchone():
            return jsonify({'success': False, 'error': '已收藏过该图库'}), 400
        
        # 添加收藏
        cursor.execute("""
            INSERT INTO gallery_favorites 
            (user_id, flower_id, folder_name, chinese_name, latin_name, sample_image)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (user_id, flower_id, folder_name, chinese_name, latin_name, sample_image))
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
def remove_gallery_favorite(favorite_id):
    """取消图库收藏"""
    user_id = g.user_id
    
    conn = get_db_connection()
    if conn is None:
        return jsonify({'success': False, 'error': '数据库连接失败'}), 500
    
    cursor = conn.cursor()
    try:
        cursor.execute("""
            DELETE FROM gallery_favorites WHERE id = %s AND user_id = %s
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
def check_gallery_favorite():
    """检查是否已收藏"""
    user_id = g.user_id
    folder_name = request.args.get('folder_name', '')
    
    if not folder_name:
        return jsonify({'success': False, 'error': '缺少文件夹名称'}), 400
    
    conn = get_db_connection()
    if conn is None:
        return jsonify({'success': False, 'error': '数据库连接失败'}), 500
    
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT id FROM gallery_favorites WHERE user_id = %s AND folder_name = %s
        """, (user_id, folder_name))

        exists = cursor.fetchone() is not None

        return jsonify({'success': True, 'is_favorited': exists})
    finally:
        cursor.close()
        conn.close()


# encyclopedia.py 中已有 /api/encyclopedia/images/<path> 服务图库图片，无需重复定义
