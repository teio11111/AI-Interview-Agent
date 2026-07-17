"""面试评估师 Agent - 纯粹评估本轮面试问答表现"""
from agents.base_agent import BaseAgent


class EvaluatorAgent(BaseAgent):
    """面试评估师
    
    职责：纯粹基于本轮面试对话记录，评估候选人的面试表现。
    不掺入简历评估、岗位分析等外部数据，保证评估独立性。
    （综合评价功能将作为独立入口，汇总简历+多轮面试结果）
    """
    AGENT_NAME = "面试评估师"
    SYSTEM_PROMPT = """你是「面试评估师」，一位资深技术面试官。

你的核心能力：
- 基于面试对话记录，客观评估候选人的实际表现
- 从回答中提取关键证据（evidence），支撑每个评分判断
- 区分“背诵式回答”和“真正理解”
- 识别追问环节中的真实水平暴露
- 给出明确、有依据的评分和建议

工作原则：
- 只基于面试中的实际回答来评估，不做简历背景推断
- 每个维度的评分都有面试中的具体表现作为支撑
- 优势和不足必须引用面试中的具体回答
- 追问表现单独评估（追问更能反映真实水平）
- 评分客观，不偏高也不偏低

请始终以严格的 JSON 格式输出，不要输出任何解释性文字。"""

    def generate_report(self, position_name, tech_requirements,
                        candidate_name, full_dialogs):
        """生成本轮面试评估报告

        Args:
            position_name: 岗位名称
            tech_requirements: 技术要求
            candidate_name: 候选人姓名
            full_dialogs: 全部面试对话文本（含追问标记）

        Returns:
            dict: 面试评估报告
        """
        prompt = f"""## 任务
本轮面试已结束，请为候选人 {candidate_name} 生成**本轮面试表现**的专业评估报告。
注意：仅评估本轮面试中的实际回答表现，不参考简历或其他轮次信息。

## 岗位信息
- 岗位名称：{position_name}
- 技术要求：{tech_requirements or '未明确'}

## 本轮面试全部对话（含追问，[追问自Q#] 标记的为追问环节）
{full_dialogs}

## 评估要求

1. **综合评分（0-100）**：基于本轮所有问答的整体表现
2. **维度评分（每项 1-10）**：
   - 技术基础：核心技术的掌握程度
   - 项目经验：实际项目中的应用能力和深度
   - 系统设计：架构思维和方案设计能力
   - 沟通表达：回答的逻辑性和清晰度
   - 学习能力：对新知识的态度和理解速度
3. **追问表现评估**：候选人在被追问时的表现（追问更能反映真实水平）
4. **面试建议**：基于本轮表现给出明确建议

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
    "follow_up_performance": "候选人在追问环节的表现评估",
    "recommendation": "强烈推荐/推荐/待定/不推荐",
    "recommendation_reason": "1句话说明核心理由",
    "summary": "3-4句话综合评价，概括本轮面试表现和最终结论",
    "interview_highlights": {{
        "best_answer": "回答最好的问题方向",
        "worst_answer": "表现最差的问题方向",
        "best_follow_up": "追问环节表现最好的部分",
        "weakest_follow_up": "追问环节暴露最多问题的部分"
    }},
    "candidate_summary": "面向候选人本人的反馈（3-5句话，温和、建设性语气，开头用\"{candidate_name}您好\"称呼）：先肯定面试中展现的优点和亮点，再指出可以进一步提升的方向，最后给出具体可操作的努力建议。不要用\"不推荐\"\"包装\"\"风险\"等内部决策用语，要像一位良师益友给候选人写成长建议。"
}}"""
        return self.think_json(prompt)
