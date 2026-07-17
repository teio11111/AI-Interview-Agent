from models.base import BaseModel
from extensions import db


class Position(BaseModel):
    """岗位模型"""
    __tablename__ = 'position'

    name = db.Column(db.String(100), nullable=False, comment='岗位名称')
    jd_content = db.Column(db.Text, comment='JD 全文')
    tech_requirements = db.Column(db.String(500), comment='技术要求，逗号分隔')
    ai_analysis = db.Column(db.Text, comment='AI 分析结果 JSON')

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'jd_content': self.jd_content,
            'tech_requirements': self.tech_requirements,
            'ai_analysis': self.ai_analysis,
            'created_at': self._datetime_str(self.created_at)
        }
