from flask import Blueprint, request, render_template
from models.interview import InterviewSession, InterviewDialog
from constants import SessionStatus
from repositories.interview_repository import InterviewRepository
from repositories.candidate_repository import CandidateRepository
from repositories.position_repository import PositionRepository
from services.interview_service import InterviewService
from utils.response import success, error
from utils.logger import logger
from utils.auth import login_required
import json

interview_bp = Blueprint('interviews', __name__, url_prefix='/api/interviews')


@interview_bp.route('/generate/<int:candidate_id>', methods=['POST'])
@login_required(role='admin')
def generate_questions(candidate_id):
    """生成面试问题"""
    candidate = CandidateRepository.find_by_id(candidate_id)
    if not candidate:
        return error('候选人不存在', 404)

    position = PositionRepository.find_by_id(candidate.position_id)
    if not position:
        return error('关联岗位不存在', 404)

    result = InterviewService.generate_questions(
        position, candidate,
        position.ai_analysis,
        candidate.ai_analysis,
        candidate.resume_text
    )

    if result:
        session = InterviewSession(
            candidate_id=candidate_id,
            status=SessionStatus.PREPARING,
            questions_plan=json.dumps(result, ensure_ascii=False)
        )
        InterviewRepository.save_session(session)
        return success({'session': session.to_dict(), 'questions': result})
    else:
        return error('生成面试问题失败', 502)


@interview_bp.route('/<int:session_id>', methods=['GET'])
@login_required(role='admin')
def get_session(session_id):
    session = InterviewRepository.find_session_by_id(session_id)
    if not session:
        return error('面试会话不存在', 404)
    dialogs = InterviewRepository.find_dialogs_by_session(session_id)
    return success({
        'session': session.to_dict(),
        'dialogs': [d.to_dict() for d in dialogs]
    })


@interview_bp.route('/<int:session_id>/dialog', methods=['POST'])
@login_required(role='admin')
def add_dialog(session_id):
    """提交问答并获取 AI 反馈"""
    session = InterviewRepository.find_session_by_id(session_id)
    if not session:
        return error('面试会话不存在', 404)

    data = request.get_json()
    if not data or not data.get('question') or not data.get('answer'):
        return error('问题和回答不能为空', 400)

    # 更新会话状态
    if session.status == SessionStatus.PREPARING:
        session.status = SessionStatus.IN_PROGRESS
        InterviewRepository.update_session(session)

    # 获取历史对话
    existing_dialogs = InterviewRepository.find_dialogs_by_session(session_id)
    dialog_history = '\n'.join([
        f"Q{d.seq}: {d.question}\nA{d.seq}: {d.answer}"
        for d in existing_dialogs
    ])

    # 获取候选人和岗位信息
    candidate = CandidateRepository.find_by_id(session.candidate_id)
    position = PositionRepository.find_by_id(candidate.position_id)

    # 调用 AI 获取反馈
    feedback = InterviewService.get_dialog_feedback(
        candidate.name, position.name,
        candidate.resume_text,
        dialog_history, data['question'], data['answer']
    )

    # 保存对话
    dialog = InterviewDialog(
        session_id=session_id,
        question=data['question'],
        answer=data['answer'],
        ai_feedback=json.dumps(feedback, ensure_ascii=False) if feedback else None,
        seq=len(existing_dialogs) + 1,
        parent_seq=data.get('parent_seq')
    )
    InterviewRepository.save_dialog(dialog)

    return success({'dialog': dialog.to_dict(), 'feedback': feedback})


@interview_bp.route('/<int:session_id>/finish', methods=['POST'])
@login_required(role='admin')
def finish_interview(session_id):
    """结束面试并生成评价报告"""
    session = InterviewRepository.find_session_by_id(session_id)
    if not session:
        return error('面试会话不存在', 404)

    session.status = SessionStatus.COMPLETED
    InterviewRepository.update_session(session)

    # 拼接全部对话（追问加标记，便于报告区分）
    dialogs = InterviewRepository.find_dialogs_by_session(session_id)
    dialog_lines = []
    for d in dialogs:
        tag = f" [追问自Q{d.parent_seq}]" if d.parent_seq else ""
        dialog_lines.append(f"Q{d.seq}{tag}: {d.question}\nA{d.seq}: {d.answer}")
    full_dialogs = '\n'.join(dialog_lines)

    candidate = CandidateRepository.find_by_id(session.candidate_id)
    position = PositionRepository.find_by_id(candidate.position_id)

    # 解析出题策略（供评估师了解每道题的考察意图）
    questions_plan = None
    if session.questions_plan:
        try:
            questions_plan = json.loads(session.questions_plan) if isinstance(session.questions_plan, str) else session.questions_plan
        except:
            pass

    # 纯面试评价：不传简历/岗位分析数据，只传对话和出题策略
    report = InterviewService.generate_report(position, candidate.name, full_dialogs,
                                              questions_plan=questions_plan)

    if report:
        session.report = json.dumps(report, ensure_ascii=False) if isinstance(report, dict) else report
        InterviewRepository.update_session(session)
        return success({'report': report})
    else:
        return error('生成评价报告失败', 502)


@interview_bp.route('/<int:session_id>/follow-up', methods=['POST'])
@login_required(role='admin')
def generate_follow_up(session_id):
    """生成连续追问"""
    session = InterviewRepository.find_session_by_id(session_id)
    if not session:
        return error('面试会话不存在', 404)

    data = request.get_json()
    dialog_seq = data.get('dialog_seq')  # 要追问的对话序号
    if dialog_seq is None:
        return error('请指定要追问的对话', 400)

    # 获取该问题及之后的所有对话（构建对话链）
    dialogs = InterviewRepository.find_dialogs_by_session(session_id)
    # 构建对话链：从指定问题开始的所有 Q&A
    chain_dialogs = [d for d in dialogs if d.seq >= dialog_seq]
    dialog_chain = '\n'.join([
        f"Q{d.seq}: {d.question}\nA{d.seq}: {d.answer}"
        for d in chain_dialogs
    ])

    if not dialog_chain:
        return error('未找到对话记录', 404)

    candidate = CandidateRepository.find_by_id(session.candidate_id)

    result = InterviewService.generate_follow_up(
        candidate.resume_text, dialog_chain
    )

    if result:
        return success(result)
    else:
        return error('追问生成失败', 502)


@interview_bp.route('/sessions', methods=['GET'])
@login_required(role='admin')
def list_sessions():
    """获取所有面试会话"""
    sessions = InterviewRepository.find_all_sessions()
    return success([s.to_dict() for s in sessions])


# 首页路由（非 API）
home_bp = Blueprint('home', __name__)

@home_bp.route('/')
@login_required(role='admin')
def index():
    return render_template('index.html')

@home_bp.route('/positions')
@login_required(role='admin')
def positions_page():
    return render_template('positions.html')

@home_bp.route('/candidates')
@login_required(role='admin')
def candidates_page():
    return render_template('candidates.html')

@home_bp.route('/interview')
@login_required(role='admin')
def interview_page():
    return render_template('interview.html')
