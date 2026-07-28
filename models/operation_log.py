"""操作审计日志模型"""
from models.base import BaseModel
from extensions import db
from datetime import datetime


class OperationLog(BaseModel):
    """操作审计日志：记录谁在什么时候对什么做了什么"""
    __tablename__ = 'operation_log'

    user_id = db.Column(db.BigInteger, db.ForeignKey('user.id'), nullable=True, comment='操作人ID')
    username = db.Column(db.String(50), nullable=False, comment='操作人用户名（冗余，防止用户删除后丢失）')
    action = db.Column(db.String(30), nullable=False, comment='操作类型：create/delete/analyze/login/finish_interview 等')
    target_type = db.Column(db.String(30), nullable=True, comment='操作对象类型：candidate/position/interview_session/user')
    target_id = db.Column(db.BigInteger, nullable=True, comment='操作对象ID')
    target_name = db.Column(db.String(200), nullable=True, comment='操作对象名称（冗余，防止对象删除后丢失）')
    detail = db.Column(db.Text, nullable=True, comment='操作详情（JSON 或文本）')
    ip_address = db.Column(db.String(50), nullable=True, comment='操作IP')

    # 关联用户（可选，用户可能已被删除）
    operator = db.relationship('User', backref=db.backref('operation_logs', lazy='dynamic'),
                               foreign_keys=[user_id])

    def to_dict(self):
        return {
            'id': self.id,
            'user_id': self.user_id,
            'username': self.username,
            'action': self.action,
            'target_type': self.target_type,
            'target_id': self.target_id,
            'target_name': self.target_name,
            'detail': self.detail,
            'ip_address': self.ip_address,
            'created_at': self._datetime_str(self.created_at)
        }
