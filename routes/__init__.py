"""
routes包初始化文件 - 统一注册所有蓝图
"""

from flask import Flask


def register_routes(app: Flask):
    """注册所有路由蓝图"""

    # 延迟导入避免循环依赖
    from . import gallery, encyclopedia, identify, auth, community, user, admin, feedback

    # 注册蓝图
    app.register_blueprint(gallery.bp)  # 图库
    app.register_blueprint(encyclopedia.bp)  # 百科
    app.register_blueprint(identify.bp)  # 识别
    app.register_blueprint(auth.bp)  # 用户认证
    app.register_blueprint(community.bp)  # 社区功能
    app.register_blueprint(user.bp)  # 用户资料和成长体系
    app.register_blueprint(admin.admin_bp)  # 管理后台
    app.register_blueprint(feedback.bp)  # 反馈管理
    print("[INFO] 所有路由蓝图注册完成")


__all__ = ['register_routes']
