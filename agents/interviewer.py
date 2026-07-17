"""主面试官 Agent - 综合顾问意见后做最终评估与追问决策"""
from agents.base_agent import BaseAgent


class InterviewerAgent(BaseAgent):
    """主面试官
    
    职责：接收技术顾问和综合顾问的评估意见，综合做出最终评分和追问决策。
    这是面试阶段的"裁判"角色，两位顾问并行评估后提交给主面试官。
    输出：最终综合评分 + 追问决策 + 红旗检测（兼容旧格式）。
    """
    AGENT_NAME = "主面试官"
    SYSTEM_PROMPT = """你是「主面试官」，一位拥有 20 年经验的资深技术面试官和招聘决策者。

你的核心职责：
- 接收技术顾问（专注技术准确性/深度）和综合顾问（专注沟通/逻辑/学习态度）的独立评估
- 综合两位顾问意见，做出**最终统一**的评分和判断
- 当两位顾问意见冲突时，给出你的最终裁决
- 决定是否需要追问，以及追问什么方向
- 识别跨维度的红旗信号

工作原则：
- 技术能力权重 60%，综合素质权重 40%
- 每个维度的评分必须有具体依据
- 追问决策要精准：技术弱就技术追问，表达弱就沟通追问
- 红旗信号要具体描述，不要笼统

请始终以严格的 JSON 格式输出，不要输出任何解释性文字。"""

    def evaluate_answer(self, candidate_name, position_name, resume_text,
                        dialog_history, question, answer,
                        tech_consultation=None, soft_consultation=None):
        """综合顾问意见后评估候选人回答

        Args:
            candidate_name: 候选人姓名
            position_name: 岗位名称
            resume_text: 简历原文
            dialog_history: 历史对话文本
            question: 当前问题
            answer: 候选人回答
            tech_consultation: 技术顾问的评估结果
            soft_consultation: 综合顾问的评估结果

        Returns:
            dict: 最终评估结果（兼容旧格式）
        """
        import json

        # 如果有顾问意见，使用新版 prompt
        if tech_consultation or soft_consultation:
            return self._evaluate_with_consultants(
                candidate_name, position_name, resume_text,
                dialog_history, question, answer,
                tech_consultation, soft_consultation
            )
        # 降级：无顾问意见时，独立评估（兼容旧调用方式）
        return self._evaluate_standalone(
            candidate_name, position_name, resume_text,
            dialog_history, question, answer
        )

    def _evaluate_with_consultants(self, candidate_name, position_name, resume_text,
                                   dialog_history, question, answer,
                                   tech_consultation, soft_consultation):
        """有顾问意见时的综合评估"""
        import json

        prompt = f"""## 任务
你是主面试官。技术顾问和综合顾问已分别独立评估了候选人的回答，
请综合两位顾问的意见，做出最终评分和追问决策。

## 候选人 {candidate_name} — 岗位 {position_name}

## 当前问答
**面试官提问：** {question}
**候选人回答：** {answer}

## 技术顾问的评估（专注技术准确性/深度/实践性）
{json.dumps(tech_consultation or {}, ensure_ascii=False, indent=2)}

## 综合顾问的评估（专注沟通表达/逻辑/学习态度）
{json.dumps(soft_consultation or {}, ensure_ascii=False, indent=2)}

## 你的职责

### 1. 综合评分（1-10）
- 技术维度权重 60%（技术顾问的 tech_score）
- 综合维度权重 40%（综合顾问的 soft_score）
- 当两位顾问意见冲突时，给出你的判断

### 2. 五维评分（每项 1-10）
- 准确性：来自技术顾问
- 深度：来自技术顾问
- 实践性：来自技术顾问
- 逻辑性：来自综合顾问
- 完整性：来自综合顾问

### 3. 追问决策
综合两位顾问的追问建议，选出最有价值的 2-3 个追问：
- 优先追问两位顾问都标记为弱项的维度
- 如果技术顾问建议深挖且技术分<7，优先技术追问
- 如果综合顾问标记了风险信号，优先排查

### 4. 红旗检测
综合两位顾问的 red_flags，加上你自己的判断

## 输出格式（严格 JSON）
{{
    "evaluation": "2-3句话的综合评估",
    "score": 7,
    "score_breakdown": {{
        "accuracy": 7, "depth": 6, "practicality": 8, "logic": 7, "completeness": 6
    }},
    "follow_up_questions": [
        "追问1（基于回答中的具体内容）",
        "追问2（层层递进）",
        "追问3（验证深度或换角度）"
    ],
    "red_flags": ["综合两位顾问的风险点"],
    "answer_quality": "优秀/良好/一般/较差/差",
    "should_deep_dive": true,
    "deep_dive_reason": "建议/不建议深挖的原因",
    "consultant_agreement": "两位顾问是否一致，分歧点是什么",
    "score_tech": 7,
    "score_soft": 7
}}"""
        return self.think_json(prompt)

    def _evaluate_standalone(self, candidate_name, position_name, resume_text,
                             dialog_history, question, answer):
        """无顾问意见时的独立评估（兼容旧调用方式）"""
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
    "follow_up_question": "自然的追问句（口语化）",
    "target": "这个追问想验证什么",
    "expected_good_answer": "好的回答应该包含什么内容"
}}"""
        return self.think_json(prompt)
