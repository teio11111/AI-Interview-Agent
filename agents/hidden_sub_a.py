"""隐性因素评估师 子任务 A - 人岗匹配维度

【v4.1 拆分】将原 hidden_evaluator 的 5803 字符 prompt 拆为 2 个子任务并发跑
- hidden_sub_a（本文件）：人岗匹配维度（3000 字符 prompt）
- hidden_sub_b：简历真实度+稳定度维度（3000 字符 prompt）
"""
import json
from agents.base_agent import BaseAgent
from utils.text_truncate import truncate_for_prompt, clean_resume_text


class HiddenSubAEvaluatorAgent(BaseAgent):
    """隐性因素评估师 - 子任务 A：人岗匹配维度

    职责：仅评估候选人背景与岗位隐性需求的匹配度
    输出：candidate_profile.education/residence/career_direction + implicit_requirement_mapping
    """
    AGENT_NAME = "隐性因素评估师-A(人岗匹配)"

    SYSTEM_PROMPT = """你是「隐性因素评估师-A」，专门评估候选人背景与岗位隐性需求的匹配度。

## 你的核心职责（只做这一件事）

从简历推断候选人的：
1. 学历背景（教育层次、学校、专业相关性）
2. 居住地与迁移意愿
3. 职业发展方向（与岗位的契合度）

并对照岗位的 6 个隐性维度（抗压、技术领导力、沟通复杂度、稳定性期望、学历偏好、技术栈隐性匹配），
给出匹配状态（匹配/有差距/差距较大/无法判断）。

## 工作原则

- 只关注人岗匹配维度，**不要评估简历真实度、稳定度、情绪等**（那是子任务 B 的工作）
- 推断必须标注置信度（high/medium/low）
- 无明确信息时不要硬凑，标注"无法判断"
- 每条说明简洁：岗位要求与候选人实际各 ≤30 字，detail ≤40 字

## 【v2.1 评分原则】

- 1-3：明显不符合（学校层次不匹配、地理位置冲突、职业方向与岗位背道而驰）
- 4-5：一般/未明确（信息不足或表现中性）
- 6-7：明显高于平均（与岗位隐性需求匹配、地理合适、方向一致）
- 8-9：优秀（学校层次高、地理完美、方向高度契合）
- 10：完美（多重要素同时高度匹配）

**5 分才是中性分**，不要默认给 6-7 分。

请始终以严格的 JSON 格式输出，不要输出任何解释性文字。"""

    def evaluate(self, position_name, tech_requirements, jd_content, resume_text,
                 position_analysis=None, candidate_name=''):
        """评估候选人 - 子任务 A：人岗匹配

        Returns:
            dict: {
                'candidate_profile': {education, residence, career_direction},
                'implicit_requirement_mapping': [...]
            }
        """
        pos_implicit = ''
        if position_analysis and isinstance(position_analysis, dict):
            ir = position_analysis.get('implicit_requirements', {})
            if ir:
                pos_implicit = json.dumps(ir, ensure_ascii=False, indent=2)

        safe_resume = truncate_for_prompt(clean_resume_text(resume_text or ''), max_chars=2500)
        safe_jd = truncate_for_prompt(jd_content or '', max_chars=1500)

        prompt = f"""## 任务
你是隐性因素评估师-A，**只从人岗匹配角度**评估候选人。
不要评估技术能力、软技能、简历真实度、稳定度（那些是子任务 B 的工作）。

## 候选人姓名
{candidate_name or '候选人'}

## 岗位要求
**岗位名称：** {position_name}
**JD 全文：**
{safe_jd or '暂无详细JD'}

## 岗位隐性需求（岗位分析师已提取）
{pos_implicit or '岗位尚未分析，请根据JD自行判断隐性需求'}

## 候选人简历
{safe_resume or '暂无'}

## 评估要求

### 1. 候选人画像（仅 3 个匹配维度）

**1.1 学历背景**（education）
- 提取：学校名称、学校层次（985/211/双一流/普通本科/未明确）、专业名称、专业相关性
- 评分 1-10（5=中性）
- 置信度标注
- 例如：华东理工大学→211，计算机科学与技术→高度相关

**1.2 居住地**（residence）
- 提取：当前城市、是否愿意迁移
- 评分 1-10
- 置信度标注

**1.3 职业发展方向**（career_direction）
- 从"职业目标""关注领域"等推断
- 判断与岗位的匹配度
- 评分 1-10
- 置信度标注

### 2. 隐性条件对照匹配（仅 6 个岗位维度）

将岗位隐性需求与候选人实际逐项对照：

1. 抗压能力（stress_tolerance）
2. 技术领导力（management_potential）—— 非人员管理，技术深度+问题解决
3. 沟通复杂度（communication_complexity）
4. 稳定性期望（stability_expectation）
5. 学历偏好（education_preference）
6. 技术栈匹配度（隐性 tech_stack_match）

每条说明：岗位要求与候选人实际各 ≤ 30 字，detail ≤ 40 字。

## 输出格式（严格 JSON）

{{
    "candidate_profile": {{
        "education": {{
            "level": "本科/硕士/博士/大专/未明确",
            "school_tier": "985/211/双一流/普通本科/未明确",
            "major_relevance": "高度相关/相关/弱相关/不相关/未明确",
            "score": 5,
            "detail": "具体学校和专业信息",
            "confidence": "high/medium/low"
        }},
        "residence": {{
            "current_city": "当前城市",
            "willingness_to_relocate": "愿意/不确定/不愿意/未明确",
            "score": 5,
            "detail": "推断依据",
            "confidence": "high/medium/low"
        }},
        "career_direction": {{
            "preferred_track": "技术专家/管理路线/全栈发展/创业/未明确",
            "alignment_with_role": "高度匹配/匹配/一般/不匹配",
            "score": 5,
            "detail": "推断依据",
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
    ]
}}"""
        return self.think_json(prompt)
