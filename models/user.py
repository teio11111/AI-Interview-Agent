from models.base import BaseModel
from extensions import db


class User(BaseModel):
    """用户模型"""
    __tablename__ = 'user'

    username = db.Column(db.String(50), unique=True, nullable=False, comment='用户名')
    password_hash = db.Column(db.String(256), nullable=False, comment='密码哈希')
    role = db.Column(db.String(20), default='candidate', comment='角色：admin / candidate')

    # 一个用户可以有多条候选人记录（投递多个岗位）
    candidates = db.relationship('Candidate', backref='user_account', lazy='dynamic',
                                 foreign_keys='Candidate.user_id')

    def to_dict(self):
        return {
            'id': self.id,
            'username': self.username,
            'role': self.role,
            'created_at': self._datetime_str(self.created_at)
        }
