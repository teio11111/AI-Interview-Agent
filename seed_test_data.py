"""本地测试数据生成器：直接写库，不调 LLM

- 3 个岗位（Python 后端 / 前端 / 产品）
- 5 个候选人，覆盖不同会话状态，便于验证两个 Bug
- 已写好简历 AI 分析 + 面试报告的 mock 数据，可直接看到 Bug 2 扣分效果
"""
import sys
sys.stdout.reconfigure(encoding='utf-8')
import json

from app import create_app
from extensions import db
from models.position import Position
from models.candidate import Candidate
from models.interview import InterviewSession, InterviewDialog, InterviewTopic
from constants import SessionStatus

app = create_app()


# =====================================================================
# Mock 数据模板
# =====================================================================

def mock_resume_analysis(match_score, tech_match, gaps):
    """模拟 ResumeService.analyze_resume 返回的结构（与 ai_analysis 字段对应）"""
    return {
        'match_score': match_score,
        'overall_assessment': f'候选人与岗位匹配度评分 {match_score}。技术栈覆盖度较好。',
        'strengths': [
            '具备扎实的 Python 后端开发经验',
            '熟悉主流 Web 框架与数据库',
            '有完整的高并发项目落地经验',
        ],
        'weaknesses': [
            '部分领域需要进一步深入',
            '软技能方面可继续提升',
        ],
        'tech_stack_match': tech_match,
        'experience_gaps': gaps,
        'interview_focus': ['系统设计', '项目深度', '沟通能力'],
    }


def mock_round_report(round_num, round_score, tech, project, soft,
                       inconsistencies=None, risks=None):
    """模拟单轮面试报告（与 InterviewSession.report 对应）"""
    return {
        'overall_score': round_score,
        'recommendation': '推荐' if round_score >= 70 else ('待定' if round_score >= 50 else '不推荐'),
        'dimension_scores': {
            'technical_ability': tech,
            'project_experience': project,
            'communication': soft,
            'learning_potential': 7,
        },
        'strengths': [
            '对核心问题有清晰的认识',
            '能结合实际项目举例说明',
        ],
        'weaknesses': [
            '部分细节追问时略显犹豫',
            '系统设计深度可进一步加强',
        ],
        'highlights': [
            {'seq': 1, 'comment': '主动补充了边界场景考虑'},
        ],
        'risks': risks or [],
        'interview_suggestions': '建议下轮面试加强系统设计类问题',
    }


def mock_meta_evaluation(final_score, cross=None, risks=None, rationale=''):
    """模拟综合元评估结果（与 meta_evaluation 字段对应）"""
    return {
        'overall_score': final_score,
        'final_recommendation': '推荐',
        'decision_rationale': rationale,
        'dimension_scores': {
            'technical_ability': 8, 'project_experience': 7,
            'system_design': 7, 'communication': 8, 'learning_potential': 8,
        },
        'cross_stage_analysis': cross or {
            'consistency_findings': [],
            'summary': '各阶段表现基本一致',
        },
        'key_risks': risks or [],
        'computation': {
            'raw_score': final_score,
            'cross_validation_penalty': 0,
            'final_score_after_penalty': final_score,
            'meta_weights': {'resume': 0.20, 'rounds': [0.35, 0.45]},
        },
    }


# =====================================================================
# 主体流程
# =====================================================================

with app.app_context():
    print('===== 清空旧测试数据 =====')
    # 删除现有候选人（级联删除会话/对话/板块）
    for c in Candidate.query.all():
        for s in c.sessions:
            db.session.execute(db.delete(InterviewDialog).where(
                InterviewDialog.session_id == s.id))
            db.session.execute(db.delete(InterviewTopic).where(
                InterviewTopic.session_id == s.id))
            db.session.delete(s)
        db.session.delete(c)
    # 删除岗位
    for p in Position.query.all():
        db.session.delete(p)
    db.session.commit()
    print('  [OK] 旧数据清空')

    # -------------------------------------------------------------
    # 1. 创建 3 个岗位
    # -------------------------------------------------------------
    print('\n===== 创建岗位 =====')
    positions_data = [
        {
            'name': 'Python后端开发工程师',
            'jd_content': '''【岗位职责】
1. 负责公司核心业务后端服务的设计、开发和维护；
2. 使用 Python（Flask/FastAPI）构建高并发 Web API；
3. 设计与实现 RESTful 接口，参与前后端联调；
4. MySQL/PostgreSQL 数据库建模、慢查询优化；
5. Redis 缓存策略、消息队列异步处理方案；
6. Docker 容器化、Kubernetes 集群部署；
7. 参与代码审查、技术分享和团队标准化建设。

【任职要求】
1. 计算机相关专业本科及以上，5 年及以上 Python 后端经验；
2. 熟练掌握 Flask/FastAPI/Django 至少一种；
3. 熟悉 MySQL/PostgreSQL，熟练 SQL，了解索引优化；
4. 熟悉 Redis 缓存、分布式锁；
5. 熟悉 RabbitMQ/Kafka 等消息中间件；
6. 有 Docker、K8s 容器化部署经验''',
            'tech_requirements': 'Python, Flask, FastAPI, Django, MySQL, PostgreSQL, Redis, RabbitMQ, Kafka, Docker, Kubernetes',
        },
        {
            'name': '高级前端工程师',
            'jd_content': '''【岗位职责】
1. 负责公司 Web 产品前端架构设计与核心模块开发；
2. 使用 React/Vue 构建复杂单页应用；
3. 性能优化、打包构建、组件库建设；
4. 配合后端定义接口规范。

【任职要求】
1. 计算机相关专业，4 年以上前端开发经验；
2. 精通 React/Vue，理解其设计思想；
3. 熟悉 TypeScript、Webpack/Vite；
4. 有大型 SPA 实战经验。''',
            'tech_requirements': 'JavaScript, TypeScript, React, Vue, Webpack, Vite, Node.js',
        },
        {
            'name': '产品经理',
            'jd_content': '''【岗位职责】
1. 负责产品需求分析、原型设计、PRD 输出；
2. 跨部门协作推动产品落地；
3. 数据驱动迭代优化。

【任职要求】
1. 3 年以上互联网产品经验；
2. 良好的需求抽象与文档能力；
3. 熟悉 Axure/Figma。''',
            'tech_requirements': 'Axure, Figma, SQL, 数据分析',
        },
    ]
    positions = {}
    for pd in positions_data:
        p = Position(
            name=pd['name'],
            jd_content=pd['jd_content'],
            tech_requirements=pd['tech_requirements'],
        )
        db.session.add(p)
        db.session.flush()
        positions[pd['name']] = p
        print(f'  [OK] 岗位 {p.id}: {p.name}')

    # -------------------------------------------------------------
    # 2. 创建 5 个候选人
    # -------------------------------------------------------------
    print('\n===== 创建候选人 =====')
    candidates_data = [
        # A: Python 后端 - 有 preparing（准备中） + 1 个 completed 会话
        {
            'name': '陈子轩', 'pos_key': 'Python后端开发工程师',
            'resume': '''陈子轩 | 男 | 1991 | 8年 Python 后端经验
核心技能：Python(8y), FastAPI(3y), Django(5y), PostgreSQL(6y), MySQL(5y), Redis(6y), Docker(5y), K8s(3y)
项目：电商核心交易系统（FastAPI + Celery + Kafka，P99 从 1.8s 降至 380ms）''',
            'match_score': 88,
            'tech_match': [
                {'skill': 'Python', 'level': 'expert', 'required': 'expert'},
                {'skill': 'FastAPI', 'level': 'expert', 'required': 'proficient'},
                {'skill': 'PostgreSQL', 'level': 'expert', 'required': 'proficient'},
                {'skill': 'K8s', 'level': 'proficient', 'required': 'proficient'},
            ],
            'gaps': [],
            'sessions': [
                {'status': SessionStatus.PREPARING,
                 'questions': json.dumps(['Q1: FastAPI 异步 IO 优势', 'Q2: 数据库分库分表策略'], ensure_ascii=False),
                 'report': None},
                {'status': SessionStatus.COMPLETED,
                 'questions': json.dumps(['Q1: 自我介绍', 'Q2: 高并发方案'], ensure_ascii=False),
                 'report': json.dumps(mock_round_report(1, 78, tech=8, project=8, soft=7), ensure_ascii=False)},
            ],
            'meta_eval': None,  # 1 轮不触发元评估
        },
        # B: 前端 - 有 in_progress（进行中）
        {
            'name': '林晓彤', 'pos_key': '高级前端工程师',
            'resume': '''林晓彤 | 女 | 1993 | 5年前端经验
核心技能：JavaScript(5y), TypeScript(4y), React(5y), Vue(3y), Webpack(4y)
项目：营销活动平台 React + TS 微前端架构''',
            'match_score': 82,
            'tech_match': [
                {'skill': 'React', 'level': 'expert', 'required': 'expert'},
                {'skill': 'TypeScript', 'level': 'expert', 'required': 'proficient'},
                {'skill': 'Vite', 'level': 'proficient', 'required': 'proficient'},
            ],
            'gaps': [],
            'sessions': [
                {'status': SessionStatus.IN_PROGRESS,
                 'questions': json.dumps(['Q1: React Hooks 设计哲学'], ensure_ascii=False),
                 'report': None},
            ],
            'meta_eval': None,
        },
        # C: 产品 - 只有 1 个 completed（验证 Bug 1：不应弹恢复 toast）
        {
            'name': '赵一鸣', 'pos_key': '产品经理',
            'resume': '''赵一鸣 | 男 | 1990 | 5年产品经验
擅长：电商、C 端产品、用户增长
代表作：DAU 从 50w 提升到 200w 的运营活动平台''',
            'match_score': 76,
            'tech_match': [
                {'skill': 'Axure', 'level': 'expert', 'required': 'proficient'},
                {'skill': 'Figma', 'level': 'expert', 'required': 'proficient'},
            ],
            'gaps': ['数据分析可加强'],
            'sessions': [
                {'status': SessionStatus.COMPLETED,
                 'questions': json.dumps(['Q1: 介绍一个你主导的项目'], ensure_ascii=False),
                 'report': json.dumps(mock_round_report(1, 72, tech=6, project=8, soft=8), ensure_ascii=False)},
            ],
            'meta_eval': None,
        },
        # D: Python 后端 - 无任何会话（首次面试，按钮显示"生成问题"）
        {
            'name': '王梓涵', 'pos_key': 'Python后端开发工程师',
            'resume': '''王梓涵 | 男 | 1996 | 2年 Python 后端经验
核心技能：Python(2y), Flask(2y), MySQL(2y)
项目：CRM 系统的工单模块''',
            'match_score': 65,
            'tech_match': [
                {'skill': 'Python', 'level': 'proficient', 'required': 'expert'},
                {'skill': 'Flask', 'level': 'proficient', 'required': 'proficient'},
            ],
            'gaps': ['高并发经验不足', '消息队列未实战', 'K8s 未接触'],
            'sessions': [],
            'meta_eval': None,
        },
        # E: Python 后端 - 2 轮 completed + 有 meta_evaluation（验证 Bug 2 扣分）
        {
            'name': '李思源', 'pos_key': 'Python后端开发工程师',
            'resume': '''李思源 | 男 | 1994 | 5年 Python 经验
简历亮点：主导过 3 个后端项目，熟悉 FastAPI / Django / MySQL
简历亮点：声称有日均千万级请求经验（面试表现弱）''',
            'match_score': 75,  # 简历分较高
            'tech_match': [
                {'skill': 'Python', 'level': 'expert', 'required': 'expert'},
                {'skill': 'FastAPI', 'level': 'proficient', 'required': 'proficient'},
            ],
            'gaps': ['简历中提到的"千万级 QPS"在面试中未能验证'],
            'sessions': [
                {'status': SessionStatus.COMPLETED,
                 'questions': json.dumps(['Q1: 介绍千万级 QPS 项目'], ensure_ascii=False),
                 'report': json.dumps(mock_round_report(1, 55, tech=6, project=5, soft=7,
                    inconsistencies=['简历称日均千万级请求，面试中无法说清限流与降级方案'],
                    risks=[{'severity': '高', 'description': '项目数据与简历描述不一致'}]), ensure_ascii=False)},
                {'status': SessionStatus.COMPLETED,
                 'questions': json.dumps(['Q1: 系统设计：短链生成系统'], ensure_ascii=False),
                 'report': json.dumps(mock_round_report(2, 60, tech=7, project=6, soft=7,
                    inconsistencies=['系统设计深度不足，对分库分表选型理由模糊'],
                    risks=[{'severity': '中', 'description': '架构设计能力需提升'}]), ensure_ascii=False)},
            ],
            # 已有 meta_evaluation：含不一致 + 高风险 → 触发扣分
            'meta_eval': {
                'overall_score': 61,  # 扣分后
                'final_recommendation': '有条件推荐',
                'decision_rationale': (
                    '候选人简历整体描述较好，但面试过程中对核心项目细节追问时表现薄弱，'
                    '存在 2 项不一致发现、1 项高风险与 1 项中风险。'
                    '\n\n【自动扣分】共扣 14 分：'
                    '其中"不一致"扣 10 分（2 项×5）、"部分一致"扣 0 分、"高风险"扣 5 分（1 项）、"中风险"扣 2 分（1 项）。'
                ),
                'dimension_scores': {
                    'technical_ability': 6, 'project_experience': 6,
                    'system_design': 6, 'communication': 7, 'learning_potential': 7,
                },
                'cross_stage_analysis': {
                    'consistency_findings': [
                        {'claim': '简历称日均千万级请求', 'verdict': '不一致', 'detail': '面试中无法说清限流与降级方案'},
                        {'claim': '系统设计深度', 'verdict': '不一致', 'detail': '对分库分表选型理由模糊'},
                    ],
                    'summary': '简历与面试表现存在明显差距，需关注项目真实性与架构设计深度。',
                },
                'key_risks': [
                    {'severity': '高', 'description': '项目数据与简历描述不一致，建议核实工作经历'},
                    {'severity': '中', 'description': '架构设计能力需提升'},
                ],
                'computation': {
                    'raw_score': 75,
                    'cross_validation_penalty': 14,
                    'final_score_after_penalty': 61,
                    'meta_weights': {'resume': 0.20, 'rounds': [0.35, 0.45]},
                    'recommendation_for': '有条件推荐',
                },
            },
        },
    ]

    for cd in candidates_data:
        pos = positions[cd['pos_key']]
        cand = Candidate(
            name=cd['name'],
            position_id=pos.id,
            resume_text=cd['resume'],
            ai_analysis=json.dumps(mock_resume_analysis(
                cd['match_score'], cd['tech_match'], cd['gaps']), ensure_ascii=False),
            match_score=cd['match_score'],
        )
        db.session.add(cand)
        db.session.flush()

        # 会话
        for sd in cd['sessions']:
            sess = InterviewSession(
                candidate_id=cand.id,
                status=sd['status'],
                questions_plan=sd['questions'],
                report=sd['report'],
            )
            db.session.add(sess)

        # 综合元评估
        if cd['meta_eval']:
            cand.meta_evaluation = json.dumps(cd['meta_eval'], ensure_ascii=False)
            cand.meta_eval_round_count = 2

        db.session.flush()
        print(f'  [OK] 候选人 {cand.id}: {cand.name} (match={cd["match_score"]}, 会话数={len(cd["sessions"])})')

    db.session.commit()

    # -------------------------------------------------------------
    # 3. 汇总
    # -------------------------------------------------------------
    print('\n===== 数据汇总 =====')
    print(f'  岗位总数: {Position.query.count()}')
    print(f'  候选人总数: {Candidate.query.count()}')
    print(f'  面试会话总数: {InterviewSession.query.count()}')
    print('  按状态:')
    for st in [SessionStatus.PREPARING, SessionStatus.IN_PROGRESS, SessionStatus.COMPLETED]:
        n = InterviewSession.query.filter_by(status=st).count()
        print(f'    - {st}: {n}')

    print('\n===== 下一步 =====')
    print('  打开 http://127.0.0.1:8088/live-interview 验证 Bug 1:')
    print('    - 陈子轩（A）: 有 preparing 会话，应弹"准备中"恢复')
    print('    - 林晓彤（B）: 有 in_progress 会话，应弹"进行中"恢复')
    print('    - 赵一鸣（C）: 只有 completed，不应弹恢复 toast，按钮显示"开始新一轮"')
    print('    - 王梓涵（D）: 无任何会话，按钮显示"生成问题"')
    print('')
    print('  打开 http://127.0.0.1:8088/candidates 验证 Bug 2:')
    print('    - 李思源（E）: 有 meta_evaluation，扣分 14 分，最终 61 分（"有条件推荐"）')