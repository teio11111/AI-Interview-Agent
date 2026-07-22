"""面试汇总师 Agent - 综合三位评估师的评分生成最终面试报告"""
from agents.base_agent import BaseAgent
import json


class InterviewEvalCoordinatorAgent(BaseAgent):
    """面试汇总师

    职责：接收项目评估师、技术评估师、素质评估师的评估结果，
    综合汇总生成本轮面试的最终评价报告。
    """
    AGENT_NAME = "面试汇总师"
    SYSTEM_PROMPT = """你是「面试汇总师」，面试评价的最终汇总人。

你的核心职责：
- 综合三位评估师（项目评估师、技术评估师、素质评估师）的评估结果
- 整合各方原始数据，产出一个能反映三方意见的综合评语
- 合并优势和不足，确保每条都有面试证据支撑
- 给出面向候选人的反馈（温和、建设性）

工作原则：
- **【重要】综合评分（0-100）与「招聘建议」等级，均由系统根据三方维度分自动加权计算与映射，你不需要、也不应该计算这两个字段。**
- 你的任务聚焦在"叙述性评语"：整合 strengths / weaknesses / follow_up_performance / summary / candidate_summary / interview_highlights
- 优势和不足从三方报告中合并去重，保留最有面试证据支撑的
- 如果三位评估师对某项评价有分歧，取多数意见或并列保留
- 招聘建议要明确，不含糊
- 面向候选人的反馈要温和、建设性

请始终以严格的 JSON 格式输出，不要输出任何解释性文字。"""

    # ---- 常量权重与推荐等级映射表 ----
    W_TECH = 0.40
    W_PROJECT = 0.35
    W_SOFT = 0.25

    RECOMMENDATION_TABLE = [
        (80, '强烈推荐'),
        (65, '推荐'),
        (45, '待定'),
        (0,  '不推荐'),
    ]

    def _avg_dimensions(self, eval_result, fallback_score=None):
        """从评估师结果中提取维度平均分（1-10），不足时退回到 evaluator 原始 score/10。

        为了避免 LLM 手工算的累加误差，**以你返回的 dimensions dict 为准**：
        - 若 dimensions 存在：取所有维度的算术平均
        - 若 dimensions 缺失/为空：退回到 evaluator 的 `score` 字段（0-100）/10
        """
        dims = (eval_result or {}).get('dimensions') or {}
        values = [v for v in dims.values() if isinstance(v, (int, float))]
        if values:
            return round(sum(values) / len(values), 2)
        if fallback_score is not None:
            return round(fallback_score / 10.0, 2)
        return 5.0  # 缺失数据时给中立平分

    def _recommendation_for(self, score):
        """根据分数映射招聘建议"""
        for threshold, label in self.RECOMMENDATION_TABLE:
            if score >= threshold:
                return label
        return '不推荐'

    def _recommendation_reason_for(self, score, tech_avg, project_avg, soft_avg):
        """根据分数与三项均值生成 1 句话原因"""
        label = self._recommendation_for(score)
        weakest = min(
            ('技术', tech_avg),
            ('项目', project_avg),
            ('素质', soft_avg),
            key=lambda x: x[1]
        )
        if label == '强烈推荐':
            return f'面试表现全面优秀，三项综合 {score}，可直接进入 offer 环节。'
        if label == '推荐':
            return f'面试综合表现良好，三项综合 {score}，推荐推进下一轮。'
        if label == '待定':
            return f'面试综合表现中等（三项综合 {score}），{weakest[0]}维度（{weakest[1]}/10）需进一步考察或进入下轮验证。'
        return f'面试表现低于岗位基本要求（三项综合 {score}），不推荐推进。'

    def synthesize(self, project_result, tech_result, soft_result,
                   position_name, candidate_name):
        """汇总三位评估师的结果

        Args:
            project_result: 项目评估师的评估结果
            tech_result: 技术评估师的评估结果
            soft_result: 素质评估师的评估结果
            position_name: 岗位名称
            candidate_name: 候选人姓名

        Returns:
            dict: 最终面试评价报告（含由系统计算的 overall_score / recommendation）
        """
        prompt = f"""## 任务
综合三位评估师的评估结果，为候选人 {candidate_name}（应聘{position_name}）生成本轮面试的最终评价报告。

## 项目评估师的评估结果
{json.dumps(project_result or {}, ensure_ascii=False, indent=2)}

## 技术评估师的评估结果
{json.dumps(tech_result or {}, ensure_ascii=False, indent=2)}

## 素质评估师的评估结果
{json.dumps(soft_result or {}, ensure_ascii=False, indent=2)}

## 汇总要求

## 评分计算规则
**以下计算由系统在后方统一处理，你不需要重复计算**：
- 各评估师维度评分加权后得到综合分（技术 40% + 项目 35% + 素质 25%）
- 系统根据综合分自动映射招聘建议等级并填充 `overall_score`、`recommendation`、`recommendation_reason` 字段
- 你输出的对应字段会被系统覆写

请你只做「叙述性整合」工作：
1. **五维评分（每项 1-10）**（仅作为参考展示；系统最终会按权重重算后将这个字段覆掉）
   - 技术基础：取自技术评估师
   - 项目经验：取自项目评估师
   - 系统设计：取自技术评估师
   - 沟通表达：取自素质评估师
   - 学习能力：取自素质评估师

2. **优势和不足**：从三方报告中合并去重，每条必须有面试证据

3. **追问表现**：综合素质评估师的 follow_up_performance

4. **面向候选人的反馈（candidate_summary）**：3-5 句话，以 "{candidate_name}您好" 开头，先肯定优点再指出可提升方向，最后给具体可操作建议。语气温和、建设性。不要用 "不推荐" "包装" "风险" 等内部决策用语。

5. **综合评价总结（summary）**：3-4 句话，用面试观察事实描述候选人面试表现。

6. **面试亮点 / 污点（interview_highlights）**：根据三方评语提炼，不虚构。

## 输出格式（严格 JSON）

**注意：以下 `overall_score`、`recommendation`、`recommendation_reason` 三个字段你**不要填**（你填了也会被系统覆写）。其他字段全部必填。**

{{
    "dimensions": {{
        "技术基础": 7,
        "项目经验": 6,
        "系统设计": 5,
        "沟通表达": 8,
        "学习能力": 7
    }},
    "strengths": [
        {{"point": "优势描述", "evidence": "面试中对应的具体表现"}}
    ],
    "weaknesses": [
        {{"point": "不足描述", "evidence": "面试中对应的具体表现", "suggestion": "改进建议"}}
    ],
    "follow_up_performance": "追问环节的表现评估",
    "summary": "3-4句话综合评价",
    "interview_highlights": {{
        "best_answer": "回答最好的问题方向",
        "worst_answer": "表现最差的问题方向",
        "best_follow_up": "追问环节表现最好的部分",
        "weakest_follow_up": "追问环节暴露最多问题的部分"
    }},
    "score_breakdown": {{
        "project_score": "项目评估师原始评分 0-100",
        "tech_score": "技术评估师原始评分 0-100",
        "soft_score": "素质评估师原始评分 0-100"
    }},
    "candidate_summary": "面向候选人本人的反馈（3-5句话，温和、建设性语气）"
}}"""
        llm_result = self.think_json(prompt)
        if not isinstance(llm_result, dict):
            # LLM 调用失败，直接返回不覆盖 overall_score / recommendation
            return llm_result

        # ---------------------------
        # 【系统计算】综合分 + 推荐等级
        # ---------------------------
        tech_avg = self._avg_dimensions(tech_result, (tech_result or {}).get('score'))
        project_avg = self._avg_dimensions(project_result, (project_result or {}).get('score'))
        soft_avg = self._avg_dimensions(soft_result, (soft_result or {}).get('score'))

        tech_score_100 = round(tech_avg * 10, 1)
        project_score_100 = round(project_avg * 10, 1)
        soft_score_100 = round(soft_avg * 10, 1)

        raw = (
            tech_score_100 * self.W_TECH
            + project_score_100 * self.W_PROJECT
            + soft_score_100 * self.W_SOFT
        )
        overall_score = int(round(raw))

        recommendation = self._recommendation_for(overall_score)
        recommendation_reason = self._recommendation_reason_for(
            overall_score, tech_avg, project_avg, soft_avg
        )

        # 覆盖 LLM 可能误填的字段（确保一致）
        llm_result['overall_score'] = overall_score
        llm_result['recommendation'] = recommendation
        llm_result['recommendation_reason'] = recommendation_reason
        # 同步更新 score_breakdown 中的三项分
        llm_result.setdefault('score_breakdown', {})
        llm_result['score_breakdown']['tech_score'] = tech_score_100
        llm_result['score_breakdown']['project_score'] = project_score_100
        llm_result['score_breakdown']['soft_score'] = soft_score_100
        # 计算明细，调试/验证用（前端可选择展示）
        llm_result['computation'] = {
            'tech_avg_dimensions': tech_avg,
            'project_avg_dimensions': project_avg,
            'soft_avg_dimensions': soft_avg,
            'tech_score_100': tech_score_100,
            'project_score_100': project_score_100,
            'soft_score_100': soft_score_100,
            'weights': {
                'tech': self.W_TECH,
                'project': self.W_PROJECT,
                'soft': self.W_SOFT,
            },
            'raw': round(raw, 2),
        }

        return llm_result
