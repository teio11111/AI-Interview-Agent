"""综合素质评估师 Agent - 专注软技能与综合素质评估"""
from agents.base_agent import BaseAgent
from utils.text_truncate import truncate_for_prompt, clean_resume_text


class SoftEvaluatorAgent(BaseAgent):
    """综合素质评估师
    
    职责：专注评估候选人的软技能与综合素质。
    并行工作：与技术评估师、隐性因素评估师同时工作。
    输出：沟通能力 + 团队协作 + 学习能力 + 领导力 + 综合素质评分。
    """
    AGENT_NAME = "综合素质评估师"
    SYSTEM_PROMPT = """你是「综合素质评估师」，一位拥有丰富人才评估经验的组织行为学专家。

你的核心专长：
- 从简历文本中推断候选人的沟通表达能力（写作结构、用词精准度）
- 评估团队协作风格（独立型/协作型/领导型）
- 判断学习能力（技术栈更新频率、跨领域经历）
- 识别领导力潜力（团队管理、项目主导、技术布道）
- 评估主动性和成长潜力

工作原则：
- 只关注软技能和综合素质，不评估技术能力
- 每个判断必须有简历中的证据支撑
- 从简历写作风格本身推断沟通能力（结构清晰、逻辑性、措辞专业度）
- 推断必须标注置信度（high/medium/low），无依据时不要硬凑

请始终以严格的 JSON 格式输出，不要输出任何解释性文字。"""

    def evaluate(self, position_name, tech_requirements, jd_content, resume_text,
                 position_analysis=None, candidate_name=''):
        """评估候选人综合素质

        Args:
            position_name: 岗位名称
            tech_requirements: 技术要求关键词
            jd_content: JD 全文
            resume_text: 候选人简历原文
            position_analysis: 岗位分析师的分析结果
            candidate_name: 候选人姓名

        Returns:
            dict: 综合素质评估结果
        """
        import json
        pos_soft = ''
        if position_analysis and isinstance(position_analysis, dict):
            ss = position_analysis.get('soft_skills', [])
            if ss:
                pos_soft = json.dumps(ss, ensure_ascii=False)

        # 清理 + 截断长简历 / JD（v2.0 修复）
        safe_resume = truncate_for_prompt(clean_resume_text(resume_text or ''), max_chars=3000)
        safe_jd = truncate_for_prompt(jd_content or '', max_chars=1500)

        prompt = f"""## 任务
你是综合素质评估师，请**只从软技能和综合素质角度**评估候选人。
不要评估具体技术能力，专注评估沟通、协作、学习、领导力等软性素质。

## 候选人姓名
{candidate_name or '候选人'}

## 岗位要求（供参考）
**岗位名称：** {position_name}
**岗位期望的软技能：** {pos_soft or '未明确'}
**JD 全文：**
{safe_jd or '暂无详细JD'}

## 候选人简历
{safe_resume or '暂无'}

## 评估要求

### 1. 沟通表达能力
从简历写作本身推断：
- 简历结构是否清晰有条理
- 用词是否精准专业，还是模糊笼统
- 项目描述是否能说清楚"做了什么、为什么做、结果如何"
- 技术表述是否准确（vs 堆砌关键词）

### 2. 团队协作风格
从项目描述中推断：
- 独立型：习惯单独负责模块
- 协作型：多次提到团队协作、跨部门
- 领导型：带团队、主导、推动

### 3. 学习能力
- 技术栈更新频率（是否持续学习新技术）
- 跨领域经历（是否有技术栈迁移经验）
- 从项目复杂度变化推断成长速度

### 4. 领导力与管理潜力
- 是否有带团队经验
- 是否主导过技术决策或架构设计
- 是否有指导他人、技术分享的经历

### 5. 主动性与成就导向
- 是否有主动优化、改进的记录
- 项目成果是否有量化数据
- 是否展示了超出岗位职责的贡献

### 5. 综合素质评分（soft_score，0-100 分制）
- 90-100：沟通协作学习能力均强，有领导力潜力
- 75-89：综合素质良好，个别维度有提升空间
- 60-74：基础素质具备但缺乏突出亮点
- 40-59：多项软性维度有欠缺
- 0-39：综合素质与岗位要求差距较大
- **注意：必须是 0-100 整数，不要给 1-10 分制！**（历史上曾出现 5/10 被误读成 5/100 = 5 分的严重 bug）

## 输出格式（严格 JSON）
{{
    "soft_score": 72,
    "communication": {{
        "level": "较强/一般/较弱",
        "resume_quality": "简历写作质量评估",
        "detail": "具体推断依据",
        "confidence": "high/medium/low"
    }},
    "teamwork_style": {{
        "style": "独立型/协作型/领导型",
        "detail": "推断依据",
        "confidence": "high/medium/low"
    }},
    "learning_ability": {{
        "level": "强/一般/较弱",
        "signals": ["观察到的信号"],
        "detail": "推断依据",
        "confidence": "high/medium/low"
    }},
    "leadership": {{
        "level": "较强/一般/较弱/无明显信号",
        "management_experience": "有无带团队经验",
        "detail": "推断依据",
        "confidence": "high/medium/low"
    }},
    "initiative": {{
        "level": "强/一般/较弱",
        "achievements": ["主动贡献的证据"],
        "detail": "推断依据",
        "confidence": "high/medium/low"
    }},
    "soft_highlights": [
        {{"point": "素质亮点", "evidence": "简历证据"}}
    ],
    "soft_concerns": [
        {{"concern": "关注点", "detail": "说明"}}
    ],
    "soft_summary": "2-3句话的综合素质总结评估"
}}"""
        return self.think_json(prompt)
