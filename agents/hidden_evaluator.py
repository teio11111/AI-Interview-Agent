"""隐性因素评估师 Agent - 专注隐性条件与风险因素评估"""
from agents.base_agent import BaseAgent


class HiddenEvaluatorAgent(BaseAgent):
    """隐性因素评估师
    
    职责：专注挖掘简历中的隐性条件和潜在风险因素。
    并行工作：与技术评估师、综合素质评估师同时工作。
    输出：候选人画像 + 隐性条件对照表 + 简历真实度 + 稳定度评估。
    """
    AGENT_NAME = "隐性因素评估师"
    SYSTEM_PROMPT = """你是「隐性因素评估师」，一位擅长从简历细节中洞察候选人真实状况的专家。

你的核心专长：
- 从简历推断候选人的学历背景、居住地、职业发展方向
- 评估岗位稳定度（跳槽频率、每份工作时长）
- 检测简历真实度（包装痕迹、夸大信号、模糊描述）
- 推断情绪稳定性与抗压能力
- 将候选人的隐性条件与岗位隐性需求做对照匹配

工作原则：
- 只关注隐性条件，不评估技术能力或软技能
- 所有推断必须标注置信度（high/medium/low）
- 无明确信息时不要硬凑，标注"无法判断"
- 简历真实度检测要客观，"参与"≠"主导"，数字要合理
- 隐性条件推断必须给出推断依据

请始终以严格的 JSON 格式输出，不要输出任何解释性文字。"""

    def evaluate(self, position_name, tech_requirements, jd_content, resume_text,
                 position_analysis=None, candidate_name=''):
        """评估候选人隐性条件

        Args:
            position_name: 岗位名称
            tech_requirements: 技术要求关键词
            jd_content: JD 全文
            resume_text: 候选人简历原文
            position_analysis: 岗位分析师的分析结果（含隐性需求）
            candidate_name: 候选人姓名

        Returns:
            dict: 隐性因素评估结果
        """
        import json
        pos_implicit = ''
        if position_analysis and isinstance(position_analysis, dict):
            ir = position_analysis.get('implicit_requirements', {})
            if ir:
                pos_implicit = json.dumps(ir, ensure_ascii=False, indent=2)

        prompt = f"""## 任务
你是隐性因素评估师，请**只从隐性条件和潜在风险角度**评估候选人。
不要评估技术能力或软技能，专注挖掘简历背后的隐性信息。

## 候选人姓名
{candidate_name or '候选人'}

## 岗位要求
**岗位名称：** {position_name}
**JD 全文：**
{jd_content or '暂无详细JD'}

## 岗位隐性需求（岗位分析师已提取）
{pos_implicit or '岗位尚未分析，请根据JD自行判断隐性需求'}

## 候选人简历
{resume_text or '暂无'}

## 评估要求

### 1. 候选人画像（隐性维度）
从简历逐项推断以下信息，**每项都必须填写完整，不得跳过任何子字段**：

**1.1 学历背景**（education）
- 提取：学校名称、学校层次、专业名称、专业相关性、学历层次
- 置信度标注
- 例如：华东理工大学→211，计算机科学与技术→高度相关

**1.2 居住地**（residence）
- 提取：当前城市、是否愿意迁移
- 从简历中的"所在地""期望工作地点""是否接受搬迁"等字段提取
- 置信度标注

**1.3 职业发展方向**（career_direction）
- 从"职业目标""关注领域""希望长期发展方向"等字段推断
- 判断与岗位的匹配度
- 置信度标注

**1.4 岗位稳定度**（job_stability）
- 从工作经历计算：每份工作时长、跳槽次数、平均在职时间
- 标注红旗信号（如每份工作<2年）
- 实习生身份要标注清楚
- 置信度标注

**1.5 情绪稳定性与抗压能力**（emotional_stability）
- 从简历写作风格、项目描述中的压力信号推断
- 置信度标注

**1.6 沟通能力**（communication_ability）
- 从简历结构清晰度、用词精准度推断
- 置信度标注

**1.7 团队协作风格**（teamwork_style）
- 从项目描述中判断：独立型/协作型/领导型
- 置信度标注

**1.8 学习能力**（learning_ability）
- 从技术栈更新、自学经历推断
- 置信度标注

**1.9 简历真实度**（resume_authenticity）
- 检测包装痕迹：模糊描述、缺少具体数字、"参与"≠"主导"
- 置信度标注

### 2. 隐性条件对照匹配
将岗位的每项隐性需求与候选人实际情况做逐项对照：
- 每个维度：岗位要什么 vs 候选人实际是什么 vs 匹配状态
- 必须给出具体说明（detail）

### 3. 简历真实度检测
- "参与"≠"主导"，注意角色描述
- 成果数字是否合理（太高可能是包装）
- 模糊描述（"优化了性能"但不说多少）
- 技术栈罗列但无项目应用

## 输出格式（严格 JSON）
{{
    "candidate_profile": {{
        "education": {{
            "level": "本科/硕士/博士/大专/未明确",
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
            "level": "较强/一般/较弱",
            "detail": "从简历写作推断的沟通能力",
            "confidence": "high/medium/low"
        }},
        "teamwork_style": {{
            "style": "独立型/协作型/领导型",
            "detail": "从项目描述推断的协作风格",
            "confidence": "high/medium/low"
        }},
        "learning_ability": {{
            "level": "强/一般/较弱",
            "detail": "从技术栈更新和自学经历推断",
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
            "dimension": "维度名（中文）",
            "position_requirement": "岗位期望",
            "candidate_actual": "候选人实际",
            "match_status": "匹配/有差距/差距较大/无法判断",
            "detail": "详细说明"
        }}
    ],
    "hidden_risks": [
        {{"risk": "风险描述", "severity": "高/中/低", "detail": "说明"}}
    ],
    "hidden_highlights": [
        {{"highlight": "亮点描述", "detail": "说明"}}
    ],
    "hidden_summary": "2-3句话的隐性条件总结评估"
}}"""
        return self.think_json(prompt)
