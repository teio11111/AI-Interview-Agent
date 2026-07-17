"""素质评估师 Agent - 专注评估沟通表达、学习能力、抗压等软技能"""
from agents.base_agent import BaseAgent
import json


class InterviewSoftEvaluatorAgent(BaseAgent):
    """素质评估师

    职责：专注评估候选人的软技能表现（沟通表达、学习能力、抗压能力等）。
    同时评估短板探测类问答中的态度表现。
    并行工作：与项目评估师、技术评估师同时工作。
    """
    AGENT_NAME = "素质评估师"
    SYSTEM_PROMPT = """你是「素质评估师」，专精于评估候选人的软技能和综合素质。

你的评估重点：
- 沟通表达：回答的逻辑性、清晰度、条理性
- 学习能力：对未知领域的态度、学习方法和速度
- 抗压能力：面对追问和难题时的表现
- 诚实度：对不会的问题是否坦诚，是否有夸大包装
- 主动性：是否展现自驱力和积极态度

工作原则：
- 从回答的方式和态度评估，而非回答的技术内容
- 追问环节最能反映真实素质（压力下的应变能力）
- 短板探测题的回答态度比答对答错更重要
- 注意区分"性格内向"和"沟通能力差"

请始终以严格的 JSON 格式输出，不要输出任何解释性文字。"""

    def evaluate(self, position_name, tech_requirements,
                 candidate_name, dialogs, questions_plan):
        """评估软技能表现

        Args:
            position_name: 岗位名称
            tech_requirements: 技术要求
            candidate_name: 候选人姓名
            dialogs: 本轮全部面试对话
            questions_plan: 出题策略（含每道题的 category 和 intent）

        Returns:
            dict: 素质维度评估结果
        """
        plan_questions = (questions_plan or {}).get('questions', [])
        soft_intents = [
            f"Q{i+1}: {q.get('intent','')}"
            for i, q in enumerate(plan_questions)
            if q.get('category') in ('短板探测', '场景设计')
        ]

        prompt = f"""## 任务
评估候选人 {candidate_name} 在面试中展现的**软技能和综合素质**。

## 岗位信息
- 岗位名称：{position_name}
- 技术要求：{tech_requirements or '未明确'}

## 相关题目的考察意图
{json.dumps(soft_intents, ensure_ascii=False) if soft_intents else '无明确出题计划'}

## 本轮面试全部对话
{dialogs}

## 评估要求
请关注回答方式和态度（而非技术内容），评估以下维度：

1. **沟通表达（1-10）**：回答的逻辑性、清晰度、条理性
2. **学习能力（1-10）**：对不会的问题的态度、学习方法展示
3. **抗压表现（1-10）**：被追问时的应变能力和情绪稳定性
4. **诚实坦度（1-10）**：对不熟悉的问题是否坦诚承认
5. **主动性（1-10）**：是否展现自驱力、积极思考

## 输出格式（严格 JSON）
{{
    "dimensions": {{
        "沟通表达": 7,
        "学习能力": 6,
        "抗压表现": 5,
        "诚实坦度": 7,
        "主动性": 6
    }},
    "strengths": [
        {{"point": "优势描述", "evidence": "面试中的具体表现证据"}}
    ],
    "weaknesses": [
        {{"point": "不足描述", "evidence": "面试中的具体表现", "suggestion": "改进建议"}}
    ],
    "follow_up_performance": "追问环节的整体表现评估（压力下的应变和态度）",
    "honesty_check": "对候选人诚实度的判断（是否有包装、夸大）",
    "overall_comment": "素质维度的综合评价（2-3句话）",
    "score": 65
}}"""
        return self.think_json(prompt)
