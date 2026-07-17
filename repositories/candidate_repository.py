from models.candidate import Candidate
from extensions import db


class CandidateRepository:

    @staticmethod
    def find_all():
        return Candidate.query.order_by(Candidate.created_at.desc()).all()

    @staticmethod
    def find_by_id(candidate_id):
        return Candidate.query.get(candidate_id)

    @staticmethod
    def find_by_position(position_id):
        return Candidate.query.filter_by(position_id=position_id).all()

    @staticmethod
    def save(candidate):
        db.session.add(candidate)
        db.session.commit()
        return candidate

    @staticmethod
    def update(candidate):
        db.session.commit()
        return candidate

    @staticmethod
    def delete(candidate):
        db.session.delete(candidate)
        db.session.commit()
