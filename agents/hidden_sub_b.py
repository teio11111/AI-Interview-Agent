"""隐性因素评估师 子任务 B - 简历真实度+稳定度+软性维度

【v4.1 拆分】与 hidden_sub_a 并发执行
- hidden_sub_a：人岗匹配维度
- hidden_sub_b（本文件）：稳定度+情绪+沟通+协作+学习+真实度+总分计算
"""
import json
from agents.base_agent import BaseAgent
from utils.text_truncate import truncate_for_prompt, clean_resume_text


class HiddenSubBEvaluatorAgent(BaseAgent):
    """隐性因素评估师 - 子任务 B：简历真实度+稳定度+软性维度

    职责：评估简历质量、候选人稳定度、软性特质
    输出：candidate_profile 的剩余 6 个维度 + hidden_score_breakdown + risks + highlights + summary
    """
    AGENT_NAME = "隐性因素评估师-B(稳定度+软性)"

    SYSTEM_PROMPT = """你是「隐性因素评估师-B」，专门评估候选人的简历真实度、稳定度和软性维度。

## 你的核心职责（只做这一件事）

从简历推断候选人的：
1. 岗位稳定度（跳槽频率、每份工作时长）
2. 情绪稳定性与抗压能力
3. 沟通能力
4. 团队协作风格
5. 学习能力
6. 简历真实度（包装痕迹检测）

## 工作原则

- 只关注稳定度和软性维度，**不要评估学历、居住地、职业方向**（那是子任务 A 的工作）
- 简历真实度检测要客观："参与"≠"主导"，数字要合理
- 所有推断必须标注置信度（high/medium/low）
- 无明确信息时不要硬凑，标注"无法判断"

## 【v2.1 评分原则】

- 1-3：明显不符合（频繁跳槽、明显包装、情绪不稳）
- 4-5：一般/未明确（信息不足或表现中性）
- 6-7：明显高于平均（稳定、真实、协作好）
- 8-9：优秀（长期稳定、简历高度可信、软性特质突出）
- 10：完美（多重要素同时优秀）

**5 分才是中性分**，不要默认给 6-7 分。
resume_authenticity 越高=简历越真实（1=明显包装、10=完全真实）。

【关键】简历信息严重不足时（如候选人提交的文本与 JD 几乎一致、明显复制 JD 作为简历、无任何个人信息、项目、教育、工作经历），
6 个软性维度统一给 **5 分**（中性）：信息不足不等于"全面差"，在没有证据表明候选人本身有问题的情况下不应给 1-3 分。
仅在可以明确判断"负面信号"时才给低分。

请始终以严格的 JSON 格式输出，不要输出任何解释性文字。"""

    def evaluate(self, position_name, tech_requirements, jd_content, resume_text,
                 position_analysis=None, candidate_name=''):
        """评估候选人 - 子任务 B：稳定度+软性维度

        Returns:
            dict: {
                'candidate_profile': {job_stability, emotional_stability, communication_ability,
                                      teamwork_style, learning_ability, resume_authenticity},
                'hidden_score_breakdown': {9 个维度评分，sub_a 维度默认 5},
                'hidden_risks': [...],
                'hidden_highlights': [...],
                'hidden_summary': "..."
            }
        """
        safe_resume = truncate_for_prompt(clean_resume_text(resume_text or ''), max_chars=2500)
        safe_jd = truncate_for_prompt(jd_content or '', max_chars=1500)

        prompt = f"""## 任务
你是隐性因素评估师-B，**只从稳定度和软性维度**评估候选人。
不要评估学历、居住地、职业方向（那是子任务 A 的工作）。

## 候选人姓名
{candidate_name or '候选人'}

## 岗位要求
**岗位名称：** {position_name}
**JD 全文：**
{safe_jd or '暂无详细JD'}

## 候选人简历
{safe_resume or '暂无'}

## 评估要求

### 1. 候选人画像（仅 6 个软性维度）

**1.1 岗位稳定度**（job_stability）
- 从工作经历计算：每份工作时长、跳槽次数、平均在职时间
- 标注红旗信号（如每份工作<2年）
- 实习生身份要标注清楚
- 评分 1-10
- 置信度标注

**1.2 情绪稳定性与抗压能力**（emotional_stability）
- 从简历写作风格、项目描述中的压力信号推断
- 评分 1-10
- 置信度标注

**1.3 沟通能力**（communication_ability）
- 从简历结构清晰度、用词精准度推断
- 评分 1-10
- 置信度标注

**1.4 团队协作风格**（teamwork_style）
- 从项目描述中判断：独立型/协作型/领导型
- 评分 1-10
- 置信度标注

**1.5 学习能力**（learning_ability）
- 从技术栈更新、自学经历推断
- 评分 1-10
- 置信度标注

**1.6 简历真实度**（resume_authenticity）
- 检测包装痕迹：模糊描述、缺少具体数字、"参与"≠"主导"
- 评分 1-10（10=完全真实，1=明显包装）
- 置信度标注

### 2. 9 维度评分汇总（hidden_score_breakdown）

**注意**：子任务 A 负责的 3 个维度（education/residence/career_direction）这里**默认给 5 分**，合并时由系统用 A 的真实分数覆盖。

{{
    "education": 5,
    "residence": 5,
    "career_direction": 5,
    "job_stability": 5,
    "emotional_stability": 5,
    "communication_ability": 5,
    "teamwork_style": 5,
    "learning_ability": 5,
    "resume_authenticity": 5
}}

### 3. 风险与亮点

**hidden_risks**: 列出简历/候选人可能存在的隐性风险（如频繁跳槽、明显包装等），每条含 risk/severity/detail
**hidden_highlights**: 列出亮点（如技术栈丰富、大厂经历等），每条含 highlight/detail

### 4. 简历真实度检测要点
- "参与"≠"主导"，注意角色描述
- 成果数字是否合理（太高可能是包装）
- 模糊描述（"优化了性能"但不说多少）
- 技术栈罗列但无项目应用

## 输出格式（严格 JSON）

{{
    "candidate_profile": {{
        "job_stability": {{
            "level": "稳定/一般/不稳定",
            "avg_tenure": "平均每份工作时长",
            "job_hops": "跳槽次数",
            "red_flags": ["稳定度风险点"],
            "score": 5,
            "detail": "推断依据",
            "confidence": "high/medium/low"
        }},
        "emotional_stability": {{
            "level": "较好/一般/待观察",
            "signals": ["观察到的信号"],
            "score": 5,
            "detail": "推断依据",
            "confidence": "high/medium/low"
        }},
        "communication_ability": {{
            "level": "较强/一般/较弱",
            "score": 5,
            "detail": "从简历写作推断的沟通能力",
            "confidence": "high/medium/low"
        }},
        "teamwork_style": {{
            "style": "独立型/协作型/领导型",
            "score": 5,
            "detail": "从项目描述推断的协作风格",
            "confidence": "high/medium/low"
        }},
        "learning_ability": {{
            "level": "强/一般/较弱",
            "score": 5,
            "detail": "从技术栈更新和自学经历推断",
            "confidence": "high/medium/low"
        }},
        "resume_authenticity": {{
            "level": "真实/有包装痕迹/明显包装",
            "packaging_signals": ["包装痕迹列表"],
            "score": 5,
            "detail": "具体说明",
            "confidence": "high/medium/low"
        }}
    }},
    "hidden_score_breakdown": {{
        "education": 5,
        "residence": 5,
        "career_direction": 5,
        "job_stability": 5,
        "emotional_stability": 5,
        "communication_ability": 5,
        "teamwork_style": 5,
        "learning_ability": 5,
        "resume_authenticity": 5
    }},
    "hidden_risks": [
        {{"risk": "风险描述", "severity": "高/中/低", "detail": "说明"}}
    ],
    "hidden_highlights": [
        {{"highlight": "亮点描述", "detail": "说明"}}
    ],
    "hidden_summary": "2-3句话的隐性条件总结评估"
}}"""
        return self.think_json(prompt)
