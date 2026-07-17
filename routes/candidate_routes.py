from flask import Blueprint, request
from models.candidate import Candidate
from models.interview import InterviewSession
from constants import SessionStatus
from repositories.candidate_repository import CandidateRepository
from repositories.position_repository import PositionRepository
from repositories.interview_repository import InterviewRepository
from services.resume_service import ResumeService
from services.interview_service import InterviewService, get_orchestrator
from utils.pdf_parser import extract_text_from_pdf
from utils.response import success, error, created
from utils.logger import logger
from utils.auth import login_required
import json

candidate_bp = Blueprint('candidates', __name__, url_prefix='/api/candidates')


@candidate_bp.route('', methods=['GET'])
@login_required(role='admin')
def list_candidates():
    candidates = CandidateRepository.find_all()
    return success([c.to_dict() for c in candidates])


@candidate_bp.route('/<int:id>', methods=['GET'])
@login_required(role='admin')
def get_candidate(id):
    candidate = CandidateRepository.find_by_id(id)
    if not candidate:
        return error('候选人不存在', 404)
    return success(candidate.to_dict())


@candidate_bp.route('', methods=['POST'])
@login_required(role='admin')
def create_candidate():
    data = request.get_json()
    if not data or not data.get('name') or not data.get('position_id'):
        return error('姓名和岗位不能为空', 400)

    position = PositionRepository.find_by_id(data['position_id'])
    if not position:
        return error('关联岗位不存在', 404)

    candidate = Candidate(
        name=data['name'],
        position_id=data['position_id'],
        resume_text=data.get('resume_text', '')
    )
    CandidateRepository.save(candidate)
    return created(candidate.to_dict())


@candidate_bp.route('/upload-resume', methods=['POST'])
@login_required(role='admin')
def upload_resume():
    """上传 PDF 简历并提取文本"""
    if 'file' not in request.files:
        return error('未上传文件', 400)

    file = request.files['file']
    if not file.filename.endswith('.pdf'):
        return error('只支持 PDF 格式', 400)

    text = extract_text_from_pdf(file.stream)
    if text:
        return success({'resume_text': text})
    else:
        return error('PDF 解析失败，请手动粘贴简历内容', 400)


@candidate_bp.route('/<int:id>/analyze', methods=['POST'])
@login_required(role='admin')
def analyze_candidate(id):
    """AI 分析简历匹配度，并自动生成面试会话"""
    candidate = CandidateRepository.find_by_id(id)
    if not candidate:
        return error('候选人不存在', 404)
    if not candidate.resume_text:
        return error('简历内容为空', 400)

    position = PositionRepository.find_by_id(candidate.position_id)
    if not position:
        return error('关联岗位不存在', 404)

    # 1. 分析简历
    result = ResumeService.analyze_resume(position, candidate.resume_text, candidate.name)

    if not result:
        return error('AI 分析失败，请重试', 502)

    candidate.ai_analysis = json.dumps(result, ensure_ascii=False)
    candidate.match_score = result.get('match_score', 0)
    CandidateRepository.update(candidate)

    # 2. 自动生成面试问题和会话
    questions = InterviewService.generate_questions(
        position, candidate,
        position.ai_analysis,
        candidate.ai_analysis,
        candidate.resume_text
    )

    session = None
    if questions:
        session = InterviewSession(
            candidate_id=candidate.id,
            status=SessionStatus.PREPARING,
            questions_plan=json.dumps(questions, ensure_ascii=False)
        )
        InterviewRepository.save_session(session)
        logger.info(f'已为候选人 {candidate.name} 自动生成面试会话')

    return success({'analysis': result, 'candidate': candidate.to_dict(), 'session': session.to_dict() if session else None})


@candidate_bp.route('/<int:id>', methods=['DELETE'])
@login_required(role='admin')
def delete_candidate(id):
    """删除候选人"""
    candidate = CandidateRepository.find_by_id(id)
    if not candidate:
        return error('候选人不存在', 404)
    CandidateRepository.delete(candidate)
    return success({'id': id})


@candidate_bp.route('/<int:id>/notes', methods=['PATCH'])
@login_required(role='admin')
def update_notes(id):
    """更新候选人备注"""
    candidate = CandidateRepository.find_by_id(id)
    if not candidate:
        return error('候选人不存在', 404)
    data = request.get_json()
    if data is None:
        return error('请求体不能为空', 400)
    candidate.notes = data.get('notes', '')
    CandidateRepository.update(candidate)
    return success({'id': id, 'notes': candidate.notes})


@candidate_bp.route('/batch-delete', methods=['POST'])
@login_required(role='admin')
def batch_delete():
    """批量删除候选人"""
    data = request.get_json()
    if not data or not data.get('ids'):
        return error('请选择要删除的候选人', 400)
    ids = data['ids']
    deleted = []
    for cid in ids:
        candidate = CandidateRepository.find_by_id(cid)
        if candidate:
            CandidateRepository.delete(candidate)
            deleted.append(cid)
    return success({'deleted': deleted, 'count': len(deleted)})


@candidate_bp.route('/<int:id>/meta-evaluation', methods=['POST'])
@login_required(role='admin')
def meta_evaluate(id):
    """综合元评估：汇总岗位分析 + 简历评估 + 各轮面试报告"""
    candidate = CandidateRepository.find_by_id(id)
    if not candidate:
        return error('候选人不存在', 404)

    position = PositionRepository.find_by_id(candidate.position_id)
    if not position:
        return error('关联岗位不存在', 404)

    # 1. 解析简历评估结果
    resume_evaluation = None
    if candidate.ai_analysis:
        try:
            resume_evaluation = json.loads(candidate.ai_analysis) if isinstance(candidate.ai_analysis, str) else candidate.ai_analysis
        except Exception:
            pass
    if not resume_evaluation:
        return error('请先完成简历 AI 分析', 400)

    # 2. 获取所有已完成面试会话的报告
    sessions = InterviewRepository.find_sessions_by_candidate(candidate.id)
    completed = [s for s in sessions if s.status == 'completed' and s.report]
    if not completed:
        return error('请先完成至少一轮面试并生成报告', 400)

    # 按创建时间排序
    completed.sort(key=lambda x: x.created_at or 0)

    interview_data = []
    for i, sess in enumerate(completed):
        try:
            report = json.loads(sess.report) if isinstance(sess.report, str) else sess.report
        except Exception:
            report = {}
        try:
            questions_plan = json.loads(sess.questions_plan) if isinstance(sess.questions_plan, str) and sess.questions_plan else None
        except Exception:
            questions_plan = None
        interview_data.append({
            'round': i + 1,
            'session_id': sess.id,
            'report': report,
            'questions_plan': questions_plan,
        })

    logger.info(f'[综合元评估] 开始: {candidate.name} → {position.name}, {len(interview_data)} 轮面试')

    # 3. 调用编排器（复用全局实例）
    orchestrator = get_orchestrator()
    result = orchestrator.generate_meta_evaluation(
        position=position,
        candidate=candidate,
        resume_evaluation=resume_evaluation,
        interview_sessions=interview_data,
    )

    if not result:
        return error('AI 综合元评估失败，请重试', 502)

    # 4. 保存结果
    candidate.meta_evaluation = json.dumps(result, ensure_ascii=False)
    candidate.meta_eval_round_count = len(interview_data)
    CandidateRepository.update(candidate)

    return success({'evaluation': result, 'candidate_id': id})


@candidate_bp.route('/<int:id>/meta-evaluation', methods=['GET'])
@login_required(role='admin')
def get_meta_evaluation(id):
    """获取已保存的综合元评估结果"""
    candidate = CandidateRepository.find_by_id(id)
    if not candidate:
        return error('候选人不存在', 404)
    if not candidate.meta_evaluation:
        return error('尚未生成综合元评估', 404)
    try:
        result = json.loads(candidate.meta_evaluation)
    except Exception:
        result = {}
    return success({'evaluation': result, 'candidate_id': id})
