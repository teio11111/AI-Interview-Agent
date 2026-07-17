"""简历评估师 Agent - 专注简历与岗位匹配度评估"""
from agents.base_agent import BaseAgent


class ResumeEvaluatorAgent(BaseAgent):
    """简历评估师
    
    职责：对比岗位要求与候选人简历，给出客观匹配度评估。
    输出：匹配度评分 + 技能匹配/缺失 + 优势/风险 + 隐性条件评估 + 建议追问方向。
    """
    AGENT_NAME = "简历评估师"
    SYSTEM_PROMPT = """你是「简历评估师」，一位拥有 15 年经验的资深技术简历审核专家。

你的核心能力：
- 精准评估候选人技术能力与岗位要求的匹配度
- 从简历文本中识别真实水平信号（vs 包装痕迹）
- 发现简历中的风险信号（夸大、模糊、版本过时）
- 提取简历中的隐性条件（学历背景、居住地、职业发展方向、岗位稳定度、情绪稳定性等）
- 为后续面试提供针对性的追问方向建议

工作原则：
- 评分严格客观，不偏高也不偏低
- 每个判断必须有简历原文作为证据（evidence）
- 风险分级明确（高/中/低）
- 隐性条件推断必须标注置信度（high/medium/low），无明确信息时不要硬凑
- 建议的追问方向要具体可执行

请始终以严格的 JSON 格式输出，不要输出任何解释性文字。"""

    def evaluate(self, position_name, tech_requirements, jd_content, resume_text, position_analysis=None, candidate_name=''):
        """评估简历匹配度

        Args:
            position_name: 岗位名称
            tech_requirements: 技术要求
            jd_content: JD 全文
            resume_text: 候选人简历原文
            position_analysis: 岗位分析师的分析结果（含隐性需求）

        Returns:
            dict: 简历评估结果
        """
        import json
        # 提取岗位的隐性需求（如果岗位已分析）
        pos_implicit = ''
        if position_analysis and isinstance(position_analysis, dict):
            ir = position_analysis.get('implicit_requirements', {})
            if ir:
                pos_implicit = json.dumps(ir, ensure_ascii=False, indent=2)

        prompt = f"""## 任务
对比岗位要求与候选人简历，给出客观、详细的匹配度评估。
除了专业技能匹配，还需要提取简历中的**隐性条件**，帮助技术负责人做更全面的判断。

## 候选人姓名
{candidate_name or '候选人'}

## 岗位要求
**岗位名称：** {position_name}
**技术要求：** {tech_requirements or '暂无'}
**JD 全文：**
{jd_content or '暂无详细JD'}

## 岗位隐性需求（岗位分析师已提取）
{pos_implicit or '岗位尚未分析，请根据JD自行判断隐性需求'}

## 候选人简历
{resume_text or '暂无'}

## 评估标准

### 一、专业技能匹配（核心）
- **匹配度评分（0-100）**：
  - 90-100：高度匹配，经验完全覆盖核心要求
  - 75-89：较好匹配，核心技能具备，个别次要技能欠缺
  - 60-74：一般匹配，基础能力具备但有明显短板
  - 40-59：匹配度较低，多项核心技能缺失
  - 0-39：不匹配，经验与岗位要求差距较大
- **风险评估维度**：
  - 经验深度是否足够
  - 技能是否停留在理论层面
  - 简历中是否有夸大嫌疑的信号
  - 技术栈版本是否过时

### 二、隐性条件提取（重要）
从简历文字中推断以下信息，每个推断必须标注置信度（high/medium/low）：

1. **学历背景**：学校层次、专业相关性
2. **居住地**：当前城市、是否愿意迁移（根据工作地、学校地推断）
3. **职业发展方向**：候选人的职业路线偏好（技术专家/管理/全栈），与当前岗位是否匹配
4. **岗位稳定度**：从跳槽频率、每份工作时长推断（稳定/一般/不稳定）
5. **情绪稳定性与抗压能力**：从简历措辞、工作压力描述推断
6. **沟通表达能力**：从简历结构清晰度、用词准确性推断
7. **团队协作风格**：从项目描述中推断（独立型/协作型/领导型）
8. **学习能力**：从技术栈更新频率、跨领域经历推断
9. **简历真实度**：检测包装痕迹（"参与"≠"主导"、数字是否合理、模糊描述）

### 三、隐性条件对照匹配（核心新增）
将岗位的每项隐性需求与候选人实际情况做**逐项对照**，输出对照表。
每个维度需要给出：岗位要什么、候选人实际是什么、匹配状态（匹配/有差距/差距较大/无法判断）。
如果岗位隐性需求未提供，请根据JD自行判断后对照。

**重要：所有字段值必须使用中文描述，dimension字段必须使用中文维度名（如“抗压能力”“管理潜力”“沟通复杂度”“稳定性期望”“学历偏好”），禁止使用英文字段名。**

## 输出格式（严格 JSON）
{{
    "match_score": 72,
    "matched_skills": [
        {{"skill": "技能名", "proficiency": "熟练/了解/基础", "evidence": "简历中对应证据"}}
    ],
    "missing_skills": [
        {{"skill": "缺失技能", "importance": "核心/重要/次要", "impact": "缺失的影响"}}
    ],
    "strengths": [
        {{"point": "优势描述", "evidence": "简历中对应证据"}}
    ],
    "risks": [
        {{"risk": "风险描述", "severity": "高/中/低", "detail": "具体说明"}}
    ],
    "candidate_profile": {{
        "education": {{
            "level": "本科/硕士/博士/大专",
            "school_tier": "985/211/双一流/普通本科/未明确",
            "major_relevance": "高度相关/相关/弱相关/不相关/未明确",
            "detail": "具体学校和专业信息",
            "confidence": "high/medium/low"
        }},
        "residence": {{
            "current_city": "当前城市",
            "willingness_to_relocate": "愿意/不确定/不愿意/未明确",
            "detail": "推断依据",
            "confidence": "high/medium/low"
        }},
        "career_direction": {{
            "preferred_track": "技术专家/管理路线/全栈发展/创业/未明确",
            "alignment_with_role": "高度匹配/匹配/一般/不匹配",
            "detail": "推断依据",
            "confidence": "high/medium/low"
        }},
        "job_stability": {{
            "level": "稳定/一般/不稳定",
            "avg_tenure": "平均每份工作时长",
            "job_hops": "跳槽次数",
            "red_flags": ["稳定度风险点"],
            "detail": "推断依据",
            "confidence": "high/medium/low"
        }},
        "emotional_stability": {{
            "level": "较好/一般/待观察",
            "signals": ["观察到的信号"],
            "detail": "推断依据",
            "confidence": "high/medium/low"
        }},
        "communication_ability": {{
            "level": "较好/一般/较弱",
            "detail": "从简历结构、用词等推断",
            "confidence": "high/medium/low"
        }},
        "teamwork_style": {{
            "style": "独立型/协作型/领导型",
            "detail": "推断依据",
            "confidence": "high/medium/low"
        }},
        "learning_ability": {{
            "level": "强/一般/较弱",
            "detail": "从技术栈更新频率等推断",
            "confidence": "high/medium/low"
        }},
        "resume_authenticity": {{
            "level": "真实/有包装痕迹/明显包装",
            "packaging_signals": ["包装痕迹列表"],
            "detail": "具体说明",
            "confidence": "high/medium/low"
        }}
    }},
    "implicit_requirement_mapping": [
        {{
            "dimension": "抗压能力",
            "position_requirement": "高（快节奏，deadline紧）",
            "candidate_actual": "一般（简历措辞平稳，无高压经历描述）",
            "match_status": "有差距",
            "detail": "候选人简历未体现高压环境经历，建议面试中探测"
        }},
        {{
            "dimension": "管理潜力",
            "position_requirement": "需要（带3-5人小组）",
            "candidate_actual": "具备（带领5人团队经验）",
            "match_status": "匹配",
            "detail": "候选人有带队经验，满足要求"
        }}
    ],
    "suggested_questions": [
        {{"topic": "追问方向", "reason": "为什么要追问这个", "example_question": "示例问题"}}
    ],
    "summary": "3-4句话的匹配度综合评估",
    "candidate_summary": "面向候选人的友好版本，开头用“{candidate_name or '候选人'}您好”称呼，3-4句话：先肯定匹配的技能优势，再温和建议可提升的方向，语气专业友好像良师益友。不要使用“不推荐”“包装”“风险”“差距较大”等内部评估用语。"
}}"""
        return self.think_json(prompt)

    def review_questions(self, questions, position_name, resume_text, resume_analysis):
        """审核出题官的题目质量（Agent辩论机制）

        Args:
            questions: 出题官输出的问题列表
            position_name: 岗位名称
            resume_text: 候选人简历原文
            resume_analysis: 简历评估结果

        Returns:
            dict: 审核意见（approved=True表示通过，否则含修改建议）
        """
        import json
        questions_text = json.dumps(questions.get('questions', []) if isinstance(questions, dict) else [], ensure_ascii=False, indent=2)
        
        prompt = f"""## 任务
你是面试题目审核专家。请审核出题官设计的面试题目，判断是否与候选人简历和岗位要求匹配。

## 岗位
{position_name}

## 候选人简历
{resume_text or '暂无'}

## 简历评估结论
{self.summarize(resume_analysis)}

## 出题官的题目
{questions_text}

## 审核标准
1. **简历关联性**：每个问题是否真的引用了简历中的具体内容？有没有凭空出题？
2. **风险覆盖**：简历评估中标记的高风险点是否都有对应题目探测？
3. **难度合理性**：难度分配是否与候选人实际经验匹配？
4. **追问可行性**：follow_up_hints 是否真的可追问，还是太笼统？

## 输出格式（严格 JSON）
{{
    "approved": true/false,
    "overall_comment": "整体评价（1-2句）",
    "issues": [
        {{
            "question_index": 1,
            "problem": "这道题的问题是什么",
            "suggestion": "建议怎么改"
        }}
    ],
    "missing_coverage": ["简历中的xxx风险点没有对应题目"]
}}"""
        return self.think_json(prompt)
