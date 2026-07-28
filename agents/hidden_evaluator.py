"""隐性因素评估师 Agent - 专注隐性条件与风险因素评估"""
from agents.base_agent import BaseAgent
from utils.text_truncate import truncate_for_prompt, clean_resume_text


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

## 【v2.1 重要】隐性条件评分原则
你必须在 hidden_score_breakdown 为 9 个隐性维度各打一个 1-10 分，原则如下：
- 1-3：明显不符合（学历不匹配岗位、明显包装、经常跳槽）
- 4-5：一般/未明确（信息不足或表现中性）
- 6-7：明显高于平均（与岗位隐性需求匹配、简历详细真实）
- 8-9：优秀（学校层次高、稳定且资深、简历高度可信）
- 10：完美（多重要素同时高度匹配岗位）

请不要默认给 6-7 分！5 分才是中性分。
resume_authenticity 越高=简历越真实（1=明显包装、10=完全真实）。

【关键】简历信息严重不足时（如候选人提交的文本与 JD 几乎一致、明显复制 JD 作为简历、无任何个人信息、项目、教育、工作经历），
9 个隐性维度统一给 **5 分**（中性）：信息不足不等于“全面差”，在没有证据表明候选人本身有问题的情况下不应给 1-3 分。
仅在可以明确判断“负面信号”时才给低分。

你输出的 hidden_score 字段**会被系统覆写**，不要填，系统会从 breakdown 计算加权分。

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

        # 清理 + 截断长简历 / JD（v2.0 修复）
        safe_resume = truncate_for_prompt(clean_resume_text(resume_text or ''), max_chars=3000)
        safe_jd = truncate_for_prompt(jd_content or '', max_chars=1500)

        prompt = f"""## 任务
你是隐性因素评估师，请**只从隐性条件和潜在风险角度**评估候选人。
不要评估技术能力或软技能，专注挖掘简历背后的隐性信息。

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

### 2. 隐性条件对照匹配（v3.6.4 精简版）

将岗位隐性需求与候选人实际逐项对照，**必须输出以下 10 个维度**，缺少的维度也要以“无法判断”填充。

**岗位隐性维度（6 个，从 JD 提取）：**
1. 抗压能力（stress_tolerance）
2. 技术领导力（management_potential）—— 非人员管理，技术深度+问题解决
3. 沟通复杂度（communication_complexity）
4. 稳定性期望（stability_expectation）
5. 学历偏好（education_preference）
6. 技术栈匹配度（隐性 tech_stack_match）

**简历自身维度（4 个，从简历推断）【v3.6.4 新增】：**
7. 简历真实度（resume_authenticity）—— 检测包装痕迹
8. 学习能力（learning_ability）—— 从技术栈更新/自学经历推断
9. 职业发展方向（career_direction）—— 与岗位匹配度
10. 居住地（residence）—— 当前城市+迁移意愿

每条说明 (**detail**) **≤40 字**，岗位要求与候选人实际各 **≤ 30 字**，要简洁，不要重复。

### 3. 简历真实度检测
- "参与"≠"主导"，注意角色描述
- 成果数字是否合理（太高可能是包装）
- 模糊描述（"优化了性能"但不说多少）
- 技术栈罗列但无项目应用

## 输出格式（严格 JSON）

**注意：`hidden_score` 字段不要填（会被系统覆写）。`hidden_score_breakdown` 必填，由系统计算加权分。**

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
    "hidden_summary": "2-3句话的隐性条件总结评估",
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
    }}
}}"""
        llm_result = self.think_json(prompt)
        if not isinstance(llm_result, dict):
            return llm_result

        # 【v2.1 BUG B 修复】系统计算 hidden_score（9 个维度 1-10 分加权）
        # 避免 LLM 虚高（resume_coordinator 的 20% 隐性权重依赖该值）
        llm_result['hidden_score'] = self._compute_hidden_score(llm_result)
        llm_result['hidden_score_source'] = 'system:9_dim_avg'

        return llm_result

    def _compute_hidden_score(self, llm_result):
        """【v2.1 BUG B 修复】从 breakdown 9 个 1-10 分计算加权综合分（0-100）。

        9 项平均产出 0-10 分，乘 10 转 0-100。
        维度缺失或异常值时退回到中立 5 分。

        Args:
            llm_result: LLM 返回的 dict

        Returns:
            int: 0-100 范围的隐性匹配综合分
        """
        breakdown = (llm_result or {}).get('hidden_score_breakdown') or {}
        KEYS = (
            'education', 'residence', 'career_direction', 'job_stability',
            'emotional_stability', 'communication_ability', 'teamwork_style',
            'learning_ability', 'resume_authenticity',
        )

        def _val(name):
            v = breakdown.get(name)
            if isinstance(v, (int, float)) and 1 <= v <= 10:
                return float(v)
            return 5.0  # 默认中立

        if not breakdown:
            # 整个 breakdown 缺失，返回中立分
            return 50

        values = [_val(k) for k in KEYS]
        # 只算实际提供的维度，但要求 9 个都给；如果都没给则返回 50
        provided = [v for k, v in zip(KEYS, values) if k in breakdown]
        if not provided:
            return 50
        score_10 = sum(provided) / len(provided)

        # 【v2.1 兑底防 LLM 严重偏低】
        # 当 LLM 把 9 个维度都打到 1 分（avg ≤ 2.5/10）时，
        # 通常是“简历信息不足”而非“候选人本身有重大问题”。
        # 强制升至 5/10（50 分）兑底，避免空简历拿 10 分。
        if score_10 <= 2.5:
            logger.warning(
                f'[隐性 9 维全低] avg={score_10:.2f}/10 → 兑底升至 50 分'
            )
            score_10 = 5.0

        return int(round(score_10 * 10))
