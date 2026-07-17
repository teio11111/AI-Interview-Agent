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
        
        # 综合元评估（1个）
        self.comprehensive_meta_eval = ComprehensiveMetaEvaluatorAgent()
        
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

    # ===== 阶段6：综合元评估 =====
    def generate_meta_evaluation(self, position, candidate,
                                 resume_evaluation, interview_sessions,
                                 on_progress=None):
        """阶段6：综合元评估 - 汇总全链路数据生成最终决策

        Args:
            position: 岗位对象（含 ai_analysis）
            candidate: 候选人对象
            resume_evaluation: 简历 3+1 评估结果 dict
            interview_sessions: 面试会话列表 [{round, report, questions_plan}]
            on_progress: 进度回调函数

        Returns:
            dict: 综合元评估报告
        """
        import json

        # 解析岗位分析
        position_analysis = None
        if position.ai_analysis:
            try:
                position_analysis = json.loads(position.ai_analysis) if isinstance(position.ai_analysis, str) else position.ai_analysis
            except Exception:
                pass

        self._emit(on_progress, 'stage_start', '', '综合元评估', '综合元评估师开始汇总全链路数据...')
        self._emit(on_progress, 'agent_start', '综合元评估师', '综合元评估', '正在整合岗位分析、简历评估与各轮面试数据...')

        start = time.time()
        result = self.comprehensive_meta_eval.evaluate(
            position_name=position.name,
            position_analysis=position_analysis,
            candidate_name=candidate.name,
            resume_text=candidate.resume_text,
            resume_evaluation=resume_evaluation,
            interview_sessions=interview_sessions,
        )
        elapsed = round(time.time() - start, 1)

        if result:
            self._emit(on_progress, 'agent_complete', '综合元评估师', '综合元评估',
                       f'综合元评估完成（{elapsed}s），评分={result.get("overall_score","?")}')
            self._emit(on_progress, 'stage_complete', '', '综合元评估', '综合元评估完成')
            logger.info(f'[编排器] 综合元评估完成: score={result.get("overall_score")}, rec={result.get("final_recommendation")}')
        else:
            self._emit(on_progress, 'agent_error', '综合元评估师', '综合元评估', '综合元评估失败')
            logger.error('[编排器] 综合元评估失败')

        return result
