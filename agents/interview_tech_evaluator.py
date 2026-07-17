"""技术评估师 Agent - 专注评估技能验证和场景设计类问答"""
from agents.base_agent import BaseAgent
import json


class InterviewTechEvaluatorAgent(BaseAgent):
    """技术评估师

    职责：专注评估「技能验证」和「场景设计」类面试问答的表现。
    并行工作：与项目评估师、素质评估师同时工作。
    """
    AGENT_NAME = "技术评估师"
    SYSTEM_PROMPT = """你是「技术评估师」，专精于评估候选人的技术能力和系统设计水平。

你的评估重点：
- 核心技术掌握程度（不是背概念，而是真正理解原理）
- 实操问题解决能力（排查思路、方案设计的合理性）
- 系统设计能力（架构思维、权衡取舍、扩展性考量）
- 技术广度和学习潜力（对新技术的了解程度）

工作原则：
- 只基于面试中的实际回答来评估
- 区分"背答案"和"真正理解"（能举一反三说明真懂了）
- 关注回答的技术准确性和深度
- 追问环节的回答往往更能反映真实水平

请始终以严格的 JSON 格式输出，不要输出任何解释性文字。"""

    def evaluate(self, position_name, tech_requirements,
                 candidate_name, dialogs, questions_plan):
        """评估技术类问答

        Args:
            position_name: 岗位名称
            tech_requirements: 技术要求
            candidate_name: 候选人姓名
            dialogs: 本轮全部面试对话
            questions_plan: 出题策略（含每道题的 category 和 intent）

        Returns:
            dict: 技术维度评估结果
        """
        plan_questions = (questions_plan or {}).get('questions', [])
        tech_intents = [
            f"Q{i+1}: {q.get('intent','')}"
            for i, q in enumerate(plan_questions)
            if q.get('category') in ('技能验证', '场景设计')
        ]

        prompt = f"""## 任务
评估候选人 {candidate_name} 在**技能验证和场景设计**类问题上的面试表现。

## 岗位信息
- 岗位名称：{position_name}
- 技术要求：{tech_requirements or '未明确'}

## 技术类题目的考察意图
{json.dumps(tech_intents, ensure_ascii=False) if tech_intents else '无明确出题计划'}

## 本轮面试全部对话
{dialogs}

## 评估要求
请只关注技术能力和系统设计相关的问答，评估以下维度：

1. **技术基础（1-10）**：核心技术的掌握程度和准确性
2. **问题解决（1-10）**：面对技术问题的排查思路和解决方案
3. **系统设计（1-10）**：架构思维、方案权衡、扩展性考量
4. **技术广度（1-10）**：对技术栈的了解范围和学习潜力

## 输出格式（严格 JSON）
{{
    "dimensions": {{
        "技术基础": 7,
        "问题解决": 6,
        "系统设计": 5,
        "技术广度": 7
    }},
    "strengths": [
        {{"point": "优势描述", "evidence": "面试中的具体回答证据"}}
    ],
    "weaknesses": [
        {{"point": "不足描述", "evidence": "面试中的具体表现", "suggestion": "改进建议"}}
    ],
    "real_understanding": "对候选人真实技术水平的判断（区分背诵和理解）",
    "overall_comment": "技术维度的综合评价（2-3句话）",
    "score": 65
}}"""
        return self.think_json(prompt)
