"""审计日志查询路由"""
from flask import Blueprint, request, render_template
from models.operation_log import OperationLog
from models.user import User
from utils.response import success, error
from utils.auth import login_required
from extensions import db
from sqlalchemy import desc

audit_bp = Blueprint('audit', __name__)


@audit_bp.route('/profile')
@login_required(role='admin')
def profile_page():
    """渲染"我的"页面"""
    return render_template('profile.html')


@audit_bp.route('/api/audit/logs', methods=['GET'])
@login_required(role='admin')
def get_logs():
    """查询操作日志

    Query params:
        user_id: 按用户筛选（可选）
        action: 按操作类型筛选（可选）
        target_type: 按对象类型筛选（可选）
        page: 页码（默认1）
        per_page: 每页条数（默认50，最大200）
    """
    page = request.args.get('page', 1, type=int)
    per_page = min(request.args.get('per_page', 50, type=int), 200)

    query = OperationLog.query

    # 筛选
    user_id = request.args.get('user_id', type=int)
    if user_id:
        query = query.filter(OperationLog.user_id == user_id)

    action = request.args.get('action')
    if action:
        query = query.filter(OperationLog.action == action)

    target_type = request.args.get('target_type')
    if target_type:
        query = query.filter(OperationLog.target_type == target_type)

    # 按时间倒序
    query = query.order_by(desc(OperationLog.created_at))

    # 分页
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)

    return success({
        'logs': [log.to_dict() for log in pagination.items],
        'total': pagination.total,
        'page': pagination.page,
        'per_page': pagination.per_page,
        'pages': pagination.pages
    })


@audit_bp.route('/api/audit/users', methods=['GET'])
@login_required(role='admin')
def get_users():
    """获取所有用户列表（用于筛选下拉）"""
    users = User.query.filter_by(role='admin').all()
    return success([u.to_dict() for u in users])
