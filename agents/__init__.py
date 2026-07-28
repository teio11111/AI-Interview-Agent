"""Agent 包"""
# 基类
from agents.base_agent import BaseAgent

# 岗位分析（1个）
from agents.position_analyst import PositionAnalystAgent

# 简历评估（3个专家 + 1个汇总）
from agents.tech_evaluator import TechEvaluatorAgent
from agents.soft_evaluator import SoftEvaluatorAgent
from agents.hidden_evaluator import HiddenEvaluatorAgent
from agents.resume_coordinator import ResumeCoordinatorAgent

# 出题（3个出题官 + 1个选题官）
from agents.project_questioner import ProjectQuestionerAgent
from agents.skill_questioner import SkillQuestionerAgent
from agents.weakness_questioner import WeaknessQuestionerAgent
from agents.question_coordinator import QuestionCoordinatorAgent

# 面试（2个顾问 + 1个主面试官）
from agents.tech_interviewer import TechInterviewerAgent
from agents.soft_interviewer import SoftInterviewerAgent
from agents.interviewer import InterviewerAgent

# 面试评价（3个评估师 + 1个汇总师）
from agents.interview_project_evaluator import InterviewProjectEvaluatorAgent
from agents.interview_tech_evaluator import InterviewTechEvaluatorAgent
from agents.interview_soft_evaluator import InterviewSoftEvaluatorAgent
from agents.interview_eval_coordinator import InterviewEvalCoordinatorAgent

# 板块切分（1个，面试结束后使用）
from agents.topic_segmenter import TopicSegmenterAgent

# 综合元评估（1个，最后阶段的最终裁判）
from agents.comprehensive_meta_evaluator import ComprehensiveMetaEvaluatorAgent

# ============================================================
# ⚠️ v1.0 保留 Agent（DEPRECATED，自 v2.0 起不再使用）
# ============================================================
# 以下 3 个 Agent 已废弃，但保留文件作 archive。**不会自动 export**，
# 业务代码如需调用，必须显式 import（同时触发 DeprecationWarning 提醒）。
# - agents.evaluator.EvaluatorAgent            → 用 InterviewEvalCoordinatorAgent
# - agents.resume_evaluator.ResumeEvaluatorAgent → 用 ResumeCoordinatorAgent
# - agents.question_designer.QuestionDesignerAgent → 用 QuestionCoordinatorAgent
# ============================================================

__all__ = [
    'BaseAgent',
    'PositionAnalystAgent',
    # 简历评估
    'TechEvaluatorAgent',
    'SoftEvaluatorAgent',
    'HiddenEvaluatorAgent',
    'ResumeCoordinatorAgent',
    # 出题
    'ProjectQuestionerAgent',
    'SkillQuestionerAgent',
    'WeaknessQuestionerAgent',
    'QuestionCoordinatorAgent',
    # 面试
    'TechInterviewerAgent',
    'SoftInterviewerAgent',
    'InterviewerAgent',
    # 面试评价（3+1）
    'InterviewProjectEvaluatorAgent',
    'InterviewTechEvaluatorAgent',
    'InterviewSoftEvaluatorAgent',
    'InterviewEvalCoordinatorAgent',
    # 板块切分
    'TopicSegmenterAgent',
    # 综合元评估
    'ComprehensiveMetaEvaluatorAgent',
    # ⚠️ 注意：以下 3 个 v1.0 Agent 不再 export，需显式 import
    # 'EvaluatorAgent',          # v2.0: 用 InterviewEvalCoordinatorAgent
    # 'ResumeEvaluatorAgent',    # v2.0: 用 ResumeCoordinatorAgent
    # 'QuestionDesignerAgent',   # v2.0: 用 QuestionCoordinatorAgent
]