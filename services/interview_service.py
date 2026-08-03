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
    def _detect_position_type(position_name):
        """【bugfix】根据岗位名称识别岗位类型

        背景：兜底题库按后端模板硬编码导致前端/算法/数据岗位匹配到 java 关键词，
        出现「前端开发工程师面试题问 JAVA」的严重错位。

        Returns:
            str: 'frontend' | 'backend' | 'algorithm' | 'data' | 'test'
        """
        name = (position_name or '').lower()
        if any(kw in name for kw in ['前端', 'web', 'h5', '移动', '客户端', 'ios',
                                      'android', 'react', 'vue', 'angular', '小程序']):
            return 'frontend'
        if any(kw in name for kw in ['算法', 'nlp', 'cv', '推荐', '深度学习',
                                      '机器学习', '大模型', 'llm', 'rag', 'aigc']):
            return 'algorithm'
        if any(kw in name for kw in ['数据', '分析', 'bi', 'etl', '数仓',
                                      'data', 'analytics']):
            return 'data'
        if any(kw in name for kw in ['测试', 'qa', 'sdet', '测开']):
            return 'test'
        return 'backend'

    @staticmethod
    def _filter_skill_corpus(tech_requirements):
        """【bugfix】过滤「了解 X 后端更好」「加分: X」等修饰词

        背景：前端岗位 tech_requirements 里写「了解 java 后端更好」「加分: docker」
        会被误识别为主技能。剥离这些修饰项，只保留核心技术要求。
        """
        if not tech_requirements:
            return ''
        keep = []
        for raw in tech_requirements.replace('，', ',').split(','):
            item = raw.strip().lower()
            if not item:
                continue
            is_decoration = (
                ('了解' in item and ('后端' in item or '更好' in item or '更佳' in item or '更优' in item))
                or '加分' in item
                or item.startswith('或有')
                or '熟悉其他' in item
                or item.startswith('懂')
                or item.startswith('会点')
            )
            if not is_decoration:
                keep.append(item)
        return ' '.join(keep)

    @staticmethod
    def generate_fallback_questions(position, resume_text=''):
        """【v2.1 性能修复】纯代码生成兜底面试题（<0.5s 完成）

        背景：
          当 LLM 出题阶段被限流/超时（场景：MiniMax API 限流，需要 25-50s），
          为保证 analyze 接口 < 60s 返回，先用模板题立即返回给候选人。
          后台线程异步跑 LLM 真出题，生成完后覆盖 session.questions_plan。

        【bugfix】兜底题按岗位类型分组：
          - 前端：react/vue/js/ts/node，不混入 java/spring
          - 后端：java/spring/redis/mysql/kafka（保持原逻辑）
          - 算法：pytorch/tensorflow/transformer/llm
          - 数据：sql/spark/hive/flink
          - 测试：selenium/pytest/jmeter

        Args:
            position: Position 模型（含 tech_requirements + jd_content）
            resume_text: 候选人简历原文（可空）

        Returns:
            dict: {
                'questions': [...5 questions...],
                'review_log': {冗余统计},
                'approved': True,
                'is_fallback': True  # 标记为兜底题，后续会被覆盖
                'position_type': str  # 【bugfix】记录岗位类型
            }
        """
        pos_name = position.name or ''
        pos_type = InterviewService._detect_position_type(pos_name)

        # 按岗位类型分组选择技能优先级（前端避开 java/spring 等后端关键词）
        skill_priority_map = {
            'frontend': ['vue', 'react', 'javascript', 'typescript', 'node.js',
                         'webpack', 'vite', 'html5', 'css3', 'sass', 'less',
                         'next.js', 'nuxt', 'taro', 'flutter'],
            'algorithm': ['pytorch', 'tensorflow', 'transformer', 'llm', 'rag',
                          '推荐', 'nlp', 'cv', 'xgboost'],
            'data': ['sql', 'hive', 'spark', 'flink', 'airflow', 'dbt',
                     '数仓分层', 'python'],
            'test': ['selenium', 'pytest', 'jmeter', 'postman', 'appium',
                     '接口测试', '自动化测试', '性能测试'],
            'backend': ['java', 'spring', 'spring boot', 'redis', 'mysql',
                        'kafka', 'docker', 'kubernetes', 'elasticsearch',
                        'python', 'go', 'rust', 'mongodb'],
        }
        skill_priority = skill_priority_map.get(pos_type, skill_priority_map['backend'])

        # 过滤「了解 X 后端更好」「加分: X」等修饰词，避免误导
        tech_filtered = InterviewService._filter_skill_corpus(position.tech_requirements or '')
        jd = (position.jd_content or '').lower() if hasattr(position, 'jd_content') else ''
        corpus = f'{tech_filtered} {jd}'

        skill_topic = None
        for kw in skill_priority:
            if kw in corpus:
                skill_topic = kw.upper()
                break

        questions = []

        # 题1：项目深挖
        questions.append({
            'seq': 1,
            'type': 'project',
            'category': '项目深挖',
            'question': '请挑一个你最有成就感的项目，完整介绍背景、你的角色、技术选型、遇到的最大挑战以及如何解决。',
            'answer_directions': '考察项目深度与归纳能力，关注候选人在项目中的具体贡献（不是项目本身）、决策与技术取舍。',
            'source': '兑底题库-项目深挖模板',
            'modified': True,
        })

        # 题2：技能验证（匹配关键词）
        if skill_topic:
            questions.append({
                'seq': 2,
                'type': 'skill',
                'category': '技能验证',
                'question': f'你在项目中是怎么使用 {skill_topic} 的？请结合一个具体场景谈谈：选型原因、关键参数踩过的坑。',
                'answer_directions': f'考察 {skill_topic} 实战能力，关注是否真用过、细节是否准确（不要泛泛而谈）。',
                'source': f'兑底题库-技能验证[{pos_type}/{skill_topic}]',
                'modified': True,
            })
        else:
            questions.append({
                'seq': 2,
                'type': 'skill',
                'category': '技能验证',
                'question': '你简历中提到的最核心的技术是什么？请结合一个具体场景详细描述你是怎么使用的。',
                'answer_directions': '考察技能真实熟练度与场景化表达。',
                'source': f'兑底题库-技能验证通用[{pos_type}]',
                'modified': True,
            })

        # 题3：技能对比（按岗位类型分模板，避免后端题被错误套用到前端）
        comparison_templates = {
            'frontend': (
                '对比两种主流的前端框架方案（如 React vs Vue、Vue2 vs Vue3、SPA vs SSR/SSG、'
                'Webpack vs Vite、Redux vs Zustand 等），谈谈它们的适用场景与取舍。',
                '考察前端技术视野与选型决策能力，避免「这个好」式回答。',
                '兑底题库-前端对比模板',
            ),
            'algorithm': (
                '对比两种主流的算法方案（如 Transformer vs RNN、判别式 vs 生成式模型、'
                '有监督 vs 自监督学习、召回 vs 精排等），谈谈它们的适用场景与取舍。',
                '考察算法视野与场景适配能力。',
                '兑底题库-算法对比模板',
            ),
            'data': (
                '对比两种主流的数据处理方案（如 Hive vs Spark、批处理 vs 流处理、'
                '关系型 vs 列式存储、Lambda vs Kappa 架构等），谈谈它们的适用场景与取舍。',
                '考察数据技术视野与场景适配能力。',
                '兑底题库-数据对比模板',
            ),
            'test': (
                '对比自动化测试与手工测试的适用场景，以及 UI 自动化 vs 接口自动化的取舍、'
                '测试金字塔（单元/接口/UI）的实践思路。',
                '考察测试方法论与场景适配能力。',
                '兑底题库-测试对比模板',
            ),
            'backend': (
                '对比两种主流的技术方案（如关系型 vs 非关系型数据库、消息队列选型等），谈谈它们的适用场景与取舍。',
                '考察技术视野与决策能力，避免「这个好」式回答。',
                '兑底题库-技能对比模板',
            ),
        }
        q3_text, q3_dir, q3_src = comparison_templates[pos_type]
        questions.append({
            'seq': 3,
            'type': 'comparison',
            'category': '技能对比',
            'question': q3_text,
            'answer_directions': q3_dir,
            'source': q3_src,
            'modified': True,
        })

        # 题4：短板探测（通用）
        questions.append({
            'seq': 4,
            'type': 'weakness',
            'category': '短板探测',
            'question': '你觉得自己在技术方面最薄弱的一块是什么？最近是怎么补的、进度如何？',
            'answer_directions': '考察自我认知、学习能力、是否对职业发展有明确规划。',
            'source': f'兑底题库-短板探测模板[{pos_type}]',
            'modified': True,
        })

        # 题5：场景设计（按岗位类型分模板）
        scenario_templates = {
            'frontend': (
                '如果你从零搭建一个中等复杂度的前端应用（如电商/社交/管理后台），你会怎么设计架构？'
                '请从工程化方案、组件库设计、状态管理、性能优化、跨端方案五个维度展开。',
                '考察前端架构能力、组件抽象、性能与体验权衡。',
                '兑底题库-前端场景设计模板',
            ),
            'algorithm': (
                '如果你要落地一个中等规模的推荐/搜索系统，你会怎么设计？'
                '请从特征工程、模型选型、召回排序、A/B 实验、在线服务五个维度展开。',
                '考察算法系统化能力与工程落地经验。',
                '兑底题库-算法场景设计模板',
            ),
            'data': (
                '如果你从零搭建一个中等规模的数据平台（如电商用户行为分析），你会怎么设计？'
                '请从数据接入、数仓分层、调度监控、数据服务四个维度展开。',
                '考察数据架构能力与平台化思维。',
                '兑底题库-数据场景设计模板',
            ),
            'test': (
                '如果你要为一个中等复杂度的互联网产品搭建质量保障体系，你会从哪些维度入手？'
                '请从测试策略、用例设计、自动化分层、环境治理、监控预警五个维度展开。',
                '考察质量保障体系化能力。',
                '兑底题库-测试场景设计模板',
            ),
            'backend': (
                '如果你从零开始设计一个中等规模的系统（如电商/社交/教育平台），你会怎么设计架构？'
                '请从分层、数据流、关键组件、容灾四个维度展开。',
                '考察系统设计能力、权衡取舍、技术深度。',
                '兑底题库-场景设计模板',
            ),
        }
        q5_text, q5_dir, q5_src = scenario_templates[pos_type]
        questions.append({
            'seq': 5,
            'type': 'scenario',
            'category': '场景设计',
            'question': q5_text,
            'answer_directions': q5_dir,
            'source': q5_src,
            'modified': True,
        })

        return {
            'questions': questions,
            'review_log': {
                'total_received': 5,
                'total_selected': 5,
                'quality_notes': (
                    'v2.1 性能修复：LLM 出题被限流时使用兑底题，后续后台异步精修会覆盖。'
                    f'【bugfix】兑底题已按岗位类型[{pos_type}]适配，避免后端模板错误套用到前端/算法等岗位。'
                ),
            },
            'approved': True,
            'is_fallback': True,
            'position_type': pos_type,
        }

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
