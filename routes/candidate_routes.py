from flask import Blueprint, request, Response, current_app
from extensions import db
from models.candidate import Candidate
from models.interview import InterviewSession, InterviewDialog
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
from utils.audit import log_interview_created, log_operation
from utils.meta_evaluation_pdf import generate_meta_evaluation_pdf
import json
import threading

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
    log_operation('create', 'candidate', candidate.id, candidate.name)
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


@candidate_bp.route('/<int:id>/ai-analysis', methods=['DELETE'])
@login_required(role='admin')
def clear_ai_analysis(id):
    """【v4.1】清除候选人的 AI 分析结果（用于重新评估）

    背景：v4.1 优化后重跑 LLM 可能输出不同评分，用户需要「重新评估」入口。
    修复：清除 ai_analysis + match_score，保留 interview sessions（老会话不被误删）。
    前端调用后需要再触发一次 SSE /api/stream/candidate-analysis/{id} 重新评估。
    """
    candidate = CandidateRepository.find_by_id(id)
    if not candidate:
        return error('候选人不存在', 404)
    if not candidate.ai_analysis:
        return error('该候选人尚无 AI 分析结果，无需清除', 400)

    candidate.ai_analysis = ''
    candidate.match_score = None
    CandidateRepository.update(candidate)
    log_operation('clear_ai_analysis', 'candidate', candidate.id, candidate.name)
    logger.info(f'[v4.1] 清除 AI 分析结果: candidate={candidate.name} (id={id})')
    return success({'cleared': True, 'candidate_id': id})


@candidate_bp.route('/<int:id>/analyze', methods=['POST'])
@login_required(role='admin')
def analyze_candidate(id):
    """AI 分析简历匹配度，并自动生成面试会话

    【v2.1 性能修复】同步只跑简历评估（≈31s）+ 兑底题（<0.5s），保证接口 < 60s：
      1. 同步调用 ResumeService.analyze_resume（3个评估师并行）
      2. 同步生成 5 道兑底模板题（纯代码，不调 LLM）
      3. 立即创建 InterviewSession（status='refining'）并返回
      4. 后台异步线程调用 InterviewService.generate_questions（LLM 真出题），
         完成后覆盖 questions_plan 并将 status 改为 'preparing'
    """
    candidate = CandidateRepository.find_by_id(id)
    if not candidate:
        return error('候选人不存在', 404)
    if not candidate.resume_text:
        return error('简历内容为空', 400)

    position = PositionRepository.find_by_id(candidate.position_id)
    if not position:
        return error('关联岗位不存在', 404)

    # 1. 分析简历（同步，必须完成，耗时 ≈31s）
    result = ResumeService.analyze_resume(position, candidate.resume_text, candidate.name)

    if not result:
        return error('AI 分析失败，请重试', 502)

    # 【v2.2 脱底去除】LLM 全面不可达时，不写虚假的 match_score 入库，
    # 而是写 0 + 失败 flag，让前端表现出明确的"待重试"状态，不让用户看到假一份话。
    is_llm_failed = bool(result.get('llm_fully_failed'))

    candidate.ai_analysis = json.dumps(result, ensure_ascii=False)
    candidate.match_score = 0 if is_llm_failed else result.get('match_score', 0)
    CandidateRepository.update(candidate)

    # 2. 【v3.6.5 同步保险】同步调用 LLM 真出题（超时 90s），保证返回时 session 一定带上定制题，
    #    不再依赖不可靠的 daemon Thread（waitress 8 worker 下 daemon thread 时灵时不灵，导致
    #    session 卡在 preparing 状态 + 兑底题，用户进入实时面试看到恢复兑底题会话的错误现象）。
    #    90s 以内能拿到 LLM 精修题，就用精修题；拿不到才退回到兑底题并在后台补精修。
    refined_questions = None
    try:
        logger.info(f'[v3.6.5] 开始同步 LLM 真出题: candidate={candidate.name}')
        refined_questions = InterviewService.generate_questions(
            position, candidate,
            position.ai_analysis,
            candidate.ai_analysis,
            candidate.resume_text,
        )
        if refined_questions and isinstance(refined_questions, dict) and refined_questions.get('questions'):
            logger.info(
                f'[v3.6.5] LLM 真出题成功: candidate={candidate.name}, '
                f'questions={len(refined_questions["questions"])}'
            )
        else:
            refined_questions = None
    except Exception as e:
        logger.error(f'[v3.6.5] 同步出题异常: candidate={candidate.name}, error={e}')
        refined_questions = None

    # 3. 【bugfix】创建新 session 前，清理该候选人所有 preparing 状态的旧 session
    # 背景：用户多次点"重新评估"会累积多个 preparing session，前端 restoreActiveSession
    # 可能拿到旧的 session 导致显示过期题目。
    old_sessions = InterviewRepository.find_sessions_by_candidate(candidate.id)
    for old_sess in old_sessions:
        if old_sess.status == SessionStatus.PREPARING:
            old_dialogs = InterviewRepository.find_dialogs_by_session(old_sess.id)
            for d in old_dialogs:
                db.session.delete(d)
            db.session.delete(old_sess)
            logger.info(f'[bugfix] 清理旧 preparing session: session_id={old_sess.id}, candidate={candidate.name}')
    db.session.commit()
    
    # 4. 同步创建 InterviewSession（优先用 LLM 定制题，失败才用底题）
    if refined_questions:
        session = InterviewSession(
            candidate_id=candidate.id,
            status=SessionStatus.PREPARING,
            questions_plan=json.dumps(refined_questions, ensure_ascii=False)
        )
    else:
        fallback_questions = InterviewService.generate_fallback_questions(
            position, candidate.resume_text
        )
        session = InterviewSession(
            candidate_id=candidate.id,
            status=SessionStatus.PREPARING,
            questions_plan=json.dumps(fallback_questions, ensure_ascii=False)
        )
        # LLM 出题失败，后台异步重试（也给机会出定制题）
        flask_app = current_app._get_current_object()
        thread = threading.Thread(
            target=_refine_questions_async,
            args=(flask_app, candidate.id, position.id, session.id),
            daemon=True,
        )
        thread.start()
        logger.info(
            f'[v3.6.5] 兑底题会话（异步补精修）: candidate={candidate.name}, '
            f'session={session.id}, thread.is_alive={thread.is_alive()}'
        )
    InterviewRepository.save_session(session)
    log_interview_created(session, candidate.name)
    log_operation('analyze', 'candidate', candidate.id, candidate.name)
    logger.info(f'[v3.6.5] 面试会话已创建: candidate={candidate.name}, session={session.id}')

    return success({'analysis': result, 'candidate': candidate.to_dict(), 'session': session.to_dict()})


def _refine_questions_async(app, candidate_id, position_id, session_id):
    """后台线程：异步生成 LLM 精修题目，覆盖兑底题

    Args:
        app: Flask app 实例（用于在线程里 push app_context）
        candidate_id: 候选人 ID
        position_id: 岗位 ID
        session_id: 会话 ID
    """
    # 【v3.6.5】诊断日志：确认 daemon 线程真的能跑。某些 Flask 实例下子线程不生效，
    # 问题表现为：同步兜底题创建后就停在 preparing，定制题永不写入。
    logger.info(f'[异步精修] ⏰ 线程入口: candidate_id={candidate_id}, session_id={session_id}')
    with app.app_context():
        try:
            from models.candidate import Candidate
            from models.position import Position
            from repositories.candidate_repository import CandidateRepository
            from repositories.position_repository import PositionRepository

            candidate = CandidateRepository.find_by_id(candidate_id)
            position = PositionRepository.find_by_id(position_id)
            if not candidate or not position:
                logger.error(f'[异步精修] candidate/position 不存在: {candidate_id}/{position_id}')
                return

            logger.info(f'[异步精修] 开始: candidate={candidate.name}, position={position.name}')
            refined = InterviewService.generate_questions(
                position, candidate,
                position.ai_analysis,
                candidate.ai_analysis,
                candidate.resume_text,
            )

            sess = InterviewRepository.find_session_by_id(session_id)
            if not sess:
                logger.error(f'[异步精修] session 不存在: {session_id}')
                return

            if refined and isinstance(refined, dict) and refined.get('questions'):
                sess.questions_plan = json.dumps(refined, ensure_ascii=False)
                logger.info(
                    f'[异步精修] 完成: candidate={candidate.name}, '
                    f'questions={len(refined["questions"])}'
                )
            else:
                logger.warning(
                    f'[异步精修] LLM 未返回有效结果，保留兑底题: candidate={candidate.name}'
                )
            InterviewRepository.update_session(sess)
        except Exception as e:
            logger.error(f'[异步精修] 异常: candidate_id={candidate_id}, error={e}')


@candidate_bp.route('/<int:id>', methods=['DELETE'])
@login_required(role='admin')
def delete_candidate(id):
    """删除候选人（级联删除面试会话和对话记录）"""
    candidate = CandidateRepository.find_by_id(id)
    if not candidate:
        return error('候选人不存在', 404)
    
    # 显式级联删除关联的面试会话和对话记录
    sessions = InterviewRepository.find_sessions_by_candidate(id)
    for session in sessions:
        dialogs = InterviewRepository.find_dialogs_by_session(session.id)
        for dialog in dialogs:
            db.session.delete(dialog)
        db.session.delete(session)
    db.session.commit()
    
    name = candidate.name
    CandidateRepository.delete(candidate)
    log_operation('delete', 'candidate', id, name)
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
            log_operation('delete', 'candidate', candidate.id, candidate.name)
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
    log_operation('meta_evaluate', 'candidate', candidate.id, candidate.name,
                  f'{len(interview_data)} 轮面试')

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


@candidate_bp.route('/<int:id>/meta-evaluation/pdf', methods=['GET'])
@login_required(role='admin')
def export_meta_evaluation_pdf(id):
    """导出综合元评估报告为 PDF 文件"""
    candidate = CandidateRepository.find_by_id(id)
    if not candidate:
        return error('候选人不存在', 404)
    if not candidate.meta_evaluation:
        return error('尚未生成综合元评估，无法导出 PDF', 404)

    # 1. 解析综合元评估
    try:
        evaluation = json.loads(candidate.meta_evaluation)
    except Exception:
        evaluation = {}

    # 2. 解析计算调试字段（从 evaluation 中提取，或传 None）
    computation = None
    if isinstance(evaluation, dict):
        # 兼容两种存储方式：顶层 raw_score/penalty，或嵌套在 computation 字段
        if isinstance(evaluation.get('computation'), dict):
            computation = evaluation['computation']
        else:
            # 从 evaluation 顶层重建一个简单的 computation 字典
            comp_keys = ['raw_score', 'penalty', 'final_score', 'resume_weight', 'round_weights']
            comp_data = {k: evaluation[k] for k in comp_keys if k in evaluation}
            computation = comp_data if comp_data else None

    # 3. 获取岗位信息
    position = None
    if candidate.position_id:
        position = PositionRepository.find_by_id(candidate.position_id)

    # 4. 准备数据结构
    candidate_dict = candidate.to_dict()
    position_dict = position.to_dict() if position else {}

    try:
        pdf_bytes = generate_meta_evaluation_pdf(
            candidate_dict=candidate_dict,
            position_dict=position_dict,
            evaluation_dict=evaluation,
            computation=computation,
        )
    except Exception as e:
        logger.error(f'生成综合元评估 PDF 失败: candidate_id={id}, error={e}')
        return error(f'PDF 生成失败：{str(e)[:80]}', 500)

    # 5. 构造文件名（含中文，UTF-8 + URL 编码）
    from urllib.parse import quote
    safe_name = candidate.name or f'candidate_{id}'
    filename = f'综合元评估报告_{safe_name}.pdf'
    filename_encoded = quote(filename)

    return Response(
        pdf_bytes,
        mimetype='application/pdf',
        headers={
            'Content-Disposition': f"attachment; filename*=UTF-8''{filename_encoded}",
            'Content-Length': str(len(pdf_bytes)),
            'Cache-Control': 'no-store',
        },
    )
