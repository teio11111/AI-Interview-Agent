"""简历分析服务 - 委托给简历评估师 Agent"""
from services.agent_orchestrator import AgentOrchestrator
from utils.logger import logger
import json


class ResumeService:
    """简历分析服务（委托给简历评估师 Agent）"""

    @staticmethod
    def analyze_resume(position, resume_text, candidate_name=''):
        """分析简历与岗位的匹配度

        Args:
            position: Position 模型对象
            resume_text: 简历文本

        Returns:
            dict: 分析结果（含 match_score），失败返回 None
        """
        from services.interview_service import get_orchestrator
        orch = get_orchestrator()
        
        # 解析岗位分析结果（含隐性需求），传给简历评估师做对照
        position_analysis = None
        if position.ai_analysis:
            try:
                position_analysis = json.loads(position.ai_analysis) if isinstance(position.ai_analysis, str) else position.ai_analysis
            except (json.JSONDecodeError, TypeError):
                logger.warning('岗位分析结果解析失败，简历评估将不包含隐性条件对照')
        
        result = orch.evaluate_resume(
            position.name,
            position.tech_requirements or '',
            position.jd_content or '',
            resume_text,
            position_analysis,
            candidate_name
        )

        if result:
            logger.info(f'简历分析完成，匹配度: {result.get("match_score", "N/A")}')
            mapping = result.get('implicit_requirement_mapping', [])
            if mapping:
                logger.info(f'隐性条件对照: {len(mapping)} 个维度')
        else:
            logger.error('简历分析失败')

        return result
