"""
百科路由模块 - 花卉百科相关API
"""

import json
import os
from flask import Blueprint, request, jsonify, send_file

from config import IMAGE_BASE_URL
from models import get_db_connection, execute_query

bp = Blueprint('encyclopedia', __name__, url_prefix='/api/encyclopedia')

# 导入认证装饰器
from routes.auth import token_required


# ============== 百科收藏表初始化 ==============

def init_encyclopedia_favorites_table():
    """初始化百科收藏表"""
    conn = get_db_connection()
    if conn is None:
        return False
    cursor = conn.cursor()
    try:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS encyclopedia_favorites (
                id INT AUTO_INCREMENT PRIMARY KEY,
                user_id VARCHAR(8) NOT NULL,
                flower_id INT NOT NULL,
                chinese_name VARCHAR(100) NOT NULL,
                latin_name VARCHAR(200) DEFAULT '',
                image_url VARCHAR(500) DEFAULT '',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE KEY uk_user_flower (user_id, flower_id),
                INDEX idx_user_id (user_id),
                INDEX idx_flower_id (flower_id)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='百科收藏表'
        """)
        conn.commit()
        print("[INFO] 百科收藏表初始化完成")
        return True
    except Exception as e:
        print(f"[ERROR] 百科收藏表初始化失败: {e}")
        conn.rollback()
        return False
    finally:
        cursor.close()
        conn.close()

# 模块加载时初始化表
try:
    init_encyclopedia_favorites_table()
except:
    pass


# ============== 工具函数 ==============

def process_image_data(flower):
    """处理花卉图片数据"""
    if flower.get('image_url'):
        try:
            image_data = json.loads(flower['image_url'])
            
            if isinstance(image_data, dict) and 'images' in image_data:
                images_list = image_data.get('images', [])
                flower_images = []
                
                for img in images_list:
                    if isinstance(img, dict):
                        if 'relative_path' in img:
                            flower_images.append(f'/api/encyclopedia/images/{img["relative_path"]}')
                        elif 'filename' in img and flower.get('chinese_name'):
                            flower_images.append(f'/api/encyclopedia/images/{flower["chinese_name"]}/{img["filename"]}')
                        elif 'absolute_path' in img:
                            abs_path = img['absolute_path']
                            parts = abs_path.split('ChineseFlowers120/')
                            if len(parts) > 1:
                                relative = parts[1].replace("\\", "/")
                                flower_images.append('/api/encyclopedia/images/' + relative)
                    elif isinstance(img, str):
                        flower_images.append(f'/api/encyclopedia/images/{img}')
                
                flower['images'] = flower_images[:20]
                
                if 'primary_image' in image_data and image_data['primary_image']:
                    flower['image_url'] = f'/api/encyclopedia/images/{image_data["primary_image"]}'
                elif flower['images']:
                    flower['image_url'] = flower['images'][0]
                else:
                    flower['image_url'] = None
                
                flower['total_images'] = len(flower_images)
                
            elif isinstance(image_data, list):
                flower['images'] = [f'/api/encyclopedia/images/{img}' for img in image_data[:20]]
                flower['image_url'] = flower['images'][0] if flower['images'] else None
                flower['total_images'] = len(image_data)
            else:
                flower['images'] = []
                flower['image_url'] = None
                flower['total_images'] = 0
                
        except (json.JSONDecodeError, TypeError):
            image_paths = str(flower['image_url']).split(',')
            flower['images'] = [f'/api/encyclopedia/images/{path.strip()}' 
                               for path in image_paths if path.strip()][:20]
            flower['image_url'] = flower['images'][0] if flower['images'] else None
            flower['total_images'] = len(image_paths)
    else:
        flower['images'] = []
        flower['image_url'] = None
        flower['total_images'] = 0
    
    return flower


# ============== 百科API ==============

@bp.route('/search', methods=['GET'])
def search_flowers():
    """搜索花卉百科"""
    try:
        keyword = request.args.get('keyword', '').strip()
        category_id = request.args.get('category_id', '')
        page = int(request.args.get('page', 1))
        page_size = int(request.args.get('page_size', 10))
        
        conn = get_db_connection()
        if conn is None:
            return jsonify({'success': False, 'error': '数据库连接失败'}), 500
        
        cursor = conn.cursor()
        
        where_conditions = []
        params = []
        
        if keyword:
            where_conditions.append("(chinese_name LIKE %s OR latin_name LIKE %s OR family LIKE %s OR genus LIKE %s)")
            like_keyword = f'%{keyword}%'
            params.extend([like_keyword, like_keyword, like_keyword, like_keyword])
        
        if category_id:
            where_conditions.append("(category_id = %s OR family = %s OR genus = %s)")
            params.extend([category_id, category_id, category_id])
        
        where_clause = "WHERE " + " AND ".join(where_conditions) if where_conditions else ""
        
        # 查询总数
        count_sql = f"SELECT COUNT(*) as total FROM flowers {where_clause}"
        cursor.execute(count_sql, params)
        total = cursor.fetchone()[0]
        
        # 分页查询
        offset = (page - 1) * page_size
        query_sql = f"""
            SELECT id, chinese_name, latin_name, family, genus, 
                   morphology, habitat, growth_habit, ornamental_value,
                   care_methods, flower_language, category_id, image_url, data_source
            FROM flowers {where_clause} 
            ORDER BY id 
            LIMIT %s OFFSET %s
        """
        cursor.execute(query_sql, params + [page_size, offset])
        columns = [desc[0] for desc in cursor.description]
        flowers = [dict(zip(columns, row)) for row in cursor.fetchall()]
        
        # 处理图片信息
        flowers = [process_image_data(flower) for flower in flowers]
        
        cursor.close()
        conn.close()
        
        return jsonify({
            'success': True,
            'data': {
                'flowers': flowers,
                'pagination': {
                    'page': page,
                    'page_size': page_size,
                    'total': total,
                    'total_pages': (total + page_size - 1) // page_size
                }
            }
        })
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500


@bp.route('/detail/<int:flower_id>', methods=['GET'])
def get_flower_detail(flower_id):
    """获取花卉详情"""
    try:
        conn = get_db_connection()
        if conn is None:
            return jsonify({'success': False, 'error': '数据库连接失败'}), 500
        
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, chinese_name, latin_name, family, genus,
morphology, habitat, growth_habit, ornamental_value,
                   care_methods, flower_language, category_id, image_url, 
                   data_source, collected_date
            FROM flowers WHERE id = %s
        """, (flower_id,))
        
        columns = [desc[0] for desc in cursor.description]
        row = cursor.fetchone()
        flower = dict(zip(columns, row)) if row else None
        
        if flower:
            flower = process_image_data(flower)
        
        cursor.close()
        conn.close()
        
        if flower:
            return jsonify({'success': True, 'data': flower})
        else:
            return jsonify({'success': False, 'error': '花卉不存在'}), 404
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500


@bp.route('/search/by-name', methods=['GET'])
def search_flower_by_name():
    """根据花卉名称（中文或英文）搜索百科，返回匹配的百科记录"""
    try:
        name = request.args.get('name', '').strip()
        if not name:
            return jsonify({'success': False, 'error': '缺少花卉名称'}), 400

        conn = get_db_connection()
        if conn is None:
            return jsonify({'success': False, 'error': '数据库连接失败'}), 500

        cursor = conn.cursor()
        # 支持中文名和拉丁名精确匹配（拉丁名使用LOWER()实现大小写不敏感）
        cursor.execute("""
            SELECT id, chinese_name, latin_name, family, genus, image_url
            FROM flowers
            WHERE chinese_name = %s OR LOWER(latin_name) = LOWER(%s)
            LIMIT 1
        """, (name, name))

        row = cursor.fetchone()
        if row:
            columns = [desc[0] for desc in cursor.description]
            flower = dict(zip(columns, row))
            flower = process_image_data(flower)
            cursor.close()
            conn.close()
            return jsonify({'success': True, 'data': flower})
        else:
            # 模糊匹配：中文名模糊匹配 或 拉丁名模糊匹配（大小写不敏感）
            cursor.execute("""
                SELECT id, chinese_name, latin_name, family, genus, image_url
                FROM flowers
                WHERE chinese_name LIKE %s OR LOWER(latin_name) LIKE LOWER(%s)
                LIMIT 5
            """, (f'%{name}%', f'%{name}%'))
            rows = cursor.fetchall()
            if rows:
                columns = [desc[0] for desc in cursor.description]
                flowers = [dict(zip(columns, row)) for row in rows]
                flowers = [process_image_data(f) for f in flowers]
                cursor.close()
                conn.close()
                return jsonify({'success': True, 'data': flowers, 'multiple': True})
            cursor.close()
            conn.close()
            return jsonify({'success': False, 'error': '未找到匹配的花卉'}), 404

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500


@bp.route('/categories', methods=['GET'])
def get_categories():
    """获取分类"""
    try:
        cat_type = request.args.get('type', 'family')
        
        conn = get_db_connection()
        if conn is None:
            return jsonify({'success': False, 'error': '数据库连接失败'}), 500
        
        cursor = conn.cursor()
        
        if cat_type == 'genus':
            cursor.execute("""
                SELECT DISTINCT genus as name FROM flowers 
                WHERE genus IS NOT NULL AND genus != '' ORDER BY genus
            """)
        else:
            cursor.execute("""
                SELECT DISTINCT family as name FROM flowers 
                WHERE family IS NOT NULL AND family != '' ORDER BY family
            """)
        
        categories = [row[0] for row in cursor.fetchall()]
        
        cursor.close()
        conn.close()
        
        return jsonify({'success': True, 'categories': categories, 'type': cat_type})
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@bp.route('/images/<path:filename>')
def serve_image(filename):
    """提供图片访问服务"""
    try:
        file_path = os.path.join(IMAGE_BASE_URL, filename)
        file_path = os.path.normpath(file_path)
        
        # 安全检查：确保路径在允许的目录内
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


# ============== 百科收藏API ==============

@bp.route('/favorites', methods=['GET'])
@token_required
def get_encyclopedia_favorites():
    """获取用户的百科收藏列表"""
    from flask import g
    user_id = g.user_id
    
    conn = get_db_connection()
    if conn is None:
        return jsonify({'success': False, 'error': '数据库连接失败'}), 500
    
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT id, flower_id, chinese_name, latin_name, image_url, created_at
            FROM encyclopedia_favorites
            WHERE user_id = %s
            ORDER BY created_at DESC
        """, (user_id,))
        
        favorites = []
        for row in cursor.fetchall():
            favorites.append({
                'id': row[0],
                'flower_id': row[1],
                'chinese_name': row[2],
                'latin_name': row[3],
                'image_url': row[4],
                'created_at': row[5].isoformat() if row[5] else None
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
def add_encyclopedia_favorite():
    """添加百科收藏"""
    from flask import g
    user_id = g.user_id
    data = request.get_json()
    
    flower_id = data.get('flower_id')
    chinese_name = data.get('chinese_name', '')
    latin_name = data.get('latin_name', '')
    image_url = data.get('image_url', '')
    
    if not flower_id:
        return jsonify({'success': False, 'error': '缺少花卉ID'}), 400
    
    if not chinese_name:
        return jsonify({'success': False, 'error': '缺少花卉名称'}), 400
    
    conn = get_db_connection()
    if conn is None:
        return jsonify({'success': False, 'error': '数据库连接失败'}), 500
    
    cursor = conn.cursor()
    try:
        # 检查是否已收藏
        cursor.execute("""
            SELECT id FROM encyclopedia_favorites WHERE user_id = %s AND flower_id = %s
        """, (user_id, flower_id))
        if cursor.fetchone():
            return jsonify({'success': False, 'error': '已收藏过该花卉'}), 400
        
        # 添加收藏
        cursor.execute("""
            INSERT INTO encyclopedia_favorites (user_id, flower_id, chinese_name, latin_name, image_url)
            VALUES (%s, %s, %s, %s, %s)
        """, (user_id, flower_id, chinese_name, latin_name, image_url))
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
def remove_encyclopedia_favorite(favorite_id):
    """取消百科收藏"""
    from flask import g
    user_id = g.user_id
    
    conn = get_db_connection()
    if conn is None:
        return jsonify({'success': False, 'error': '数据库连接失败'}), 500
    
    cursor = conn.cursor()
    try:
        cursor.execute("""
            DELETE FROM encyclopedia_favorites WHERE id = %s AND user_id = %s
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
def check_encyclopedia_favorite():
    """检查是否已收藏"""
    from flask import g
    user_id = g.user_id
    flower_id = request.args.get('flower_id', type=int)
    
    if not flower_id:
        return jsonify({'success': False, 'error': '缺少花卉ID'}), 400
    
    conn = get_db_connection()
    if conn is None:
        return jsonify({'success': False, 'error': '数据库连接失败'}), 500
    
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT id FROM encyclopedia_favorites WHERE user_id = %s AND flower_id = %s
        """, (user_id, flower_id))
        
        exists = cursor.fetchone() is not None
        
        return jsonify({'success': True, 'is_favorited': exists})
    finally:
        cursor.close()
        conn.close()
