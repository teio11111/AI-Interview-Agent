"""项目评估师 Agent - 专注评估项目深挖类问答"""
from agents.base_agent import BaseAgent
import json


class InterviewProjectEvaluatorAgent(BaseAgent):
    """项目评估师

    职责：专注评估「项目深挖」类面试问答的表现。
    并行工作：与技术评估师、素质评估师同时工作。
    """
    AGENT_NAME = "项目评估师"
    SYSTEM_PROMPT = """你是「项目评估师」，专精于评估候选人在项目相关问题上的回答质量。

你的评估重点：
- 项目经验的真实性和深度（是否真的做过）
- 具体贡献和角色（是核心参与者还是打酱油）
- 技术决策能力（选型原因、权衡取舍）
- 问题解决能力（遇到挑战怎么应对）
- 成果量化意识（能否用数据说明成果）

工作原则：
- 只基于面试中的实际回答来评估
- 区分"背诵项目介绍"和"真正理解项目"
- 关注回答中的细节一致性（前后矛盾说明可能在编造）
- 给出具体证据支撑每个评分

请始终以严格的 JSON 格式输出，不要输出任何解释性文字。"""

    def evaluate(self, position_name, tech_requirements,
                 candidate_name, dialogs, questions_plan):
        """评估项目类问答

        Args:
            position_name: 岗位名称
            tech_requirements: 技术要求
            candidate_name: 候选人姓名
            dialogs: 本轮全部面试对话
            questions_plan: 出题策略（含每道题的 category 和 intent）

        Returns:
            dict: 项目维度评估结果
        """
        # 提取项目类题目的出题意图
        plan_questions = (questions_plan or {}).get('questions', [])
        project_intents = [
            f"Q{i+1}: {q.get('intent','')}"
            for i, q in enumerate(plan_questions)
            if q.get('category') in ('项目深挖',)
        ]

        prompt = f"""## 任务
评估候选人 {candidate_name} 在**项目深挖**类问题上的面试表现。

## 岗位信息
- 岗位名称：{position_name}
- 技术要求：{tech_requirements or '未明确'}

## 项目类题目的考察意图
{json.dumps(project_intents, ensure_ascii=False) if project_intents else '无明确出题计划'}

## 本轮面试全部对话
{dialogs}

## 评估要求
请只关注与项目经验相关的问答，评估以下维度：

1. **项目真实性（1-10）**：候选人是否真正参与了项目，细节是否一致
2. **技术深度（1-10）**：对项目技术细节的理解深度
3. **决策能力（1-10）**：技术选型和问题解决中的思考过程
4. **成果表达（1-10）**：能否清晰描述自己的贡献和项目成果

## 输出格式（严格 JSON）
{{
    "dimensions": {{
        "项目真实性": 7,
        "技术深度": 6,
        "决策能力": 5,
        "成果表达": 7
    }},
    "strengths": [
        {{"point": "优势描述", "evidence": "面试中的具体回答证据"}}
    ],
    "weaknesses": [
        {{"point": "不足描述", "evidence": "面试中的具体表现", "suggestion": "改进建议"}}
    ],
    "authenticity_check": "对项目经验真实性的判断（细节一致性、回答深度等）",
    "overall_comment": "项目维度的综合评价（2-3句话）",
    "score": 65
}}"""
        return self.think_json(prompt)
