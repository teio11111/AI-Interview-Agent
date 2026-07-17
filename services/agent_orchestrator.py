"""Agent 编排器 - 协调多智能体协作完成面试流程"""
from agents import (
    PositionAnalystAgent,
    ResumeEvaluatorAgent,
    QuestionDesignerAgent,
    InterviewerAgent,
    EvaluatorAgent
)
from utils.logger import logger


class AgentOrchestrator:
    """Agent 编排器
    
    协调 5 个专业 Agent 完成完整的 AI 面试流程：
    1. 岗位分析师 → 分析岗位 JD
    2. 简历评估师 → 评估简历匹配度
    3. 出题官 → 设计面试问题初稿
    4. 简历评估师 → 审核出题质量（Agent辩论）
    5. 出题官 → 根据审核反馈修订（如未通过）
    6. 面试官 → 评估回答 + 生成追问
    7. 评价官 → 生成综合评价报告
    
    特色机制：Agent辩论 - 出题官与简历评估师之间形成审核-修订循环，
    确保题目质量经过交叉校验后才输出。
    """

    def __init__(self):
        """初始化所有 Agent"""
        self.position_analyst = PositionAnalystAgent()
        self.resume_evaluator = ResumeEvaluatorAgent()
        self.question_designer = QuestionDesignerAgent()
        self.interviewer = InterviewerAgent()
        self.evaluator = EvaluatorAgent()
        logger.info('Agent 编排器初始化完成，5 个 Agent 就绪')

    # ===== 岗位分析阶段 =====
    def analyze_position(self, position_name, tech_requirements, jd_content):
        """阶段1：岗位分析师分析岗位

        Returns:
            dict: 岗位分析结果
        """
        logger.info(f'[编排器] 阶段1: 岗位分析师 → {position_name}')
        return self.position_analyst.analyze(position_name, tech_requirements, jd_content)

    # ===== 简历评估阶段 =====
    def evaluate_resume(self, position_name, tech_requirements, jd_content, resume_text, position_analysis=None, candidate_name=''):
        """阶段2：简历评估师评估简历

        Args:
            position_analysis: 岗位分析结果（含隐性需求），用于隐性条件对照

        Returns:
            dict: 简历评估结果
        """
        logger.info(f'[编排器] 阶段2: 简历评估师')
        return self.resume_evaluator.evaluate(position_name, tech_requirements, jd_content, resume_text, position_analysis, candidate_name)

    # ===== 出题阶段（含辩论机制） =====
    def design_questions(self, position_name, tech_requirements, 
                         position_analysis, resume_analysis, resume_text):
        """阶段3：出题官设计面试问题 + 简历评估师审核 + 出题官修订
        
        Agent辩论机制：
        1. 出题官初稿
        2. 简历评估师审核（检查简历关联性、风险覆盖、难度合理性）
        3. 若未通过，出题官根据反馈修订
        4. 最多辩论 1 轮（避免过度调用）

        Returns:
            dict: 面试问题列表（含辩论过程记录）
        """
        # 第一轮：出题官出题
        logger.info(f'[编排器] 阶段3.1: 出题官初稿（接收岗位分析+简历评估结果）')
        questions = self.question_designer.design_questions(
            position_name, tech_requirements,
            position_analysis, resume_analysis, resume_text
        )
        
        # 第二轮：简历评估师审核（Agent辩论）
        logger.info(f'[编排器] 阶段3.2: 简历评估师审核出题质量')
        review = self.resume_evaluator.review_questions(
            questions, position_name, resume_text, resume_analysis
        )
        
        debate_log = [{
            'round': 1,
            'action': 'initial_design',
            'question_count': len(questions.get('questions', [])) if questions else 0
        }, {
            'round': 2,
            'action': 'review',
            'approved': review.get('approved', True) if review else True,
            'overall_comment': review.get('overall_comment', '审核通过') if review else '审核通过',
            'issue_count': len(review.get('issues', [])) if review else 0
        }]
        
        # 如果审核未通过，出题官修订
        if review and not review.get('approved', True):
            logger.info(f'[编排器] 阶段3.3: 出题官根据审核反馈修订题目')
            revised = self.question_designer.revise_questions(
                questions, review, resume_text
            )
            debate_log.append({
                'round': 3,
                'action': 'revision',
                'revision_notes': revised.get('revision_notes', '已修订') if revised else '已修订',
                'final_count': len(revised.get('questions', [])) if revised else 0
            })
            # 使用修订后的题目
            final_questions = revised
            logger.info(f'[编排器] 辩论完成：修订后 {len(final_questions.get("questions", []))} 题')
        else:
            final_questions = questions
            logger.info(f'[编排器] 审核通过，无需修订')
        
        # 将辩论记录附加到结果中
        if final_questions and isinstance(final_questions, dict):
            final_questions['debate_log'] = debate_log
        
        return final_questions

    # ===== 面试对话阶段 =====
    def evaluate_dialog(self, candidate_name, position_name, resume_text,
                        dialog_history, question, answer):
        """阶段4a：面试官评估候选人回答

        Returns:
            dict: 反馈结果（含追问建议）
        """
        logger.info(f'[编排器] 阶段4a: 面试官评估回答')
        return self.interviewer.evaluate_answer(
            candidate_name, position_name, resume_text,
            dialog_history, question, answer
        )

    def generate_follow_up(self, resume_text, dialog_chain):
        """阶段4b：面试官生成深度追问

        Returns:
            dict: 追问结果
        """
        logger.info(f'[编排器] 阶段4b: 面试官生成追问')
        return self.interviewer.generate_follow_up(resume_text, dialog_chain)

    # ===== 评价报告阶段 =====
    def generate_report(self, position_name, tech_requirements, 
                        candidate_name, full_dialogs, resume_analysis=None):
        """阶段5：评价官生成综合评价报告
        
        可选接收简历评估结果用于交叉验证。

        Returns:
            dict: 评价报告
        """
        logger.info(f'[编排器] 阶段5: 评价官生成报告')
        return self.evaluator.generate_report(
            position_name, tech_requirements,
            candidate_name, full_dialogs, resume_analysis
        )

    # ===== 完整流程编排 =====
    def run_full_pipeline(self, position, candidate):
        """执行完整的面试准备流水线（岗位分析 → 简历评估 → 出题）

        Args:
            position: Position 模型
            candidate: Candidate 模型

        Returns:
            dict: {
                'position_analysis': 岗位分析结果,
                'resume_analysis': 简历评估结果,
                'questions': 面试问题列表
            }
        """
        logger.info(f'[编排器] 启动完整流水线: {candidate.name} → {position.name}')
        
        # 阶段1：岗位分析
        position_analysis = self.analyze_position(
            position.name, position.tech_requirements, position.jd_content
        )
        
        # 阶段2：简历评估（传入岗位分析，用于隐性条件对照）
        resume_analysis = self.evaluate_resume(
            position.name, position.tech_requirements, 
            position.jd_content, candidate.resume_text,
            position_analysis
        )
        
        # 阶段3：出题（使用阶段1和2的输出）
        questions = self.design_questions(
            position.name, position.tech_requirements,
            position_analysis, resume_analysis, candidate.resume_text
        )
        
        logger.info(f'[编排器] 流水线完成，出题 {len(questions.get("questions", [])) if questions else 0} 道')
        
        return {
            'position_analysis': position_analysis,
            'resume_analysis': resume_analysis,
            'questions': questions
        }
