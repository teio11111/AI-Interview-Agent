"""面试服务 - 委托给 Agent 编排器执行"""
from services.agent_orchestrator import AgentOrchestrator
from services.llm_service import LlmService
from utils.logger import logger
import json


# 全局编排器实例
_orchestrator = None

def get_orchestrator():
    """获取全局编排器（懒加载）"""
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = AgentOrchestrator()
    return _orchestrator


class InterviewService:
    """面试服务（编排层）
    
    所有业务逻辑委托给 AgentOrchestrator，保持 API 路由不变。
    """

    @staticmethod
    def generate_questions(position, candidate, position_analysis, resume_analysis, resume_text=None):
        """生成面试问题（委托给出题官 Agent）

        Args:
            position: Position 模型
            candidate: Candidate 模型
            position_analysis: 岗位分析结果 (dict 或 str)
            resume_analysis: 简历评估结果 (dict 或 str)
            resume_text: 候选人简历原文

        Returns:
            dict: 问题列表，失败返回 None
        """
        orch = get_orchestrator()
        return orch.design_questions(
            position.name,
            position.tech_requirements or '',
            position_analysis,
            resume_analysis,
            resume_text or candidate.resume_text or ''
        )

    @staticmethod
    def get_dialog_feedback(candidate_name, position_name, resume_text, dialog_history, question, answer):
        """获取面试问答反馈（委托给面试官 Agent）

        Returns:
            dict: 反馈结果，失败返回 None
        """
        orch = get_orchestrator()
        return orch.evaluate_dialog(
            candidate_name, position_name, resume_text,
            dialog_history, question, answer
        )

    @staticmethod
    def generate_follow_up(resume_text, dialog_chain):
        """生成连续追问（委托给面试官 Agent）

        Returns:
            dict: 追问结果，失败返回 None
        """
        orch = get_orchestrator()
        return orch.generate_follow_up(resume_text, dialog_chain)

    @staticmethod
    def generate_report(position, candidate_name, full_dialogs_text, resume_analysis=None):
        """生成评价报告（委托给评价官 Agent）

        Args:
            position: Position 模型
            candidate_name: 候选人姓名
            full_dialogs_text: 全部对话文本
            resume_analysis: 简历评估结果（可选，用于交叉验证）

        Returns:
            dict: 评价报告，失败返回 None
        """
        orch = get_orchestrator()
        return orch.generate_report(
            position.name,
            position.tech_requirements or '',
            candidate_name,
            full_dialogs_text,
            resume_analysis
        )
