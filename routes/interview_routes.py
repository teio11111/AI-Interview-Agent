from flask import Blueprint, request, render_template
from models.interview import InterviewSession, InterviewTopic
from constants import SessionStatus
from repositories.interview_repository import InterviewRepository
from repositories.candidate_repository import CandidateRepository
from repositories.position_repository import PositionRepository
from services.interview_service import InterviewService
from utils.response import success, error
from utils.logger import logger
from utils.auth import login_required
from utils.audit import log_interview_created, log_interview_finished, log_operation
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
        log_interview_created(session, candidate.name)
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


@interview_bp.route('/<int:session_id>', methods=['DELETE'])
@login_required(role='admin')
def delete_session(session_id):
    """删除面试会话（级联删除对话记录）"""
    session = InterviewRepository.find_session_by_id(session_id)
    if not session:
        return error('面试会话不存在', 404)
    # 获取候选人名称用于审计
    candidate = CandidateRepository.find_by_id(session.candidate_id)
    target_name = candidate.name if candidate else f'session#{session_id}'
    InterviewRepository.delete_session(session)
    log_operation('delete', 'interview_session', session_id, target_name)
    return success({'id': session_id})


@interview_bp.route('/<int:session_id>/dialog', methods=['POST'])
@login_required(role='admin')
def add_dialog(session_id):
    """提交问答并获取 AI 反馈（统一接口，支持追问与实时面试两个场景）

    请求参数：
      - question: 面试官问题
      - answer: 候选人回答
      - parent_seq: 追问来源问题序号（NULL/不传表示非追问）
      - context: 实时面试场景下的对话历史（可选，仅供 LLM 参考，不入库）

    返回：
      - dialog: 保存的对话记录
      - feedback: AI 反馈字典
    """
    from models.interview import InterviewDialog
    session = InterviewRepository.find_session_by_id(session_id)
    if not session:
        return error('面试会话不存在', 404)

    data = request.get_json()
    if not data or not data.get('question') or not data.get('answer'):
        return error('问题和回答不能为空', 400)

    # 更新会话状态为进行中（如果是 preparing 状态）
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
    if not candidate:
        return error('候选人不存在', 404)
    position = PositionRepository.find_by_id(candidate.position_id)
    if not position:
        return error('关联岗位不存在', 404)

    # 调用 AI 获取反馈（传入简历上下文）
    feedback = InterviewService.get_dialog_feedback(
        candidate.name, position.name,
        candidate.resume_text or '',
        dialog_history, data['question'], data['answer']
    )

    # 校验并修正评分（实时面试场景）
    if feedback and isinstance(feedback, dict):
        if 'score' in feedback:
            try:
                score = int(feedback['score'])
                feedback['score'] = max(1, min(10, score))
            except (ValueError, TypeError):
                feedback['score'] = 5
        if 'score_breakdown' in feedback and isinstance(feedback['score_breakdown'], dict):
            for k, v in feedback['score_breakdown'].items():
                try:
                    feedback['score_breakdown'][k] = max(1, min(10, int(v)))
                except (ValueError, TypeError):
                    feedback['score_breakdown'][k] = 5

    # 保存对话（含追问标识 parent_seq）
    dialog = InterviewDialog(
        session_id=session_id,
        question=data['question'],
        answer=data['answer'],
        ai_feedback=json.dumps(feedback, ensure_ascii=False) if feedback else None,
        seq=len(existing_dialogs) + 1,
        parent_seq=data.get('parent_seq')
    )
    InterviewRepository.save_dialog(dialog)

    # LLM 全部失败时返回兑底反馈，不报 502（前端实时面试需要降级可用）
    if not feedback:
        feedback = {
            'score': 5,
            'answer_quality': '待评估',
            'evaluation': 'AI 分析暂时不可用，请稍后重试。',
            'follow_up_questions': []
        }

    return success({'dialog': dialog.to_dict(), 'feedback': feedback})


@interview_bp.route('/<int:session_id>/finish', methods=['POST'])
@login_required(role='admin')
def finish_interview(session_id):
    """结束面试：板块切分 → 以板块摘要作为 3+1 评估输入"""
    session = InterviewRepository.find_session_by_id(session_id)
    if not session:
        return error('面试会话不存在', 404)

    session.status = SessionStatus.COMPLETED
    InterviewRepository.update_session(session)

    # 收集本场完整对话（seq/question/answer 供板块切分师使用）
    dialogs = InterviewRepository.find_dialogs_by_session(session_id)
    full_dialogs = [
        {'seq': d.seq, 'question': d.question or '', 'answer': d.answer or ''}
        for d in dialogs
    ]

    candidate = CandidateRepository.find_by_id(session.candidate_id)
    position = PositionRepository.find_by_id(candidate.position_id)

    # 解析出题策略（供评估师了解每道题的考察意图）
    questions_plan = None
    if session.questions_plan:
        try:
            questions_plan = json.loads(session.questions_plan) if isinstance(session.questions_plan, str) else session.questions_plan
        except:
            pass

    # ===== 阶段A：板块切分（单 Agent）=====
    segment_result = InterviewService.segment_topics(candidate.name, position.name, full_dialogs)
    topics = (segment_result or {}).get('topics', []) if segment_result else []
    logger.info(f'[finish_interview] 切分出 {len(topics)} 个板块')

    # 清除旧板块（重跑场景）
    InterviewRepository.delete_topics_by_session(session_id)

    # 保存板块到 DB（save_topic 会同时回填 dialog.topic_id）
    saved_topics = []
    for t in topics:
        topic = InterviewTopic(
            session_id=session_id,
            topic_index=t.get('topic_index', len(saved_topics) + 1),
            title=(t.get('topic_title') or t.get('title') or '未命名板块')[:120],
            summary=t.get('topic_summary') or t.get('summary') or '',
            dialog_ids_json=json.dumps(t.get('dialog_indexes') or t.get('dialog_ids') or [], ensure_ascii=False)
        )
        InterviewRepository.save_topic(topic)
        saved_topics.append(topic)

    # ===== 阶段B：以板块摘要作为 3+1 评估输入 =====
    if saved_topics:
        topic_blocks = []
        for t in saved_topics:
            topic_blocks.append(
                f"### 板块 {t.topic_index}：{t.title}\n{t.summary}"
            )
        full_dialogs_text = '\n\n'.join(topic_blocks)
    else:
        # 降级：仍用原始拼接
        dialog_lines = []
        for d in dialogs:
            tag = f" [追问自Q{d.parent_seq}]" if d.parent_seq else ""
            dialog_lines.append(f"Q{d.seq}{tag}: {d.question}\nA{d.seq}: {d.answer}")
        full_dialogs_text = '\n'.join(dialog_lines)

    report = InterviewService.generate_report(position, candidate.name, full_dialogs_text,
                                              questions_plan=questions_plan)

    if report:
        # 附加板块信息到报告（供面试工作台一次性渲染使用）
        if isinstance(report, dict):
            report['topics'] = [t.to_dict() for t in saved_topics]
        session.report = json.dumps(report, ensure_ascii=False) if isinstance(report, dict) else report
        InterviewRepository.update_session(session)
        log_interview_finished(session, candidate.name, len(saved_topics), len(dialogs))
        return success({'report': report})
    else:
        return error('生成评价报告失败', 502)


@interview_bp.route('/<int:session_id>/topics', methods=['GET'])
@login_required(role='admin')
def list_session_topics(session_id):
    """获取一场面试的所有板块（含各板块对话详情，按板块分组）"""
    session = InterviewRepository.find_session_by_id(session_id)
    if not session:
        return error('面试会话不存在', 404)

    topics = InterviewRepository.find_topics_by_session(session_id)
    dialogs = InterviewRepository.find_dialogs_by_session(session_id)

    # 构造 topic_id → dialogs 映射
    dialogs_by_topic = {}
    no_topic_dialogs = []
    for d in dialogs:
        if d.topic_id:
            dialogs_by_topic.setdefault(d.topic_id, []).append(d)
        else:
            no_topic_dialogs.append(d)

    topics_payload = []
    for t in topics:
        td = t.to_dict()
        # 附加该板块下的对话详情
        td['dialogs'] = [d.to_dict() for d in dialogs_by_topic.get(t.id, [])]
        topics_payload.append(td)

    return success({
        'topics': topics_payload,
        'orphan_dialogs': [d.to_dict() for d in no_topic_dialogs]  # 未划入板块的对话（保底）
    })


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

@home_bp.route('/live-interview')
@login_required(role='admin')
def live_interview_page():
    return render_template('live_interview.html')
