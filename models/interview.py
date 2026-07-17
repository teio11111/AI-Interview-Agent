from models.base import BaseModel
from extensions import db


class InterviewSession(BaseModel):
    """面试会话模型"""
    __tablename__ = 'interview_session'

    candidate_id = db.Column(db.BigInteger, db.ForeignKey('candidate.id'), nullable=False, comment='关联候选人')
    status = db.Column(db.String(20), default='preparing', comment='状态：preparing / in_progress / completed')
    questions_plan = db.Column(db.Text, comment='AI 生成的面试问题 JSON')
    report = db.Column(db.Text, comment='AI 最终评价报告')

    candidate = db.relationship('Candidate', backref=db.backref('sessions', cascade='all, delete-orphan'))

    def to_dict(self):
        return {
            'id': self.id,
            'candidate_id': self.candidate_id,
            'status': self.status,
            'questions_plan': self.questions_plan,
            'report': self.report,
            'created_at': self._datetime_str(self.created_at)
        }


class InterviewDialog(BaseModel):
    """面试对话模型"""
    __tablename__ = 'interview_dialog'

    session_id = db.Column(db.BigInteger, db.ForeignKey('interview_session.id'), nullable=False, comment='关联面试会话')
    question = db.Column(db.Text, comment='面试官问题')
    answer = db.Column(db.Text, comment='候选人回答摘要')
    ai_feedback = db.Column(db.Text, comment='AI 反馈 JSON')
    seq = db.Column(db.Integer, comment='顺序号')
    parent_seq = db.Column(db.Integer, comment='追问来源问题的序号，NULL表示非追问')

    session = db.relationship('InterviewSession', backref=db.backref('dialogs', cascade='all, delete-orphan'))

    def to_dict(self):
        return {
            'id': self.id,
            'session_id': self.session_id,
            'question': self.question,
            'answer': self.answer,
            'ai_feedback': self.ai_feedback,
            'seq': self.seq,
            'parent_seq': self.parent_seq,
            'created_at': self._datetime_str(self.created_at)
        }
