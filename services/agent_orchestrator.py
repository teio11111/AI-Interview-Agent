"""Agent 编排器 - 协调多智能体协作完成面试流程（专家小组+汇总裁判模式）"""
from concurrent.futures import ThreadPoolExecutor, as_completed
from flask import current_app
import time
from datetime import datetime

from agents import (
    PositionAnalystAgent,
    TechEvaluatorAgent,
    SoftEvaluatorAgent,
    HiddenEvaluatorAgent,
    ResumeCoordinatorAgent,
    ProjectQuestionerAgent,
    SkillQuestionerAgent,
    WeaknessQuestionerAgent,
    QuestionCoordinatorAgent,
    TechInterviewerAgent,
    SoftInterviewerAgent,
    InterviewerAgent,
    InterviewProjectEvaluatorAgent,
    InterviewTechEvaluatorAgent,
    InterviewSoftEvaluatorAgent,
    InterviewEvalCoordinatorAgent,
    TopicSegmenterAgent,
    ComprehensiveMetaEvaluatorAgent,
)
from utils.logger import logger


class AgentOrchestrator:
    """Agent 编排器（多智能体协作模式）
    
    架构：专家小组 + 汇总裁判
    
    阶段1：岗位分析师（1个）→ 分析 JD
    阶段2：简历评估（3并行 + 1汇总）
        ├── 技术评估师 ──┐
        ├── 综合素质评估师 ─┤── 简历汇总师
        └── 隐性因素评估师 ─┘
    阶段3：出题（3并行 + 1选题）
        ├── 项目深挖出题 ──┐
        ├── 技能验证出题 ──┤── 选题官
        └── 短板探测出题 ──┘
    阶段4：面试（2并行 + 1主面试官）
        ├── 技术顾问 ──┐
        └── 综合顾问 ──┤── 主面试官
    阶段5：面试评价（3并行 + 1汇总）
        ├── 项目评估师 ──┐
        ├── 技术评估师 ──┤── 面试汇总师
        └── 素质评估师 ──┘
    阶段6：综合元评估（1个）
        汇总岗位分析 + 简历评估 + 各轮面试报告 → 最终决策
    
    每个阶段支持 on_progress 回调用于 SSE 实时推送。
    """

    def __init__(self):
        """初始化所有 Agent"""
        # 岗位分析
        self.position_analyst = PositionAnalystAgent()
        
        # 简历评估（3专家 + 1汇总）
        self.tech_evaluator = TechEvaluatorAgent()
        self.soft_evaluator = SoftEvaluatorAgent()
        self.hidden_evaluator = HiddenEvaluatorAgent()
        self.resume_coordinator = ResumeCoordinatorAgent()
        
        # 出题（3出题官 + 1选题官）
        self.project_questioner = ProjectQuestionerAgent()
        self.skill_questioner = SkillQuestionerAgent()
        self.weakness_questioner = WeaknessQuestionerAgent()
        self.question_coordinator = QuestionCoordinatorAgent()
        
        # 面试（2顾问 + 1主面试官）
        self.tech_interviewer = TechInterviewerAgent()
        self.soft_interviewer = SoftInterviewerAgent()
        self.interviewer = InterviewerAgent()
        
        # 面试评价（3评估师 + 1汇总）
        self.interview_project_eval = InterviewProjectEvaluatorAgent()
        self.interview_tech_eval = InterviewTechEvaluatorAgent()
        self.interview_soft_eval = InterviewSoftEvaluatorAgent()
        self.interview_eval_coord = InterviewEvalCoordinatorAgent()

        # 板块切分（1个，面试结束后使用）
        self.topic_segmenter = TopicSegmenterAgent()

        # 综合元评估（最后阶段的最终裁判）
        self.meta_evaluator = ComprehensiveMetaEvaluatorAgent()

        logger.info('Agent 编排器初始化完成（多智能体协作模式）')

    def _emit(self, on_progress, event_type, agent_name, stage, message=''):
        """发送进度事件"""
        if on_progress:
            try:
                on_progress(event_type, {
                    'agent': agent_name,
                    'stage': stage,
                    'message': message,
                    'timestamp': datetime.now().isoformat()
                })
            except Exception:
                pass

    def _run_parallel(self, agents_map, common_args, on_progress, stage, max_workers=3):
        """通用并行执行器：并行调用多个 Agent，收集结果

        Args:
            agents_map: {key: (name, func)} 字典
            common_args: 公共参数元组
            on_progress: 进度回调
            stage: 阶段名称
            max_workers: 最大线程数

        Returns:
            dict: {key: result}
        """
        results = {}
        start = time.time()

        for key, (name, _) in agents_map.items():
            self._emit(on_progress, 'agent_start', name, stage, f'{name}开始工作...')

        app = current_app._get_current_object()

        def _wrap(f):
            def wrapper(*args):
                with app.app_context():
                    return f(*args)
            return wrapper

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {}
            for key, (name, func) in agents_map.items():
                future = executor.submit(_wrap(func), *common_args)
                futures[future] = (key, name)

            for future in as_completed(futures):
                key, name = futures[future]
                elapsed = round(time.time() - start, 1)
                try:
                    results[key] = future.result()
                    self._emit(on_progress, 'agent_complete', name, stage,
                               f'{name}完成 ({elapsed}s)')
                except Exception as e:
                    logger.error(f'[{name}] {stage}失败: {e}')
                    results[key] = None
                    self._emit(on_progress, 'agent_error', name, stage,
                               f'{name}出错: {e}')

        return results

    # ===== 阶段1：岗位分析 =====
    def analyze_position(self, position_name, tech_requirements, jd_content,
                         on_progress=None):
        """阶段1：岗位分析师分析岗位

        Returns:
            dict: 岗位分析结果
        """
        self._emit(on_progress, 'stage_start', '', '岗位分析', '岗位分析师开始分析...')
        self._emit(on_progress, 'agent_start', '岗位分析师', '岗位分析', '正在分析岗位 JD...')
        
        start = time.time()
        result = self.position_analyst.analyze(position_name, tech_requirements, jd_content)
        elapsed = round(time.time() - start, 1)
        
        self._emit(on_progress, 'agent_complete', '岗位分析师', '岗位分析',
                   f'岗位分析完成 ({elapsed}s)')
        self._emit(on_progress, 'stage_complete', '', '岗位分析', '岗位分析阶段完成')
        return result

    # ===== 阶段2：简历评估（3并行+1汇总）=====
    def evaluate_resume(self, position_name, tech_requirements, jd_content,
                        resume_text, position_analysis=None, candidate_name='',
                        on_progress=None):
        """阶段2：三位评估师并行评估 + 汇总师综合

        Returns:
            dict: 统一简历画像
        """
        self._emit(on_progress, 'stage_start', '', '简历评估', '三位评估师开始并行工作...')
        
        common_args = (position_name, tech_requirements, jd_content, resume_text,
                       position_analysis, candidate_name)
        
        # 并行调用 3 个评估师
        agents_map = {
            'tech': ('技术评估师', self.tech_evaluator.evaluate),
            'soft': ('综合素质评估师', self.soft_evaluator.evaluate),
            'hidden': ('隐性因素评估师', self.hidden_evaluator.evaluate),
        }
        
        results = self._run_parallel(agents_map, common_args, on_progress, '简历评估')
        
        # 汇总
        self._emit(on_progress, 'agent_start', '简历汇总师', '简历评估', '正在综合三方意见...')
        start_coord = time.time()
        result = self.resume_coordinator.synthesize(
            results.get('tech'), results.get('soft'), results.get('hidden'),
            position_name, candidate_name
        )
        elapsed_coord = round(time.time() - start_coord, 1)
        
        self._emit(on_progress, 'agent_complete', '简历汇总师', '简历评估',
                   f'简历汇总完成 ({elapsed_coord}s)')
        self._emit(on_progress, 'stage_complete', '', '简历评估', '简历评估阶段完成')
        
        # 强制合并隐性评估师的原始详细数据（双保险：Prompt + 代码层）
        if result and isinstance(result, dict):
            hidden_raw = results.get('hidden') or {}
            # 强制覆盖 candidate_profile（确保详细嵌套结构不丢失）
            hidden_profile = hidden_raw.get('candidate_profile')
            if hidden_profile and isinstance(hidden_profile, dict):
                # 检查汇总师的输出是否丢失了详细字段
                coord_profile = result.get('candidate_profile')
                if not coord_profile or not isinstance(coord_profile, dict) or \
                   len(coord_profile) < len(hidden_profile):
                    result['candidate_profile'] = hidden_profile
            # 强制覆盖 implicit_requirement_mapping
            hidden_mapping = hidden_raw.get('implicit_requirement_mapping')
            if hidden_mapping and isinstance(hidden_mapping, list) and len(hidden_mapping) > 0:
                coord_mapping = result.get('implicit_requirement_mapping')
                if not coord_mapping or not isinstance(coord_mapping, list) or \
                   len(coord_mapping) < len(hidden_mapping):
                    result['implicit_requirement_mapping'] = hidden_mapping
        
        # 附加各专家的原始结果（供后续阶段参考）
        if result and isinstance(result, dict):
            result['_expert_details'] = {
                'tech': results.get('tech'),
                'soft': results.get('soft'),
                'hidden': results.get('hidden'),
            }
        
        return result

    # ===== 阶段3：出题（3并行+1选题）=====
    def design_questions(self, position_name, tech_requirements,
                         position_analysis, resume_analysis, resume_text,
                         on_progress=None):
        """阶段3：三位出题官并行出题 + 选题官审核定稿

        Returns:
            dict: 面试问题列表（含审核记录）
        """
        self._emit(on_progress, 'stage_start', '', '出题', '三位出题官开始并行工作...')
        
        common_args = (position_name, tech_requirements,
                       position_analysis, resume_analysis, resume_text)
        
        agents_map = {
            'project': ('项目深挖出题官', self.project_questioner.design),
            'skill': ('技能验证出题官', self.skill_questioner.design),
            'weakness': ('短板探测出题官', self.weakness_questioner.design),
        }
        
        results = self._run_parallel(agents_map, common_args, on_progress, '出题')
        
        # 选题官审核整合
        self._emit(on_progress, 'agent_start', '选题官', '出题', '正在审核整合题目...')
        start_coord = time.time()
        final = self.question_coordinator.select(
            results.get('project'), results.get('skill'), results.get('weakness'),
            position_name, resume_text, resume_analysis
        )
        elapsed_coord = round(time.time() - start_coord, 1)
        
        q_count = len((final or {}).get('questions', []))
        self._emit(on_progress, 'agent_complete', '选题官', '出题',
                   f'选题完成，定稿 {q_count} 题 ({elapsed_coord}s)')
        self._emit(on_progress, 'stage_complete', '', '出题', f'出题阶段完成，共 {q_count} 题')
        
        # 附加辩论日志（兼容旧格式）
        if final and isinstance(final, dict):
            review_log = final.get('review_log', {})
            final['debate_log'] = [
                {'round': 1, 'action': 'parallel_design',
                 'project_count': len((results.get('project') or {}).get('questions', [])),
                 'skill_count': len((results.get('skill') or {}).get('questions', [])),
                 'weakness_count': len((results.get('weakness') or {}).get('questions', []))},
                {'round': 2, 'action': 'review_select',
                 'approved': final.get('approved', True),
                 'total_received': review_log.get('total_received', 0),
                 'total_selected': review_log.get('total_selected', 0),
                 'quality_notes': review_log.get('quality_notes', '')}
            ]
        
        return final

    # ===== 阶段4a：面试对话评估（2并行+1主面试官）=====
    def evaluate_dialog(self, candidate_name, position_name, resume_text,
                        dialog_history, question, answer, on_progress=None):
        """阶段4a：两位顾问并行评估 + 主面试官综合决策

        Returns:
            dict: 反馈结果（含追问建议）
        """
        self._emit(on_progress, 'stage_start', '', '面试评估', '两位顾问开始并行评估...')
        
        common_args = (candidate_name, position_name, resume_text,
                       dialog_history, question, answer)
        
        agents_map = {
            'tech': ('技术顾问', self.tech_interviewer.evaluate),
            'soft': ('综合顾问', self.soft_interviewer.evaluate),
        }
        
        consultations = self._run_parallel(agents_map, common_args, on_progress, '面试评估', max_workers=2)
        
        # 主面试官综合决策
        self._emit(on_progress, 'agent_start', '主面试官', '面试评估', '综合顾问意见做最终决策...')
        start_chief = time.time()
        result = self.interviewer.evaluate_answer(
            *common_args,
            tech_consultation=consultations.get('tech'),
            soft_consultation=consultations.get('soft')
        )
        elapsed_chief = round(time.time() - start_chief, 1)
        
        self._emit(on_progress, 'agent_complete', '主面试官', '面试评估',
                   f'主面试官决策完成 ({elapsed_chief}s)')
        self._emit(on_progress, 'stage_complete', '', '面试评估', '面试评估完成')
        
        return result

    def generate_follow_up(self, resume_text, dialog_chain):
        """阶段4b：主面试官生成追问

        Returns:
            dict: 追问结果
        """
        logger.info('[编排器] 主面试官生成追问')
        return self.interviewer.generate_follow_up(resume_text, dialog_chain)

    # ===== 阶5：面试评价（3并行+1汇总）=====
    def generate_report(self, position_name, tech_requirements,
                        candidate_name, full_dialogs, questions_plan=None,
                        on_progress=None):
        """阶5：三位评估师并行评估 + 汇总师生成最终报告

        Returns:
            dict: 面试评价报告
        """
        self._emit(on_progress, 'stage_start', '', '面试评价', '三位评估师开始并行评估...')
        
        common_args = (position_name, tech_requirements, candidate_name,
                       full_dialogs, questions_plan)
        
        agents_map = {
            'project': ('项目评估师', self.interview_project_eval.evaluate),
            'tech': ('技术评估师', self.interview_tech_eval.evaluate),
            'soft': ('素质评估师', self.interview_soft_eval.evaluate),
        }
        
        results = self._run_parallel(agents_map, common_args, on_progress, '面试评价')
        
        # 汇总师整合
        self._emit(on_progress, 'agent_start', '面试汇总师', '面试评价', '正在综合三方评估...')
        start_coord = time.time()
        result = self.interview_eval_coord.synthesize(
            results.get('project'), results.get('tech'), results.get('soft'),
            position_name, candidate_name
        )
        elapsed_coord = round(time.time() - start_coord, 1)
        
        self._emit(on_progress, 'agent_complete', '面试汇总师', '面试评价',
                   f'汇总完成 ({elapsed_coord}s)')
        self._emit(on_progress, 'stage_complete', '', '面试评价', '面试评价阶段完成')
        
        # 附加各评估师的原始结果
        if result and isinstance(result, dict):
            result['_evaluator_details'] = {
                'project': results.get('project'),
                'tech': results.get('tech'),
                'soft': results.get('soft'),
            }

        return result

    # ===== 阶段5.5：板块切分（单Agent，面试结束后使用）=====
    def segment_topics(self, candidate_name, position_name, full_dialogs,
                      on_progress=None):
        """板块切分师（单Agent）将完整面试对话按话题边界切成若干板块

        Args:
            candidate_name: 候选人姓名
            position_name: 岗位名称
            full_dialogs: 完整对话列表
                [
                    {'seq': 1, 'question': '...', 'answer': '...'},
                    {'seq': 2, 'question': '...', 'answer': '...'},
                    ...
                ]
            on_progress: 进度回调函数

        Returns:
            dict: {
                'topics': [
                    {
                        'topic_index': 1,
                        'topic_title': 'Redis缓存设计',
                        'topic_summary': '候选人介绍了...',
                        'dialog_indexes': [1, 2, 3]
                    },
                    ...
                ],
                'total_topics': 3
            }
        """
        # 将对话列表转为 Q/A 文本格式
        lines = []
        for d in (full_dialogs or []):
            seq = d.get('seq', '?')
            q = (d.get('question') or '').strip()
            a = (d.get('answer') or '').strip()
            tag = f" [追问自Q{d.get('parent_seq')}]" if d.get('parent_seq') else ""
            lines.append(f"Q{seq}{tag}: {q}\nA{seq}: {a}")
        dialogs_text = '\n'.join(lines)

        self._emit(on_progress, 'stage_start', '', '板块切分', '板块切分师开始切分话题...')
        self._emit(on_progress, 'agent_start', '板块切分师', '板块切分', '正在识别话题边界...')

        start = time.time()
        result = self.topic_segmenter.segment(candidate_name, position_name, dialogs_text)
        elapsed = round(time.time() - start, 1)

        topics = (result or {}).get('topics', []) if result else []
        t_count = len(topics)
        self._emit(on_progress, 'agent_complete', '板块切分师', '板块切分',
                   f'切分完成，共 {t_count} 个板块 ({elapsed}s)')
        self._emit(on_progress, 'stage_complete', '', '板块切分', f'板块切分阶段完成，共 {t_count} 个板块')

        if result and isinstance(result, dict):
            result['total_topics'] = t_count

        return result

    # ===== 完整流程编排 =====
    def run_full_pipeline(self, position, candidate, on_progress=None):
        """执行完整的面试准备流水线（岗位分析 → 简历评估 → 出题）

        Args:
            position: Position 模型
            candidate: Candidate 模型
            on_progress: 进度回调函数

        Returns:
            dict: {
                'position_analysis': 岗位分析结果,
                'resume_analysis': 简历评估结果,
                'questions': 面试问题列表
            }
        """
        logger.info(f'[编排器] 启动完整流水线: {candidate.name} → {position.name}')
        
        # 阶段1：岗位分析
        position_analysis = self.analyze_position(
            position.name, position.tech_requirements, position.jd_content,
            on_progress=on_progress
        )
        
        # 阶段2：简历评估（并行）
        resume_analysis = self.evaluate_resume(
            position.name, position.tech_requirements,
            position.jd_content, candidate.resume_text,
            position_analysis, candidate.name,
            on_progress=on_progress
        )
        
        # 阶段3：出题（并行）
        questions = self.design_questions(
            position.name, position.tech_requirements,
            position_analysis, resume_analysis, candidate.resume_text,
            on_progress=on_progress
        )
        
        q_count = len((questions or {}).get('questions', []))
        logger.info(f'[编排器] 流水线完成，出题 {q_count} 道')
        
        return {
            'position_analysis': position_analysis,
            'resume_analysis': resume_analysis,
            'questions': questions
        }

    # ===== 阶段6：综合元评估（最终裁判）=====
    def generate_meta_evaluation(self, position, candidate,
                                 resume_evaluation, interview_sessions,
                                 on_progress=None):
        """阶段6：综合元评估

        汇总岗位分析 + 简历评估 + 各轮面试评价 → 最终招聘决策。
        综合得分与招聘建议均由【系统】根据预设权重计算（避免 LLM 虚高）。
        """
        try:
            # 1. 准备入参：岗位分析与简历原文
            position_analysis = None
            if position.ai_analysis:
                import json
                try:
                    position_analysis = json.loads(position.ai_analysis) \
                        if isinstance(position.ai_analysis, str) else position.ai_analysis
                except Exception:
                    logger.warning('岗位分析 JSON 解析失败，综合元评估将不含岗位信息')

            resume_text = candidate.resume_text or ''

            # 【兼容性】agent 期望 interview_sessions 是 dict 列表，但仓储返回 ORM 模型
            # 这里统一转为 {id, round, report, questions_plan} dict 形式
            normalized_sessions = []
            for idx, sess in enumerate(interview_sessions or []):
                if isinstance(sess, dict):
                    normalized_sessions.append(sess)
                    continue
                # ORM 模型 → dict
                sess_dict = {
                    'id': getattr(sess, 'id', idx + 1),
                    'round': idx + 1,
                    'report': getattr(sess, 'report', None),
                    'questions_plan': getattr(sess, 'questions_plan', None),
                    'status': getattr(sess, 'status', None),
                }
                normalized_sessions.append(sess_dict)
            interview_sessions = normalized_sessions

            self._emit(on_progress, 'agent_start', '综合元评估师',
                       '综合元评估', '综合元评估师开始总结全链路数据...')

            # 2. 调用综合元评估师（LLM 仅负责叙述性结论）
            result = self.meta_evaluator.evaluate(
                position_name=position.name,
                position_analysis=position_analysis,
                candidate_name=candidate.name,
                resume_text=resume_text,
                resume_evaluation=resume_evaluation,
                interview_sessions=interview_sessions,
            )

            if not isinstance(result, dict):
                logger.error('[综合元评估] 返回结果不是 dict')
                self._emit(on_progress, 'stage_complete', '',
                           '综合元评估', '综合元评估阶段失败')
                return None

            # 3. 提取各轮面试综合分（供 Python 加权用）
            round_scores = []
            for i, sess in enumerate(interview_sessions or []):
                report = sess.get('report') if isinstance(sess, dict) else None
                if isinstance(report, str):
                    import json
                    try:
                        report = json.loads(report)
                    except Exception:
                        report = {}
                if isinstance(report, dict):
                    s = report.get('overall_score')
                    if isinstance(s, (int, float)):
                        round_scores.append(float(s))

            # 4. 提取简历匹配度（从第一次简历评估中拿到 match_score）
            resume_match_score = None
            if isinstance(resume_evaluation, dict):
                resume_match_score = resume_evaluation.get('match_score')
                if not isinstance(resume_match_score, (int, float)):
                    resume_match_score = None

            # 5. 【系统计算】综合得分 & 招聘建议
            final_score = ComprehensiveMetaEvaluatorAgent.compute_overall_score(
                resume_match_score=resume_match_score,
                round_scores_100=round_scores,
            )
            final_recommendation = ComprehensiveMetaEvaluatorAgent.recommendation_for(final_score)

            # 检测 LLM 是否填了占位字符串，如果是则用系统生成
            _PLACEHOLDERS = {'系统自动生成', '系统生成', '由系统填充', '由系统填入', '系统填入'}
            llm_rationale = (result.get('decision_rationale') or '').strip()
            if llm_rationale and llm_rationale not in _PLACEHOLDERS:
                decision_rationale = llm_rationale
            else:
                decision_rationale = ComprehensiveMetaEvaluatorAgent.decision_rationale_for(
                    final_score, round_scores, resume_match_score,
                )

            # 6. 覆写 LLM 可能误填的字段（防虚高）
            result['overall_score'] = final_score
            result['final_recommendation'] = final_recommendation
            result['decision_rationale'] = decision_rationale

            # 7. 注入 computation 调试字段
            result['computation'] = {
                'resume_match_score': resume_match_score,
                'round_scores': round_scores,
                'final_score_raw': ComprehensiveMetaEvaluatorAgent.compute_overall_score_raw(
                    resume_match_score=resume_match_score,
                    round_scores_100=round_scores,
                ),
                'n_rounds': len(round_scores),
            }

            self._emit(on_progress, 'stage_complete', '',
                       '综合元评估',
                       f'综合元评估完成: {final_score}/{final_recommendation}')

            logger.info(f'[综合元评估] 完成: {candidate.name} → '
                        f'{final_score} 分 / {final_recommendation}')
            return result

        except Exception as e:
            logger.error(f'[综合元评估] 失败: {type(e).__name__}: {e}')
            self._emit(on_progress, 'stage_complete', '',
                       '综合元评估', f'综合元评估阶段失败: {e}')
            return None
