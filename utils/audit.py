"""审计日志工具模块"""
from flask import session, request
from utils.logger import logger


def log_operation(action, target_type=None, target_id=None, target_name=None, detail=None):
    """记录操作审计日志

    在需要记录操作的地方调用即可：
        from utils.audit import log_operation
        log_operation('create', 'candidate', candidate.id, candidate.name)

    Args:
        action: 操作类型 (create/delete/analyze/login/logout/finish_interview/change_password 等)
        target_type: 操作对象类型 (candidate/position/interview_session/user)
        target_id: 操作对象ID
        target_name: 操作对象名称（冗余存储）
        detail: 额外详情（文本或 JSON 字符串）
    """
    from models.operation_log import OperationLog
    from extensions import db

    user_id = session.get('user_id')
    # 尝试获取用户名
    username = 'anonymous'
    if user_id:
        from models.user import User
        user = db.session.get(User, user_id)
        if user:
            username = user.username

    try:
        log = OperationLog(
            user_id=user_id,
            username=username,
            action=action,
            target_type=target_type,
            target_id=target_id,
            target_name=(target_name or '')[:200],
            detail=detail,
            ip_address=request.remote_addr if request else None
        )
        db.session.add(log)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        logger.warning(f'[审计日志] 写入失败: {e}')
