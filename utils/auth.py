"""认证工具模块"""
from functools import wraps
from flask import session, redirect, url_for, request
from werkzeug.security import generate_password_hash, check_password_hash
from extensions import db


def hash_password(password):
    """生成密码哈希"""
    return generate_password_hash(password)


def verify_password(password_hash, password):
    """验证密码"""
    return check_password_hash(password_hash, password)


def get_current_user():
    """从 session 获取当前用户"""
    user_id = session.get('user_id')
    if not user_id:
        return None
    from models.user import User
    return db.session.get(User, user_id)


def login_required(role=None):
    """登录守卫装饰器

    Args:
        role: 可选，限定角色访问。如 'admin' 或 'candidate'
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            user = get_current_user()
            if not user:
                # API 请求返回 JSON 401，页面请求跳转登录
                if request.path.startswith('/api/'):
                    return {'code': 401, 'msg': '请先登录'}, 401
                return redirect(url_for('auth.login_page', next=request.url))
            if role and user.role != role:
                if request.path.startswith('/api/'):
                    return {'code': 403, 'msg': '权限不足'}, 403
                # admin 访问 candidate 页面 或反之，跳转到对应首页
                if user.role == 'admin':
                    return redirect(url_for('home.index'))
                else:
                    return redirect(url_for('candidate_portal.portal_page'))
            return f(*args, **kwargs)
        return decorated_function
    return decorator
