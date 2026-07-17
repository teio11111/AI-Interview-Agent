from models.position import Position
from extensions import db


class PositionRepository:

    @staticmethod
    def find_all():
        return Position.query.order_by(Position.created_at.desc()).all()

    @staticmethod
    def find_by_id(position_id):
        return Position.query.get(position_id)

    @staticmethod
    def save(position):
        db.session.add(position)
        db.session.commit()
        return position

    @staticmethod
    def update(position):
        db.session.commit()
        return position

    @staticmethod
    def delete(position):
        db.session.delete(position)
        db.session.commit()
