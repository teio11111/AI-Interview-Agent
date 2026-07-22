from models.interview import InterviewSession, InterviewDialog, InterviewTopic
from extensions import db
from sqlalchemy import update


class InterviewRepository:

    @staticmethod
    def find_session_by_id(session_id):
        return InterviewSession.query.get(session_id)

    @staticmethod
    def find_sessions_by_candidate(candidate_id):
        return InterviewSession.query.filter_by(candidate_id=candidate_id).all()

    @staticmethod
    def find_all_sessions():
        return InterviewSession.query.order_by(InterviewSession.created_at.desc()).all()

    @staticmethod
    def save_session(session):
        db.session.add(session)
        db.session.commit()
        return session

    @staticmethod
    def update_session(session):
        db.session.commit()
        return session

    @staticmethod
    def find_dialogs_by_session(session_id):
        return InterviewDialog.query.filter_by(session_id=session_id).order_by(InterviewDialog.seq).all()

    @staticmethod
    def save_dialog(dialog):
        db.session.add(dialog)
        db.session.commit()
        return dialog

    @staticmethod
    def delete_session(session):
        """删除面试会话（级联删除对话记录与板块）"""
        # 先删除关联的对话记录
        InterviewDialog.query.filter_by(session_id=session.id).delete()
        InterviewTopic.query.filter_by(session_id=session.id).delete()
        db.session.delete(session)
        db.session.commit()

    # ============== 板块（Topic）CRUD ==============

    @staticmethod
    def save_topic(topic):
        """保存一个板块（且同时回填该板块对话的 topic_id）"""
        db.session.add(topic)
        # 回填 dialog.topic_id
        db.session.flush()  # 先拿到 topic.id
        if topic.id and topic.dialog_ids_json:
            import json
            try:
                indexes = json.loads(topic.dialog_ids_json)
            except (json.JSONDecodeError, TypeError):
                indexes = []
            if indexes:
                db.session.execute(
                    update(InterviewDialog)
                    .where(InterviewDialog.session_id == topic.session_id,
                           InterviewDialog.seq.in_(indexes))
                    .values(topic_id=topic.id)
                )
        db.session.commit()
        return topic

    @staticmethod
    def find_topics_by_session(session_id):
        """获取一场面试的所有板块（按序号排序）"""
        return InterviewTopic.query.filter_by(session_id=session_id).order_by(InterviewTopic.topic_index).all()

    @staticmethod
    def delete_topics_by_session(session_id):
        """删除一场面试的所有板块（及 dialog.topic_id 回填）"""
        db.session.execute(
            update(InterviewDialog)
            .where(InterviewDialog.session_id == session_id)
            .values(topic_id=None)
        )
        InterviewTopic.query.filter_by(session_id=session_id).delete()
        db.session.commit()
