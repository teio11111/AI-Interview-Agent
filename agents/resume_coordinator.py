"""简历汇总师 Agent - 综合三位评估师的结果生成统一简历画像"""
from agents.base_agent import BaseAgent


class ResumeCoordinatorAgent(BaseAgent):
    """简历汇总师
    
    职责：接收技术评估师、综合素质评估师、隐性因素评估师的三方结果，
    综合分析生成统一的候选人简历画像。
    输出格式兼容原有 resume_evaluator 的格式，保证下游（出题官等）不 break。
    """
    AGENT_NAME = "简历汇总师"
    SYSTEM_PROMPT = """你是「简历汇总师」，一位资深人才评估协调专家。

你的核心职责：
- 接收三位专家（技术评估师、综合素质评估师、隐性因素评估师）的独立评估结果
- 识别三位专家结论中的**一致点**和**分歧点**
- 综合三方意见，给出**最终统一**的候选人画像
- 生成针对后续面试的建议追问方向

工作原则：
- 当三位专家意见一致时，增强置信度
- 当专家意见冲突时，标注分歧并给出你的判断
- 综合匹配度评分应综合考虑技术（权重60%）+ 素质（权重20%）+ 隐性条件（权重20%）
- 建议的追问方向要具体可执行，重点追问专家分歧点和高风险项

请始终以严格的 JSON 格式输出，不要输出任何解释性文字。"""

    def synthesize(self, tech_result, soft_result, hidden_result,
                   position_name, candidate_name=''):
        """综合三方评估结果生成统一画像

        Args:
            tech_result: 技术评估师的结果 dict
            soft_result: 综合素质评估师的结果 dict
            hidden_result: 隐性因素评估师的结果 dict
            position_name: 岗位名称
            candidate_name: 候选人姓名

        Returns:
            dict: 统一简历画像（兼容旧 resume_evaluator 输出格式）
        """
        import json

        # 隐性因素评估师的详细数据（用于明确指令保留）
        hidden_profile = json.dumps(
            (hidden_result or {}).get('candidate_profile', {}),
            ensure_ascii=False, indent=2
        )
        hidden_mapping = json.dumps(
            (hidden_result or {}).get('implicit_requirement_mapping', []),
            ensure_ascii=False, indent=2
        )
        hidden_risks = json.dumps(
            (hidden_result or {}).get('hidden_risks', []),
            ensure_ascii=False, indent=2
        )
        hidden_highlights = json.dumps(
            (hidden_result or {}).get('hidden_highlights', []),
            ensure_ascii=False, indent=2
        )

        prompt = f"""## 任务
你是简历汇总师。三位专家已分别独立完成了对候选人的评估，请综合三方结果，
生成**最终统一**的候选人简历画像。

## 候选人姓名
{candidate_name or '候选人'}

## 岗位名称
{position_name}

## 技术评估师的评估结果
{json.dumps(tech_result or {}, ensure_ascii=False, indent=2)}

## 综合素质评估师的评估结果
{json.dumps(soft_result or {}, ensure_ascii=False, indent=2)}

## 隐性因素评估师的评估结果
{json.dumps(hidden_result or {}, ensure_ascii=False, indent=2)}

## 综合分析要求

### 1. 一致性检查
找出三位专家结论中：
- 一致的判断（增强置信度）
- 分歧的判断（标注分歧并给出你的最终判断）

### 2. 综合匹配度评分（0-100）
- 技术能力权重 60%（技术评估师的 tech_depth_score）
- 综合素质权重 20%（综合素质评估师的 soft_score）
- 隐性条件权重 20%（隐性因素评估师的整体评价）

### 3. 优势整合
从三位专家的 highlights 中筛选最重要的 3-5 个优势，标注来源

### 4. 风险整合
从三位专家的 risks/concerns 中筛选最重要的 3-5 个风险，标注来源

### 5. 建议追问方向
基于专家的分歧点和高风险项，建议 4-6 个面试追问方向

### 6. ★ 隐性因素数据：必须原样保留 ★
以下数据来自隐性因素评估师，**必须原样复制到输出中，不得简化、省略或改写**。
每一项嵌套字段（education/residence/career_direction/job_stability/emotional_stability/resume_authenticity）
都必须完整保留，包括 detail、confidence 等子字段。

**候选人画像（隐性维度）：**
{hidden_profile}

**隐性条件对照表：**
{hidden_mapping}

## 输出格式（严格 JSON）
{{
    "match_score": 0,
    "matched_skills": [
        {{"skill": "技能名", "proficiency": "精通/熟练/了解/基础", "evidence": "简历证据"}}
    ],
    "missing_skills": [
        {{"skill": "缺失技能", "importance": "核心/重要/次要", "impact": "缺失影响"}}
    ],
    "strengths": [
        {{"point": "优势描述", "evidence": "简历证据", "source": "技术评估师/综合素质评估师/隐性因素评估师"}}
    ],
    "risks": [
        {{"risk": "风险描述", "severity": "高/中/低", "detail": "具体说明", "source": "来源Agent"}}
    ],
    "candidate_profile": "必须原样复制上方【候选人画像（隐性维度）】的完整JSON，包含education/residence/career_direction/job_stability/emotional_stability/resume_authenticity全部嵌套字段",
    "implicit_requirement_mapping": "必须原样复制上方【隐性条件对照表】的完整JSON数组",
    "suggested_questions": [
        {{"topic": "追问方向", "reason": "为什么要追问（基于哪个专家的意见）", "example_question": "示例问题"}}
    ],
    "expert_consensus": ["专家一致的判断"],
    "expert_divergence": [
        {{"topic": "分歧点", "opinions": "各方意见", "final_judgment": "你的最终判断"}}
    ],
    "score_breakdown": {{
        "tech_component": 0,
        "soft_component": 0,
        "hidden_component": 0,
        "detail": "各维度评分说明"
    }},
    "summary": "3-4句话的匹配度综合评估",
    "candidate_summary": "面向候选人的友好版本，开头用\"{candidate_name or '候选人'}您好\"称呼，3-4句话：先肯定匹配的技能优势，再温和建议可提升的方向，语气专业友好像良师益友。不要使用\"不推荐\"\"包装\"\"风险\"\"差距较大\"等内部评估用语。"
}}"""
        return self.think_json(prompt)
