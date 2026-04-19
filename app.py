"""
Flask后端服务 - 花卉识别系统主入口
模块化架构版本

启动命令: python app.py
"""

import os
import sys

# 确保项目根目录在Python路径中
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from flask import Flask, jsonify, g
from flask_cors import CORS

# 导入配置
from config import FLASK_CONFIG

# 导入路由注册函数
from routes import register_routes

import traceback

# 创建Flask应用
app = Flask(__name__, static_folder='static', static_url_path='/static')

# 配置 CORS - 允许所有来源和所有方法
CORS(app, resources={
    r"/api/*": {
        "origins": "*",
        "supports_credentials": True,
        "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        "allowed_headers": ["Content-Type", "Authorization"]
    }
}, expose_headers=['Content-Type', 'Authorization'])

# 注册所有路由
register_routes(app)

# 全局错误处理
@app.errorhandler(Exception)
def handle_error(e):
    print(traceback.format_exc())
    return jsonify({'success': False, 'error': str(e)}), 500

# ============== 启动信息 ==============

def print_startup_info():
    """打印启动信息"""
    print("=" * 50)
    print("Flower Recognition API Server")
    print("模块化架构版本")
    print("=" * 50)
    print("\n可用接口:")
    print("  健康检查:")
    print("    GET  /api/health              - 服务健康检查")
    print("")
    print("  花卉识别:")
    print("    POST /api/classify            - 识别花卉图像")
    print("    GET  /api/classes             - 获取所有花卉类别")
    print("    GET  /api/flower-info/<id>    - 获取花卉信息")
    print("")
    print("  花卉百科:")
    print("    GET  /api/encyclopedia/search - 搜索百科")
    print("    GET  /api/encyclopedia/detail/<id> - 获取详情")
    print("    GET  /api/encyclopedia/categories - 获取分类")
    print("")
    print("  花卉图库:")
    print("    GET  /api/gallery/flowers     - 获取所有图库")
    print("    GET  /api/gallery/flower/<name> - 获取花卉图片")
    print("    GET  /api/gallery/search       - 搜索图库")
    print("")
    print("=" * 50)
    print(f"服务地址: http://{FLASK_CONFIG['host']}:{FLASK_CONFIG['port']}")
    print("=" * 50)


if __name__ == '__main__':
    print_startup_info()
    
    # 预加载模型（可选，取消注释以启用）
    # from routes.identify import load_model
    # load_model()
    
    # 启动服务
    app.run(
        host=FLASK_CONFIG['host'],
        port=FLASK_CONFIG['port'],
        debug=FLASK_CONFIG['debug']
    )
