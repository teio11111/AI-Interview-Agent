"""面试汇总师 Agent - 综合三位评估师的评分生成最终面试报告"""
from agents.base_agent import BaseAgent
import json


class InterviewEvalCoordinatorAgent(BaseAgent):
    """面试汇总师

    职责：接收项目评估师、技术评估师、素质评估师的评估结果，
    综合汇总生成本轮面试的最终评价报告。
    """
    AGENT_NAME = "面试汇总师"
    SYSTEM_PROMPT = """你是「面试汇总师」，面试评价的最终汇总人。

你的核心职责：
- 综合三位评估师（项目评估师、技术评估师、素质评估师）的评估结果
- 整合各方原始数据，产出一个能反映三方意见的综合评语
- 合并优势和不足，确保每条都有面试证据支撑
- 给出面向候选人的反馈（温和、建设性）

工作原则：
- **【重要】综合评分（0-100）与「招聘建议」等级，均由系统根据三方维度分自动加权计算与映射，你不需要、也不应该计算这两个字段。**
- 你的任务聚焦在"叙述性评语"：整合 strengths / weaknesses / follow_up_performance / summary / candidate_summary / interview_highlights
- 优势和不足从三方报告中合并去重，保留最有面试证据支撑的
- 如果三位评估师对某项评价有分歧，取多数意见或并列保留
- 招聘建议要明确，不含糊
- 面向候选人的反馈要温和、建设性

请始终以严格的 JSON 格式输出，不要输出任何解释性文字。"""

    # ---- 权重与推荐等级映射表 ----
    # 【v2.1 BUG A 修复】汇总师重新评估 5 维评分（技术基础/项目经验/系统设计/沟通表达/学习能力），
    # 综合分由这 5 维加权得出（每项 1-10，权重 0.20），避免老版本"取三个评估师维度各自平均"造成的脱钩问题。
    W_TECH_FOUNDATION = 0.20   # 技术基础
    W_PROJECT_EXP = 0.20       # 项目经验
    W_SYSTEM_DESIGN = 0.20     # 系统设计
    W_COMMUNICATION = 0.20     # 沟通表达
    W_LEARNING = 0.20          # 学习能力

    # 综合分公式：final = 单轮平均 × 60% + 汇总师5维加权 × 40%
    # 单轮平均：从每条对话的实时 score（1-10）取平均，反映候选人在每个问答上的真实表现
    # 汇总师5维加权：横切 5 个维度的综合分，反映整场面试的综合性
    W_SINGLE_ROUND = 0.60  # 单轮实时评分权重（必须高，让单轮有话语权）
    W_COORD_5DIM = 0.40     # 汇总师 5 维评分权重（v2.1: 由 5 维加权替代老 W_COORD_DIM）

    RECOMMENDATION_TABLE = [
        (80, '强烈推荐'),
        (65, '推荐'),
        (45, '待定'),
        (0,  '不推荐'),
    ]

    def _compute_5dim_weighted_score(self, llm_result):
        """【v2.1 BUG A 修复】从汇总师输出的 5 维评分计算加权综合分（0-100）。

        5 维各 0.20，加权和产出 0-10 范围分数，乘 10 转 0-100。
        维度缺失时退回到中立 5 分。

        Args:
            llm_result: 汇总师 think_json 返回的 dict

        Returns:
            float: 0-100 范围的加权分
        """
        dims = (llm_result or {}).get('dimensions') or {}

        def _val(name):
            v = dims.get(name)
            if isinstance(v, (int, float)) and 1 <= v <= 10:
                return float(v)
            return 5.0  # 默认中立

        score_10 = (
            _val('技术基础') * self.W_TECH_FOUNDATION
            + _val('项目经验') * self.W_PROJECT_EXP
            + _val('系统设计') * self.W_SYSTEM_DESIGN
            + _val('沟通表达') * self.W_COMMUNICATION
            + _val('学习能力') * self.W_LEARNING
        )
        return round(score_10 * 10, 2)

    def _recommendation_for(self, score):
        """根据分数映射招聘建议"""
        for threshold, label in self.RECOMMENDATION_TABLE:
            if score >= threshold:
                return label
        return '不推荐'

    def _recommendation_reason_for(self, score, dims):
        """根据综合分与 5 维评分生成 1 句话推荐理由

        Args:
            score: 综合分（0-100）
            dims: 汇总师输出的 5 维评分 dict
        """
        label = self._recommendation_for(score)
        # 找最弱维度（仅供推荐理由使用）
        weakest_name, weakest_v = None, 999
        for k, v in (dims or {}).items():
            if isinstance(v, (int, float)) and 1 <= v <= 10:
                if v < weakest_v:
                    weakest_v = v
                    weakest_name = k

        if label == '强烈推荐':
            return f'本轮面试表现全面优秀，综合 {score} 分，可直接进入 offer 环节。'
        if label == '推荐':
            return f'本轮面试表现良好，综合 {score} 分，推荐推进下一轮。'
        if label == '待定':
            if weakest_name:
                return f'本轮面试综合中等（{score} 分），「{weakest_name}」维度（{weakest_v}/10）需进一步考察或下轮验证。'
            return f'本轮面试综合中等（{score} 分），需进一步考察。'
        return f'本轮面试表现低于岗位基本要求（{score} 分），不推荐推进。'

    def synthesize(self, project_result, tech_result, soft_result,
                   position_name, candidate_name, single_round_scores=None):
        """汇总三位评估师的结果

        Args:
            project_result: 项目评估师的评估结果
            tech_result: 技术评估师的评估结果
            soft_result: 素质评估师的评估结果
            position_name: 岗位名称
            candidate_name: 候选人姓名
            single_round_scores: 【新增】单轮实时评分列表，每个为 1-10 分制
                                  来自每条对话的 AI 实时评估 feedback.score

        Returns:
            dict: 最终面试评价报告（含由系统计算的 overall_score / recommendation）
        """
        prompt = f"""## 任务
你作为「面试汇总师」，需要在三位评估师报告基础上**重新评估 5 维评分**，
为本轮面试生成最终评价报告。

## 输入数据

### 项目评估师结果
{json.dumps(project_result or {}, ensure_ascii=False, indent=2)}

### 技术评估师结果
{json.dumps(tech_result or {}, ensure_ascii=False, indent=2)}

### 素质评估师结果
{json.dumps(soft_result or {}, ensure_ascii=False, indent=2)}

## 【v2.1 重要】重新评估 5 维评分（必填，权重 0.20×5=1.00）

**不要**直接把三方评估师的分取平均！**你要根据三个评估师的报告内容，综合出横跨项目/技术/系统/沟通/学习这 5 个维度的统一评分**。

### 5 维评分原则（严禁虚高）
- **9-10**：远超岗位要求，业内顶尖（要有面试中的具体证据，不能凭印象）
- **7-8**：明显高于平均（技术基础强、回答有深度、项目有细节）
- **5-6**：接近平均（普通水平，**5 分才是真实中位**，不要默认打 6-7）
- **3-4**：低于岗位基本要求（回答模糊、无细节、问诼较多）
- **1-2**：明显不合格（答非所问、虚构项目）

### 各维度的考察重点
- **技术基础**（1-10）：候选人核心技术的掌握程度。**参考技术评估师**，结合项目中的代码细节问题。
- **项目经验**（1-10）：候选人项目经验的真实性与深度。**参考项目评估师**，结合技术/素质评估师对项目的观察。
- **系统设计**（1-10）：候选人架构思维和方案设计能力。**参考技术评估师**，结合项目评估师对技术选型的描述。
- **沟通表达**（1-10）：候选人回答的逻辑性、清晰度、能否让听众迅速理解。**参考素质评估师**，结合三位评估师对细节描述的判断。
- **学习能力**（1-10）：候选人面对未知领域的态度、学习速度、问题分解能力。**参考素质评估师**，结合技术评估师的追问表现。

## 汇总要求

## 评分计算规则
**以下计算由系统在后方统一处理，你不需要重复计算**：
- 汇总师重新评估的 5 维评分各权重 0.20，加权产出 0-10 分，乘 10 转 0-100
- 最终综合分 = 单轮实时平均 × 60% + 汇总师 5 维加权 × 40%
- 系统根据综合分自动映射招聘建议等级并填充 `overall_score`、`recommendation`、`recommendation_reason` 字段
- 你输出的对应字段会被系统覆写

## 其他任务

1. **优势和不足**：从三方报告中合并去重，每条必须有面试证据
2. **追问表现**：综合素质评估师的 follow_up_performance
3. **面向候选人的反馈（candidate_summary）**：3-5 句话，以 "{candidate_name}您好" 开头，先肯定优点再指出可提升方向，最后给具体可操作建议。语气温和、建设性。不要用 "不推荐" "包装" "风险" 等内部决策用语。
4. **综合评价总结（summary）**：3-4 句话，用面试观察事实描述候选人面试表现。
5. **面试亮点 / 污点（interview_highlights）**：根据三方评语提炼，不虚构。

## 输出格式（严格 JSON）

**注意：以下 `overall_score`、`recommendation`、`recommendation_reason` 三个字段你**不要填**（你填了也会被系统覆写）。其他字段全部必填。**

{{
    "dimensions": {{
        "技术基础": 7,
        "项目经验": 6,
        "系统设计": 5,
        "沟通表达": 8,
        "学习能力": 7
    }},
    "strengths": [
        {{"point": "优势描述", "evidence": "面试中对应的具体表现"}}
    ],
    "weaknesses": [
        {{"point": "不足描述", "evidence": "面试中对应的具体表现", "suggestion": "改进建议"}}
    ],
    "follow_up_performance": "追问环节的表现评估",
    "summary": "3-4句话综合评价",
    "interview_highlights": {{
        "best_answer": "回答最好的问题方向",
        "worst_answer": "表现最差的问题方向",
        "best_follow_up": "追问环节表现最好的部分",
        "weakest_follow_up": "追问环节暴露最多问题的部分"
    }},
    "candidate_summary": "面向候选人本人的反馈（3-5句话，温和、建设性语气）"
}}"""
        llm_result = self.think_json(prompt)
        if not isinstance(llm_result, dict):
            # LLM 调用失败，直接返回不覆盖 overall_score / recommendation
            return llm_result

        # ---------------------------
        # 【v2.1 BUG A 修复】综合分：直接读汇总师重新评估的 5 维评分，加权产出
        # ---------------------------
        coord_5dim_100 = self._compute_5dim_weighted_score(llm_result)

        # 【Bug 修复】综合分与单轮实时评分挂钩
        # 原来的 overall_score 仅取汇总师重新评的 5 维分（虚高），不反映每条对话的实时评分。
        # 新公式：综合分 = 单轮平均×60% + 汇总师 5 维加权×40%
        #   - single_round_avg：每条对话实时评分（1-10）的算术平均
        #   - single_round_score_100：转 0-100 分制
        #   - 如果没传单轮评分（老调用/数据缺失），退回到纯汇总师 5 维分
        single_round_avg = None
        if single_round_scores:
            valid = [s for s in single_round_scores if isinstance(s, (int, float)) and 1 <= s <= 10]
            if valid:
                single_round_avg = round(sum(valid) / len(valid), 2)
                single_round_score_100 = round(single_round_avg * 10, 1)
                overall_score = int(round(
                    self.W_SINGLE_ROUND * single_round_score_100
                    + self.W_COORD_5DIM * coord_5dim_100
                ))
            else:
                overall_score = int(round(coord_5dim_100))
        else:
            overall_score = int(round(coord_5dim_100))

        recommendation = self._recommendation_for(overall_score)
        recommendation_reason = self._recommendation_reason_for(
            overall_score, llm_result.get('dimensions') or {}
        )

        # 覆盖 LLM 可能误填的字段（确保一致）
        llm_result['overall_score'] = overall_score
        llm_result['recommendation'] = recommendation
        llm_result['recommendation_reason'] = recommendation_reason

        # 5 维评分转 0-100（前端展示用）
        dims_100 = {}
        for k, v in (llm_result.get('dimensions') or {}).items():
            if isinstance(v, (int, float)) and 1 <= v <= 10:
                dims_100[k] = round(v * 10, 1)

        # 同步更新 score_breakdown（v2.1: 展示 5 维加权拆解）
        llm_result['score_breakdown'] = {
            'five_dim_score_100': round(coord_5dim_100, 2),
            'five_dim_per_dim_100': dims_100,
            'weights_5dim': {
                'tech_foundation': self.W_TECH_FOUNDATION,
                'project_exp': self.W_PROJECT_EXP,
                'system_design': self.W_SYSTEM_DESIGN,
                'communication': self.W_COMMUNICATION,
                'learning': self.W_LEARNING,
            },
            'final_weights': {
                'single_round': self.W_SINGLE_ROUND,
                'coord_5dim': self.W_COORD_5DIM,
            },
        }

        # 计算明细，调试/验证用（前端可选择展示）
        llm_result['computation'] = {
            'single_round_avg': single_round_avg,
            'single_round_score_100': round(single_round_avg * 10, 1) if single_round_avg else None,
            'coord_5dim_100': round(coord_5dim_100, 2),
            'formula': 'final = 单轮平均×60% + 汇总师 5 维加权×40%',
            'weights': {
                'single_round': self.W_SINGLE_ROUND,
                'coord_5dim': self.W_COORD_5DIM,
                'five_dim': {
                    'tech_foundation': self.W_TECH_FOUNDATION,
                    'project_exp': self.W_PROJECT_EXP,
                    'system_design': self.W_SYSTEM_DESIGN,
                    'communication': self.W_COMMUNICATION,
                    'learning': self.W_LEARNING,
                },
            },
        }

        return llm_result
