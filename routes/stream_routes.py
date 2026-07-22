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
from utils.logger import logger
import json
import queue
import threading

stream_bp = Blueprint('stream', __name__, url_prefix='/api/stream')


def _sse_response(generator_fn):
    """包装 SSE 响应"""
    return Response(
        stream_with_context(generator_fn()),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'X-Accel-Buffering': 'no',
            'Connection': 'close',
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
    """SSE: 候选人分析全流水线（简历评估 → 出题 → 创建会话）"""
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
        q, on_progress = _create_progress_bridge()
        app = current_app._get_current_object()
        result_holder = {'resume': None, 'questions': None, 'session': None, 'error': None}

        def worker():
            with app.app_context():
                try:
                    # 在 worker 线程内重新加载对象，避免跨线程 DetachedInstanceError
                    cand = CandidateRepository.find_by_id(candidate_id)
                    pos = PositionRepository.find_by_id(cand.position_id)
                    
                    # 阶段A: 简历评估 (3+1)
                    from services.resume_service import ResumeService
                    result_holder['resume'] = ResumeService.analyze_resume(
                        pos, cand.resume_text, cand.name
                    )
                    if not result_holder['resume']:
                        result_holder['error'] = '简历评估失败'
                        return
                    # 保存简历分析结果
                    cand.ai_analysis = json.dumps(result_holder['resume'], ensure_ascii=False)
                    cand.match_score = result_holder['resume'].get('match_score', 0)
                    CandidateRepository.update(cand)

                    # 阶段B: 出题 (3+1)
                    pos_analysis = None
                    if pos.ai_analysis:
                        try:
                            pos_analysis = json.loads(pos.ai_analysis) if isinstance(pos.ai_analysis, str) else pos.ai_analysis
                        except Exception:
                            pass
                    
                    result_holder['questions'] = InterviewService.generate_questions(
                        pos, cand, pos_analysis,
                        result_holder['resume'], cand.resume_text,
                        on_progress=on_progress
                    )
                    if result_holder['questions']:
                        # 创建面试会话
                        session = InterviewSession(
                            candidate_id=cand.id,
                            status=SessionStatus.PREPARING,
                            questions_plan=json.dumps(result_holder['questions'], ensure_ascii=False)
                        )
                        InterviewRepository.save_session(session)
                        # 在 worker 线程内序列化 session，避免 DetachedInstanceError
                        result_holder['session_dict'] = session.to_dict()
                except Exception as e:
                    result_holder['error'] = str(e)
                finally:
                    q.put('__DONE__')

        t = threading.Thread(target=worker, daemon=True)
        t.start()

        while True:
            try:
                event = q.get(timeout=300)
                if event == '__DONE__':
                    break
                yield _sse_event('progress', event)
            except queue.Empty:
                yield f": keepalive\n\n"

        if result_holder['error']:
            yield _sse_event('error', {'message': result_holder['error']})
        elif result_holder['resume']:
            yield _sse_event('complete', {
                'result': result_holder['resume'],
                'session': result_holder.get('session_dict')
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
