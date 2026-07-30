from flask import Blueprint, request
from models.position import Position
from repositories.position_repository import PositionRepository
from utils.response import success, error, created
from utils.logger import logger
from utils.auth import login_required
from utils.audit import log_operation
from utils.pdf_parser import extract_text_from_pdf

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
    log_operation('create', 'position', position.id, position.name)
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
    name = position.name
    PositionRepository.delete(position)
    log_operation('delete', 'position', id, name)
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
        log_operation('analyze', 'position', position.id, position.name)
        return success({'analysis': result, 'position': position.to_dict()})
    else:
        return error('AI 分析失败，请重试', 502)


@position_bp.route('/parse-jd', methods=['POST'])
@login_required(role='admin')
def parse_jd():
    """从 PDF 或文本中解析 JD 结构化字段

    支持两种入参：
    - multipart/form-data 包含 'file' 字段（PDF 文件）
    - application/json 包含 'text' 字段（纯文本）

    Returns:
        {name, jd_content, tech_requirements}
    """
    from agents.position_jd_parser import PositionJdParserAgent

    raw_text = ''
    # 1. PDF 上传路径
    if 'file' in request.files:
        f = request.files['file']
        if not f.filename.endswith('.pdf'):
            return error('只支持 PDF 格式', 400)
        raw_text = extract_text_from_pdf(f.stream)
        if not raw_text:
            return error('PDF 解析失败，请手动粘贴文本', 400)
    else:
        # 2. 文本路径
        data = request.get_json(silent=True) or {}
        raw_text = (data.get('text') or '').strip()
        if not raw_text:
            return error('请上传 PDF 或粘贴 JD 文本', 400)

    agent = PositionJdParserAgent()
    parsed = agent.parse(raw_text)
    if not parsed:
        return error('AI 解析 JD 失败，请重试', 502)

    logger.info(f'[parse_jd] 解析成功: name={parsed.get("name")}, tech_count={parsed.get("tech_requirements", "").count(",") + 1 if parsed.get("tech_requirements") else 0}')
    return success({
        'name': parsed.get('name', ''),
        'jd_content': parsed.get('jd_content', ''),
        'tech_requirements': parsed.get('tech_requirements', ''),
        'raw_text_length': len(raw_text),
    })
