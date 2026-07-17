from models.interview import InterviewSession, InterviewDialog
from extensions import db


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
