"""岗位分析师 Agent - 专注岗位 JD 解析"""
from agents.base_agent import BaseAgent


class PositionAnalystAgent(BaseAgent):
    """岗位分析师
    
    职责：深入分析技术岗位 JD，提取核心能力要求，制定面试考察策略，
    并解析岗位的隐性需求和理想候选人画像。
    输出：结构化岗位分析报告（核心技能 + 隐性需求 + 团队画像 + 考察策略）。
    """
    AGENT_NAME = "岗位分析师"
    SYSTEM_PROMPT = """你是「岗位分析师」，一位拥有 15 年经验的资深技术招聘专家。

你的核心能力：
- 从 JD 文本中精准提取技术能力矩阵（必须/重要/加分三级分类）
- 深入解读岗位的**真实需求**（JD写的不等于真正要的）
- 判断岗位的经验层级和年限要求
- 解析岗位对候选人软性条件的隐性要求（抗压、管理潜力、文化匹配）
- 为后续面试设计考察策略（考察方向 + 权重 + 难度分布）

工作原则：
- 客观分析 JD 要求，不过度推断
- 核心技能不超过 8 个，聚焦真正重要的
- 考察方向必须可操作（面试官能据此出题）
- 隐性需求分析必须给出推断依据

请始终以严格的 JSON 格式输出，不要输出任何解释性文字。"""

    def analyze(self, position_name, tech_requirements, jd_content):
        """分析岗位 JD

        Args:
            position_name: 岗位名称
            tech_requirements: 技术要求关键词
            jd_content: JD 全文

        Returns:
            dict: 岗位分析结果
        """
        prompt = f"""## 任务
深入分析以下技术岗位 JD，提取核心能力要求、解读岗位真实需求，并制定面试考察策略。

## 输入信息
**岗位名称：** {position_name}
**技术要求（关键词）：** {tech_requirements or '暂无'}
**JD 全文：**
{jd_content or '暂无详细JD'}

## 分析要求

### 一、专业技能矩阵（核心）
1. **核心技能**：5-8 个，按重要性排序（必须/重要/加分）
2. **经验级别**：初级(0-2年)/中级(3-5年)/高级(5年+)
3. **面试重点**：4-6 个考察方向，每个有权重百分比
4. **考察主题**：5-8 个具体技术主题
5. **难度分布**：easy/medium/hard 的百分比

### 二、岗位真实需求解读（重要）
JD写的和实际要的不一定一样。请解读：
1. **岗位本质需求**：这个岗位真正要解决的核心问题是什么？
2. **团队文化画像**：从JD用词推断团队风格（快节奏/稳定/创业型/大厂规范）
3. **成长路径**：岗位提供的职业发展空间
4. **理想候选人画像**：综合所有分析，这个岗位最想要什么样的人

### 三、隐性条件需求（新增）
从 JD 推断岗位对候选人以下隐性条件的要求：
1. **抗压能力需求**：高强度/中等/轻松（从“加班”“快节奏”“deadline”等词推断）
2. **管理能力潜力**：是否需要带人/纯IC（从“带领”“团队”“指导”推断）
3. **沟通复杂度**：跨部门多/纯技术沟通/面向客户
4. **稳定性要求**：是否期望长期稳定（从“长期”“深耕”推断）
5. **学历偏好**：是否有隐性学历偏好（从“985/211优先”“优秀学历”推断）

## 输出格式（严格 JSON）
{{
    "core_skills": [
        {{"skill": "技能名", "importance": "必须/重要/加分", "reason": "为什么重要"}}
    ],
    "experience_level": "初级/中级/高级",
    "experience_years": "建议最低年限",
    "interview_focus": [
        {{"topic": "考察方向", "weight": 30, "description": "该方向应考察什么能力"}}
    ],
    "recommended_topics": ["主题1", "主题2"],
    "soft_skills": ["软技能1", "软技能2"],
    "difficulty_distribution": {{"easy": 20, "medium": 50, "hard": 30}},
    "position_insights": {{
        "real_need": "岗位本质需求（这个岗位真正要解决什么问题）",
        "team_culture": "团队文化画像（快节奏/稳定/创业型/大厂规范）",
        "culture_detail": "推断依据",
        "growth_path": "岗位提供的职业发展空间",
        "ideal_candidate": "理想候选人画像（综合描述）"
    }},
    "implicit_requirements": {{
        "stress_tolerance": {{
            "level": "高/中/低",
            "detail": "推断依据"
        }},
        "management_potential": {{
            "needed": true/false,
            "detail": "是否需要带人，纯IC还是管理路线"
        }},
        "communication_complexity": {{
            "level": "高/中/低",
            "detail": "跨部门协作程度"
        }},
        "stability_expectation": {{
            "level": "高/中/低",
            "detail": "是否期望候选人长期稳定"
        }},
        "education_preference": {{
            "explicit": "JD中明确的学历要求",
            "implicit": "隐性学历偏好",
            "detail": "推断依据"
        }}
    }},
    "summary": "2-3句话总结该岗位的核心画像"
}}"""
        return self.think_json(prompt)
