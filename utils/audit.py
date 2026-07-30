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


def _has_interview_log(action, session_id):
    """判断指定面试操作是否已记录，避免 SSE 重连或重复提交产生重复日志。"""
    from models.operation_log import OperationLog

    return OperationLog.query.filter_by(
        action=action,
        target_type='interview_session',
        target_id=session_id
    ).first() is not None


def log_interview_created(interview_session, candidate_name):
    """记录面试会话创建，并按候选人的会话时间顺序计算轮次。"""
    if _has_interview_log('create', interview_session.id):
        return False

    from models.interview import InterviewSession
    from sqlalchemy import and_, or_

    round_number = InterviewSession.query.filter(
        InterviewSession.candidate_id == interview_session.candidate_id,
        or_(
            InterviewSession.created_at < interview_session.created_at,
            and_(
                InterviewSession.created_at == interview_session.created_at,
                InterviewSession.id <= interview_session.id
            )
        )
    ).count()
    log_operation(
        'create', 'interview_session', interview_session.id, candidate_name,
        f'第 {max(round_number, 1)} 轮'
    )
    return True


def log_interview_finished(interview_session, candidate_name, topic_count, dialog_count):
    """记录面试结束；同一会话只记录一次。"""
    if _has_interview_log('finish_interview', interview_session.id):
        return False

    log_operation(
        'finish_interview', 'interview_session', interview_session.id, candidate_name,
        f'板块 {topic_count} 个, 对话 {dialog_count} 轮'
    )
    return True
