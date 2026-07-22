import sys
sys.stdout.reconfigure(encoding='utf-8')
import requests

BASE = 'http://127.0.0.1:8088'
s = requests.Session()

# 1. 登录
r = s.post(f'{BASE}/login', data={'username': 'admin', 'password': 'admin123'}, timeout=5, allow_redirects=False)
print(f'POST /login  status={r.status_code}')
# 获取 session cookie


# ============================================
# 创建测试岗位：Python 后端工程师
# ============================================
position_data = {
    'name': 'Python后端开发工程师',
    'jd_content': '''【岗位职责】
1. 负责公司核心业务后端服务的设计、开发和维护，参与系统架构演进；
2. 使用 Python（Django/Flask/FastAPI）构建高并发 Web API，支撑日均千万级请求；
3. 设计与实现 RESTful/GraphQL 接口，参与前后端接口联调与文档输出；
4. 负责 MySQL/PostgreSQL 数据库建模、慢查询优化和分库分表方案设计；
5. 引入并落地 Redis 缓存策略、消息队列（RabbitMQ/Kafka）异步处理方案；
6. 配合 DevOps 团队完成 CI/CD 流水线、Docker 容器化、Kubernetes 集群部署；
7. 参与代码审查、技术分享和团队标准化建设。

【任职要求】
1. 计算机相关专业本科及以上学历，5 年及以上 Python 后端开发经验；
2. 熟练掌握 Django、Flask 或 FastAPI 至少一种主流框架，并有大型项目实战经验；
3. 熟悉 MySQL/PostgreSQL 关系数据库，熟练使用 SQL，了解索引优化和事务隔离；
4. 熟悉 Redis 常用数据结构及典型应用场景（缓存、分布式锁、限流）；
5. 熟悉 RabbitMQ 或 Kafka 等消息中间件，了解其使用场景和最佳实践；
6. 有 Docker、K8s 容器化部署经验，了解 CI/CD（GitLab CI/Jenkins）流程；
7. 具备良好的系统设计能力、问题排查能力和团队协作意识；
8. 有开源项目贡献者、技术博客作者优先。''',
    'tech_requirements': 'Python, Django, Flask, FastAPI, MySQL, PostgreSQL, Redis, RabbitMQ, Kafka, Docker, Kubernetes, CI/CD, RESTful'
}

r = s.post(f'{BASE}/api/positions', json=position_data, timeout=5)
print(f'\nPOST /api/positions  status={r.status_code}')
print(f'  body: {r.text[:300]}')

if r.status_code != 201:
    print('❌ 岗位创建失败')
    sys.exit(1)
pos_id = r.json()['data']['id']
print(f'✅ 岗位创建成功 id={pos_id}')


# ============================================
# 创建候选人（简历精简但命中要点）
# ============================================
resume_text = '''陈子轩 | 男 | 1991年出生 | 联系电话 138-XXXX-8866 | 邮箱 chen.zixuan@example.com | 现居上海

【个人简介】
8 年 Python 后端开发经验，专注高并发 Web 服务与微服务架构设计。擅长 FastAPI + Django 双栈，曾主导日均 6000 万级请求的电商核心交易系统的从 0 到 1 建设，对系统稳定性、性能优化与团队协作有完整方法论。

【核心技能】
• 编程语言：Python（8年，熟练）、Shell（4年，熟练）、Go（2年，了解）
• Web 框架：FastAPI（3年，熟练，含异步 IO 与依赖注入体系）、Django（5年，熟练，含 DRF、Django Channels）、Flask（3年，熟练）
• 数据库：PostgreSQL（6年，熟练，含主从、分库分表、PostGIS）、MySQL（5年，熟练，索引与事务隔离）、MongoDB（2年，了解）
• 缓存与中间件：Redis（6年，熟练，含 Cluster、Sentinel、分布式锁、Lua 脚本）、RabbitMQ（4年，熟练，含死信队列、延迟队列）、Kafka（2年，了解）
• 容器与运维：Docker（5年，熟练）、Kubernetes（3年，熟练，Helm 模板编写）、GitLab CI（4年，熟练）、Jenkins（2年，了解）、Prometheus + Grafana（3年，熟练）
• 其他：RESTful API 设计、gRPC、领域驱动设计（DDD）、单元测试与 TDD、Linux 内核性能调优

【工作经历】

▌上海 XXXXX 信息技术有限公司（互联网电商） | 资深 Python 后端工程师  2022.04 至今
- 主导核心交易链路重构：将单体的下单服务拆分为 FastAPI + 异步任务（Celery）+ Kafka 的微服务架构，P99 延迟从 1.8s 降至 380ms；
- 设计三级缓存体系（本地 Caffeine + Redis Cluster + 热点预加载），应对双 11 大促峰值 25 万 QPS，命中率 96%；
- 推动 PostgreSQL 分库分表落地（基于 ShardingSphere），订单表按 user_id 哈希分 64 库 1024 表，单表行数控制在 500 万；
- 主导 K8s 化迁移，将 32 个服务从 ECS 迁至 K8s，资源利用率提升 40%，平均扩容时间从 15 分钟降至 90 秒；
- 作为技术评审委员会成员，负责核心系统设计评审，半年内累计评审 38 个方案，推动统一日志、监控、链路追踪规范；
- 带教 5 名中高级工程师，组织内部 Tech Talk 12 场，覆盖 DDD、性能调优、稳定性治理。

▌上海 XXXXX 科技有限公司（金融科技） | Python 后端工程师  2018.06 - 2022.03
- 参与公司核心账务系统的迭代，负责账户、交易、清算模块的日常开发；
- 自研基于 FastAPI + Tortoise-ORM 的内部框架，统一了 8 个业务线的 API 规范，提升研发效率约 30%；
- 引入 Celery + Redis 构建异步任务平台，承担日均 200 万笔交易的对账和清分任务，错误率从 0.05% 降至 0.003%；
- 设计并落地全链路灰度发布方案，支持按用户标签、地域、版本多维度灰度；
- 主导 PostgreSQL 慢查询治理：通过索引重建 + SQL 重写 + 读写分离，月均慢查询数从 1.2k 降至 110。

▌杭州 XXXXX 信息技术有限公司（SaaS 初创） | Python 开发工程师  2017.07 - 2018.05
- 参与公司 SaaS 客户管理系统的从 0 到 1 开发，使用 Django + DRF + PostgreSQL；
- 独立完成 SSO 认证、权限管理、审计日志等基础模块的开发；
- 配合运维完成阿里云部署，参与 Docker 化落地。

【教育背景】
浙江大学 | 计算机科学与技术 | 本科  | 2013.09 - 2017.06
• GPA 3.78/4.0（年级前 10%），获国家奖学金、蓝桥杯省级一等奖
• 主修课程：数据结构、操作系统、计算机网络、数据库系统、分布式系统（均 90+）

【项目亮点（业余）】
• FastAPI-Best-Practice（GitHub 1.2k star）：总结 FastAPI 工程实践的开源模板
• Python-Performance-Tricks（GitHub 580 star）：个人整理的 Python 性能优化技巧集
• 知乎专栏《深入浅出 Python 异步编程》累计 40 万阅读量

【自我评价】
我是一个能沉下心做事的人。8 年开发里，我最骄傲的不是技术多新，而是经手的服务稳定性始终保持在 4 个 9 以上。期待加入一个有技术追求、能持续打磨产品的团队。'''

candidate_data = {
    'name': '陈子轩',
    'position_id': pos_id,
    'resume_text': resume_text
}

r = s.post(f'{BASE}/api/candidates', json=candidate_data, timeout=5)
print(f'\nPOST /api/candidates  status={r.status_code}')
print(f'  body: {r.text[:400]}')

if r.status_code != 201:
    print('❌ 候选人创建失败')
    sys.exit(1)
cand_id = r.json()['data']['id']
print(f'✅ 候选人创建成功 id={cand_id}')

print()
print('=' * 60)
print('汇报')
print('=' * 60)
print(f'岗位 ID: {pos_id}')
print(f'候选人 ID: {cand_id}')
print(f'  - 候选人: 陈子轩')
print(f'  - 岗位: Python后端开发工程师')
print(f'  - 简历长度: {len(resume_text)} 字')
print()
print('下一步：通过浏览器执行岗位 AI 分析 + 候选人 AI 分析（简历评估）')