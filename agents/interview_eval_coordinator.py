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
- 整合各方评分，给出统一的维度评分和综合评分
- 合并优势和不足，确保每条都有面试证据支撑
- 给出明确的招聘建议

工作原则：
- 综合评分应反映各维度的加权平均（技术稍重、项目次之、素质参考）
- 优势和不足从三方报告中合并去重，保留最有代表性的
- 如果三位评估师对某项评价有分歧，取多数意见
- 招聘建议要明确，不含糊
- 面向候选人的反馈要温和、建设性

请始终以严格的 JSON 格式输出，不要输出任何解释性文字。"""

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
            dict: 最终面试评价报告
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

1. **综合评分（0-100）**：参考三位评估师的评分，加权计算
   - 技术维度权重 40%（技术评估师）
   - 项目维度权重 35%（项目评估师）
   - 素质维度权重 25%（素质评估师）

2. **五维评分（每项 1-10）**：
   - 技术基础：取自技术评估师
   - 项目经验：取自项目评估师
   - 系统设计：取自技术评估师
   - 沟通表达：取自素质评估师
   - 学习能力：取自素质评估师

3. **优势和不足**：从三方报告中合并去重，每条必须有面试证据

4. **追问表现**：综合素质评估师的 follow_up_performance

5. **招聘建议**：基于综合评分和各维度表现

## 输出格式（严格 JSON）
{{
    "overall_score": 72,
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
    "recommendation": "强烈推荐/推荐/待定/不推荐",
    "recommendation_reason": "1句话说明核心理由",
    "summary": "3-4句话综合评价",
    "interview_highlights": {{
        "best_answer": "回答最好的问题方向",
        "worst_answer": "表现最差的问题方向",
        "best_follow_up": "追问环节表现最好的部分",
        "weakest_follow_up": "追问环节暴露最多问题的部分"
    }},
    "score_breakdown": {{
        "project_score": "项目评估师评分",
        "tech_score": "技术评估师评分",
        "soft_score": "素质评估师评分"
    }},
    "candidate_summary": "面向候选人本人的反馈（3-5句话，温和、建设性语气，开头用\\"{candidate_name}您好\\"称呼）：先肯定面试中展现的优点和亮点，再指出可以进一步提升的方向，最后给出具体可操作的努力建议。不要用\\"不推荐\\"\\"包装\\"\\"风险\\"等内部决策用语。"
}}"""
        return self.think_json(prompt)
