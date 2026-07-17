from flask import Blueprint, request, session, render_template, redirect, url_for
from models.user import User
from utils.auth import hash_password, verify_password
from utils.response import success, error
from utils.logger import logger
from extensions import db

auth_bp = Blueprint('auth', __name__)


@auth_bp.route('/login')
def login_page():
    """渲染登录页面"""
    # 已登录则跳转对应首页
    user_id = session.get('user_id')
    if user_id:
        user = db.session.get(User, user_id)
        if user:
            if user.role == 'admin':
                return redirect(url_for('home.index'))
            else:
                return redirect(url_for('candidate_portal.portal_page'))
    return render_template('login.html')


@auth_bp.route('/api/auth/login', methods=['POST'])
def login():
    """登录"""
    data = request.get_json()
    if not data or not data.get('username') or not data.get('password'):
        return error('用户名和密码不能为空', 400)

    user = User.query.filter_by(username=data['username']).first()
    if not user or not verify_password(user.password_hash, data['password']):
        return error('用户名或密码错误', 401)

    session['user_id'] = user.id
    session['user_role'] = user.role
    logger.info(f'用户 {user.username} 登录成功 (role={user.role})')

    redirect_url = '/' if user.role == 'admin' else '/candidate'
    return success({'user': user.to_dict(), 'redirect': redirect_url})


@auth_bp.route('/api/auth/register', methods=['POST'])
def register():
    """候选人自注册"""
    data = request.get_json()
    if not data or not data.get('username') or not data.get('password'):
        return error('用户名和密码不能为空', 400)

    # 检查用户名是否已存在
    existing = User.query.filter_by(username=data['username']).first()
    if existing:
        return error('用户名已存在', 400)

    user = User(
        username=data['username'],
        password_hash=hash_password(data['password']),
        role='candidate'
    )
    db.session.add(user)
    db.session.commit()

    session['user_id'] = user.id
    session['user_role'] = user.role
    logger.info(f'候选人 {user.username} 注册成功')

    return success({'user': user.to_dict(), 'redirect': '/candidate'}, message='注册成功')


@auth_bp.route('/api/auth/logout', methods=['POST'])
def logout():
    """登出"""
    session.clear()
    return success(message='已登出')


@auth_bp.route('/api/auth/me', methods=['GET'])
def me():
    """获取当前用户"""
    user_id = session.get('user_id')
    if not user_id:
        return error('未登录', 401)
    user = db.session.get(User, user_id)
    if not user:
        session.clear()
        return error('用户不存在', 401)
    return success(user.to_dict())
