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
    topic_id = db.Column(db.BigInteger, db.ForeignKey('interview_topic.id'), nullable=True, comment='所属板块ID（板块分析后回填）')

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
            'topic_id': self.topic_id,
            'created_at': self._datetime_str(self.created_at)
        }


class InterviewTopic(BaseModel):
    """面试板块模型（结束面试后由「板块切分师」生成）

    一个板块 = 1 个话题方向（含主问题与若干追问），便于：
    - 面试工作台分块展示
    - 后续 3+1 评估师聚焦到板块，而非一次性读全部对话
    """
    __tablename__ = 'interview_topic'

    session_id = db.Column(db.BigInteger, db.ForeignKey('interview_session.id'), nullable=False, comment='关联面试会话')
    topic_index = db.Column(db.Integer, nullable=False, comment='板块序号（1-based，按对话时序）')
    title = db.Column(db.String(120), nullable=False, comment='板块标题（5-12字）')
    summary = db.Column(db.Text, comment='板块摘要（1-3 句）')
    dialog_ids_json = db.Column(db.Text, comment='该板块对话 ID 列表 JSON：如 "[1,2,3]"')

    session = db.relationship('InterviewSession', backref=db.backref('topics', cascade='all, delete-orphan'))

    def get_dialog_ids(self):
        import json
        if not self.dialog_ids_json:
            return []
        try:
            return json.loads(self.dialog_ids_json)
        except (json.JSONDecodeError, TypeError):
            return []

    def to_dict(self):
        return {
            'id': self.id,
            'session_id': self.session_id,
            'topic_index': self.topic_index,
            'title': self.title,
            'summary': self.summary,
            'dialog_ids': self.get_dialog_ids(),
            'created_at': self._datetime_str(self.created_at)
        }
