import os
import time

# 仅设置当前 Flask 进程时区，不修改云服务器全局配置。
os.environ['TZ'] = 'Asia/Shanghai'
if hasattr(time, 'tzset'):
    time.tzset()

from flask import Flask, redirect, url_for
from extensions import db, socketio
from utils.logger import logger


def create_app():
    """创建并配置 Flask 应用"""
    app = Flask(__name__)

    # 加载配置
    from config.config import Config
    app.config.from_object(Config)
    # 【v4.1 演示前】启动时安全检查
    Config.warn_if_insecure()

    # 初始化数据库
    db.init_app(app)
    
    # 初始化 SocketIO
    socketio.init_app(app)

    # 注册路由蓝图
    from routes.position_routes import position_bp
    from routes.candidate_routes import candidate_bp
    from routes.interview_routes import interview_bp, home_bp
    from routes.auth_routes import auth_bp
    from routes.stream_routes import stream_bp
    from routes.asr_routes import asr_bp
    from routes.audit_routes import audit_bp
    app.register_blueprint(auth_bp)
    app.register_blueprint(home_bp)
    app.register_blueprint(position_bp)
    app.register_blueprint(candidate_bp)
    app.register_blueprint(interview_bp)
    app.register_blueprint(stream_bp)
    app.register_blueprint(asr_bp)
    app.register_blueprint(audit_bp)

    # 导入所有模型并创建表
    with app.app_context():
        from models import position, candidate, interview, user, operation_log  # noqa: F401
        db.create_all()

    # 模板上下文：注入当前用户
    @app.context_processor
    def inject_user():
        from utils.auth import get_current_user
        return {'current_user': get_current_user()}

    # 模板上下文：注入更新日志（首页 Dashboard 使用）
    @app.context_processor
    def inject_changelog():
        import json
        import os
        changelog_path = os.path.join(os.path.dirname(__file__), 'data', 'changelog.json')
        try:
            with open(changelog_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return {'changelog_versions': data.get('versions', [])}
        except Exception:
            return {'changelog_versions': []}

    # 未登录访问根路径时跳转登录
    @app.before_request
    def redirect_root():
        from flask import request, session
        if request.path == '/' and not session.get('user_id'):
            return redirect(url_for('auth.login_page'))

    return app


# SocketIO 事件处理（必须在 create_app 外注册，否则 waitress-serve --call 启动时不会执行）
from flask_socketio import join_room, leave_room

@socketio.on('join')
def handle_join(room):
    join_room(room)
    logger.info(f'[SocketIO] 客户端加入房间: {room}')

@socketio.on('leave')
def handle_leave(room):
    leave_room(room)


if __name__ == '__main__':
    app = create_app()

    # 【v3.1 修复】改用 waitress 提供 WSGI 服务
    # 原 socketio.run(app, ..., allow_unsafe_werkzeug=True) 用的是 Werkzeug dev server，
    # 它会缓冲 SSE 输出，导致前端进度条只看到第一个事件后就卡 75%，要等 5s 心跳才 flush。
    # waitress 不会缓冲流式响应，每个 yield 立即送到浏览器，进度条能平滑增长。
    # SocketIO 中间件已在 socketio.init_app(app) 时挂到 app.wsgi_app，waitress 会自动走它。
    from waitress import serve
    logger.info('[启动] 使用 waitress 提供 WSGI 服务（流式响应零缓冲）')
    serve(app, host='0.0.0.0', port=8088, threads=8)
