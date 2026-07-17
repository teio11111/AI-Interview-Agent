"""面试官 Agent - 专注面试对话评估与追问"""
from agents.base_agent import BaseAgent


class InterviewerAgent(BaseAgent):
    """面试官
    
    职责：评估候选人回答质量，生成反馈和追问建议。
    输出：多维评分 + 追问建议 + 红旗检测。
    """
    AGENT_NAME = "面试官"
    SYSTEM_PROMPT = """你是「面试官」，一位拥有 15 年经验的资深技术面试官。

你的面试风格：
- 通过项目场景切入提问，不使用背诵题
- 擅长层层追问，从候选人回答中挖掘真实水平
- 能识别"面经式回答"（背答案），通过追问细节验证
- 关注候选人"做了什么"而非"知道什么"

工作原则：
- 评分基于具体回答内容，不凭感觉
- 每个维度的评分有明确依据
- 追问必须基于候选人回答中的具体内容
- 红旗信号要具体描述，不要笼统

请始终以严格的 JSON 格式输出，不要输出任何解释性文字。"""

    def evaluate_answer(self, candidate_name, position_name, resume_text,
                        dialog_history, question, answer):
        """评估候选人回答

        Args:
            candidate_name: 候选人姓名
            position_name: 岗位名称
            resume_text: 简历原文（用于验证真实性）
            dialog_history: 历史对话文本
            question: 当前问题
            answer: 候选人回答

        Returns:
            dict: 反馈结果
        """
        prompt = f"""## 任务
你正在面试候选人 {candidate_name}，应聘 {position_name} 岗位。
请评估当前回答的质量，并生成精准的追问建议。

## 候选人简历（用于验证回答真实性）
{resume_text or '暂无'}

## 面试对话历史
{dialog_history or '（这是第一个问题）'}

## 当前问答
**面试官提问：** {question}
**候选人回答：** {answer}

## 评估维度
1. **准确性**：技术内容是否正确
2. **深度**：是否展示深入理解（vs 表面背诵）
3. **实践性**：是否有项目经验支撑（vs 纯理论/面经式）
4. **逻辑性**：回答是否条理清晰
5. **完整性**：是否遗漏关键要点

## 评分标准（1-10分）
- 9-10：准确深入，有具体项目案例和数据支撑
- 7-8：基本正确，有一定理解，缺少实践细节
- 5-6：部分正确，表面理解，像"面经"
- 3-4：回答模糊，有明显错误或知识盲区
- 1-2：答非所问或完全不了解

## 红旗信号检测
- 回答与简历描述不符
- 过于"教科书式"，无法结合自己项目
- 声称做过但说不出具体细节
- 自相矛盾的技术描述

## 追问策略
根据回答质量生成 2-3 个层层递进的追问：
- 7分以上：要求具体例子 → 边界场景 → 方案对比
- 5-6分：要求具体化 → 验证深度 → 换角度
- 4分以下：降低难度验证基础 → 换方向

## 输出格式（严格 JSON）
{{
    "evaluation": "2-3句话的专业评估",
    "score": 7,
    "score_breakdown": {{
        "accuracy": 7, "depth": 6, "practicality": 8, "logic": 7, "completeness": 6
    }},
    "follow_up_questions": [
        "追问1（基于回答中的具体内容）",
        "追问2（层层递进）",
        "追问3（验证深度或换角度）"
    ],
    "red_flags": ["风险点或空数组"],
    "answer_quality": "优秀/良好/一般/较差/差",
    "should_deep_dive": true,
    "deep_dive_reason": "建议/不建议深挖的原因"
}}"""
        return self.think_json(prompt)

    def generate_follow_up(self, resume_text, dialog_chain):
        """基于对话链生成连续追问

        Args:
            resume_text: 候选人简历原文
            dialog_chain: 当前问题的完整对话链

        Returns:
            dict: 追问结果
        """
        prompt = f"""## 任务
基于候选人在当前问题上的回答历史，生成 1 个精准的追问。
追问要像真人面试官一样自然。

## 候选人简历
{resume_text or '暂无'}

## 当前问题的完整对话链
{dialog_chain}

## 追问策略
1. 追问必须基于候选人**刚才回答中的具体内容**
2. 给出项目案例 → 追问技术细节（数据量、并发、踩过的坑）
3. 回答模糊 → 要求举真实例子
4. 说"了解但不深入" → 追问实际用的方案
5. 追问口吻要自然，像"好的，那你说的xxx，具体是怎么做的？"

## 输出格式（严格 JSON）
{{
    "follow_up_question": "自然的追问语句（口语化）",
    "target": "这个追问想验证什么",
    "expected_good_answer": "好的回答应该包含什么内容"
}}"""
        return self.think_json(prompt)
