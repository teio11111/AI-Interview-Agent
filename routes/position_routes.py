from flask import Blueprint, request
from models.position import Position
from repositories.position_repository import PositionRepository
from utils.response import success, error, created
from utils.logger import logger
from utils.auth import login_required

position_bp = Blueprint('positions', __name__, url_prefix='/api/positions')


@position_bp.route('', methods=['GET'])
@login_required(role='admin')
def list_positions():
    positions = PositionRepository.find_all()
    return success([p.to_dict() for p in positions])


@position_bp.route('/<int:id>', methods=['GET'])
@login_required(role='admin')
def get_position(id):
    position = PositionRepository.find_by_id(id)
    if not position:
        return error('岗位不存在', 404)
    return success(position.to_dict())


@position_bp.route('', methods=['POST'])
@login_required(role='admin')
def create_position():
    data = request.get_json()
    if not data or not data.get('name'):
        return error('岗位名称不能为空', 400)

    position = Position(
        name=data['name'],
        jd_content=data.get('jd_content', ''),
        tech_requirements=data.get('tech_requirements', '')
    )
    PositionRepository.save(position)
    return created(position.to_dict())


@position_bp.route('/<int:id>', methods=['PUT'])
@login_required(role='admin')
def update_position(id):
    position = PositionRepository.find_by_id(id)
    if not position:
        return error('岗位不存在', 404)

    data = request.get_json()
    if data.get('name'):
        position.name = data['name']
    if 'jd_content' in data:
        position.jd_content = data['jd_content']
    if 'tech_requirements' in data:
        position.tech_requirements = data['tech_requirements']

    PositionRepository.update(position)
    return success(position.to_dict())


@position_bp.route('/<int:id>', methods=['DELETE'])
@login_required(role='admin')
def delete_position(id):
    position = PositionRepository.find_by_id(id)
    if not position:
        return error('岗位不存在', 404)
    PositionRepository.delete(position)
    return success(message='岗位已删除')


@position_bp.route('/<int:id>/analyze', methods=['POST'])
@login_required(role='admin')
def analyze_position(id):
    """AI 分析岗位（委托给岗位分析师 Agent）"""
    position = PositionRepository.find_by_id(id)
    if not position:
        return error('岗位不存在', 404)

    from services.interview_service import get_orchestrator
    orch = get_orchestrator()
    result = orch.analyze_position(
        position.name, position.tech_requirements, position.jd_content
    )

    if result:
        import json
        position.ai_analysis = json.dumps(result, ensure_ascii=False)
        PositionRepository.update(position)
        return success({'analysis': result, 'position': position.to_dict()})
    else:
        return error('AI 分析失败，请重试', 502)
