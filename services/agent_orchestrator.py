"""Agent 编排器 - 协调多智能体协作完成面试流程（专家小组+汇总裁判模式）"""
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import BoundedSemaphore
from flask import current_app
import time

from agents import (
    PositionAnalystAgent,
    TechEvaluatorAgent,
    SoftEvaluatorAgent,
    HiddenEvaluatorAgent,
    HiddenSubAEvaluatorAgent,  # 【v4.1】拆分并发
    HiddenSubBEvaluatorAgent,  # 【v4.1】拆分并发
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
from utils import beijing_now
from utils.logger import logger
import re


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
        # 【v4.1】拆分并发：原 5803 字符 prompt 拆 2 个子任务
        self.hidden_sub_a = HiddenSubAEvaluatorAgent()
        self.hidden_sub_b = HiddenSubBEvaluatorAgent()
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

    def _emit(self, on_progress, event_type, agent_name, stage, message='', percent=None, _extra=None):
        """发送进度事件

        【v3.1】新增 percent 参数：让前端 bar 能跟 agent 一起平滑增长。
        若调用方没传 percent，前端 pushAiStage 会忽略 bar 更新（只追加阶段列表）。

        【v3.6】新增 _extra 参数：可传递 dict，合并到 payload（用于 partial_result 等）。
        """
        if on_progress:
            try:
                payload = {
                    'agent': agent_name,
                    'stage': stage,
                    'message': message,
                    'timestamp': beijing_now().isoformat(),
                }
                if percent is not None:
                    payload['percent'] = percent
                if isinstance(_extra, dict):
                    payload.update(_extra)
                on_progress(event_type, payload)
            except Exception:
                pass

    def _run_parallel(self, agents_map, common_args, on_progress, stage, max_workers=3):
        """通用并行执行器：并行调用多个 Agent，收集结果

        【v3.0 重要修复】默认 max_workers=2（从 3 调低）
          背景：3 个 evaluator 同时调 LLM 会被 LLM 服务端限流/拒服，3 个一起 50s 超时。
          修复：限制最多 2 个并发 + LLM retry × 3（1s/2s/4s 退避）双保险。

        【v3.1】进度条修复：给每个 agent_start/complete 带递增的 percent。
          - 假设调用方传入时上层已设定 stage_start = base，
            每个 agent_start = base + i*step，
            每个 agent_complete = base + step/2 + i*step
          - 这样前端 bar 不会一直卡 75%，而是随 agent 推进平滑增长。

        Args:
            agents_map: {key: (name, func)} 字典
            common_args: 公共参数元组
            on_progress: 进度回调
            stage: 阶段名称
            max_workers: 最大线程数（默认 2，避免 LLM 限流）

        Returns:
            dict: {key: result}
        """
        results = {}
        start = time.time()

        # 【v3.1】准备阶段基线 + 每个 agent 的 percent 递增。
        # 默认区间 [25, 65]，留给 stage_complete 上调到 75%。
        n = max(1, len(agents_map))
        base_pct = 25  # stage_start 已给出 10，本阶段从 25 起跳
        step = max(1, int(40 / (n + 1)))  # n 个 agent 加 1 个 stage_complete 补齐到 ~75

        agent_list = list(agents_map.items())
        for i, (key, (name, _)) in enumerate(agent_list):
            pct = base_pct + i * step
            self._emit(on_progress, 'agent_start', name, stage,
                       f'{name}开始工作...', percent=pct)

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
                # 按完成顺序拿到 i，再算 percent
                i = next((idx for idx, (k, (n2, _)) in enumerate(agent_list) if k == key), 0)
                pct = base_pct + step // 2 + i * step
                try:
                    results[key] = future.result()
                    self._emit(on_progress, 'agent_complete', name, stage,
                               f'{name}完成 ({elapsed}s)', percent=pct)
                except Exception as e:
                    logger.error(f'[{name}] {stage}失败: {e}')
                    results[key] = None
                    self._emit(on_progress, 'agent_error', name, stage,
                               f'{name}出错: {e}', percent=pct)

        return results

    def _merge_hidden_results(self, sub_a_r, sub_b_r):
        """【v4.1】合并 hidden_sub_a + hidden_sub_b 结果到原 hidden_evaluator 格式

        sub_a_r: {candidate_profile: {education, residence, career_direction}, implicit_requirement_mapping: [...]}
        sub_b_r: {candidate_profile: {job_stability, emotional_stability, communication_ability, teamwork_style, learning_ability, resume_authenticity}, hidden_score_breakdown, hidden_risks, hidden_highlights, hidden_summary}

        Returns:
            dict: 与原 hidden_evaluator.evaluate() 输出一致（包含 hidden_score 系统计算、_expert_details 标记）
        """
        if not sub_a_r and not sub_b_r:
            return None

        merged = {}

        # 1. candidate_profile：sub_a 取前 3 个，sub_b 取后 6 个
        merged_profile = {}
        if isinstance(sub_a_r, dict):
            a_profile = (sub_a_r.get('candidate_profile') or {})
            for k in ('education', 'residence', 'career_direction'):
                if k in a_profile:
                    merged_profile[k] = a_profile[k]
        if isinstance(sub_b_r, dict):
            b_profile = (sub_b_r.get('candidate_profile') or {})
            for k in ('job_stability', 'emotional_stability', 'communication_ability',
                      'teamwork_style', 'learning_ability', 'resume_authenticity'):
                if k in b_profile:
                    merged_profile[k] = b_profile[k]
        merged['candidate_profile'] = merged_profile

        # 2. implicit_requirement_mapping：仅 sub_a 有
        if isinstance(sub_a_r, dict) and sub_a_r.get('implicit_requirement_mapping'):
            merged['implicit_requirement_mapping'] = sub_a_r['implicit_requirement_mapping']

        # 3. hidden_score_breakdown：sub_b 为主，sub_a 的 3 个维度优先
        breakdown = {}
        if isinstance(sub_b_r, dict):
            breakdown.update(sub_b_r.get('hidden_score_breakdown') or {})
        # 用 sub_a 里的 score 字段（如果有）覆盖
        if isinstance(sub_a_r, dict):
            a_profile = (sub_a_r.get('candidate_profile') or {})
            for dim in ('education', 'residence', 'career_direction'):
                if dim in a_profile and isinstance(a_profile[dim], dict):
                    score = a_profile[dim].get('score')
                    if isinstance(score, (int, float)) and 1 <= score <= 10:
                        breakdown[dim] = int(score)
        # 补齐缺失维度为 5（中性分）
        for dim in ('education', 'residence', 'career_direction', 'job_stability',
                    'emotional_stability', 'communication_ability', 'teamwork_style',
                    'learning_ability', 'resume_authenticity'):
            breakdown.setdefault(dim, 5)
        merged['hidden_score_breakdown'] = breakdown

        # 4. risks / highlights / summary：仅 sub_b 有
        if isinstance(sub_b_r, dict):
            for k in ('hidden_risks', 'hidden_highlights', 'hidden_summary'):
                if k in sub_b_r:
                    merged[k] = sub_b_r[k]

        # 5. 系统计算 hidden_score（调用原 hidden_evaluator 的 _compute_hidden_score 逻辑）
        KEYS = (
            'education', 'residence', 'career_direction', 'job_stability',
            'emotional_stability', 'communication_ability', 'teamwork_style',
            'learning_ability', 'resume_authenticity',
        )
        values = [breakdown.get(k, 5) for k in KEYS]
        provided_vals = [v for k, v in zip(KEYS, values) if isinstance(breakdown.get(k), (int, float)) and 1 <= breakdown[k] <= 10]
        if provided_vals:
            score_10 = sum(provided_vals) / len(provided_vals)
            if score_10 <= 2.5:
                score_10 = 5.0  # 防 LLM 严重偏低兑底
            merged['hidden_score'] = int(round(score_10 * 10))
            merged['hidden_score_source'] = 'system:9_dim_avg_v4.1_split'
        else:
            merged['hidden_score'] = 50
            merged['hidden_score_source'] = 'system:fallback_50'

        return merged

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

        【v3.6 异步改造】隐藏维度评估师改异步
          - 阶段 A：tech + soft 并发（限 120s）→ 先返回基础分给前端
          - 阶段 B：hidden 单独跑（限 180s）→ 完成后增量更新隐性维度
          - 解决：之前 3 个并发跑最慢的 hidden 评估师拖死整体（曾实测 60+ 秒）

        Returns:
            dict: 统一简历画像（带 _partial / _hidden_done 标记）
        """
        self._emit(on_progress, 'stage_start', '', '简历评估',
                   '【v3.6】先跑技术+素质，隐性维度异步评估...', percent=20)

        # 【v4.1】截断长简历避免 prompt 过大（节省 token 和 LLM 推理时间）
        from utils.text_truncate import truncate_for_prompt, clean_resume_text
        safe_resume = truncate_for_prompt(clean_resume_text(resume_text or ''), max_chars=2500)

        common_args = (position_name, tech_requirements, jd_content, safe_resume,
                       position_analysis, candidate_name)
        position_requirements_text = (tech_requirements or '') + '\n' + (jd_content or '')

        # ========== 阶段A：tech + soft 并发（限时 120s）==========
        tech_soft_map = {
            'tech': ('技术评估师', self.tech_evaluator.evaluate),
            'soft': ('综合素质评估师', self.soft_evaluator.evaluate),
        }
        results = self._run_parallel(tech_soft_map, common_args, on_progress, '简历评估',
                                     max_workers=2)

        tech_r = results.get('tech')
        soft_r = results.get('soft')

        # 先汇总一次（hidden 给 None → 默认 60 中性分），作为 partial 结果
        self._emit(on_progress, 'agent_start', '简历汇总师', '简历评估',
                   '正在汇总技术+素质分数（基础分）...', percent=55)
        partial = self.resume_coordinator.synthesize(
            tech_r, soft_r, None,
            position_name, candidate_name,
            position_requirements_text=position_requirements_text,
            resume_text=resume_text,
        )
        # partial 标记，前端据此先刷新基础分
        if partial:
            partial['_partial'] = True
            partial['_hidden_done'] = False
        # 【v3.6】将 partial 结果作为 payload 推送给 stream，前端先看基础分
        partial_payload = {
            'partial_result': partial if partial else None,
        }
        self._emit(on_progress, 'partial_complete', '简历汇总师', '简历评估',
                   f'基础评估完成 (匹配度 {partial.get("match_score", "?") if partial else "?"}/100) '
                   f'，隐性维度评估中...', percent=65,
                   _extra=partial_payload)

        # ========== 阶段B：hidden 拆为 A/B 并发（限时 90s）==========
        # 【v4.1】拆分原因：原 hidden_evaluator 5803 字符 prompt 调一次要 60-75s
        # 拆为 sub_a(人岗匹配, 3000 字符) + sub_b(稳定度+软性, 3000 字符) 并发
        import concurrent.futures
        app = current_app._get_current_object()

        def _wrap_single(f):
            def wrapper(*args):
                with app.app_context():
                    return f(*args)
            return wrapper

        hidden_r = None
        hidden_timed_out = False
        sub_a_r = None
        sub_b_r = None
        self._emit(on_progress, 'agent_start', '隐性因素评估师-A', '简历评估',
                   '【v4.1拆分】评估人岗匹配维度（学历/居住地/职业方向）...', percent=68)
        self._emit(on_progress, 'agent_start', '隐性因素评估师-B', '简历评估',
                   '【v4.1拆分】评估稳定度+软性维度（真实度/稳定度/沟通/协作）...', percent=68)
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as hidden_ex:
            f_a = hidden_ex.submit(_wrap_single(self.hidden_sub_a.evaluate), *common_args)
            f_b = hidden_ex.submit(_wrap_single(self.hidden_sub_b.evaluate), *common_args)
            try:
                # A 和 B 并发，取最慢的（max timeout 90s）
                sub_a_r = f_a.result(timeout=90)
                sub_b_r = f_b.result(timeout=90)
                self._emit(on_progress, 'agent_complete', '隐性因素评估师-A', '简历评估',
                           '人岗匹配评估完成', percent=78)
                self._emit(on_progress, 'agent_complete', '隐性因素评估师-B', '简历评估',
                           '稳定度+软性评估完成', percent=78)
            except concurrent.futures.TimeoutError:
                hidden_timed_out = True
                # 超时时，收集已完成的部分结果
                sub_a_r = sub_a_r if f_a.done() else None
                sub_b_r = sub_b_r if f_b.done() else None
                logger.error(f'[v4.1] hidden 拆分子任务超时（>90s），A={bool(sub_a_r)}, B={bool(sub_b_r)}')
                self._emit(on_progress, 'agent_error', '隐性因素评估师', '简历评估',
                           '隐性维度评估超时（>90s），将使用基础分（隐藏维度为中性 60）',
                           percent=80)
            except Exception as e:
                logger.error(f'[v4.1] hidden 拆分子任务异常: {e}')
                self._emit(on_progress, 'agent_error', '隐性因素评估师', '简历评估',
                           f'隐性维度评估异常: {e}', percent=80)

        # ========== 合并 sub_a + sub_b 结果到原 hidden 格式 ==========
        hidden_r = self._merge_hidden_results(sub_a_r, sub_b_r)
        if not hidden_r:
            hidden_r = None

        # ========== 最终汇总（带 hidden）==========
        self._emit(on_progress, 'agent_start', '简历汇总师', '简历评估',
                   '综合三方意见（含隐性维度）...', percent=85)
        start_coord = time.time()
        result = self.resume_coordinator.synthesize(
            tech_r, soft_r, hidden_r,
            position_name, candidate_name,
            position_requirements_text=position_requirements_text,
            resume_text=resume_text,
        )
        elapsed_coord = round(time.time() - start_coord, 1)

        # 是否完整（hidden 是否带数据）
        hidden_complete = bool(hidden_r and (
            hidden_r.get('candidate_profile')
            or hidden_r.get('hidden_score_breakdown')
            or hidden_r.get('implicit_requirement_mapping')
        ))
        if result and isinstance(result, dict):
            result['_partial'] = False
            result['_hidden_done'] = hidden_complete
            result['_hidden_timed_out'] = hidden_timed_out

        self._emit(on_progress, 'agent_complete', '简历汇总师', '简历评估',
                   f'最终汇总完成 ({elapsed_coord}s)', percent=95)
        self._emit(on_progress, 'stage_complete', '', '简历评估', '简历评估阶段完成')

        # 强制合并隐性评估师的原始详细数据（双保险：Prompt + 代码层）
        if result and isinstance(result, dict):
            hidden_raw = hidden_r or {}
            # 强制覆盖 candidate_profile
            hidden_profile = hidden_raw.get('candidate_profile')
            if hidden_profile and isinstance(hidden_profile, dict):
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

        # 附加各专家的原始结果
        if result and isinstance(result, dict):
            result['_expert_details'] = {
                'tech': tech_r,
                'soft': soft_r,
                'hidden': hidden_r,
            }

        # 【v3.6】除了返回最终结果，同时返回 partial 结果给上层（stream）以便分两次 yield。
        # 但是为了不破坏其他调用者（design_questions 等依赖 return 字典作为 _final_），
        # 这里仍然返回 result（最终汇总）作为主返回值。partial 结果通过 _partial_result 字段附带。
        if result and isinstance(result, dict) and isinstance(partial, dict):
            # partial 副本（避免主结果被覆盖）
            partial_copy = {
                **partial,
                '_partial': True,
                '_hidden_done': False,
                '_partial_marker': True,
            }
            result['_partial_result'] = partial_copy

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
        
        # 【bugfix】代码层安全网：过滤与岗位技术栈不匹配的题目
        results = self._filter_off_topic_questions(results, position_name, tech_requirements)
        
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
        
        # 【bugfix】二次过滤：选题官 LLM 备份路径也可能引入不相关题目
        if final and isinstance(final, dict) and final.get('questions'):
            pos_type = self._detect_position_type(position_name, tech_requirements)
            forbidden_map = {
                'frontend': [
                    r'\bjava\b', r'\bspring\b', r'\bspringboot\b', r'\bspring boot\b',
                    r'\bjvm\b', r'\bmybatis\b', r'\bhibernate\b', r'\bmaven\b',
                    r'\bgradle\b', r'\bkafka\b', r'\brabbitmq\b', r'\bredis\b',
                    r'\bmysql\b', r'\bpostgresql\b', r'\bmicroservice\b', r'微服务',
                    r'\bdubbo\b', r'\bnetty\b',
                ],
                'backend': [
                    r'\breact\b', r'\bvue\b', r'\bangular\b', r'\bwebpack\b',
                    r'\bvite\b', r'\btypescript\b', r'\bjavascript\b', r'\bhtml5\b',
                    r'\bcss3\b', r'\becharts\b', r'\b小程序\b', r'\bh5\b',
                ],
            }
            forbidden = forbidden_map.get(pos_type, [])
            if forbidden:
                original_count = len(final['questions'])
                filtered_qs = []
                for q in final['questions']:
                    q_text = (q.get('question', '') + ' ' + q.get('target_skill', '') + ' ' + q.get('intent', '')).lower()
                    if not any(re.search(p, q_text, re.IGNORECASE) for p in forbidden):
                        filtered_qs.append(q)
                    else:
                        logger.warning(f'[岗位匹配过滤-二次] 移除: {q.get("question", "")[:60]}...')
                final['questions'] = filtered_qs
                removed = original_count - len(filtered_qs)
                if removed > 0:
                    logger.info(f'[岗位匹配过滤-二次] 从最终题目中移除 {removed} 道不相关题目')
        
        return final
    
    @staticmethod
    def _detect_position_type(position_name, tech_requirements=''):
        """检测岗位类型，用于过滤不相关的题目"""
        name = (position_name or '').lower()
        tech = (tech_requirements or '').lower()
        combined = f'{name} {tech}'
            
        if any(kw in combined for kw in ['前端', 'web', 'h5', '移动', '客户端', 'ios',
                                          'android', 'react', 'vue', 'angular', '小程序']):
            return 'frontend'
        if any(kw in combined for kw in ['算法', 'nlp', 'cv', '推荐', '深度学习',
                                          '机器学习', '大模型', 'llm', 'rag', 'aigc']):
            return 'algorithm'
        if any(kw in combined for kw in ['数据', '分析', 'bi', 'etl', '数仓',
                                          'data', 'analytics']):
            return 'data'
        if any(kw in combined for kw in ['测试', 'qa', 'sdet', '测开']):
            return 'test'
        return 'backend'
    
    @staticmethod
    def _filter_off_topic_questions(results, position_name, tech_requirements=''):
        """【bugfix】代码层安全网：过滤与岗位技术栈不匹配的题目
            
        防止 LLM 出题时跑偏到候选人简历中其他不相关的技术栈。
        例如：前端岗位不应出现 Java/Spring/JVM 等后端题目。
        """
        pos_type = AgentOrchestrator._detect_position_type(position_name, tech_requirements)
            
        # 定义每个岗位类型的"禁忌关键词"——出现这些词的题目会被过滤
        forbidden_keywords = {
            'frontend': [
                r'\bjava\b', r'\bspring\b', r'\bspringboot\b', r'\bspring boot\b',
                r'\bjvm\b', r'\bmybatis\b', r'\bhibernate\b', r'\bmaven\b',
                r'\bgradle\b', r'\bkafka\b', r'\brabbitmq\b', r'\bredis\b',
                r'\bmysql\b', r'\bpostgresql\b', r'\bmicroservice\b', r'微服务',
                r'\bdubbo\b', r'\bnetty\b',
            ],
            'backend': [
                r'\breact\b', r'\bvue\b', r'\bangular\b', r'\bwebpack\b',
                r'\bvite\b', r'\btypescript\b', r'\bjavascript\b', r'\bhtml5\b',
                r'\bcss3\b', r'\becharts\b', r'\b小程序\b', r'\bh5\b',
            ],
            'algorithm': [
                r'\bjava\b', r'\bspring\b', r'\breact\b', r'\bvue\b',
                r'微服务', r'\bmysql\b', r'\bredis\b',
            ],
            'data': [
                r'\bjava\b', r'\bspring\b', r'\breact\b', r'\bvue\b',
                r'微服务', r'\bjvm\b',
            ],
            'test': [
                r'\bjava\b', r'\bspring\b', r'\breact\b', r'\bvue\b',
                r'微服务', r'\bjvm\b',
            ],
        }
            
        forbidden = forbidden_keywords.get(pos_type, [])
        if not forbidden:
            return results
            
        filtered_results = {}
        total_removed = 0
            
        for agent_key, agent_result in results.items():
            if not agent_result or not isinstance(agent_result, dict):
                filtered_results[agent_key] = agent_result
                continue
                
            questions = agent_result.get('questions', [])
            if not questions:
                filtered_results[agent_key] = agent_result
                continue
                
            kept = []
            for q in questions:
                q_text = (q.get('question', '') + ' ' + q.get('target_skill', '') + ' ' + q.get('intent', '')).lower()
                is_off_topic = False
                for pattern in forbidden:
                    if re.search(pattern, q_text, re.IGNORECASE):
                        is_off_topic = True
                        total_removed += 1
                        logger.warning(
                            f'[岗位匹配过滤] 移除不相关题目 (岗位={position_name}, '
                            f'类型={pos_type}): {q.get("question", "")[:60]}...'
                        )
                        break
                if not is_off_topic:
                    kept.append(q)
                
            filtered_result = dict(agent_result)
            filtered_result['questions'] = kept
            filtered_results[agent_key] = filtered_result
            
        if total_removed > 0:
            logger.info(f'[岗位匹配过滤] 共移除 {total_removed} 道与岗位不相关的题目')
            
        return filtered_results
    
    # ===== 阶4a：面试对话评估（2并行+1主面试官）=====
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
                        single_round_scores=None,
                        on_progress=None):
        """阶5：三位评估师并行评估 + 汇总师生成最终报告

        Args:
            single_round_scores: 【新增】每条对话的实时评分（1-10），会传给汇总师。
                                  为 None 或空列表时退回到纯汇总师 5 维算法。

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
            position_name, candidate_name,
            single_round_scores=single_round_scores,
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
            #    【设计修复】应用跨阶段一致性惩罚，让简历「说好」但面试「差」的不一致
            #    真正反映在最终分数里（仅靠加权求和会被掩盖）。
            final_score, penalty = ComprehensiveMetaEvaluatorAgent.compute_overall_score_with_validation(
                resume_match_score=resume_match_score,
                round_scores_100=round_scores,
                cross_stage_analysis=result.get('cross_stage_analysis'),
                key_risks=result.get('key_risks'),
            )
            final_recommendation = ComprehensiveMetaEvaluatorAgent.recommendation_for(final_score)

            # 原始分（未扣惩罚），供决策理由中展示扣分幅度
            raw_score = ComprehensiveMetaEvaluatorAgent.compute_overall_score_raw(
                resume_match_score=resume_match_score,
                round_scores_100=round_scores,
            )

            # 检测 LLM 是否填了占位字符串，如果是则用系统生成
            _PLACEHOLDERS = {'系统自动生成', '系统生成', '由系统填充', '由系统填入', '系统填入'}
            llm_rationale = (result.get('decision_rationale') or '').strip()
            if llm_rationale and llm_rationale not in _PLACEHOLDERS:
                decision_rationale = llm_rationale
                # 若系统计算了扣分，在 LLM 提供的理由后追加扣分说明
                if penalty > 0:
                    penalty_note = ComprehensiveMetaEvaluatorAgent._format_penalty_note(
                        penalty,
                        result.get('cross_stage_analysis'),
                        result.get('key_risks'),
                    )
                    decision_rationale = decision_rationale + penalty_note
            else:
                decision_rationale = ComprehensiveMetaEvaluatorAgent.decision_rationale_for_with_validation(
                    raw_score, final_score, round_scores, resume_match_score,
                    result.get('cross_stage_analysis'),
                    result.get('key_risks'),
                )

            # 6. 覆写 LLM 可能误填的字段（防虚高）
            result['overall_score'] = final_score
            result['final_recommendation'] = final_recommendation
            result['decision_rationale'] = decision_rationale

            # 7. 注入 computation 调试字段（增加跨阶段一致性惩罚明细）
            result['computation'] = {
                'resume_match_score': resume_match_score,
                'round_scores': round_scores,
                'final_score_raw': ComprehensiveMetaEvaluatorAgent.compute_overall_score_raw(
                    resume_match_score=resume_match_score,
                    round_scores_100=round_scores,
                ),
                'cross_validation_penalty': penalty,
                'final_score_after_penalty': final_score,
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
