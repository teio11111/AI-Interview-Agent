"""候选人门户路由"""
from flask import Blueprint, request, render_template, session
from models.user import User
from models.candidate import Candidate
from models.interview import InterviewSession
from repositories.position_repository import PositionRepository
from repositories.candidate_repository import CandidateRepository
from repositories.interview_repository import InterviewRepository
from services.resume_service import ResumeService
from utils.response import success, error
from utils.auth import login_required, get_current_user
from utils.logger import logger
from extensions import db
import json

candidate_portal_bp = Blueprint('candidate_portal', __name__)


@candidate_portal_bp.route('/candidate')
@login_required(role='candidate')
def portal_page():
    """候选人门户页面"""
    return render_template('candidate_portal.html')


@candidate_portal_bp.route('/api/candidate/positions', methods=['GET'])
@login_required(role='candidate')
def list_positions():
    """获取可投递的岗位列表"""
    user = get_current_user()
    # 查询当前用户已投递的岗位
    my_candidates = Candidate.query.filter_by(user_id=user.id).all()
    applied_map = {c.position_id: c.id for c in my_candidates}
    
    positions = PositionRepository.find_all()
    result = []
    for p in positions:
        d = {
            'id': p.id,
            'name': p.name,
            'tech_requirements': p.tech_requirements,
            'applied': p.id in applied_map,
            'candidate_id': applied_map.get(p.id),
        }
        result.append(d)
    return success(result)


@candidate_portal_bp.route('/api/candidate/apply', methods=['POST'])
@login_required(role='candidate')
def apply():
    """提交简历投递"""
    data = request.get_json()
    if not data or not data.get('position_id') or not data.get('resume_text'):
        return error('请选择岗位并填写简历', 400)

    position = PositionRepository.find_by_id(data['position_id'])
    if not position:
        return error('岗位不存在', 404)

    user = get_current_user()

    # 检查是否已投递该岗位
    existing = Candidate.query.filter_by(user_id=user.id, position_id=position.id).first()
    if existing:
        # 更新简历
        existing.resume_text = data['resume_text']
        CandidateRepository.update(existing)
        candidate = existing
    else:
        # 创建候选人记录
        candidate = Candidate(
            name=data.get('real_name', user.username),
            position_id=position.id,
            user_id=user.id,
            resume_text=data['resume_text']
        )
        CandidateRepository.save(candidate)

    logger.info(f'候选人 {user.username} 投递岗位 {position.name}')
    return success({'candidate': candidate.to_dict()}, message='投递成功')


@candidate_portal_bp.route('/api/candidate/analyze', methods=['POST'])
@login_required(role='candidate')
def analyze_resume():
    """AI 分析简历"""
    data = request.get_json()
    candidate_id = data.get('candidate_id')
    if not candidate_id:
        return error('缺少候选人ID', 400)

    candidate = CandidateRepository.find_by_id(candidate_id)
    if not candidate:
        return error('候选人不存在', 404)
    if not candidate.resume_text:
        return error('简历为空', 400)

    # 验证是当前用户的候选人
    user = get_current_user()
    if candidate.user_id != user.id:
        return error('无权操作', 403)

    position = PositionRepository.find_by_id(candidate.position_id)
    if not position:
        return error('岗位不存在', 404)

    result = ResumeService.analyze_resume(position, candidate.resume_text, candidate.name)
    if not result:
        return error('AI 分析失败，请重试', 502)

    candidate.ai_analysis = json.dumps(result, ensure_ascii=False)
    candidate.match_score = result.get('match_score', 0)
    CandidateRepository.update(candidate)

    return success({'analysis': result, 'candidate': candidate.to_dict()})


@candidate_portal_bp.route('/api/candidate/my-info', methods=['GET'])
@login_required(role='candidate')
def my_info():
    """获取我的信息（所有投递记录+分析+面试）"""
    user = get_current_user()
    # 查询当前用户的所有候选人记录
    candidates = Candidate.query.filter_by(user_id=user.id).order_by(
        Candidate.created_at.desc()
    ).all()

    if not candidates:
        return success({'applications': []})

    applications = []
    for candidate in candidates:
        position = PositionRepository.find_by_id(candidate.position_id)

        # 解析候选人分析
        cand_dict = candidate.to_dict()
        if candidate.ai_analysis:
            try:
                cand_dict['ai_analysis'] = json.loads(candidate.ai_analysis) if isinstance(candidate.ai_analysis, str) else candidate.ai_analysis
            except (json.JSONDecodeError, TypeError):
                pass

        # 获取面试会话
        sessions = InterviewSession.query.filter_by(candidate_id=candidate.id).order_by(
            InterviewSession.created_at.desc()
        ).all()
        sessions_data = []
        for s in sessions:
            sd = s.to_dict()
            if s.report:
                try:
                    sd['report'] = json.loads(s.report) if isinstance(s.report, str) else s.report
                except (json.JSONDecodeError, TypeError):
                    sd['report'] = None
            sessions_data.append(sd)

        applications.append({
            'candidate': cand_dict,
            'position': position.to_dict() if position else None,
            'sessions': sessions_data
        })

    return success({'applications': applications})
