"""⚠️ DEPRECATED: 出题官 Agent (v1.0 单 Agent 架构)

⚠️ 本文件已废弃，自 v2.0 多 Agent 架构起不再使用：

✅ v2.0 替代方案（3 个出题官 + 1 个选题官）：
- 项目出题官：agents.project_questioner.ProjectQuestionerAgent
- 技能出题官：agents.skill_questioner.SkillQuestionerAgent
- 短板出题官：agents.weakness_questioner.WeaknessQuestionerAgent
- 选题官：agents.question_coordinator.QuestionCoordinatorAgent

⚠️ 本文件作为历史代码保留，仅供查阅。

保留原因：v1.0 与 v2.0 架构过渡期间，业务方可能仍在引用老接口，避免强制删除破坏依赖。
如需查看 v1.0 出题逻辑，请参考 git 历史或 ARCHIVE_README。

Deprecated since: v2.0 (2026-07-15)
"""
from agents.base_agent import BaseAgent


class QuestionDesignerAgent(BaseAgent):
    """出题官
    
    职责：基于候选人简历和岗位分析结果，设计针对性面试问题。
    输出：6-8 个结构化问题（含分类、难度、追问提示）。
    """
    AGENT_NAME = "出题官"
    SYSTEM_PROMPT = """你是「出题官」，一位擅长技术面试题目设计的专家。

你的出题哲学：
- 绝不问"请介绍xxx"这种背诵题，而是用项目场景切入
- 每个问题必须追溯到候选人简历中的具体内容（项目/技术/经验）
- 关注候选人"做了什么"而非"知道什么"
- 问题要有梯度：从验证基础到探测深度
- **问题要精简**：一次最多聚焦 2 个功能点/技术点，避免大而泛
- **必须给出回答方向**：每道题附 2-4 个关键词/回答方向，便于候选人/面试官把握要点

工作原则：
- 出题必须引用简历原文（resume_reference），不能凭空出题
- 4 类题目配比：项目深挖(3) + 技能验证(2) + 短板探测(1-2) + 场景设计(1)
- 每道题都预设追问方向（follow_up_hints）
- 每道题必须给出 answer_directions（回答方向/关键词，2-4 个）
- 按 category + difficulty 排序输出

请始终以严格的 JSON 格式输出，不要输出任何解释性文字。"""

    def design_questions(self, position_name, tech_requirements, 
                         position_analysis, resume_analysis, resume_text):
        """设计面试问题

        Args:
            position_name: 岗位名称
            tech_requirements: 技术要求
            position_analysis: 岗位分析结果（岗位分析师的输出）
            resume_analysis: 简历评估结果（简历评估师的输出）
            resume_text: 候选人简历原文

        Returns:
            dict: 问题列表
        """
        prompt = f"""## 任务
基于候选人的**真实简历内容**和岗位要求，设计一套有针对性的面试问题。
每个问题必须能追溯到简历中的具体内容，**问题要精简（单题最多聚焦 2 个功能点）**，并必须附上回答方向/关键词。

## 岗位信息
- 岗位名称：{position_name}
- 技术要求：{tech_requirements or ''}

## 岗位分析师的分析结果
{self.summarize(position_analysis)}

## 简历评估师的评估结果
{self.summarize(resume_analysis)}

## 候选人简历原文
{resume_text or '暂无'}

## 出题策略（严格按此执行）

### 1. 项目经历深挖题（必须 3 题）
从简历中提取具体项目，针对每个项目设计 1 道深挖题：
- 问具体负责内容和技术挑战
- 问技术选型原因和替代方案
- 问改进思路
- **每个问题只聚焦 2 个以内的技术点/功能点**

### 2. 技能验证题（必须 2 题）
针对声称掌握的核心技能，设计**实操场景题**：
- 不问"什么是xxx"，而是"假设线上系统出现xxx问题，怎么排查？"
- 针对"精通"的技能出 hard 题验证
- **每个问题只聚焦 2 个以内的技术点**

### 3. 短板探测题（1-2 题）
从简历评估的 missing_skills 和 risks 出发：
- 技能"了解但不深入" → 出题探底
- 模糊描述"参与过" → 追问具体贡献
- **问题精简，最多 2 个探测点**

### 4. 场景设计题（1 题）
给实际工作场景，考察系统设计能力，难度 medium-hard，**问题应聚焦 1-2 个核心设计点**

## 输出格式（严格 JSON，6-8 个问题）
{{
    "questions": [
        {{
            "question": "具体问题（必须引用简历中的项目/技术/经历，单题聚焦 1-2 个功能点）",
            "category": "项目深挖/技能验证/短板探测/场景设计",
            "difficulty": "easy/medium/hard",
            "resume_reference": "简历中对应的原文引用",
            "intent": "这道题想考察什么能力",
            "expected_depth": "候选人应该回答到什么程度算合格",
            "answer_directions": ["关键词或方向1", "关键词或方向2", "关键词或方向3"],
            "follow_up_hints": ["回答好可追问什么", "回答模糊应追问什么"]
        }}
    ]
}}"""
        result = self.think_json(prompt)
        
        # 按优先级排序
        if result and isinstance(result, dict) and 'questions' in result:
            priority = {'项目深挖': 0, '技能验证': 1, '短板探测': 2, '场景设计': 3}
            diff_order = {'hard': 0, 'medium': 1, 'easy': 2}
            result['questions'].sort(key=lambda q: (
                priority.get(q.get('category', ''), 99),
                diff_order.get(q.get('difficulty', ''), 9)
            ))
        
        return result

    def revise_questions(self, original_questions, review_feedback, resume_text):
        """根据审核反馈修订题目（Agent辩论机制）

        Args:
            original_questions: 原始题目
            review_feedback: 审核官的反馈
            resume_text: 候选人简历原文

        Returns:
            dict: 修订后的问题列表
        """
        import json
        original_text = json.dumps(original_questions.get('questions', []) if isinstance(original_questions, dict) else [], ensure_ascii=False, indent=2)
        feedback_text = json.dumps(review_feedback, ensure_ascii=False, indent=2)
        
        prompt = f"""## 任务
你之前设计的面试题目被审核专家提出了修改意见，请根据反馈修订题目。

## 原始题目
{original_text}

## 审核反馈
{feedback_text}

## 候选人简历（供参考）
{resume_text or '暂无'}

## 修订原则
1. 只修改审核反馈中指出的问题，不要改动其他题目
2. 如果审核指出缺少某个风险点的探测，补充对应题目
3. 修订后的题目仍需引用简历原文
4. 保持原有的 JSON 格式和排序规则

## 输出格式（完整 JSON，包含所有题目）
{{
    "questions": [
        {{
            "question": "修订后的问题（单题聚焦 1-2 个功能点）",
            "category": "项目深挖/技能验证/短板探测/场景设计",
            "difficulty": "easy/medium/hard",
            "resume_reference": "简历中对应的原文引用",
            "intent": "这道题想考察什么能力",
            "expected_depth": "候选人应该回答到什么程度算合格",
            "answer_directions": ["关键词或方向1", "关键词或方向2", "关键词或方向3"],
            "follow_up_hints": ["追问方向1", "追问方向2"]
        }}
    ],
    "revision_notes": "简要说明修订了哪些内容"
}}"""
        result = self.think_json(prompt)
        
        # 排序
        if result and isinstance(result, dict) and 'questions' in result:
            priority = {'项目深挖': 0, '技能验证': 1, '短板探测': 2, '场景设计': 3}
            diff_order = {'hard': 0, 'medium': 1, 'easy': 2}
            result['questions'].sort(key=lambda q: (
                priority.get(q.get('category', ''), 99),
                diff_order.get(q.get('difficulty', ''), 9)
            ))
        
        return result
