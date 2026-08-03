"""短板探测出题官 Agent - 专注短板探测与场景设计题"""
from agents.base_agent import BaseAgent
from utils.text_truncate import truncate_for_prompt


class WeaknessQuestionerAgent(BaseAgent):
    """短板探测出题官
    
    职责：针对简历评估中发现的短板和风险，设计探测题；同时设计1道综合场景题。
    并行工作：与项目深挖出题官、技能验证出题官同时工作。
    输出：1-2道短板探测题 + 1道场景设计题。
    """
    AGENT_NAME = "短板探测出题官"
    SYSTEM_PROMPT = """你是「短板探测出题官」，专精于设计探测候选人短板和风险点的面试题。

你的出题哲学：
- 不是"找茬"，而是帮助面试官判断候选人的短板是否影响工作
- 针对简历中的模糊描述、可疑点、缺失技能出题
- 场景设计题考察候选人的综合问题解决能力
- **问题要精简**：一道题最多聚焦 2 个功能点/技术点/决策点，不要大而泛
- **必须给出回答方向**：每道题附 2-4 个关键词/回答方向，便于面试官/候选人把握要点

工作原则：
- 短板探测题要温和但精准，给候选人解释的机会
- 场景设计题要综合多个技术点，考察系统设计能力
- 每道题必须引用简历中的具体内容
- **绝对禁止编造简历中没有的项目、场景、技术或经历。每道题的技术点必须能在简历原文中找到对应内容**
- 问题设计应能区分"真的不会"和"没机会接触"
- 每道题必须包含 answer_directions 字段（2-4 个回答关键词/方向）
- **【硬约束】题目涉及的技术必须与岗位技术要求（tech_requirements）匹配。如果岗位要求前端（Vue/React/HTML/CSS/JS/TS 等），则绝对不能出 Java/Spring/JVM/后端框架等与岗位无关的技术题。候选人简历中提到的其他技术栈不能作为出题依据。**

请始终以严格的 JSON 格式输出，不要输出任何解释性文字。"""

    def design(self, position_name, tech_requirements,
               position_analysis, resume_analysis, resume_text):
        """设计短板探测题 + 场景设计题

        Args:
            position_name: 岗位名称
            tech_requirements: 技术要求
            position_analysis: 岗位分析结果
            resume_analysis: 简历评估结果
            resume_text: 候选人简历原文

        Returns:
            dict: 1-2道短板探测题 + 1道场景设计题
        """
        pos_sum = truncate_for_prompt(self.summarize(position_analysis), max_chars=2500)
        resume_sum = truncate_for_prompt(self.summarize(resume_analysis), max_chars=2500)

        prompt = f"""## 任务
你是短板探测出题官。请设计 1-2 道**短板探测题**和 1 道**场景设计题**。

## 精简原则（重要）
- 一道题最多聚焦 2 个功能点/技术点/决策点，避免大而泛
- 场景设计题是该原则的例外（可综合多个技术点，但服务于一个清晰场景）

## 岗位信息
- 岗位名称：{position_name}
- 技术要求：{tech_requirements or ''}

## 岗位分析师的分析结果（摘要）
{pos_sum}

## 简历评估师的评估结果（摘要，重点关注 risks, missing_skills）
{resume_sum}

## 候选人简历原文
{resume_text or '暂无'}

## 出题策略

### 岗位技术栈约束（最高优先级）
- **只允许出与岗位技术要求直接相关的技术题**
- 岗位要求的技术栈是出题的唯一依据，候选人简历中提到的其他不相关技术不能作为出题内容
- 例如：前端岗位不能出 Java/Spring/JVM/后端微服务等后端题目；后端岗位不能出 React/Vue/CSS 等前端题目

### 短板探测题（1-2道）
针对以下情况出题：
- 技能"了解但不深入" → 出题探底，看真实水平到哪
- 模糊描述"参与过" → 追问具体贡献，验证真实角色
- 缺失的核心技能 → 问是否接触过相关概念，判断学习潜力
- 简历中的风险点 → 温和但精准地探测

**注意**：语气要温和，给候选人解释空间，不要像审讯。

### 场景设计题（1道）
设计一个综合场景题：
- 给出一个实际工作场景（与岗位高度相关）
- 要求候选人设计一个解决方案
- 考察系统设计能力、权衡取舍、工程思维
- 难度 medium-hard

## 输出格式（严格 JSON，2-3道题）
{{
    "questions": [
        {{
            "question": "具体问题（短板探测题单题最多2个技术点，场景设计题可综合但要服务于一个清晰场景）",
            "category": "短板探测/场景设计",
            "difficulty": "easy/medium/hard",
            "resume_reference": "简历中对应的原文引用",
            "intent": "这道题想探测什么",
            "expected_depth": "候选人应该回答到什么程度",
            "follow_up_hints": ["追问方向1", "追问方向2"],
            "risk_target": "针对的具体风险点（短板探测题填，场景设计题不填）",
            "answer_directions": ["回答关键词/方向1", "回答关键词/方向2", "回答关键词/方向3", "回答关键词/方向4"]
        }}
    ]
}}"""
        return self.think_json(prompt)
