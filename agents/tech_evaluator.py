"""技术评估师 Agent - 专注技术技能匹配度评估"""
from agents.base_agent import BaseAgent


class TechEvaluatorAgent(BaseAgent):
    """技术评估师
    
    职责：专注评估候选人技术能力与岗位要求的匹配度。
    并行工作：与综合素质评估师、隐性因素评估师同时工作。
    输出：技能匹配/缺失 + 技术深度评分 + 技术风险。
    """
    AGENT_NAME = "技术评估师"
    SYSTEM_PROMPT = """你是「技术评估师」，一位拥有 15 年经验的资深技术简历审核专家。

你的核心专长：
- 精准评估候选人技术栈与岗位要求的匹配度
- 判断技术经验的深度（理论了解 vs 实际项目应用 vs 精通）
- 识别技术栈版本是否过时、技能是否停留在表面
- 从简历中判断真实技术水平（区分"用过"和"精通"）

工作原则：
- 只关注技术能力，不评估软技能或隐性条件
- 每个判断必须有简历原文作为证据（evidence）
- 区分"声称掌握"和"证据支撑"的技能
- 评分严格客观，不偏高也不偏低

请始终以严格的 JSON 格式输出，不要输出任何解释性文字。"""

    def evaluate(self, position_name, tech_requirements, jd_content, resume_text,
                 position_analysis=None, candidate_name=''):
        """评估候选人技术能力匹配度

        Args:
            position_name: 岗位名称
            tech_requirements: 技术要求关键词
            jd_content: JD 全文
            resume_text: 候选人简历原文
            position_analysis: 岗位分析师的分析结果（用于了解核心技术要求）
            candidate_name: 候选人姓名

        Returns:
            dict: 技术评估结果
        """
        import json
        pos_skills = ''
        if position_analysis and isinstance(position_analysis, dict):
            cs = position_analysis.get('core_skills', [])
            if cs:
                pos_skills = json.dumps(cs, ensure_ascii=False, indent=2)

        prompt = f"""## 任务
你是技术评估师，请**只从技术能力角度**评估候选人简历与岗位的匹配度。
不要评估沟通能力、团队协作、学历背景等非技术因素。

## 候选人姓名
{candidate_name or '候选人'}

## 岗位要求
**岗位名称：** {position_name}
**技术要求：** {tech_requirements or '暂无'}
**JD 全文：**
{jd_content or '暂无详细JD'}

## 岗位核心技能要求（岗位分析师已提取）
{pos_skills or '岗位尚未分析，请根据JD自行判断'}

## 候选人简历
{resume_text or '暂无'}

## 评估要求

### 1. 技能匹配分析
逐项对照岗位核心技能与简历中的技术经验：
- 匹配的技能：标注熟练度（精通/熟练/了解/基础）和简历证据
- 缺失的技能：标注重要程度（核心/重要/次要）和缺失影响

### 2. 技术深度评分（0-100）
- 90-100：核心技术全部精通，有深度项目经验
- 75-89：核心技术基本熟练，个别技能欠缺
- 60-74：基础能力具备但有明显短板
- 40-59：多项核心技能缺失或停留在理论
- 0-39：技术要求与经验差距较大

### 3. 技术风险识别
- 经验深度不足（项目太简单或太短）
- 技能停留在理论（无实际项目应用）
- 简历夸大嫌疑（"精通"但无细节支撑）
- 技术栈版本过时
- 经验广度不足（只涉及单一领域）

## 输出格式（严格 JSON）
{{
    "tech_depth_score": 72,
    "matched_skills": [
        {{"skill": "技能名", "proficiency": "精通/熟练/了解/基础", "evidence": "简历中对应证据", "years": "经验年限"}}
    ],
    "missing_skills": [
        {{"skill": "缺失技能", "importance": "核心/重要/次要", "impact": "缺失的影响"}}
    ],
    "tech_risks": [
        {{"risk": "风险描述", "severity": "高/中/低", "detail": "具体说明", "evidence": "简历中的证据"}}
    ],
    "experience_assessment": {{
        "total_years": "估算总工作年限",
        "relevant_years": "与岗位相关的经验年限",
        "level": "初级/中级/高级/资深",
        "detail": "经验年限评估依据"
    }},
    "tech_highlights": [
        {{"point": "技术亮点", "evidence": "简历证据"}}
    ],
    "tech_summary": "2-3句话的技术能力总结评估"
}}"""
        return self.think_json(prompt)
