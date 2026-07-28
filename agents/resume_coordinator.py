"""简历汇总师 Agent - 纯代码组装（v2.1 性能修复）

历史：v2.0 时代是 LLM 综合，耗时 30-60s 且易出现 6 分虚低 bug。
v2.1 重构：纯代码组装，不再调用 LLM。
  - match_score / score_breakdown / computation 由代码根据三方分数字段计算
  - matched_skills / missing_skills 直接从 tech_evaluator 透传
  - candidate_profile / implicit_requirement_mapping 直接从 hidden_evaluator 透传
  - strengths / risks 从三方 highlights + risks 合并去重
  - suggested_questions 从缺失技能 + 风险推断（无 LLM）
  - summary 由三方 summary 拼接生成

输出字段集兼容原 LLM 版本，下游（出题官、候选人管理前端）无需改动。
"""
from agents.base_agent import BaseAgent
from utils.text_truncate import truncate_for_prompt


class ResumeCoordinatorAgent(BaseAgent):
    """简历汇总师（v2.1 纯代码版）"""

    AGENT_NAME = "简历汇总师"
    SYSTEM_PROMPT = "占位：v2.1 纯代码组装不再需要 SYSTEM_PROMPT，但 BaseAgent 要求非空。"

    def __init__(self):
        super().__init__()

    def synthesize(self, tech_result, soft_result, hidden_result,
                   position_name, candidate_name='',
                   position_requirements_text='',
                   resume_text=''):
        """综合三方评估结果生成统一画像（不调用 LLM）

        Args:
            tech_result: 技术评估师的结果 dict
            soft_result: 综合素质评估师的结果 dict
            hidden_result: 隐性因素评估师的结果 dict
            position_name: 岗位名称
            candidate_name: 候选人姓名
            position_requirements_text: 【v2.3】岗位 tech_requirements+jd_content 拼起来的文本，
                用于 LLM 全部失败时代码层兑底匹配技能。
            resume_text: 【v2.3】候选人简历原文，用于代码层兑底扫描技能关键词。

        Returns:
            dict: 统一简历画像（兼容旧 resume_evaluator 输出格式）
        """
        tech_result = tech_result or {}
        soft_result = soft_result or {}
        hidden_result = hidden_result or {}

        # 【v2.1 重要】检测「三个评估师都失败」的严重场景（LLM 完全不可达）。
        llm_fully_failed = (
            not tech_result.get('tech_depth_score')
            and not soft_result.get('soft_score')
            and not hidden_result.get('hidden_score_breakdown')
            and not hidden_result.get('candidate_profile')
        )

        # ========== 1. match_score 计算（系统算，不让 LLM 编造）==========
        # 【v2.1 关键修复】三个分数字段来源不同，不能统一处理：
        #   - tech_depth_score: tech_evaluator 输出，默认 1-10 制（prompt 未强制）
        #   - soft_score:       soft_evaluator 输出，默认 1-10 制（prompt 未强制）
        #   - hidden_score:     hidden_evaluator._compute_hidden_score 已×10 转 0-100
        # 历史上 tech/soft 给 5 被误判成 5/100 = 5%；hidden 给 10 被误判成 1-10 制×10 = 100。
        tech_raw = tech_result.get('tech_depth_score')
        soft_raw = soft_result.get('soft_score')
        hidden_raw = hidden_result.get('hidden_score')

        if llm_fully_failed:
            tech_c = soft_c = hidden_c = 60.0
        else:
            # 【v3.6.5 BUG 修复】tech_depth_score / soft_score 的 prompt 明确要求 0-100 分制
            # （参见 tech_evaluator.py:82 / soft_evaluator.py:103），但代码历史上误用 scale='1-10' 解读，
            # 导致 LLM 输出的 88/95 等 0-100 分被判为“越界”走 fallback 到 60 分，严重拉低/抬高分。
            # hidden_score 本身由系统计算后已经是 0-100，保持原样。
            tech_c = self._normalize_100(tech_raw, scale='0-100', default=60)
            soft_c = self._normalize_100(soft_raw, scale='0-100', default=60)
            hidden_c = self._normalize_100(hidden_raw, scale='0-100', default=60)

        # 【v3.4 评分公式调整】技术权重下调 + 加技能覆盖度加分项
        # 历史公式：tech 60% + soft 20% + hidden 20% → 张伟(7.5年/14匹配)只65、晨晨(不匹配)却有53
        # 新公式：tech 50% + soft 25% + hidden 15% + skill_coverage 10%
        #   - skill_coverage = 匹配技能数 / (匹配+缺失) × 100，量化「简历与JD的契合度」
        #   - 缺失 matched/missing 时回退到 60（中性）
        if llm_fully_failed:
            skill_cov = 60.0
        else:
            mc = len(tech_result.get('matched_skills') or [])
            mm = len(tech_result.get('missing_skills') or [])
            if mc + mm > 0:
                skill_cov = float(mc) / float(mc + mm) * 100.0
            else:
                skill_cov = 60.0  # 中性保底

        match_score = int(round(
            tech_c * 0.50
            + soft_c * 0.25
            + hidden_c * 0.15
            + skill_cov * 0.10
        ))

        # 【v3.4 二次修正】让"高匹配/低匹配"区分更明显：
        #   - 技能覆盖率 >= 80%：+5（强匹配奖励，覆盖大量JD技能）
        #   - 技能覆盖率 <= 25%：-8（弱匹配惩罚，关键技能大面积缺失）
        if not llm_fully_failed:
            if skill_cov >= 80.0:
                match_score = min(100, match_score + 5)
            elif skill_cov <= 25.0:
                match_score = max(0, match_score - 8)

        # 【v3.6.5 基线偏置】用户校准反馈：LLM 给分整体偏低 +5 就接近期望。
        # 保留 LLM 真实判断（不被压到 60），只在最终结果上统一加一个偏置，
        # 反映“LLM 评分曲线比人类预期略偏低”的系统性差异。
        match_score = min(100, max(0, match_score + 5))

        # 【v2.2 移除兑底】让 LLM 真实评分反映，不人为拉高/拉低。
        # 如果 LLM 评估服务完全不可达，接口应明示失败，由前端引导重试，
        # 而不是返一个假 60 分 + 默认内容（会被用户误以为是“垃圾 AI”）。
        result_note = ''

        # ========== 2. 字段透传（兼容前端）==========
        matched_skills = tech_result.get('matched_skills') or []
        missing_skills = tech_result.get('missing_skills') or []

        # 【v2.3】LLM 未能返回技能匹配 → 代码层从 JD/简历文本提取关键词兑底。
        #         让 UI 不会只显示一行“无”，至少有“匹配技能 / 缺失技能”列表可看。
        if not matched_skills and not missing_skills:
            fb_matched, fb_missing = self._extract_skills_by_keywords(
                position_requirements_text, resume_text
            )
            if fb_matched or fb_missing:
                matched_skills = fb_matched
                missing_skills = fb_missing

        candidate_profile = hidden_result.get('candidate_profile') or {}
        implicit_requirement_mapping = hidden_result.get('implicit_requirement_mapping') or []

        # 【v2.2】LLM 全面失败 → 不再组装假内容，而是返空，UI 能感知到「失败」状态
        strengths = self._merge_strengths(tech_result, soft_result, hidden_result)
        risks = self._merge_risks(tech_result, soft_result, hidden_result)
        suggested_questions = self._generate_suggested_questions(
            missing_skills, risks, position_name, candidate_name
        )

        # 【v2.3】代码层兑底 strengths/risks（避免 LLM 失败时优点/风险列全空）。
        if not strengths and matched_skills:
            strengths = [
                {'point': f'掌握{ (s.get("skill") if isinstance(s, dict) else s) }',
                 'evidence': '与JD关键词同时出现于简历',
                 'source': '代码兑底（关键词匹配）'}
                for s in matched_skills[:5]
            ]
        if not risks and missing_skills:
            risks = [
                {'risk': f'未提及{ (s.get("skill") if isinstance(s, dict) else s) }',
                 'severity': '中',
                 'detail': 'JD要求但简历未提及，建议面试中确认是否真正掌握',
                 'source': '代码兑底（关键词缺失）'}
                for s in missing_skills[:5]
            ]

        # ========== 5. summary 由三方 summary 拼接 ==========
        summary = self._build_summary(tech_result, soft_result, hidden_result,
                                       candidate_name, position_name, match_score)

        # ========== 6. 组装结果 ==========
        result = {
            '_note': result_note,
            'llm_fully_failed': llm_fully_failed,  # 【v2.2】显式告诉前端：AI 评估完全失败
            'matched_skills': matched_skills,
            'missing_skills': missing_skills,
            'strengths': strengths,
            'risks': risks,
            'candidate_profile': candidate_profile,
            'implicit_requirement_mapping': implicit_requirement_mapping,
            'suggested_questions': suggested_questions,
            'summary': summary,
            'candidate_summary': summary,  # 兼容字段：与 summary 同内容
            'expert_consensus': self._extract_consensus(tech_result, soft_result, hidden_result),
            'expert_divergence': self._extract_divergence(tech_result, soft_result, hidden_result),

            # 评分字段（系统计算）
            'match_score': match_score,
            'score_breakdown': {
                'tech_component': int(round(tech_c)),
                'soft_component': int(round(soft_c)),
                'hidden_component': int(round(hidden_c)),
                'detail': '技术60% + 素质20% + 隐性20% = match_score',
                'tech_source': 'tech_evaluator.tech_depth_score',
                'soft_source': 'soft_evaluator.soft_score',
                'hidden_source': 'hidden_evaluator.hidden_score (9个隐性维度加权)',
                'formula': 'final = tech×60% + soft×20% + hidden×20%',
            },
            'computation': {
                'tech_score_100': tech_c,
                'soft_score_100': soft_c,
                'hidden_score_100': hidden_c,
                'match_score': match_score,
                'weights': {'tech': 0.60, 'soft': 0.20, 'hidden': 0.20},
                'formula': 'final = tech×60% + soft×20% + hidden×20%',
                'normalized_from': {
                    'tech_raw': tech_raw,
                    'soft_raw': soft_raw,
                    'hidden_raw': hidden_raw,
                    'note': 'LLM 给出 0-10 分会被自动×10 转 0-100',
                },
            },
        }

        return result

    # ========== 工具方法 ==========

    @staticmethod
    def _normalize_100(value, scale='0-100', default=60):
        """把 LLM 给的分数归一到 0-100 范围。

        scale:
          - '0-100': 传入值已在 0-100 范围（如 hidden_evaluator._compute_hidden_score 输出）
          - '1-10':  传入值是 1-10 分制（如 tech/soft_evaluator 输出），需×10 转 0-100

        历史 bug：
          - tech=5 被误判为 5/100 = 5%（实际是 5/10 = 50%）
          - hidden=10 被误判为 1-10 制×10 = 100（实际是 10/100 = 10%）
        两 bug 都造成 match_score 计算严重失真。

        Args:
            value: LLM 返回的分数
            scale: 原始量纲（'0-100' 或 '1-10'）
            default: 缺失/越界时的默认分（默认 60 = 中性偏上）

        Returns:
            float: 0-100 范围的分数
        """
        if value is None or not isinstance(value, (int, float)):
            return float(default)
        v = float(value)
        if v < 0:
            return float(default)

        if scale == '1-10':
            # 1-10 分制：1-10 整数/小数都×10 转 0-100
            # 0 视为未填（按默认），11-100 视为异常（接 default）
            if 1 <= v <= 10:
                return min(100.0, v * 10)
            return float(default)
        else:
            # '0-100' 量纲：直接使用
            if v <= 100:
                return v
            return float(default)

    @staticmethod
    def _merge_strengths(tech_result, soft_result, hidden_result):
        """从三方 highlights 合并 strengths，标注来源。"""
        out = []
        for source_name, src in (
            ('技术评估师', tech_result),
            ('综合素质评估师', soft_result),
            ('隐性因素评估师', hidden_result),
        ):
            for item in (src or {}).get('tech_highlights', []) or []:
                point = item.get('point') or item.get('highlight') or ''
                if point:
                    out.append({'point': point, 'evidence': item.get('evidence', ''), 'source': source_name})
            for item in (src or {}).get('soft_highlights', []) or []:
                point = item.get('point') or item.get('highlight') or ''
                if point:
                    out.append({'point': point, 'evidence': item.get('evidence', ''), 'source': source_name})
            for item in (src or {}).get('hidden_highlights', []) or []:
                point = item.get('highlight') or item.get('point') or ''
                if point:
                    out.append({'point': point, 'evidence': item.get('detail', ''), 'source': source_name})
        return out

    @staticmethod
    def _merge_risks(tech_result, soft_result, hidden_result):
        """从三方 risks/concerns 合并 risks，标注来源。"""
        out = []
        for source_name, src in (
            ('技术评估师', tech_result),
            ('综合素质评估师', soft_result),
            ('隐性因素评估师', hidden_result),
        ):
            for item in (src or {}).get('tech_risks', []) or []:
                risk = item.get('risk', '')
                if risk:
                    out.append({
                        'risk': risk,
                        'severity': item.get('severity', '中'),
                        'detail': item.get('detail', ''),
                        'source': source_name,
                    })
            for item in (src or {}).get('soft_concerns', []) or []:
                concern = item.get('concern', '')
                if concern:
                    out.append({
                        'risk': concern,
                        'severity': '中',
                        'detail': item.get('detail', ''),
                        'source': source_name,
                    })
            for item in (src or {}).get('hidden_risks', []) or []:
                risk = item.get('risk', '')
                if risk:
                    out.append({
                        'risk': risk,
                        'severity': item.get('severity', '中'),
                        'detail': item.get('detail', ''),
                        'source': source_name,
                    })
        return out

    @staticmethod
    def _generate_suggested_questions(missing_skills, risks, position_name, candidate_name):
        """从缺失技能 + 风险生成面试追问方向（不调 LLM）"""
        questions = []
        # 从缺失技能生成
        for m in (missing_skills or [])[:3]:
            skill = m.get('skill', '')
            importance = m.get('importance', '重要')
            if skill:
                questions.append({
                    'topic': f'验证{skill}掌握度',
                    'reason': f'简历中未明确体现{skill}（{importance}）',
                    'example_question': f'请介绍你在最近项目中如何使用{skill}解决实际问题？',
                })
        # 从风险生成
        for r in (risks or [])[:3]:
            risk = r.get('risk', '')
            if risk:
                questions.append({
                    'topic': f'澄清风险点：{risk[:30]}',
                    'reason': f'基于风险信号：{r.get("detail", "")[:80]}',
                    'example_question': f'请举例说明你如何处理：{risk[:40]}？',
                })
        return questions[:6]  # 最多 6 个

    @staticmethod
    def _build_summary(tech_result, soft_result, hidden_result,
                       candidate_name, position_name, match_score):
        """由三方 summary 字段拼接生成综合 summary"""
        parts = []
        cn = candidate_name or '候选人'
        pos = position_name or '该岗位'
        parts.append(f'针对{cn}应聘{pos}的简历评估，综合技术、素质、隐性因素三方意见，匹配度 {match_score}/100。')

        tech_sum = (tech_result or {}).get('tech_summary', '')
        if tech_sum:
            parts.append('【技术】' + tech_sum)
        soft_sum = (soft_result or {}).get('soft_summary', '')
        if soft_sum:
            parts.append('【素质】' + soft_sum)
        hidden_sum = (hidden_result or {}).get('hidden_summary', '')
        if hidden_sum:
            parts.append('【隐性】' + hidden_sum)

        return '\n'.join(parts)

    @staticmethod
    def _extract_consensus(tech_result, soft_result, hidden_result):
        """提取三方一致意见（简化版：基于 summary 中关键词重合度）"""
        # 简化实现：返回空列表，调用方不需要
        return []

    @staticmethod
    def _extract_divergence(tech_result, soft_result, hidden_result):
        """提取三方分歧（简化版：基于 summary 中关键词差异）"""
        return []

    @staticmethod
    def _extract_skills_by_keywords(position_text='', resume_text=''):
        """【v2.3】代码层技能兑底匹配。

        背景：当 3 个评估师全部失败（LLM 超时/限流），UI 原本只能看到
        “匹配技能: 无 / 缺失技能: 无”。本方法从 JD 与简历文本扫描技术关键词，
        至少给出“匹配技能”和“缺失技能”两份代码列表，让 UI 不只显示一行话。

        算法：
          1) 用一份常用技术词表（覆盖后端/前端/数据库/中间件/云/测试）。
          2) JD 中出现的技能 → 作为“岗位要求技能”。
          3) 简历中出现的技能 → 作为“候选人拥有技能”。
          4) matched = JD∩简历，missing = JD\简历。

        Returns:
            (matched, missing): 两个 list，每个元素是
                {"skill": "...", "importance/proficiency": "..."}
        """
        # 通用技术词表（后期可以补更多/从 position.tech_requirements 中拼）
        TECH_VOCAB = [
            # 后端语言与框架
            'Java', 'Spring', 'Spring Boot', 'Spring Cloud', 'Spring Batch',
            'Quarkus', 'Python', 'Django', 'Flask', 'FastAPI',
            'Go', 'Golang', 'Node.js', 'NodeJS', 'C++', 'C#', '.NET',
            # 前端
            'React', 'Vue', 'Angular', 'TypeScript', 'JavaScript',
            'React Native', 'Next.js',
            # 数据库
            'MySQL', 'PostgreSQL', 'Oracle', 'SQL Server', 'Redis',
            'MongoDB', 'Elasticsearch', 'ClickHouse', 'Hive', 'HDFS',
            # 中间件
            'Kafka', 'RabbitMQ', 'RocketMQ', 'Nginx', 'Tomcat',
            # 云 / DevOps
            'Docker', 'Kubernetes', 'K8s', 'Terraform', 'AWS', 'GCP', 'Azure',
            'CI/CD', 'Jenkins', 'GitHub Actions',
            # 架构 / 微服务
            'Microservice', 'REST', 'RESTful', 'GraphQL', 'gRPC', 'SOAP',
            'WebSocket', 'API Gateway',
            # 大数据 / 消息
            'Spark', 'Hadoop', 'Airflow', 'Flink', 'Storm',
            # 测试 / 质量
            'JUnit', 'Mockito', 'SonarQube', 'Cucumber', 'Selenium',
            'TDD', 'BDD',
            # 流程 / 协作
            'JIRA', 'Scrum', 'Agile', 'SOLID', 'Design Patterns',
            # AI / 新兴
            'LangGraph', 'RAG', 'LLM', 'GitHub Copilot', 'ChatGPT', 'Claude',
        ]
        pos_lower = (position_text or '').lower()
        resume_lower = (resume_text or '').lower()

        matched, missing = [], []
        for skill in TECH_VOCAB:
            sl = skill.lower()
            in_jd = sl in pos_lower
            in_resume = sl in resume_lower
            if in_jd and in_resume:
                matched.append({
                    'skill': skill,
                    'proficiency': '简历提及',
                    'evidence': '简历与JD同时包含该关键词',
                })
            elif in_jd and not in_resume:
                missing.append({
                    'skill': skill,
                    'importance': '重要',
                    'impact': 'JD要求但简历未提及',
                })
        # 限制返回条数（UI 不需要太长的列表）
        matched = matched[:8]
        missing = missing[:8]
        return matched, missing