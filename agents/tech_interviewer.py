"""技术顾问 Agent - 专注面试回答的技术准确性与深度评估"""
from agents.base_agent import BaseAgent


class TechInterviewerAgent(BaseAgent):
    """技术顾问
    
    职责：专注评估候选人面试回答的技术准确性、深度和实践性。
    并行工作：与综合顾问同时工作，两者结果提交给主面试官。
    输出：技术维度评分 + 技术追问建议 + 红旗信号。
    """
    AGENT_NAME = "技术顾问"
    SYSTEM_PROMPT = """你是「技术顾问」，一位拥有 20 年经验的资深技术专家。

你的核心职责：
- 评估候选人回答的技术准确性（是否正确）
- 评估技术深度（是否展示了深入理解 vs 表面背诵）
- 评估实践性（是否有真实项目经验支撑 vs 面经式回答）
- 识别技术层面的红旗信号

工作原则：
- 只评估技术维度，不评估沟通表达等软性因素
- 技术评分必须有具体依据
- 识别"面经式回答"：背答案但无真实理解
- 追问建议要技术层面递进

请始终以严格的 JSON 格式输出，不要输出任何解释性文字。"""

    def evaluate(self, candidate_name, position_name, resume_text,
                 dialog_history, question, answer):
        """评估候选人回答的技术维度

        Args:
            candidate_name: 候选人姓名
            position_name: 岗位名称
            resume_text: 简历原文
            dialog_history: 历史对话文本
            question: 当前问题
            answer: 候选人回答

        Returns:
            dict: 技术维度评估结果
        """
        prompt = f"""## 任务
你是技术顾问，请**只从技术维度**评估候选人 {candidate_name} 的回答。
专注评估技术准确性、深度和实践性，不评估沟通表达等软性因素。

## 岗位
{position_name}

## 候选人简历（用于验证回答真实性）
{resume_text or '暂无'}

## 面试对话历史
{dialog_history or '（这是第一个问题）'}

## 当前问答
**面试官提问：** {question}
**候选人回答：** {answer}

## 技术评估维度

### 1. 准确性（1-10）
- 技术内容是否正确
- 是否有事实性错误
- 对关键概念的理解是否准确

### 2. 深度（1-10）
- 是否展示深入理解（vs 表面背诵）
- 能否解释底层原理
- 是否了解技术的局限和适用场景

### 3. 实践性（1-10）
- 是否有真实项目经验支撑
- 能否结合自己的项目举例
- 是否了解实际工程中的坑和注意事项

### 4. 技术红旗
- 回答与简历描述不符
- 声称精通但回答很浅
- 技术描述自相矛盾
- 过于"教科书式"无自己思考

## 输出格式（严格 JSON）
{{
    "tech_score": 7,
    "score_breakdown": {{
        "accuracy": 7,
        "depth": 6,
        "practicality": 8
    }},
    "tech_evaluation": "2-3句话的技术维度评估",
    "tech_follow_ups": [
        "技术追问1（基于回答中的具体技术点深入）",
        "技术追问2（验证是否真理解 vs 背答案）"
    ],
    "tech_red_flags": ["技术层面的风险点"],
    "is_tech_solid": true,
    "tech_detail": "判断依据"
}}"""
        return self.think_json(prompt)
