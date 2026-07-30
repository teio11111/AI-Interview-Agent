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
]
# v1.0 废弃 Agent（evaluator.py / resume_evaluator.py / question_designer.py）
# 已于 2026-07-28 物理删除，对应 CHANGELOG「P2 BUG」条目同步清除。