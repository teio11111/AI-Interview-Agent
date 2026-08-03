"""项目深挖出题官 Agent - 专注设计项目经历深挖题"""
from agents.base_agent import BaseAgent
from utils.text_truncate import truncate_for_prompt


class ProjectQuestionerAgent(BaseAgent):
    """项目深挖出题官
    
    职责：从候选人简历中提取具体项目，设计深挖问题。
    并行工作：与技能验证出题官、短板探测出题官同时工作。
    输出：3道项目深挖题（每道引用简历原文）。
    """
    AGENT_NAME = "项目深挖出题官"
    SYSTEM_PROMPT = """你是「项目深挖出题官」，专精于从候选人项目经历中设计深度追问。

你的出题哲学：
- 绝不问"介绍一下这个项目"这种表面题
- 聚焦候选人"做了什么"而非"知道什么"
- 每个问题必须追溯到简历中的具体项目
- 通过追问细节验证候选人是否真正参与了项目
- **问题要精简**：一道题最多聚焦 2 个功能点/技术点/决策点，不要大而泛
- **必须给出回答方向**：每道题附 2-4 个关键词/回答方向，便于面试官/候选人把握要点

工作原则：
- 严格引用简历原文（resume_reference），不能凭空出题
- **绝对禁止编造简历中没有的项目、场景、技术或经历。每道题的项目名称和技术细节必须能在简历原文中找到对应内容**
- 问题要探测：具体负责内容、技术挑战、选型原因、改进思路
- 问题有梯度：从验证基础到探测深度
- 每道题预设追问方向
- 每道题必须包含 answer_directions 字段（2-4 个回答关键词/方向）
- **【硬约束】题目涉及的技术必须与岗位技术要求（tech_requirements）匹配。如果岗位要求前端（Vue/React/HTML/CSS/JS/TS 等），则绝对不能出 Java/Spring/JVM/后端框架等与岗位无关的技术题。候选人简历中提到的其他技术栈不能作为出题依据。**

请始终以严格的 JSON 格式输出，不要输出任何解释性文字。"""

    def design(self, position_name, tech_requirements,
               position_analysis, resume_analysis, resume_text):
        """设计项目深挖题

        Args:
            position_name: 岗位名称
            tech_requirements: 技术要求
            position_analysis: 岗位分析结果
            resume_analysis: 简历评估结果
            resume_text: 候选人简历原文

        Returns:
            dict: 3道项目深挖题
        """
        pos_sum = truncate_for_prompt(self.summarize(position_analysis), max_chars=2500)
        resume_sum = truncate_for_prompt(self.summarize(resume_analysis), max_chars=2500)

        prompt = f"""## 任务
你是项目深挖出题官。请从候选人简历中提取 2-3 个最有价值的项目，
为每个项目设计 1 道深挖题（共 3 道题）。

## 精简原则（重要）
- 一道题最多聚焦 2 个功能点/技术点/决策点，避免大而泛
- 例：「Redis 在你项目中怎么用的？主要缓存了哪些数据？」比「介绍下你项目中的 Redis 使用」要好
- 不要把多个独立问题打包到一道题里

## 岗位信息
- 岗位名称：{position_name}
- 技术要求：{tech_requirements or ''}

## 岗位分析师的分析结果（摘要）
{pos_sum}

## 简历评估师的评估结果（摘要）
{resume_sum}

## 候选人简历原文
{resume_text or '暂无'}

## 深挖题设计策略

### 岗位技术栈约束（最高优先级）
- **只允许出与岗位技术要求直接相关的技术题**
- 岗位要求的技术栈是出题的唯一依据，候选人简历中提到的其他不相关技术不能作为出题内容
- 例如：前端岗位不能出 Java/Spring/JVM/后端微服务等后端题目；后端岗位不能出 React/Vue/CSS 等前端题目

针对每个项目，问以下角度中的 1 个（选最有价值的）：
1. **具体负责内容和技术挑战**：你在项目中具体负责哪部分？遇到的最大技术挑战是什么？
2. **技术选型原因和替代方案**：为什么选这个技术方案？考虑过哪些替代方案？
3. **改进思路和成果量化**：如果让你重做这个项目，有什么会改进？取得了什么量化成果？

## 选题标准
优先选择：
- 与目标岗位最相关的项目
- 简历描述最详细的项目（有深挖空间）
- 有可疑点需要验证的项目（描述模糊、数字夸大）

## 输出格式（严格 JSON，3道题）
{{
    "questions": [
        {{
            "question": "具体问题（必须引用简历中的项目名称和技术细节，单题最多2个功能点）",
            "category": "项目深挖",
            "difficulty": "easy/medium/hard",
            "resume_reference": "简历中对应的原文引用",
            "project_name": "对应的项目名称",
            "intent": "这道题想考察什么能力",
            "expected_depth": "候选人应该回答到什么程度算合格",
            "follow_up_hints": ["回答好可追问什么", "回答模糊应追问什么"],
            "probe_angle": "具体负责/技术选型/改进思路",
            "answer_directions": ["回答关键词/方向1", "回答关键词/方向2", "回答关键词/方向3", "回答关键词/方向4"]
        }}
    ]
}}"""
        return self.think_json(prompt)
