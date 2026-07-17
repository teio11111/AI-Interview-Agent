"""评价官 Agent - 专注综合评价报告生成"""
from agents.base_agent import BaseAgent


class EvaluatorAgent(BaseAgent):
    """评价官
    
    职责：基于全部面试对话，生成专业综合评价报告。
    输出：综合评分 + 维度评分 + 优势/不足 + 招聘建议。
    """
    AGENT_NAME = "评价官"
    SYSTEM_PROMPT = """你是「评价官」，一位资深的技术招聘决策者。

你的核心能力：
- 综合多轮面试表现（含追问环节），给出客观全面的最终评价
- 从面试对话中提取关键证据（evidence），支撑每个评分判断
- 区分候选人的"真实能力"和"面试表现"
- 给出明确、有依据的招聘建议

工作原则：
- 每个维度的评分都有面试中的具体表现作为支撑
- 优势和不足必须引用面试中的具体回答
- 招聘建议要明确（强烈推荐/推荐/待定/不推荐），不含糊
- 追问表现单独评估：候选人能否经受住追问

请始终以严格的 JSON 格式输出，不要输出任何解释性文字。"""

    def generate_report(self, position_name, tech_requirements, 
                        candidate_name, full_dialogs, resume_analysis=None):
        """生成综合评价报告

        Args:
            position_name: 岗位名称
            tech_requirements: 技术要求
            candidate_name: 候选人姓名
            full_dialogs: 全部面试对话文本（含追问标记）
            resume_analysis: 简历评估结果（可选，用于交叉验证）

        Returns:
            dict: 评价报告
        """
        resume_context = ""
        if resume_analysis:
            resume_context = f"""
## 简历评估师的评估（供交叉参考）
{self.summarize(resume_analysis)}
"""

        prompt = f"""## 任务
面试已结束，请为候选人 {candidate_name} 生成专业、全面的综合评价报告。

## 岗位要求
- 岗位名称：{position_name}
- 技术要求：{tech_requirements or ''}
{resume_context}
## 全部面试对话（含追问，[追问自Q#] 标记的为追问环节）
{full_dialogs}

## 评估要求

1. **综合评分（0-100）**：基于所有对话（含追问）的整体表现
2. **维度评分（每项 1-10）**：
   - 技术基础：核心技术的掌握程度
   - 项目经验：实际项目中的应用能力和深度
   - 系统设计：架构思维和方案设计能力
   - 沟通表达：回答的逻辑性和清晰度
   - 学习能力：对新知识的态度和理解速度
3. **追问表现评估**：候选人在被追问时的表现
4. **招聘建议**：基于匹配度和面试表现给出明确建议

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
    "summary": "3-4句话综合评价，包含候选人画像和最终结论",
    "interview_highlights": {{
        "best_answer": "回答最好的问题方向",
        "worst_answer": "表现最差的问题方向",
        "best_follow_up": "追问环节表现最好的部分",
        "weakest_follow_up": "追问环节暴露最多问题的部分"
    }},
    "candidate_summary": "面向候选人本人的反馈（3-5句话，温和、建设性语气，开头用“{candidate_name}您好”称呼）：先肯定面试中展现的优点和亮点，再指出可以进一步提升的方向，最后给出具体可操作的努力建议。不要用“不推荐”“包装”“风险”等内部决策用语，要像一位良师益友给候选人写成长建议。"
}}"""
        return self.think_json(prompt)
