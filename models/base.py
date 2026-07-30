from extensions import db
from utils import beijing_now


class BaseModel(db.Model):
    """模型基类，提供公共字段和方法"""
    __abstract__ = True

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    created_at = db.Column(db.DateTime, default=beijing_now, comment='创建时间')

    def to_dict(self):
        raise NotImplementedError

    def _datetime_str(self, dt):
        return dt.strftime('%Y-%m-%d %H:%M:%S') if dt else None
