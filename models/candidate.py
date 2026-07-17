from models.base import BaseModel
from extensions import db


class Candidate(BaseModel):
    """候选人模型"""
    __tablename__ = 'candidate'

    name = db.Column(db.String(50), nullable=False, comment='姓名')
    position_id = db.Column(db.BigInteger, db.ForeignKey('position.id'), nullable=False, comment='关联岗位')
    user_id = db.Column(db.BigInteger, db.ForeignKey('user.id'), nullable=True, comment='关联用户账户')
    resume_text = db.Column(db.Text, comment='简历文本（粘贴或 PDF 提取）')
    ai_analysis = db.Column(db.Text, comment='AI 分析结果 JSON')
    match_score = db.Column(db.Integer, comment='匹配度评分（0-100）')
    notes = db.Column(db.Text, nullable=True, comment='管理员备注')
    meta_evaluation = db.Column(db.Text, nullable=True, comment='综合元评估结果 JSON')
    meta_eval_round_count = db.Column(db.Integer, nullable=True, default=0, comment='综合元评估时包含的面试轮次数')

    # 关联
    position = db.relationship('Position', backref=db.backref('candidates', cascade='all, delete-orphan'))

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'position_id': self.position_id,
            'resume_text': self.resume_text,
            'ai_analysis': self.ai_analysis,
            'match_score': self.match_score,
            'notes': self.notes,
            'meta_evaluation': self.meta_evaluation,
            'meta_eval_round_count': self.meta_eval_round_count or 0,
            'created_at': self._datetime_str(self.created_at)
        }
