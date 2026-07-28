from flask import Blueprint, request, session, render_template, redirect, url_for
from models.user import User
from utils.auth import hash_password, verify_password, login_required
from utils.response import success, error
from utils.logger import logger
from utils.audit import log_operation
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
                # 【隐藏】候选人门户已下线，清除 session 强制回登录页
                session.clear()
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

    # 【隐藏】候选人门户已下线，拒绝候选人登录
    if user.role != 'admin':
        return error('候选人门户已下线，请使用管理员账号登录', 403)

    session['user_id'] = user.id
    session['user_role'] = user.role
    logger.info(f'用户 {user.username} 登录成功 (role={user.role})')
    log_operation('login', 'user', user.id, user.username)

    redirect_url = '/' if user.role == 'admin' else '/candidate'
    return success({'user': user.to_dict(), 'redirect': redirect_url})


@auth_bp.route('/api/auth/register', methods=['POST'])
def register():
    """候选人自注册（已下线）"""
    # 【隐藏】候选人门户已下线，注册入口关闭
    return error('候选人门户已下线，请联系管理员', 403)


@auth_bp.route('/api/auth/logout', methods=['POST'])
def logout():
    """登出"""
    # 在清除 session 前记录审计
    user_id = session.get('user_id')
    if user_id:
        user = db.session.get(User, user_id)
        if user:
            log_operation('logout', 'user', user.id, user.username)
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


@auth_bp.route('/api/auth/change-password', methods=['POST'])
@login_required()
def change_password():
    """修改密码"""
    data = request.get_json()
    if not data:
        return error('请求体不能为空', 400)

    old_password = data.get('old_password', '')
    new_password = data.get('new_password', '')

    if not old_password or not new_password:
        return error('旧密码和新密码不能为空', 400)
    if len(new_password) < 6:
        return error('新密码至少 6 位', 400)

    user = db.session.get(User, session['user_id'])
    if not user:
        return error('用户不存在', 404)

    if not verify_password(user.password_hash, old_password):
        return error('旧密码不正确', 400)

    user.password_hash = hash_password(new_password)
    db.session.commit()
    log_operation('change_password', 'user', user.id, user.username)
    logger.info(f'用户 {user.username} 修改密码成功')
    return success(message='密码修改成功')


@auth_bp.route('/api/auth/change-username', methods=['POST'])
@login_required()
def change_username():
    """修改用户名"""
    data = request.get_json()
    if not data:
        return error('请求体不能为空', 400)

    new_username = data.get('new_username', '').strip()
    password = data.get('password', '')

    if not new_username or not password:
        return error('新用户名和密码不能为空', 400)
    if len(new_username) < 2:
        return error('用户名至少 2 个字符', 400)
    if len(new_username) > 30:
        return error('用户名最多 30 个字符', 400)

    user = db.session.get(User, session['user_id'])
    if not user:
        return error('用户不存在', 404)

    if not verify_password(user.password_hash, password):
        return error('密码不正确', 400)

    old_username = user.username
    if new_username == old_username:
        return error('新用户名和旧用户名相同', 400)

    # 检查用户名是否已被占用
    existing = User.query.filter_by(username=new_username).first()
    if existing:
        return error(f'用户名 "{new_username}" 已被使用', 400)

    user.username = new_username
    db.session.commit()
    log_operation('change_username', 'user', user.id, new_username, f'旧用户名: {old_username}')
    logger.info(f'用户 {old_username} 改名为 {new_username}')
    return success(message=f'用户名已修改为 {new_username}')
