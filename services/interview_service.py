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
    支持 on_progress 回调用于 SSE 实时推送。
    """

    @staticmethod
    def analyze_position(position_name, tech_requirements, jd_content, on_progress=None):
        """岗位分析（委托给岗位分析师 Agent）

        Returns:
            dict: 岗位分析结果，失败返回 None
        """
        orch = get_orchestrator()
        return orch.analyze_position(position_name, tech_requirements, jd_content,
                                     on_progress=on_progress)

    @staticmethod
    def evaluate_resume(position_name, tech_requirements, jd_content,
                        resume_text, position_analysis=None, candidate_name='',
                        on_progress=None):
        """简历评估（委托给多智能体协作评估）

        Returns:
            dict: 简历评估结果，失败返回 None
        """
        orch = get_orchestrator()
        return orch.evaluate_resume(
            position_name, tech_requirements, jd_content,
            resume_text, position_analysis, candidate_name,
            on_progress=on_progress
        )

    @staticmethod
    def generate_questions(position, candidate, position_analysis, resume_analysis,
                           resume_text=None, on_progress=None):
        """生成面试问题（委托给多智能体出题协作）

        Returns:
            dict: 问题列表，失败返回 None
        """
        orch = get_orchestrator()
        return orch.design_questions(
            position.name,
            position.tech_requirements or '',
            position_analysis,
            resume_analysis,
            resume_text or candidate.resume_text or '',
            on_progress=on_progress
        )


    @staticmethod
    def get_dialog_feedback(candidate_name, position_name, resume_text,
                            dialog_history, question, answer, on_progress=None):
        """获取面试问答反馈（委托给多智能体面试协作）

        Returns:
            dict: 反馈结果，失败返回 None
        """
        orch = get_orchestrator()
        return orch.evaluate_dialog(
            candidate_name, position_name, resume_text,
            dialog_history, question, answer,
            on_progress=on_progress
        )

    @staticmethod
    def generate_follow_up(resume_text, dialog_chain):
        """生成连续追问（委托给主面试官 Agent）

        Returns:
            dict: 追问结果，失败返回 None
        """
        orch = get_orchestrator()
        return orch.generate_follow_up(resume_text, dialog_chain)

    @staticmethod
    def segment_topics(candidate_name, position_name, full_dialogs, on_progress=None):
        """板块切分（委托给板块切分师 Agent，单Agent）

        Args:
            candidate_name: 候选人姓名
            position_name: 岗位名称
            full_dialogs: 完整对话列表 [{'seq', 'question', 'answer'}]
            on_progress: 进度回调

        Returns:
            dict: 板块切分结果（含 topics 列表），失败返回 None
        """
        orch = get_orchestrator()
        return orch.segment_topics(candidate_name, position_name, full_dialogs, on_progress=on_progress)

    @staticmethod
    def generate_report(position, candidate_name, full_dialogs_text,
                        questions_plan=None, single_round_scores=None,
                        on_progress=None):
        """生成本轮面试评价报告（委托给 3+1 多智能体）

        Args:
            position: Position 模型
            candidate_name: 候选人姓名
            full_dialogs_text: 全部对话文本
            questions_plan: 出题策略（可选）
            single_round_scores: 【新增】每条对话实时评分（1-10），会传给汇总师

        Returns:
            dict: 面试评价报告，失败返回 None
        """
        orch = get_orchestrator()
        return orch.generate_report(
            position.name,
            position.tech_requirements or '',
            candidate_name,
            full_dialogs_text,
            questions_plan=questions_plan,
            single_round_scores=single_round_scores,
            on_progress=on_progress
        )
