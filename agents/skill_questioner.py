"""技能验证出题官 Agent - 专注设计技能验证场景题"""
from agents.base_agent import BaseAgent
from utils.text_truncate import truncate_for_prompt


class SkillQuestionerAgent(BaseAgent):
    """技能验证出题官
    
    职责：针对候选人声称掌握的核心技能，设计实操场景验证题。
    并行工作：与项目深挖出题官、短板探测出题官同时工作。
    输出：2道技能验证题（实操场景题，不问背诵题）。
    """
    AGENT_NAME = "技能验证出题官"
    SYSTEM_PROMPT = """你是「技能验证出题官」，专精于设计实操场景题来验证候选人的真实技术水平。

你的出题哲学：
- 绝不问"什么是xxx"这种背诵题
- 用真实工作场景切入："假设线上系统出现xxx问题，怎么排查？"
- 针对候选人"精通"的技能出 hard 题验证
- 关注"能不能做"而非"知不知道"
- **问题要精简**：一道题最多聚焦 2 个功能点/技术点/决策点，不要大而泛
- **必须给出回答方向**：每道题附 2-4 个关键词/回答方向，便于面试官/候选人把握要点

工作原则：
- 题目必须基于候选人简历中声称掌握的技能
- **绝对禁止编造简历中没有的项目、场景、技术或经历。每道题的技术点必须能在简历原文中找到对应内容**
- 场景要真实、具体、有约束条件
- 问题设计应能区分"背答案"和"真正理解"
- 每道题预设追问方向
- 每道题必须包含 answer_directions 字段（2-4 个回答关键词/方向）
- **【硬约束】题目涉及的技术必须与岗位技术要求（tech_requirements）匹配。如果岗位要求前端（Vue/React/HTML/CSS/JS/TS 等），则绝对不能出 Java/Spring/JVM/后端框架等与岗位无关的技术题。候选人简历中提到的其他技术栈不能作为出题依据。**

请始终以严格的 JSON 格式输出，不要输出任何解释性文字。"""

    def design(self, position_name, tech_requirements,
               position_analysis, resume_analysis, resume_text):
        """设计技能验证题

        Args:
            position_name: 岗位名称
            tech_requirements: 技术要求
            position_analysis: 岗位分析结果
            resume_analysis: 简历评估结果
            resume_text: 候选人简历原文

        Returns:
            dict: 2道技能验证题
        """
        pos_sum = truncate_for_prompt(self.summarize(position_analysis), max_chars=2500)
        resume_sum = truncate_for_prompt(self.summarize(resume_analysis), max_chars=2500)

        prompt = f"""## 任务
你是技能验证出题官。请针对候选人声称掌握的核心技能，设计 2 道**实操场景验证题**。

## 精简原则（重要）
- 一道题最多聚焦 2 个功能点/技术点，避免「请系统性地讲讲你对 X 的理解」这种大题
- 例：「Redis 的缓存淘汰策略怎么选？什么时候用 LRU vs LFU？」比「Redis 性能怎么优化」更聚焦

## 岗位信息
- 岗位名称：{position_name}
- 技术要求：{tech_requirements or ''}

## 岗位分析师的分析结果（摘要）
{pos_sum}

## 简历评估师的评估结果（摘要，重点关注 matched_skills）
{resume_sum}

## 候选人简历原文
{resume_text or '暂无'}

## 出题策略

### 岗位技术栈约束（最高优先级）
- **只允许出与岗位技术要求直接相关的技术题**
- 岗位要求的技术栈是出题的唯一依据，候选人简历中提到的其他不相关技术不能作为出题内容
- 例如：前端岗位不能出 Java/Spring/JVM/后端微服务等后端题目；后端岗位不能出 React/Vue/CSS 等前端题目

### 选题原则
- 选候选人声称"精通"或"熟练"的核心技能
- 优先选岗位最需要的技能
- 2道题覆盖不同技能

### 场景设计要求
每道题必须是一个**真实工作场景**，包含：
- 具体背景（"你负责的系统..."）
- 具体问题（"出现了xxx情况"）
- 约束条件（"需要在xxx时间内解决"）

### 题目类型示例
- 排查题："线上服务突然响应变慢，你会怎么排查？"
- 设计题："需要设计一个xxx功能，请说说你的方案"
- 对比题："你用过A和B，什么场景下选A不选B？"
- 边界题："在xxx极端情况下，你的方案会有什么问题？"

## 输出格式（严格 JSON，2道题）
{{
    "questions": [
        {{
            "question": "具体场景题（必须有背景、问题、约束，单题最多2个技术点）",
            "category": "技能验证",
            "difficulty": "medium/hard",
            "resume_reference": "简历中声称掌握该技能的原文",
            "target_skill": "要验证的技能名称",
            "intent": "这道题想验证什么能力",
            "expected_depth": "好的回答应该包含什么",
            "follow_up_hints": ["回答好可追问什么", "回答模糊应追问什么"],
            "red_flag_answers": ["什么样的回答说明其实不会"],
            "answer_directions": ["回答关键词/方向1", "回答关键词/方向2", "回答关键词/方向3", "回答关键词/方向4"]
        }}
    ]
}}"""
        return self.think_json(prompt)
