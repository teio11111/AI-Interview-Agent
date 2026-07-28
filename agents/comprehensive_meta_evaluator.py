"""综合元评估师 Agent - 汇总全链路数据生成最终招聘决策"""
from agents.base_agent import BaseAgent
import json


class ComprehensiveMetaEvaluatorAgent(BaseAgent):
    """综合元评估师

    职责：汇总候选人全链路评估数据（岗位分析 + 简历评估 + 各轮面试评价），
    进行跨阶段交叉分析，生成最终招聘决策报告。
    该 Agent 是整个面试系统的最终裁判，负责将所有中间结果整合为一份综合判断。

    输出：综合元评估报告（最终评分 + 招聘建议 + 跨阶段分析 + 决策依据）。
    """

    # -------- 权重与推荐等级映射表（由系统计算使用）--------
    # 不同轮次下，简历评估 vs 面试评价 的权重
    META_WEIGHTS = {
        0: {'resume': 1.00, 'rounds': []},                       # 仅有简历
        1: {'resume': 0.35, 'rounds': [0.65]},                  # 1 轮
        2: {'resume': 0.20, 'rounds': [0.35, 0.45]},            # 2 轮
        # 3+ 轮：简历 15%，面试递增（总 85%）
    }

    # 五档推荐等级阈值表
    RECOMMENDATION_TABLE = [
        (85, '强烈推荐'),
        (70, '推荐'),
        (60, '有条件推荐'),
        (50, '不推荐'),
        (0,  '强烈不推荐'),
    ]

    @staticmethod
    def _round_weights(n):
        """n 轮面试的递增权重（线性递增 1..n, 归一后总和为 1）"""
        if n <= 0:
            return []
        weights = [i + 1 for i in range(n)]
        total = sum(weights)
        return [w / total for w in weights]

    @classmethod
    def compute_overall_score_raw(cls, resume_match_score, round_scores_100):
        """计算 raw 综合分（保留两位小数），方便保存到 computation 调试字段。"""
        n = len(round_scores_100 or [])
        if n >= 3:
            resume_w = 0.15
            round_w_total = 0.85
            round_weights = cls._round_weights(n)
            s = (resume_match_score or 0) * resume_w
            s += sum(score * w for score, w in zip(round_scores_100, round_weights)) * round_w_total
            return round(s, 2)
        # 复用固定映射
        conf = cls.META_WEIGHTS.get(n, cls.META_WEIGHTS[0])
        s = (resume_match_score or 0) * conf['resume']
        for i, w in enumerate(conf['rounds']):
            if i < n:
                s += round_scores_100[i] * w
        return round(s, 2)

    @classmethod
    def compute_overall_score(cls, resume_match_score, round_scores_100):
        """计算最终综合分（取整 0-100）。"""
        raw = cls.compute_overall_score_raw(resume_match_score, round_scores_100)
        return int(round(raw))

    # ===== 【设计修复】跨阶段一致性惩罚 =====

    @classmethod
    def _cross_validation_penalty(cls, cross_stage_analysis=None, key_risks=None):
        """根据跨阶段一致性 + 关键风险计算综合评分惩罚（最多扣 25 分）。

        设计原因：
        - 仅靠加权求和算分时，简历「说好」但面试「差」这种不一致会被分数掩盖。
        - cross_stage_analysis（跨阶段交叉验证） 与 key_risks（关键风险）
          是 LLM 识别出的「质性信号」，应该量化反映到最终分数里。
        - 惩罚规则：
            · 每 1 条「不一致」 结论 → 扣 5 分
            · 每 1 条「部分一致」结论 → 扣 2 分
            · 每 1 个「高」严重度风险 → 扣 5 分
            · 每 1 个「中」严重度风险 → 扣 2 分
            · 累计上限 25 分（避免过度惩罚导致分数断崖下跌）

        Returns:
            int: 扣分值（0–25）
        """
        penalty = 0
        if cross_stage_analysis and isinstance(cross_stage_analysis, dict):
            findings = cross_stage_analysis.get('consistency_findings') or []
            for f in findings:
                if not isinstance(f, dict):
                    continue
                verdict = (f.get('verdict') or '').strip()
                if verdict == '不一致':
                    penalty += 5
                elif verdict == '部分一致':
                    penalty += 2
        if key_risks and isinstance(key_risks, list):
            for r in key_risks:
                if not isinstance(r, dict):
                    continue
                sev = (r.get('severity') or '').strip()
                if sev == '高':
                    penalty += 5
                elif sev == '中':
                    penalty += 2
        return min(25, penalty)

    @classmethod
    def compute_overall_score_with_validation(cls, resume_match_score, round_scores_100,
                                              cross_stage_analysis=None, key_risks=None):
        """计算最终综合分（应用跨阶段一致性惩罚后），返回 (final_score, penalty)。

        与 compute_overall_score 的区别：本方法会在加权求和基础上，
        依据跨阶段验证和关键风险对分数进行扣减，避免“简历说好但面试差”不被发现。

        Returns:
            tuple: (final_score, penalty)
        """
        raw = cls.compute_overall_score_raw(resume_match_score, round_scores_100)
        penalty = cls._cross_validation_penalty(cross_stage_analysis, key_risks)
        final = max(0, int(round(raw)) - penalty)
        return final, penalty

    @classmethod
    def _format_penalty_note(cls, penalty, cross_stage_analysis, key_risks):
        """生成「扣分说明」中文本（如 已应用跨阶段一致性验证：2项不一致 + 1项高风险，扣15分）。"""
        if penalty <= 0:
            return ''

        inconsistency_count = 0
        partial_count = 0
        high_risk_count = 0
        med_risk_count = 0

        if cross_stage_analysis and isinstance(cross_stage_analysis, dict):
            for f in (cross_stage_analysis.get('consistency_findings') or []):
                if isinstance(f, dict):
                    v = (f.get('verdict') or '').strip()
                    if v == '不一致':
                        inconsistency_count += 1
                    elif v == '部分一致':
                        partial_count += 1
        if key_risks and isinstance(key_risks, list):
            for r in key_risks:
                if isinstance(r, dict):
                    sev = (r.get('severity') or '').strip()
                    if sev == '高':
                        high_risk_count += 1
                    elif sev == '中':
                        med_risk_count += 1

        notes = []
        if inconsistency_count or partial_count:
            s = f'{inconsistency_count}项不一致'
            if partial_count:
                s += f'+{partial_count}项部分一致'
            notes.append(s)
        if high_risk_count or med_risk_count:
            s = f'{high_risk_count}项高风险'
            if med_risk_count:
                s += f'+{med_risk_count}项中风险'
            notes.append(s)

        if notes:
            return f'（已应用跨阶段一致性验证：{" / ".join(notes)}，扣{penalty}分）'
        return f'（已应用跨阶段一致性验证，扣{penalty}分）'

    @classmethod
    def decision_rationale_for_with_validation(cls, raw_score, final_score, round_scores,
                                               resume_match_score,
                                               cross_stage_analysis=None, key_risks=None):
        """在基础决策理由上叠加跨阶段一致性扣分说明。"""
        base = cls.decision_rationale_for(final_score, round_scores, resume_match_score)
        penalty = max(0, int(round(raw_score)) - final_score)
        note = cls._format_penalty_note(penalty, cross_stage_analysis, key_risks)
        return (base + note) if note else base

    @classmethod
    def recommendation_for(cls, score):
        """根据综合分查五档推荐等级"""
        for threshold, label in cls.RECOMMENDATION_TABLE:
            if score >= threshold:
                return label
        return '强烈不推荐'

    @classmethod
    def decision_rationale_for(cls, score, round_scores, resume_match_score):
        """根据计算数据生成 1-2 句话决策理由（LLM 未提供时使用）"""
        label = cls.recommendation_for(score)
        n = len(round_scores or [])
        if n == 0 and not resume_match_score:
            return '数据不足，无法生成评判。'
        avg_round = round(sum(round_scores) / len(round_scores), 1) if round_scores else None
        if label == '强烈推荐':
            return f'综合表现优秀（{score}），各项证据一致，可推进 offer。'
        if label == '推荐':
            return f'综合表现良好（{score}），面试表现均合门槛，推荐推进下一轮。'
        if label == '有条件推荐':
            return (f'综合表现达到门槛（{score}），可推进但需关注以下几点风险。'
                    + (f'面试平均 {avg_round}/100。' if avg_round else ''))
        if label == '不推荐':
            return (f'综合表现未达推荐门槛（{score}），关键面试环节表现偏弱，'
                    f'建议暂不推进。')
        return f'综合表现明显低于岗位要求（{score}），不推荐推进。'

    AGENT_NAME = "综合元评估师"
    SYSTEM_PROMPT = """你是「综合元评估师」，一位拥有 20 年经验的招聘决策委员会主席。

你的角色定位：
- 你是整个面试系统的**最终裁判**，不替代任何前序评估师，而是在他们的工作基础上做最终判断
- 你拿到的所有数据来自多个独立评估师的分析结果，你需要**综合交叉**而非简单平均
- 你的结论要有**明确决策依据**，能经得起追问

你的核心能力：
- 跨阶段交叉分析：简历评估 vs 面试表现的**一致性验证**
- 多轮面试进步追踪：候选人是否有成长曲线还是原地踏步
- 识别"说得好"vs"做得到"的差距
- 综合所有维度给出最终招聘决策
- 给出有说服力的决策理由

工作原则：
1. **以数据为依据**：每个判断都要指出具体来源（"简历评估中X..."、"第N轮面试中..."）
2. **交叉验证**：简历说什么 vs 面试表现如何，发现不一致要标注
3. **权重动态调整**：
   - 有 1 轮面试时：简历评估 35% + 面试评价 65%
   - 有 2 轮面试时：简历评估 20% + 第一轮面试 35% + 第二轮面试 45%
   - 有 3+ 轮面试时：简历评估 15% + 面试评价按轮次递增权重
4. **决策要果断**：给出明确建议，不要模棱两可

请始终以严格的 JSON 格式输出，不要输出任何解释性文字。"""

    def evaluate(self, position_name, position_analysis,
                 candidate_name, resume_text, resume_evaluation,
                 interview_sessions):
        """生成综合元评估报告

        Args:
            position_name: 岗位名称
            position_analysis: 岗位分析结果 dict
            candidate_name: 候选人姓名
            resume_text: 原始简历文本
            resume_evaluation: 简历 3+1 评估结果 dict
            interview_sessions: 面试会话列表，每个包含 {round, report, questions_plan}

        Returns:
            dict: 综合元评估报告
        """
        # 构建岗位摘要
        pos_summary = self._summarize_position(position_analysis)

        # 构建简历评估摘要
        resume_summary = self._summarize_resume_eval(resume_evaluation)

        # 构建各轮面试摘要
        sessions_summary = self._summarize_sessions(interview_sessions)

        # 确定轮次数和权重说明
        n_rounds = len(interview_sessions)
        if n_rounds == 1:
            weight_desc = "简历评估 35% + 面试评价 65%"
        elif n_rounds == 2:
            weight_desc = "简历评估 20% + 第一轮 35% + 第二轮 45%"
        else:
            weight_desc = f"简历评估 15% + {n_rounds}轮面试评价按轮次递增权重"

        prompt = f"""## 任务
综合候选人的全部评估数据，生成最终招聘决策报告。

## 基本信息
- **候选人姓名**：{candidate_name}
- **应聘岗位**：{position_name}
- **面试轮次**：{n_rounds} 轮
- **权重方案**：{weight_desc}

## 一、岗位画像摘要
{pos_summary}

## 二、简历评估结果（来自 3+1 多智能体协作）
{resume_summary}

## 三、各轮面试评价结果（每轮来自 3+1 多智能体协作）
{sessions_summary}

## 分析要求

### A. 跨阶段交叉验证（核心）
1. **一致性检验**：简历评估结论 vs 面试表现是否一致？
   - 例：简历说"学习能力强"，面试中追问技术细节时是否体现？
   - 例：简历说"有项目主导经验"，面试是否展现出决策能力？
2. **发现的不一致点**：明确列出并说明影响
3. **验证通过的结论**：哪些判断在面试中得到确认

### B. 多轮面试追踪（如有多轮）
1. 各轮侧重点变化
2. 候选人是否有进步/退步
3. 多轮结论是否趋同

### C. 综合评分
**重要：本阶段的 `overall_score`、`final_recommendation`、`decision_rationale` 三个字段均由系统根据预设权重和交叉验证表自动生成，你**不要、不要、不要填写这三个字段（你填了也会被覆写）**。**

系统使用以下权重方案：
- 有 1 轮面试时：简历评估 35% + 面试评价 65%
- 有 2 轮面试时：简历评估 20% + 第一轮面试 35% + 第二轮面试 45%
- 有 3+ 轮面试时：简历评估 15% + 面试评价按轮次递增权重（总 85%）

系统使用以下五档推荐等级映射表：
- **85-100** → 强烈推荐
- **70-84** → 推荐
- **60-69** → 有条件推荐
- **50-59** → 不推荐
- **0-49**  → 强烈不推荐

**你任务只做两类工作：**
1. **跨阶段交叉分析**（cross_stage_analysis）：简历 vs 面试的一致性检查、多轮面试追踪
2. **叙述性结论**：key_strengths / key_risks / onboarding_suggestions / candidate_message / summary

`dimension_scores` （五维 0-10）是允许填写的，系统仅将其作为信息保存，**不影响综合评分**。

### 核心价值观
- 以数据为依据：每个判断都要指出具体来源（简历评估中X...、第N轮面试中...）
- 交叉验证：简历说什么 vs 面试表现如何，发现不一致要标注
- 决策要果断（让系统在分数上表现果断、你可在叙述中明确快）

## 输出格式（严格 JSON）
{{
    "overall_score": 0-100综合得分,
    "dimension_scores": {{
        "technical_ability": 0-10,
        "project_experience": 0-10,
        "system_design": 0-10,
        "communication": 0-10,
        "learning_potential": 0-10
    }},
    "final_recommendation": "强烈推荐/推荐/有条件推荐/不推荐/强烈不推荐",
    "decision_rationale": "核心决策理由（2-3句话，说明为什么给出此建议）",
    "cross_stage_analysis": {{
        "consistency_findings": [
            {{
                "claim": "简历/评估结论",
                "interview_evidence": "面试中的对应表现",
                "verdict": "一致/不一致/部分一致",
                "impact": "对最终决策的影响"
            }}
        ],
        "validated_conclusions": ["在面试中得到确认的简历评估结论"],
        "inconsistency_alerts": ["发现的简历与实际不符之处"]
    }},
    "multi_round_tracking": {{
        "round_summary": [
            {{
                "round": 1,
                "focus": "本轮侧重点",
                "score": 0-100,
                "key_findings": "主要发现"
            }}
        ],
        "progression": "进步/平稳/退步",
        "progression_detail": "多轮表现变化分析",
        "consensus_across_rounds": "多轮面试结论是否趋同"
    }},
    "key_strengths": [
        {{
            "point": "优势点",
            "evidence": "来自哪些阶段的证据",
            "relevance": "对岗位的 relevance"
        }}
    ],
    "key_risks": [
        {{
            "risk": "风险点",
            "evidence": "来自哪些阶段的证据",
            "severity": "高/中/低",
            "mitigation": "如何规避或关注"
        }}
    ],
    "onboarding_suggestions": {{
        "if_hired": "入职后建议重点关注或培养的方向",
        "first_90_days": "前90天的建议安排"
    }},
    "candidate_message": "给候选人的综合反馈（200字以内，专业、友善、有建设性）",
    "summary": "3-5句话的最终评估总结，涵盖核心发现和建议"
}}"""
        return self.think_json(prompt)

    def _summarize_position(self, analysis):
        """将岗位分析结果转为文本摘要"""
        if not analysis:
            return "无岗位分析数据"
        if isinstance(analysis, str):
            try:
                analysis = json.loads(analysis)
            except Exception:
                return analysis[:500]
        parts = []
        # 核心技能
        skills = analysis.get("core_skills", [])
        if skills:
            skill_names = [s.get("skill", s) if isinstance(s, dict) else s for s in skills[:6]]
            parts.append(f"核心技能: {', '.join(skill_names)}")
        # 经验要求
        exp = analysis.get("experience_level", "")
        yrs = analysis.get("experience_years", "")
        if exp or yrs:
            parts.append(f"经验要求: {exp} ({yrs})")
        # 考察重点
        focus = analysis.get("interview_focus", [])
        if focus:
            topics = [f.get("topic", "") for f in focus[:4] if isinstance(f, dict)]
            parts.append(f"面试考察重点: {', '.join(topics)}")
        # 隐性要求
        impl = analysis.get("implicit_requirements", {})
        if impl:
            stress = impl.get("stress_tolerance", {}).get("level", "")
            mgmt = impl.get("management_potential", {}).get("needed", "")
            parts.append(f"隐性要求: 抗压={stress}, 管理潜力={mgmt}")
        # 摘要
        summary = analysis.get("summary", "")
        if summary:
            parts.append(f"岗位摘要: {summary}")
        return "\n".join(parts) if parts else "岗位分析数据不完整"

    def _summarize_resume_eval(self, evaluation):
        """将简历评估结果转为文本摘要"""
        if not evaluation:
            return "无简历评估数据"
        if isinstance(evaluation, str):
            try:
                evaluation = json.loads(evaluation)
            except Exception:
                return evaluation[:500]
        parts = []
        # 匹配度
        score = evaluation.get("match_score", "")
        if score:
            parts.append(f"简历匹配度: {score}分")
        # 匹配技能
        matched = evaluation.get("matched_skills", [])
        if matched:
            names = [s.get("skill", s) if isinstance(s, dict) else s for s in matched[:6]]
            parts.append(f"匹配技能: {', '.join(names)}")
        # 缺失技能
        missing = evaluation.get("missing_skills", [])
        if missing:
            names = [s.get("skill", s) if isinstance(s, dict) else s for s in missing[:5]]
            parts.append(f"缺失技能: {', '.join(names)}")
        # 优势
        strengths = evaluation.get("strengths", [])
        if strengths:
            pts = [s.get("point", s) if isinstance(s, dict) else s for s in strengths[:3]]
            parts.append(f"核心优势: {'; '.join(pts)}")
        # 风险
        risks = evaluation.get("risks", [])
        if risks:
            pts = [r.get("risk", r) if isinstance(r, dict) else r for r in risks[:3]]
            parts.append(f"主要风险: {'; '.join(pts)}")
        # 候选人画像摘要
        profile = evaluation.get("candidate_profile", {})
        if profile:
            img_parts = []
            for key in ["education", "job_stability", "learning_ability", "resume_authenticity"]:
                item = profile.get(key, {})
                if isinstance(item, dict):
                    detail = item.get("detail", "")
                    conf = item.get("confidence", "")
                    if detail:
                        label_map = {
                            "education": "学历", "job_stability": "稳定度",
                            "learning_ability": "学习能力", "resume_authenticity": "简历真实度"
                        }
                        img_parts.append(f"{label_map.get(key, key)}: {detail[:30]}(conf={conf})")
            if img_parts:
                parts.append("候选人画像: " + " | ".join(img_parts))
        # 隐性条件
        mapping = evaluation.get("implicit_requirement_mapping", [])
        if mapping:
            maps = [f"{m.get('dimension','')}: {m.get('match_status','')}" for m in mapping[:4]]
            parts.append("隐性条件对照: " + " | ".join(maps))
        # 共识与分歧
        consensus = evaluation.get("expert_consensus", [])
        if consensus:
            parts.append(f"三方共识({len(consensus)}条): " + "; ".join(str(c)[:30] for c in consensus[:3]))
        divergence = evaluation.get("expert_divergence", [])
        if divergence:
            parts.append(f"三方分歧({len(divergence)}项): " + "; ".join(str(d)[:30] for d in divergence[:2]))
        # 总结
        summary = evaluation.get("summary", "")
        if summary:
            parts.append(f"简历评估总结: {summary}")
        return "\n".join(parts) if parts else "简历评估数据不完整"

    def _summarize_sessions(self, sessions):
        """将各轮面试评价转为文本摘要"""
        if not sessions:
            return "无面试评价数据"
        parts = []
        for i, sess in enumerate(sessions):
            round_num = sess.get("round", i + 1) if isinstance(sess, dict) else i + 1
            report_raw = sess.get("report") if isinstance(sess, dict) else None
            report = report_raw if report_raw else {}
            if isinstance(report, str):
                try:
                    report = json.loads(report)
                except Exception:
                    parts.append(f"第{round_num}轮: 报告解析失败")
                    continue
            if not isinstance(report, dict):
                report = {}
            # 基本信息
            score = report.get("overall_score", "?")
            rec = report.get("recommendation", "")
            parts.append(f"--- 第{round_num}轮面试 ---")
            parts.append(f"综合分: {score}, 建议: {rec}")
            # 维度
            dims = report.get("dimensions", {})
            if dims:
                dim_str = ", ".join(f"{k}={v}" for k, v in dims.items())
                parts.append(f"维度: {dim_str}")
            # 三方评分
            bd = report.get("score_breakdown", {})
            if bd:
                parts.append(f"三方评分: project={bd.get('project_score','?')}, tech={bd.get('tech_score','?')}, soft={bd.get('soft_score','?')}")
            # 优势
            strengths = report.get("strengths", [])
            if strengths:
                pts = [s.get("point", s) if isinstance(s, dict) else s for s in strengths[:2]]
                parts.append(f"面试优势: {'; '.join(pts)}")
            # 不足
            weaknesses = report.get("weaknesses", [])
            if weaknesses:
                pts = [w.get("point", w) if isinstance(w, dict) else w for w in weaknesses[:2]]
                parts.append(f"面试不足: {'; '.join(pts)}")
            # 亮点
            highlights = report.get("interview_highlights", {})
            best = highlights.get("best_answer", "")
            worst = highlights.get("worst_answer", "")
            if best:
                parts.append(f"最佳回答: {best[:60]}")
            if worst:
                parts.append(f"最弱回答: {worst[:60]}")
            # 总结
            summary = report.get("summary", "")
            if summary:
                parts.append(f"面试总结: {summary[:100]}")
            parts.append("")
        return "\n".join(parts) if parts else "面试评价数据不完整"
