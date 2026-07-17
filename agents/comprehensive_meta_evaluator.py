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
1. **综合得分**（0-100）：按上述权重方案加权
2. **五维最终评分**（0-10分/维）：
   - 技术能力
   - 项目经验
   - 系统设计
   - 沟通表达
   - 学习潜力

### D. 最终决策
从以下五档中选择：
- **强烈推荐**：综合 85+ 且无明显短板
- **推荐**：综合 70+ 且风险可控
- **有条件推荐**：综合 60+ 但需关注某些风险
- **不推荐**：综合 50-60 或有关键短板
- **强烈不推荐**：综合 <50 或有严重问题

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
            round_num = sess.get("round", i + 1)
            report = sess.get("report", {})
            if isinstance(report, str):
                try:
                    report = json.loads(report)
                except Exception:
                    parts.append(f"第{round_num}轮: 报告解析失败")
                    continue
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
