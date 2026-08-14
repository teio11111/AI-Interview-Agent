"""
移动端 AI 面试助手 - HTTP 接口（方案 A：HTTP 协议）
【v5.0 移动端】2026-08-06 新增

设计原则：
- 不修改任何现有路由文件
- 不依赖 Flask session（移动端走 X-Demo-Token 头）
- 复用 InterviewService / AgentOrchestrator / Repository
- 仅写入数据（候选人会话、对话、报告），不动现有 schema

接口列表：
  GET  /api/mobile/positions     岗位列表
  POST /api/mobile/questions     拉题 + 自动建候选人/会话
  POST /api/mobile/chat          提交回答 → AI 反馈
  POST /api/mobile/result        结束面试 → 板块切分 + 3+1 报告
"""
import json
import os
import time
from functools import wraps

from flask import Blueprint, request

from constants import SessionStatus
from models.candidate import Candidate
from models.interview import InterviewDialog, InterviewSession, InterviewTopic
from repositories.candidate_repository import CandidateRepository
from repositories.interview_repository import InterviewRepository
from repositories.position_repository import PositionRepository
from services.interview_service import InterviewService
from utils.audit import log_operation
from utils.logger import logger
from utils.response import error, success

mobile_bp = Blueprint('mobile', __name__, url_prefix='/api/mobile')


# ============================================================
# 评分提取（鲁棒版）
# ============================================================
def _extract_score(feedback: dict | None) -> int:
    """从 LLM 返回的 feedback dict 里提取 1-10 的分数，多层兜底。

    LLM 真实返回结构很不稳定（MiniMax-M3 / DeepSeek-R1），常见：
      1) {score: 7, ...}                      —— 顶层有 score
      2) {feedback: {score: 7, ...}, ...}     —— 嵌套 feedback 子字段
      3) {score: '', score_breakdown: {...}}  —— score 空，从 breakdown 平均
      4) {score_tech: 7, score_soft: 6}       —— 只有顾问分，按 6:4 加权
      5) {answer_quality: '一般'}             —— 字符串兜底映射

    Returns:
        int: 1-10 的分数，无法提取时返回 5
    """
    if not isinstance(feedback, dict):
        return 5

    # 第 1 优先：顶层 score（数值或可解析为数字的字符串）
    raw = feedback.get('score')
    if raw in (None, '', 0):
        raw = None
    elif isinstance(raw, (int, float, str)):
        # 无法转为数字的（如 'abc'、'unknown'）也视为无效，继续回退
        try:
            float(raw)
        except (ValueError, TypeError):
            raw = None

    # 第 2 优先：嵌套 feedback 子字段
    if raw is None and isinstance(feedback.get('feedback'), dict):
        raw = feedback['feedback'].get('score')
        if raw in (None, '', 0):
            raw = None

    # 第 3 优先：score_breakdown 五维平均
    if raw is None and isinstance(feedback.get('score_breakdown'), dict):
        nums = [v for v in feedback['score_breakdown'].values()
                if isinstance(v, (int, float))]
        if nums:
            raw = round(sum(nums) / len(nums))

    # 第 4 优先：score_tech / score_soft 按 6:4 加权
    if raw is None:
        tech = feedback.get('score_tech')
        soft = feedback.get('score_soft')
        if isinstance(tech, (int, float)) and isinstance(soft, (int, float)):
            raw = round(tech * 0.6 + soft * 0.4)

    # 第 5 优先：answer_quality 文本映射
    if raw is None:
        q = (feedback.get('answer_quality') or '').strip()
        quality_map = {'优秀': 8, '良好': 7, '一般': 5, '较差': 3, '差': 2}
        if q in quality_map:
            raw = quality_map[q]

    # 裁剪到 1-10
    try:
        return max(1, min(10, int(round(float(raw)))))
    except (ValueError, TypeError):
        return 5


# ============================================================
# 演示鉴权：X-Demo-Token 头（生产替换为 OAuth / JWT）
# ============================================================
def _expected_token() -> str:
    return os.getenv('MOBILE_DEMO_TOKEN', 'mobile-demo-2026')


def mobile_token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get('X-Demo-Token', '')
        expected = _expected_token()
        if not token or token != expected:
            logger.warning(
                f'[mobile] 鉴权失败: got={token[:8]!r}..., expected={expected[:8]!r}..., path={request.path}'
            )
            return error('演示 token 无效', 401)
        return f(*args, **kwargs)
    return decorated


# ============================================================
# 浏览器 CORS（演示用，方便 Postman / 浏览器调试）
# 移动端原生 HTTP 不受 CORS 限制
# ============================================================
@mobile_bp.after_request
def _add_cors_headers(response):
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type, X-Demo-Token'
    return response


@mobile_bp.route('/<path:_any>', methods=['OPTIONS'])
def _cors_preflight(_any):
    return _add_cors_headers(mobile_bp.make_response(('', 204)))


# ============================================================
# 1. 岗位列表
# ============================================================
@mobile_bp.route('/positions', methods=['GET'])
@mobile_token_required
def list_positions():
    """返回所有岗位（演示用，不分页）"""
    positions = PositionRepository.find_all()
    return success({
        'positions': [
            {
                'id': p.id,
                'name': p.name,
                'tech_requirements': p.tech_requirements or '',
                'has_ai_analysis': bool(p.ai_analysis)
            }
            for p in positions
        ],
        'count': len(positions)
    })


# ============================================================
# 2. 拉题 + 自动建候选人/会话
# ============================================================
@mobile_bp.route('/questions', methods=['POST'])
@mobile_token_required
def pull_questions():
    """
    按岗位拉题 + 自动创建 candidate + session

    请求体：
      {
        "position_id": 1,
        "device_id": "android-uuid-xxxx",     # 必填
        "candidate_name": "移动端候选人",      # 可选，默认 "移动端-{device_id[:8]}"
        "resume_text": "..."                  # 可选
      }

    返回：
      {
        "session_id": 12,
        "candidate_id": 8,
        "position": {id, name, tech_requirements},
        "questions": {...},        # questions_plan 解析后
        "elapsed": 35.2            # 出题耗时（秒）
      }
    """
    data = request.get_json() or {}
    position_id = data.get('position_id')
    device_id = (data.get('device_id') or '').strip()
    candidate_name = (data.get('candidate_name') or '').strip()
    resume_text = data.get('resume_text') or ''

    if not position_id:
        return error('position_id 必填', 400)
    if not device_id:
        return error('device_id 必填（移动端身份标识）', 400)
    if len(device_id) > 64:
        return error('device_id 过长（≤64 字符）', 400)

    position = PositionRepository.find_by_id(int(position_id))
    if not position:
        return error('岗位不存在', 404)
    if not position.ai_analysis:
        return error('该岗位尚未完成 AI 解析，请先在网页端完成岗位创建', 400)

    # 复用候选人：同 device_id+岗位 → 复用
    name_tag = candidate_name or f'移动端-{device_id[:8]}'
    existing = Candidate.query.filter_by(name=name_tag, position_id=position.id).first()
    if existing:
        candidate = existing
        if resume_text and not candidate.resume_text:
            candidate.resume_text = resume_text
            CandidateRepository.update(candidate)
    else:
        candidate = Candidate(
            name=name_tag,
            position_id=position.id,
            resume_text=resume_text or None,
            notes=f'移动端设备 {device_id[:24]}'
        )
        CandidateRepository.save(candidate)

    # 出题（同步，30-60s）
    logger.info(
        f'[mobile/questions] position={position.name!r} candidate={candidate.name!r} '
        f'device={device_id[:8]} resume={bool(resume_text)}'
    )
    t0 = time.time()
    questions = InterviewService.generate_questions(
        position, candidate,
        position.ai_analysis,
        candidate.ai_analysis,
        candidate.resume_text
    )
    elapsed = round(time.time() - t0, 1)
    q_count = len(questions.get('questions', [])) if isinstance(questions, dict) else 0
    logger.info(f'[mobile/questions] 出题完成 耗时 {elapsed}s, 共 {q_count} 题')

    if not questions:
        return error('出题失败，请稍后重试', 502)

    # 建会话
    sess = InterviewSession(
        candidate_id=candidate.id,
        status=SessionStatus.PREPARING,
        questions_plan=json.dumps(questions, ensure_ascii=False)
    )
    InterviewRepository.save_session(sess)
    log_operation(
        'mobile_create', 'interview_session', sess.id, candidate.name,
        f'position={position.name}, device={device_id[:8]}, elapsed={elapsed}s, q={q_count}'
    )

    return success({
        'session_id': sess.id,
        'candidate_id': candidate.id,
        'position': {
            'id': position.id,
            'name': position.name,
            'tech_requirements': position.tech_requirements or ''
        },
        'questions': questions,
        'elapsed': elapsed
    })


# ============================================================
# 3. 对话（用户回答 → AI 反馈）
# ============================================================
@mobile_bp.route('/chat', methods=['POST'])
@mobile_token_required
def mobile_chat():
    """
    提交用户回答，获取 AI 反馈（实时面试单轮）

    请求体：
      {
        "session_id": 12,
        "question": "请介绍一下你的项目经验",
        "answer": "我在 xx 公司..."
      }

    返回：
      {
        "dialog_id": 100,
        "seq": 3,
        "feedback": {
          "score": 7,
          "answer_quality": "...",
          "evaluation": "AI 回应文字（直接给 TTS 读）",
          "follow_up_questions": ["..."]
        }
      }
    """
    data = request.get_json() or {}
    session_id = data.get('session_id')
    question = (data.get('question') or '').strip()
    answer = (data.get('answer') or '').strip()

    if not session_id or not question or not answer:
        return error('session_id / question / answer 必填', 400)
    if len(answer) > 4000:
        return error('answer 过长（≤4000 字符）', 400)

    sess = InterviewRepository.find_session_by_id(int(session_id))
    if not sess:
        return error('面试会话不存在', 404)
    if sess.status == SessionStatus.COMPLETED:
        return error('该面试已结束，无法继续对话', 400)

    # 状态推进
    if sess.status == SessionStatus.PREPARING:
        sess.status = SessionStatus.IN_PROGRESS
        InterviewRepository.update_session(sess)

    # 历史对话
    existing = InterviewRepository.find_dialogs_by_session(sess.id)
    dialog_history = '\n'.join([
        f"Q{d.seq}: {d.question}\nA{d.seq}: {d.answer}" for d in existing
    ])

    candidate = CandidateRepository.find_by_id(sess.candidate_id)
    position = PositionRepository.find_by_id(candidate.position_id)

    # AI 反馈
    logger.info(f'[mobile/chat] session={sess.id} answer_len={len(answer)}')
    t0 = time.time()
    feedback = InterviewService.get_dialog_feedback(
        candidate.name, position.name,
        candidate.resume_text or '',
        dialog_history, question, answer
    )
    elapsed = round(time.time() - t0, 1)
    logger.info(f'[mobile/chat] 反馈完成 耗时 {elapsed}s')

    # 评分提取（鲁棒版，从顶层 score / 嵌套 feedback / score_breakdown / 顾问分 / 文本 顺序回退）
    if not feedback:
        feedback = {
            'score': 5,
            'answer_quality': '待评估',
            'evaluation': 'AI 暂时不可用，请继续回答下一题。',
            'follow_up_questions': []
        }
    score = _extract_score(feedback)
    if isinstance(feedback, dict):
        feedback['score'] = score   # 同步写回顶层，方便客户端/调试

    # 存对话
    dialog = InterviewDialog(
        session_id=sess.id,
        question=question,
        answer=answer,
        ai_feedback=json.dumps(feedback, ensure_ascii=False) if feedback else None,
        seq=len(existing) + 1,
        parent_seq=None
    )
    InterviewRepository.save_dialog(dialog)

    return success({
        'dialog_id': dialog.id,
        'seq': dialog.seq,
        'score': score,             # 【新增】顶层 score，客户端可直接读
        'feedback': feedback,
        'elapsed': elapsed
    })


# ============================================================
# 4. 结束面试 + 存结果
# ============================================================
@mobile_bp.route('/result', methods=['POST'])
@mobile_token_required
def mobile_result():
    """
    结束面试 → 板块切分 → 3+1 评估报告

    请求体：{ "session_id": 12 }

    返回：完整 report + topics
    """
    data = request.get_json() or {}
    session_id = data.get('session_id')
    if not session_id:
        return error('session_id 必填', 400)

    sess = InterviewRepository.find_session_by_id(int(session_id))
    if not sess:
        return error('面试会话不存在', 404)
    if sess.status == SessionStatus.COMPLETED and sess.report:
        # 幂等：已结束 → 直接返回已存报告
        try:
            cached = json.loads(sess.report) if isinstance(sess.report, str) else sess.report
        except Exception:
            cached = sess.report
        return success({
            'session_id': sess.id,
            'report': cached,
            'topics': [t.to_dict() for t in InterviewRepository.find_topics_by_session(sess.id)],
            'cached': True
        })

    # 收尾
    sess.status = SessionStatus.COMPLETED
    InterviewRepository.update_session(sess)

    dialogs = InterviewRepository.find_dialogs_by_session(sess.id)
    full_dialogs = [
        {'seq': d.seq, 'question': d.question or '', 'answer': d.answer or ''}
        for d in dialogs
    ]

    candidate = CandidateRepository.find_by_id(sess.candidate_id)
    position = PositionRepository.find_by_id(candidate.position_id)

    # 解析出题策略
    questions_plan = None
    if sess.questions_plan:
        try:
            questions_plan = (
                json.loads(sess.questions_plan)
                if isinstance(sess.questions_plan, str) else sess.questions_plan
            )
        except Exception:
            pass

    # 板块切分
    logger.info(f'[mobile/result] session={sess.id} 开始板块切分, dialogs={len(dialogs)}')
    t0 = time.time()
    segment_result = InterviewService.segment_topics(candidate.name, position.name, full_dialogs)
    topics = (segment_result or {}).get('topics', []) if segment_result else []
    logger.info(f'[mobile/result] 板块切分完成 耗时 {round(time.time()-t0,1)}s, 共 {len(topics)} 板块')

    InterviewRepository.delete_topics_by_session(sess.id)
    saved_topics = []
    for t in topics:
        topic = InterviewTopic(
            session_id=sess.id,
            topic_index=t.get('topic_index', len(saved_topics) + 1),
            title=(t.get('topic_title') or t.get('title') or '未命名板块')[:120],
            summary=t.get('topic_summary') or t.get('summary') or '',
            dialog_ids_json=json.dumps(
                t.get('dialog_indexes') or t.get('dialog_ids') or [],
                ensure_ascii=False
            )
        )
        InterviewRepository.save_topic(topic)
        saved_topics.append(topic)

    # 拼接板块摘要
    if saved_topics:
        topic_blocks = [f"### 板块 {t.topic_index}：{t.title}\n{t.summary}" for t in saved_topics]
        full_dialogs_text = '\n\n'.join(topic_blocks)
    else:
        full_dialogs_text = '\n'.join([
            f"Q{d.seq}: {d.question}\nA{d.seq}: {d.answer}" for d in dialogs
        ])

    # 3+1 评估
    t1 = time.time()
    report = InterviewService.generate_report(
        position, candidate.name, full_dialogs_text,
        questions_plan=questions_plan
    )
    logger.info(f'[mobile/result] 3+1 评估完成 耗时 {round(time.time()-t1,1)}s')

    if report and isinstance(report, dict):
        report['topics'] = [t.to_dict() for t in saved_topics]
        sess.report = json.dumps(report, ensure_ascii=False)
        InterviewRepository.update_session(sess)
        log_operation(
            'mobile_finish', 'interview_session', sess.id, candidate.name,
            f'topics={len(saved_topics)}, dialogs={len(dialogs)}'
        )
        return success({
            'session_id': sess.id,
            'report': report,
            'topics': [t.to_dict() for t in saved_topics]
        })
    else:
        return error('生成评价报告失败', 502)
