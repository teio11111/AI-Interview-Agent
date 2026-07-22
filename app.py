from flask import Flask, redirect, url_for
from extensions import db, socketio
from utils.logger import logger


def create_app():
    """创建并配置 Flask 应用"""
    app = Flask(__name__)

    # 加载配置
    from config.config import Config
    app.config.from_object(Config)

    # 初始化数据库
    db.init_app(app)
    
    # 初始化 SocketIO
    socketio.init_app(app)

    # 注册路由蓝图
    from routes.position_routes import position_bp
    from routes.candidate_routes import candidate_bp
    from routes.interview_routes import interview_bp, home_bp
    from routes.auth_routes import auth_bp
    from routes.candidate_portal_routes import candidate_portal_bp
    from routes.stream_routes import stream_bp
    from routes.asr_routes import asr_bp
    app.register_blueprint(auth_bp)
    app.register_blueprint(home_bp)
    app.register_blueprint(position_bp)
    app.register_blueprint(candidate_bp)
    app.register_blueprint(interview_bp)
    app.register_blueprint(candidate_portal_bp)
    app.register_blueprint(stream_bp)
    app.register_blueprint(asr_bp)

    # 导入所有模型并创建表
    with app.app_context():
        from models import position, candidate, interview, user  # noqa: F401
        db.create_all()

    # 模板上下文：注入当前用户
    @app.context_processor
    def inject_user():
        from utils.auth import get_current_user
        return {'current_user': get_current_user()}

    # 未登录访问根路径时跳转登录
    @app.before_request
    def redirect_root():
        from flask import request, session
        if request.path == '/' and not session.get('user_id'):
            return redirect(url_for('auth.login_page'))

    return app


if __name__ == '__main__':
    app = create_app()
    
    # SocketIO 事件处理
    from flask_socketio import join_room, leave_room
    
    @socketio.on('join')
    def handle_join(room):
        join_room(room)
        logger.info(f'[SocketIO] 客户端加入房间: {room}')
    
    @socketio.on('leave')
    def handle_leave(room):
        leave_room(room)
    
    socketio.run(app, host='0.0.0.0', port=8088, debug=True, allow_unsafe_werkzeug=True)
