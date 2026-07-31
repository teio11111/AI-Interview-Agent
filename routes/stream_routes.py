"""SSE 流式路由 - 多智能体协作过程实时推送"""
from flask import Blueprint, Response, stream_with_context, request, current_app
from repositories.candidate_repository import CandidateRepository
from repositories.position_repository import PositionRepository
from repositories.interview_repository import InterviewRepository
from models.interview import InterviewSession
from constants import SessionStatus
from services.interview_service import InterviewService
from utils.response import error
from utils.auth import login_required
from utils.audit import log_interview_created, log_interview_finished
from utils.logger import logger
import json
import queue
import threading

stream_bp = Blueprint('stream', __name__, url_prefix='/api/stream')


def _sse_response(generator_fn):
    """包装 SSE 响应

    【v3.1 修复】去掉 'Connection: close' 头——
    waitress 严格遵循 PEP 3333，拒绝 WSGI 应用设置 hop-by-hop 头，会报 AssertionError。
    waitress 默认会用 keep-alive，浏览器原生支持 SSE 不需要显式 Connection: close。
    """
    return Response(
        stream_with_context(generator_fn()),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'X-Accel-Buffering': 'no',
        }
    )


def _sse_event(event_type, data):
    """格式化 SSE 事件"""
    payload = json.dumps({'event': event_type, **data}, ensure_ascii=False)
    return f"data: {payload}\n\n"


def _create_progress_bridge():
    """创建进度桥接器：回调 → 队列 → SSE 生成器"""
    q = queue.Queue()

    def on_progress(event_type, data):
        """回调函数，编排器调用"""
        try:
            q.put({'event': event_type, **data}, timeout=1)
        except Exception:
            pass

    return q, on_progress


@stream_bp.route('/position/<int:position_id>')
@login_required(role='admin')
def stream_position_analysis(position_id):
    """SSE: 岗位分析流式推送"""
    position = PositionRepository.find_by_id(position_id)
    if not position:
        return error('岗位不存在', 404)

    def generate():
        q, on_progress = _create_progress_bridge()
        app = current_app._get_current_object()
        result_holder = {'result': None, 'error': None}
        
        def worker():
            with app.app_context():
                try:
                    result_holder['result'] = InterviewService.analyze_position(
                        position.name, position.tech_requirements, position.jd_content,
                        on_progress=on_progress
                    )
                    # 保存分析结果到数据库
                    if result_holder['result']:
                        pos = PositionRepository.find_by_id(position_id)
                        if pos:
                            pos.ai_analysis = json.dumps(result_holder['result'], ensure_ascii=False)
                            PositionRepository.update(pos)
                except Exception as e:
                    result_holder['error'] = str(e)
                finally:
                    q.put('__DONE__')
        
        t = threading.Thread(target=worker, daemon=True)
        t.start()
        
        while True:
            try:
                event = q.get(timeout=120)
                if event == '__DONE__':
                    break
                yield _sse_event('progress', event)
            except queue.Empty:
                yield f": keepalive\n\n"
        
        if result_holder['error']:
            yield _sse_event('error', {'message': result_holder['error']})
        elif result_holder['result']:
            yield _sse_event('complete', {'result': result_holder['result']})
        else:
            yield _sse_event('error', {'message': '岗位分析失败'})

    return _sse_response(generate)


@stream_bp.route('/resume/<int:candidate_id>')
@login_required(role='admin')
def stream_resume_evaluation(candidate_id):
    """SSE: 简历评估流式推送（3评估师并行+汇总）"""
    candidate = CandidateRepository.find_by_id(candidate_id)
    if not candidate:
        return error('候选人不存在', 404)
    position = PositionRepository.find_by_id(candidate.position_id)
    if not position:
        return error('关联岗位不存在', 404)

    # 获取岗位分析结果（如果已有）
    position_analysis = None
    if position.ai_analysis:
        try:
            position_analysis = json.loads(position.ai_analysis) if isinstance(position.ai_analysis, str) else position.ai_analysis
        except Exception:
            pass

    def generate():
        q, on_progress = _create_progress_bridge()
        app = current_app._get_current_object()
        result_holder = {'result': None, 'error': None}
        
        def worker():
            with app.app_context():
                try:
                    result_holder['result'] = InterviewService.evaluate_resume(
                        position.name, position.tech_requirements, position.jd_content,
                        candidate.resume_text, position_analysis, candidate.name,
                        on_progress=on_progress
                    )
                except Exception as e:
                    result_holder['error'] = str(e)
                finally:
                    q.put('__DONE__')
        
        t = threading.Thread(target=worker, daemon=True)
        t.start()
        
        while True:
            try:
                event = q.get(timeout=180)
                if event == '__DONE__':
                    break
                yield _sse_event('progress', event)
            except queue.Empty:
                yield f": keepalive\n\n"
        
        if result_holder['error']:
            yield _sse_event('error', {'message': result_holder['error']})
        elif result_holder['result']:
            yield _sse_event('complete', {'result': result_holder['result']})
        else:
            yield _sse_event('error', {'message': '简历评估失败'})

    return _sse_response(generate)


@stream_bp.route('/candidate-analysis/<int:candidate_id>', methods=['POST'])
@login_required(role='admin')
def stream_candidate_analysis(candidate_id):
    """SSE: 候选人分析全流水线（v2.2 重构【同步仅简历评估 + 兑底题、LLM 出题后台异步】）

    设计：
      阶段A 【同步、必须完成】简历评估（3并行 + 1汇总）→ ~30-35s
      阶段B 【同步、<0.5s】兑底题目生成 → 主线程不等待 LLM
      阶段C 【后台异步】LLM 真出题，由 daemon 线程跑，跑完后写 session.questions_plan

    SSE 超时：【v3.3】120s 强制 yield error，1分钟后前端预警提示用户“分析时间偏长”。
    """
    candidate = CandidateRepository.find_by_id(candidate_id)
    if not candidate:
        return error('候选人不存在', 404)
    position = PositionRepository.find_by_id(candidate.position_id)
    if not position:
        return error('关联岗位不存在', 404)
    if not candidate.resume_text:
        return error('简历内容为空', 400)

    position_analysis = None
    if position.ai_analysis:
        try:
            position_analysis = json.loads(position.ai_analysis) if isinstance(position.ai_analysis, str) else position.ai_analysis
        except Exception:
            pass

    def generate():
        # 【v3.6】在 generate 函数顶部 explictily import，避免嵌套 worker() 闪 free variable 错误。
        # （Python 闭包+ inline from-import 会让 worker 无法解析外层作用域的 CandidateRepository）
        from repositories.candidate_repository import CandidateRepository
        from repositories.position_repository import PositionRepository
        import time
        q, on_progress = _create_progress_bridge()
        app = current_app._get_current_object()
        result_holder = {
            'resume': None,
            'session_dict': None,
            'error': None,
            'completed_at_step': None,
            'partial_resume': None,       # 【v3.6】partial 结果（tech+soft）
            'partial_saved_at_step': None, # 【v3.6】partial 是否已写入人库
        }
        # 【v3.6】SSE 超时 320s = 120(基础) + 180(hidden) + 20(buffer)
        # 阶段 A: tech+soft ≤120s 后 yield partial_complete（推前端）并入友
        # 阶段 B: hidden 单独跑 ≤180s
        # 总 SSE 保持连接直到 2 阶段都完成，避免前端误以为“卡住了”
        SSE_TIMEOUT = 320
        # 前端预警阈值（60s）：此处仅作文档化，实际由前端独立计时。
        SLOW_WARNING_AT = 60

        def worker():
            """后台 worker：跑同步简历评估"""
            # 【v3.6】在 worker 函数顶部直接 inline import，避免让 worker 闪
            # "imports not allowed at top of function" 带来 other-name free variable 问题
            from services.resume_service import ResumeService
            with app.app_context():
                try:
                    cand = CandidateRepository.find_by_id(candidate_id)
                    pos = PositionRepository.find_by_id(cand.position_id)

                    # 【v3.1】手动推送阶段进度事件（调整初始 percent 以配合缓动）
                    q.put({'event': 'progress', 'stage': '简历评估',
                           'agent': 'AI 调度员',
                           'message': '简历评估启动，三位评估师并行分析中…',
                           'percent': 15})

                    # 阶段A: 简历评估（同步必须完成）
                    result_holder['resume'] = ResumeService.analyze_resume(
                        pos, cand.resume_text, cand.name, on_progress=on_progress,
                    )
                    if not result_holder['resume']:
                        result_holder['error'] = '简历评估失败'
                        return
                    result_holder['completed_at_step'] = 'resume_eval_done'

                    # 【v3.1】进度推送：汇总师完成 ⇒ 75%
                    q.put({'event': 'progress', 'stage': '简历评估',
                           'agent': '简历汇总师',
                           'message': '简历汇总完成',
                           'percent': 75})

                    # 保存简历评估结果（v2.2 LLM 全面失败时 match_score=0）
                    is_llm_failed = bool(result_holder['resume'].get('llm_fully_failed'))
                    cand.ai_analysis = json.dumps(result_holder['resume'], ensure_ascii=False)
                    cand.match_score = 0 if is_llm_failed else result_holder['resume'].get('match_score', 0)
                    CandidateRepository.update(cand)

                    q.put({'event': 'progress', 'stage': '兑底题目',
                           'agent': '题目模板',
                           'message': '正在生成兜底面试题（保证 5 道题立即可用）…',
                           'percent': 80})

                    # 阶段B: 同步生成兑底题目（不调 LLM，<0.5s）
                    from services.interview_service import InterviewService
                    fallback_questions = InterviewService.generate_fallback_questions(
                        pos, cand.resume_text
                    )
                    sess = InterviewSession(
                        candidate_id=cand.id,
                        status=SessionStatus.PREPARING,
                        questions_plan=json.dumps(fallback_questions, ensure_ascii=False)
                    )
                    InterviewRepository.save_session(sess)
                    result_holder['session_dict'] = sess.to_dict()
                    result_holder['completed_at_step'] = 'fallback_session_created'
                    result_holder['fallback_session'] = sess  # 【v3.6.5】保存引用，便于覆盖

                    q.put({'event': 'progress', 'stage': '兑底题目',
                           'agent': '题目模板',
                           'message': '兜底面试题已生成',
                           'percent': 95})

                    # 【v4.1 性能修复】LLM 精修出题改为 daemon thread 异步执行
                    # v3.6.5 改同步导致总耗时从 ~68s 暴增到 ~170s（违反 60s SLA）
                    # 修复：先用兑底题立即返回 SSE complete，精修出题在后台异步完成
                    # 前端拿到兑底题即可开始面试，精修完成后 DB 自动覆盖
                    _sess_id = sess.id
                    _cand_id = cand.id
                    _pos_id = pos.id
                    _cand_name = cand.name

                    def _refine_worker():
                        """后台异步精修出题：独立 app_context，独立 DB 会话"""
                        with app.app_context():
                            try:
                                from services.interview_service import InterviewService as _IS
                                from repositories.candidate_repository import CandidateRepository as _CR
                                from repositories.position_repository import PositionRepository as _PR
                                _cand = _CR.find_by_id(_cand_id)
                                _pos = _PR.find_by_id(_pos_id)
                                _sess = InterviewRepository.find_session_by_id(_sess_id)
                                if not _cand or not _pos or not _sess:
                                    logger.warning(f'[v4.1 精修] 对象不存在: cand={_cand_id} pos={_pos_id} sess={_sess_id}')
                                    return
                                refined = _IS.generate_questions(
                                    _pos, _cand, _pos.ai_analysis, _cand.ai_analysis,
                                    _cand.resume_text,
                                )
                                if refined and isinstance(refined, dict) and refined.get('questions'):
                                    _sess.questions_plan = json.dumps(refined, ensure_ascii=False)
                                    InterviewRepository.update_session(_sess)
                                    logger.info(
                                        f'[v4.1 精修] LLM 出题成功: candidate={_cand_name}, '
                                        f'session={_sess.id}, questions={len(refined["questions"])}'
                                    )
                                else:
                                    logger.warning(
                                        f'[v4.1 精修] LLM 返回为空,保留兑底题: '
                                        f'candidate={_cand_name}, session={_sess.id}'
                                    )
                            except Exception as _e:
                                logger.error(f'[v4.1 精修] LLM 精修异常: candidate={_cand_name}, error={_e}')

                    _refine_thread = threading.Thread(target=_refine_worker, daemon=True)
                    _refine_thread.start()
                    logger.info(f'[v4.1] 精修出题已提交后台线程: candidate={_cand_name}, session={_sess_id}')
                except Exception as e:
                    result_holder['error'] = str(e)
                finally:
                    q.put('__DONE__')

        t = threading.Thread(target=worker, daemon=True)
        t.start()
        start_time = time.time()
        # 【v4.1 演示前】隐性阶段 30s 没业务事件时，每 5s yield 一次 progress 让前端进度条跳动
        _last_idle_progress = start_time

        while True:
            # 超时控制：超过 120s 强制 yield error
            elapsed = time.time() - start_time
            if elapsed > SSE_TIMEOUT:
                result_holder['error'] = (
                    f'简历分析超过 2 分钟未返回，可能是 LLM 服务忙或简历过长。'
                    f'请稍后重试，或检查网络/服务状态。'
                )
                logger.warning(
                    f'[stream_candidate_analysis] SSE 超时 {elapsed:.1f}s > {SSE_TIMEOUT}s，'
                    f'candidate_id={candidate_id}'
                )
                break

            try:
                event = q.get(timeout=1)
                if event == '__DONE__':
                    break
                # 【v3.6】partial_complete 事件需要额外推给前端，让前端提前显示基础分
                if isinstance(event, dict) and event.get('event') == 'partial_complete':
                    # 先让进度 UI 更新
                    yield _sse_event('progress', event)
                    # 接着推一个独立的 partial_complete 事件供前端 modal 使用
                    yield _sse_event('partial_complete', {
                        'partial_result': event.get('partial_result'),
                        'percent': event.get('percent', 65),
                    })
                    # 在 partial 阶段同时把基础结果写入人库，避免候选人列表还是「待分析」
                    if result_holder.get('partial_saved_at_step') != 'partial_saved':
                        try:
                            # CandidateRepository / PositionRepository 已在模块顶部导入
                            partial_res = event.get('partial_result') or {}
                            if partial_res:
                                cand_now = CandidateRepository.find_by_id(candidate_id)
                                pos_now = PositionRepository.find_by_id(cand_now.position_id) if cand_now else None
                                if cand_now:
                                    cand_now.ai_analysis = json.dumps(partial_res, ensure_ascii=False)
                                    is_fail = bool(partial_res.get('llm_fully_failed'))
                                    cand_now.match_score = 0 if is_fail else partial_res.get('match_score', 0)
                                    CandidateRepository.update(cand_now)
                                    result_holder['partial_saved_at_step'] = 'partial_saved'
                                    logger.info(
                                        f'[v3.6] partial 结果已入友 candidate={cand_now.name} '
                                        f'score={cand_now.match_score}'
                                    )
                        except Exception as _e:
                            logger.warning(f'[v3.6] partial 入友失败: {_e}')
                else:
                    yield _sse_event('progress', event)
            except queue.Empty:
                yield f": keepalive\n\n"
                # 【v4.1 演示前】隐性维度 30s 等待期间每 5s yield 一次 progress 事件
                if time.time() - _last_idle_progress > 5:
                    _last_idle_progress = time.time()
                    yield _sse_event('progress', {
                        'agent': 'AI 调度员',
                        'stage': '简历评估',
                        'message': 'AI 隐性维度深度分析中（最长 30 秒）...',
                        'percent': 72,
                    })

        if result_holder['error']:
            yield _sse_event('error', {'message': result_holder['error']})
        elif result_holder['resume']:
            session_dict = result_holder.get('session_dict')
            if session_dict:
                created_session = InterviewRepository.find_session_by_id(session_dict.get('id'))
                if created_session:
                    log_interview_created(created_session, candidate.name)
            yield _sse_event('complete', {
                'result': result_holder['resume'],
                'session': session_dict,
            })
        else:
            yield _sse_event('error', {'message': '候选人分析失败'})

    return _sse_response(generate)


@stream_bp.route('/questions/<int:candidate_id>')
@login_required(role='admin')
def stream_question_generation(candidate_id):
    """SSE: 出题流式推送（3出题官并行+选题）"""
    candidate = CandidateRepository.find_by_id(candidate_id)
    if not candidate:
        return error('候选人不存在', 404)
    position = PositionRepository.find_by_id(candidate.position_id)
    if not position:
        return error('关联岗位不存在', 404)

    # 解析已有的分析结果
    position_analysis = None
    if position.ai_analysis:
        try:
            position_analysis = json.loads(position.ai_analysis) if isinstance(position.ai_analysis, str) else position.ai_analysis
        except Exception:
            pass
    
    resume_analysis = None
    if candidate.ai_analysis:
        try:
            resume_analysis = json.loads(candidate.ai_analysis) if isinstance(candidate.ai_analysis, str) else candidate.ai_analysis
        except Exception:
            pass

    def generate():
        q, on_progress = _create_progress_bridge()
        app = current_app._get_current_object()
        result_holder = {'result': None, 'error': None}
        
        def worker():
            with app.app_context():
                try:
                    result_holder['result'] = InterviewService.generate_questions(
                        position, candidate, position_analysis, resume_analysis,
                        candidate.resume_text, on_progress=on_progress
                    )
                except Exception as e:
                    result_holder['error'] = str(e)
                finally:
                    q.put('__DONE__')
        
        t = threading.Thread(target=worker, daemon=True)
        t.start()
        
        while True:
            try:
                event = q.get(timeout=180)
                if event == '__DONE__':
                    break
                yield _sse_event('progress', event)
            except queue.Empty:
                yield f": keepalive\n\n"
        
        if result_holder['error']:
            yield _sse_event('error', {'message': result_holder['error']})
        elif result_holder['result']:
            # 自动创建或复用面试会话并保存出题结果
            try:
                # 检查是否已有 preparing 状态的 session，有则复用
                existing_sessions = InterviewRepository.find_sessions_by_candidate(candidate_id)
                preparing_session = None
                for s in existing_sessions:
                    if s.status == SessionStatus.PREPARING:
                        preparing_session = s
                        break
                
                if preparing_session:
                    # 复用已有 session，更新出题计划
                    preparing_session.questions_plan = json.dumps(result_holder['result'], ensure_ascii=False)
                    InterviewRepository.update_session(preparing_session)
                    session = preparing_session
                else:
                    # 创建新 session
                    session = InterviewSession(
                        candidate_id=candidate_id,
                        status=SessionStatus.PREPARING,
                        questions_plan=json.dumps(result_holder['result'], ensure_ascii=False)
                    )
                    InterviewRepository.save_session(session)
                    log_interview_created(session, candidate.name)
                yield _sse_event('complete', {'result': result_holder['result'], 'session': session.to_dict()})
            except Exception as e:
                yield _sse_event('error', {'message': f'出题成功但会话创建失败: {e}'})
        else:
            yield _sse_event('error', {'message': '出题失败'})

    return _sse_response(generate)


@stream_bp.route('/dialog/<int:session_id>', methods=['POST'])
@login_required(role='admin')
def stream_dialog_evaluation(session_id):
    """SSE: 面试对话评估流式推送（2顾问并行+主面试官）"""
    session = InterviewRepository.find_session_by_id(session_id)
    if not session:
        return error('面试会话不存在', 404)

    data = request.get_json()
    if not data or not data.get('question') or not data.get('answer'):
        return error('问题和回答不能为空', 400)

    candidate = CandidateRepository.find_by_id(session.candidate_id)
    position = PositionRepository.find_by_id(candidate.position_id)

    # 获取历史对话
    existing_dialogs = InterviewRepository.find_dialogs_by_session(session_id)
    dialog_history = '\n'.join([
        f"Q{d.seq}: {d.question}\nA{d.seq}: {d.answer}"
        for d in existing_dialogs
    ])

    def generate():
        q, on_progress = _create_progress_bridge()
        app = current_app._get_current_object()
        result_holder = {'result': None, 'error': None}
        
        def worker():
            with app.app_context():
                try:
                    result_holder['result'] = InterviewService.get_dialog_feedback(
                        candidate.name, position.name, candidate.resume_text,
                        dialog_history, data['question'], data['answer'],
                        on_progress=on_progress
                    )
                except Exception as e:
                    result_holder['error'] = str(e)
                finally:
                    q.put('__DONE__')
        
        t = threading.Thread(target=worker, daemon=True)
        t.start()
        
        while True:
            try:
                event = q.get(timeout=120)
                if event == '__DONE__':
                    break
                yield _sse_event('progress', event)
            except queue.Empty:
                yield f": keepalive\n\n"
        
        if result_holder['error']:
            yield _sse_event('error', {'message': result_holder['error']})
        elif result_holder['result']:
            yield _sse_event('complete', {'result': result_holder['result']})
        else:
            yield _sse_event('error', {'message': '评估失败'})

    return _sse_response(generate)


@stream_bp.route('/report/<int:session_id>', methods=['POST'])
@login_required(role='admin')
def stream_report_generation(session_id):
    """SSE: 评价报告生成流式推送（板块切分 + 3+1 评估）"""
    from models.interview import InterviewTopic

    session = InterviewRepository.find_session_by_id(session_id)
    if not session:
        return error('面试会话不存在', 404)

    candidate = CandidateRepository.find_by_id(session.candidate_id)
    position = PositionRepository.find_by_id(candidate.position_id)

    # 拼接全部对话（供板块切分师使用）
    dialogs = InterviewRepository.find_dialogs_by_session(session_id)
    full_dialogs = [
        {'seq': d.seq, 'question': d.question or '', 'answer': d.answer or ''}
        for d in dialogs
    ]

    # 【Bug 修复】提取每条对话的实时评分（1-10）用于汇总师综合分计算
    # 避免“单轮都 2 分但综合分 41”这种脱钩问题。
    single_round_scores = []
    for d in dialogs:
        if not d.ai_feedback:
            continue
        try:
            fb = json.loads(d.ai_feedback) if isinstance(d.ai_feedback, str) else d.ai_feedback
        except (json.JSONDecodeError, TypeError):
            continue
        score = (fb or {}).get('score')
        if isinstance(score, (int, float)) and 1 <= score <= 10:
            single_round_scores.append(score)
    logger.info(f'[stream_report] 提取到 {len(single_round_scores)} 条单轮评分: {single_round_scores}')

    # 解析出题策略
    questions_plan = None
    if session.questions_plan:
        try:
            questions_plan = json.loads(session.questions_plan) if isinstance(session.questions_plan, str) else session.questions_plan
        except Exception:
            pass

    def generate():
        q, on_progress = _create_progress_bridge()
        app = current_app._get_current_object()
        result_holder = {'result': None, 'error': None, 'topics': None}

        def worker():
            with app.app_context():
                try:
                    # 1) 更新会话状态为已完成
                    sess = InterviewRepository.find_session_by_id(session_id)
                    sess.status = SessionStatus.COMPLETED
                    InterviewRepository.update_session(sess)

                    # 2) 板块切分（单Agent）
                    seg_result = InterviewService.segment_topics(
                        candidate.name, position.name, full_dialogs,
                        on_progress=on_progress
                    )
                    topics = (seg_result or {}).get('topics', []) if seg_result else []
                    logger.info(f'[stream_report] 切分出 {len(topics)} 个板块')

                    # 清理旧板块并保存新板块（save_topic 会同时回填 dialog.topic_id）
                    InterviewRepository.delete_topics_by_session(session_id)
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

                    # 3) 以板块摘要作为 3+1 评估输入
                    if saved_topics:
                        topic_blocks = [
                            f"### 板块 {t.topic_index}：{t.title}\n{t.summary}"
                            for t in saved_topics
                        ]
                        full_text = '\n\n'.join(topic_blocks)
                    else:
                        # 降级：原始拼接
                        lines = []
                        for d in dialogs:
                            tag = f" [追问自Q{d.parent_seq}]" if d.parent_seq else ""
                            lines.append(f"Q{d.seq}{tag}: {d.question}\nA{d.seq}: {d.answer}")
                        full_text = '\n'.join(lines)

                    # 4) 3+1 多智能体并行评估
                    result = InterviewService.generate_report(
                        position, candidate.name, full_text,
                        questions_plan=questions_plan,
                        single_round_scores=single_round_scores,
                        on_progress=on_progress
                    )
                    # 附加板块信息到报告（供前端一次性渲染使用）
                    if result and isinstance(result, dict):
                        result['topics'] = [t.to_dict() for t in saved_topics]
                    result_holder['result'] = result
                    result_holder['topics'] = [t.to_dict() for t in saved_topics]
                except Exception as e:
                    logger.error(f'[stream_report] 失败: {e}')
                    result_holder['error'] = str(e)
                finally:
                    q.put('__DONE__')

        t = threading.Thread(target=worker, daemon=True)
        t.start()

        while True:
            try:
                event = q.get(timeout=180)
                if event == '__DONE__':
                    break
                yield _sse_event('progress', event)
            except queue.Empty:
                yield f": keepalive\n\n"

        if result_holder['error']:
            yield _sse_event('error', {'message': result_holder['error']})
        elif result_holder['result']:
            # 保存报告到会话
            try:
                sess = InterviewRepository.find_session_by_id(session_id)
                sess.report = json.dumps(result_holder['result'], ensure_ascii=False) if isinstance(result_holder['result'], dict) else result_holder['result']
                InterviewRepository.update_session(sess)
                log_interview_finished(
                    sess, candidate.name,
                    len(result_holder.get('topics') or []), len(dialogs)
                )
            except Exception as e:
                logger.error(f'报告保存失败: {e}')
            yield _sse_event('complete', {
                'result': result_holder['result'],
                'topics': result_holder.get('topics') or []
            })
        else:
            yield _sse_event('error', {'message': '评价报告生成失败'})

    return _sse_response(generate)


@stream_bp.route('/meta-evaluation/<int:candidate_id>', methods=['POST'])
@login_required(role='admin')
def stream_meta_evaluation(candidate_id):
    """SSE: 综合元评估流式推送"""
    from services.interview_service import get_orchestrator
    
    candidate = CandidateRepository.find_by_id(candidate_id)
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

    def generate():
        q, on_progress = _create_progress_bridge()
        app = current_app._get_current_object()
        result_holder = {'result': None, 'error': None}
        
        def worker():
            with app.app_context():
                try:
                    orch = get_orchestrator()
                    result_holder['result'] = orch.generate_meta_evaluation(
                        position=position,
                        candidate=candidate,
                        resume_evaluation=resume_evaluation,
                        interview_sessions=interview_data,
                        on_progress=on_progress
                    )
                except Exception as e:
                    result_holder['error'] = str(e)
                finally:
                    q.put('__DONE__')
        
        t = threading.Thread(target=worker, daemon=True)
        t.start()
        
        while True:
            try:
                event = q.get(timeout=180)
                if event == '__DONE__':
                    break
                yield _sse_event('progress', event)
            except queue.Empty:
                yield f": keepalive\n\n"
        
        if result_holder['error']:
            yield _sse_event('error', {'message': result_holder['error']})
        elif result_holder['result']:
            # 保存结果到数据库
            if result_holder['result']:
                candidate.meta_evaluation = json.dumps(result_holder['result'], ensure_ascii=False)
                candidate.meta_eval_round_count = len(interview_data)
                CandidateRepository.update(candidate)
            yield _sse_event('complete', {'result': result_holder['result'], 'candidate_id': candidate_id})
        else:
            yield _sse_event('error', {'message': '综合元评估失败'})

    return _sse_response(generate)
