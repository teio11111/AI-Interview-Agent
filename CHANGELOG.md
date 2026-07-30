# 更新日志

> - 每次发版在 `## [版本号] - 日期` 块下记录
> - 类目：`Added`（新增）/ `Changed`（变更）/ `Fixed`（修复）/ `Removed`（移除）
> - 首页 Dashboard 卡片只展示最近 3 个版本（见 `data/changelog.json`）

---

## [v3.3] - 2026-07-29 - 项目级北京时间

### Changed
- `app.py` 启动时为当前 Flask 进程设置 `TZ=Asia/Shanghai`，`datetime.now()` 在云服务器 UTC 环境下也返回北京时间
- `deploy/start.sh` 激活 venv 前 `export TZ=Asia/Shanghai`，双保险
- `utils/beijing_now()` 统一封装，所有 `datetime.now()` 调用改为 `beijing_now()`
- `models/base.py` 默认值、`services/agent_orchestrator.py` 时间戳、`services/asr_service.py` 时间戳、`utils/meta_evaluation_pdf.py` 生成时间均统一改为北京时间

### Fixed
- 云服务器（系统时区 UTC）上所有时间生成和入库均偏移 8 小时的 BUG
- 云端历史 UTC 数据一次性 +8 小时回填（25 条记录：1 candidate / 1 session / 1 topic / 13 operation_log / 2 position / 7 user）

### Notes
- 不修改云服务器全局时区，仅在项目进程内设置，避免影响服务器上其他项目

---

## [v3.2] - 2026-07-28 - 代码精简与安全加固

### Removed
- v1.0 废弃 Agent 物理删除（evaluator.py / resume_evaluator.py / question_designer.py）
- 候选人门户路由与模板全量删除（routes/candidate_portal_routes.py + templates/candidate_portal.html）
- 重复的面试对话接口：`/api/interviews/<id>/follow-up` 与 `/api/interviews/dialog/evaluate` 合并到统一接口
- interview_routes.py 死 import（InterviewSession/InterviewDialog/InterviewTopic 从未在路由中直接使用）

### Changed
- 面试对话接口统一：`POST /api/interviews/<session_id>/dialog` 现在同时支持追问（`parent_seq` 字段）与实时面试两种场景，返回结构统一为 `{dialog, feedback}`
- 登录接口加入「登录失败」审计（密码错 + 候选人试图访问门户均记录 IP），审计页新增「登录失败」选项
- 候选人门户下线后非 admin 访问路径自动跳登录页（而非错误跳转）

### Fixed
- 面试接口重复逻辑收敛：`add_dialog` / `evaluate_dialog` 合并为同一函数
- auth_routes.py 清理 dead code（候选人门户 redirect 字段）

---

## [v3.1] - 2026-07-28 - 多账号 + 操作审计

### Added
- 5 个面试官账号：admin1 / admin2 / admin3 / admin4 / admin5，初始密码 123456
- 修改密码 + 修改用户名（用户菜单）
- 操作审计日志：自动记录"谁/什么时间/做了什么/对象是谁"
- 操作动态页面（导航栏"动态"入口，支持筛选 + 分页）

---

## [v3.0] - 2026-07-28 - SSE 兜底题修复 + 评分重构 + 隐性维度异步评估

### Fixed
- **P0**: SSE 流式接口"新人第一次面试恢复兜底题" — 改为同步 LLM 出题，拿到定制题才创建 session
- **P1**: 添加候选人简历数据串位 bug — 添加成功后强制清空 file input
- **P0**: 评分逻辑 3 个 BUG（汇总师 5 维评分脱钩 / 隐性条件 20% 权重虚高 / 废弃 Agent 残留）
- 评分基线校准 +5 分偏置

### Added
- 隐性维度（简历真实度/学习能力/职业发展方向/居住地）异步评估，前端先看到基础分
- 综合元评估报告一键导出 PDF
- 岗位 JD 解析 Agent + 文本截断工具
- 冒烟测试扩到 87 项

---

## [v2.0] - 2026-07-23 - 综合元评估 + 候选人门户下线 + PDF 导入导出

### Added
- 综合元评估师 Agent：跨阶段一致性验证 + 多轮追踪 + 五档推荐等级
- 综合评分公式动态化（1/2/3+ 轮不同权重）+ 跨阶段一致性惩罚
- 综合元评估 PDF 导出 + 中文字体自动适配
- 岗位管理 PDF 智能导入（上传 JD → AI 识别 → 预览确认）
- 实时面试页布局重排（对话区 75% + 控制面板 25%）
- 首页 Dashboard 数据统计卡片 + 更新日志卡片

### Removed
- 候选人门户入口与注册功能下线

---

## [v1.0] - 2026-07-22 - 正式上线

### Added
- 多智能体协作面试系统（3+1 评估架构）
- 岗位 / 候选人 / 实时面试工作台
- 单轮面试报告 + 基础综合分

---

[历史归档]：本系统起步于 2026 年初，最初版本为单智能体架构，无元评估机制。
# 更新日志

本文件按 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.0.0/) 规范编写，
本项目遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

> **格式说明**：
> - 每次发版在 `## [版本号] - 日期` 块下记录
> - 未发布的小修复/维护/清理可放在 `## [Unreleased]` 区块，下一发版时合并到对应版本
> - 类目固定为：`Added`（新增）/ `Changed`（变更）/ `Fixed`（修复）/ `Removed`（移除）/ `Security`（安全）
> - 首页 Dashboard 卡片只展示用户可感知的最近 3 个版本（见 `data/changelog.json`）
> - 重大版本（v1.x、v2.x 等）需配套写 Word 文档（截图 + 详细说明），交付给客户

---

## [v3.1] - 2026-07-28 - 多账号 + 操作审计

### Added（新增）
- **多账号支持**：初始化 5 个独立账号 `admin1` / `admin2` / `admin3` / `admin4` / `admin5`，统一初始密码 `123456`，登录后各自修改
- **修改密码**：右上角用户菜单 → "修改密码"弹窗，验证旧密码 + 新密码至少 6 位
- **修改用户名**：用户可自定义自己的登录名（2-30 字符，自动查重，需密码确认）
- **操作审计日志**：自动记录每个操作（谁/什么时间/做了什么/对象是谁/IP）
  - 覆盖：登录/登出/创建候选人/AI分析候选人/删除候选人/批量删除/创建岗位/分析岗位/删除岗位/删除面试会话/结束面试/修改密码/修改用户名
  - 用户名/对象名冗余存储，防止删除后丢失
- **"操作动态"页面**：导航栏新增入口，支持按用户/操作类型/对象类型筛选 + 分页查看
  - `/profile` 页面 + `/api/audit/logs` + `/api/audit/users` 三个查询接口

### Verified（验证）
- v3.1 功能测试 **27/27 PASS**：admin1-5 全部登录、改用户名（含同名冲突/太短/旧名失效等边界）、改密码、审计筛选、动态页面渲染
- 冒烟测试 **87/87 PASS**：原有功能不受影响

---

## [v3.0] - 2026-07-28 - SSE 路径兜底题修复 + 评分逻辑重构 + 隐性维度异步评估

### Fixed（修复）

#### 【P0】SSE 流式接口"新人第一次面试恢复兜底题"缺陷
- **症状**：用户报告"新人第一次面试就显示恢复之前的对话，而且题也是之前的"
- **根因**：`routes/stream_routes.py` 的 `stream_candidate_analysis` worker 只创建兜底 session，**不触发 LLM 真出题**；前端 `candidates.html` 调用的恰好是这条 SSE 路径（不是 HTTP 同步路径），所以 session 永远是兜底题
- **修复**：在 SSE worker 内兜底 session 创建后**同步**调用 `InterviewService.generate_questions`（SSE_TIMEOUT=320s 充裕，LLM 出题约 60-90s），LLM 出题成功 → **覆盖** `sess.questions_plan` 为定制题
- **同步修复**：`routes/candidate_routes.py` 的 `analyze_candidate` HTTP 接口也改为同步保险
- **验证**：所有候选人当前 preparing 会话 qplan_len 均 > 14000（旧兜底题只有 2157），前端不再看到兜底题

#### 【P1】添加候选人简历数据串位 bug
- **症状**：手动粘贴简历文本时，被默默填充成了上次的 PDF 简历内容
- **根因**：`templates/candidates.html` 添加候选人成功后只清空 `newResume` textarea，未清空 `resumeFile` file input，导致下次添加候选人时浏览器静默提交上次的 PDF 覆盖粘贴的简历
- **修复**：line 487 后添加 `const fi = document.getElementById('resumeFile'); if (fi) fi.value = '';`

#### 【P2】v2.1 AI 面试评分逻辑 BUG 修复（3 个评分计算错误）
- **BUG A【P0】汇总师 5 维评分脱钩问题**：
  - 问题：`agents/interview_eval_coordinator.py` 计算综合分时调用 `_avg_dimensions()` 取三个评估师各自维度的平均，但汇总师 prompt 已经要求输出统一的 5 维评分（技术基础/项目经验/系统设计/沟通表达/学习能力），该字段完全被忽略，造成综合分与人工填写脱钩
  - 修复：删除 `_avg_dimensions()`，改用 `_compute_5dim_weighted_score()` 直接读汇总师重新评估的 5 维评分（每维 0.20，加权和转 0-100）
  - 同步：`W_TECH/W_PROJECT/W_SOFT` 老权重常量删除，改用 `W_TECH_FOUNDATION/W_PROJECT_EXP/W_SYSTEM_DESIGN/W_COMMUNICATION/W_LEARNING` 5 维权重常量（各 0.20）
  - prompt 重写：明确告知汇总师"重新评估 5 维评分"（不是取平均），加入 9-10/7-8/5-6/3-4/1-2 五档虚高防护原则
  - 前端 `templates/live_interview.html` 同步：计算明细展示由 `coord_raw_100` 改为 `coord_5dim_100`
- **BUG B【P0】隐性条件 20% 权重虚高问题**：
  - 问题：`agents/hidden_evaluator.py` 输出无 `hidden_score` 数字字段，简历汇总师 20% 隐性权重依赖 LLM 主观编造 `score_breakdown.hidden_component`，造成简历匹配度虚高
  - 修复：`hidden_evaluator.py` prompt 输出格式加 `hidden_score_breakdown`（9 个子维度各 1-10 分），代码 `_compute_hidden_score()` 加权产出 `hidden_score`（0-100）
  - 同步：`resume_coordinator.py` 删除 prompt 里的 `score_breakdown` 字段让 LLM 编的部分，代码从 `tech_result.tech_depth_score` / `soft_result.soft_score` / `hidden_result.hidden_score` 读真实数字计算 `match_score`（tech×60% + soft×20% + hidden×20%）
- **BUG C【P2】v1.0 废弃 Agent 残留**：
  - 问题：`agents/__init__.py` 还在 `from agents.evaluator import EvaluatorAgent` 等 3 个 v1.0 单 Agent，业务代码从未使用但存在误用风险
  - 修复：3 个文件顶部加 `⚠️ DEPRECATED` 文档 + v2.0 替代方案指引，`__init__.py` 移除 3 个 export，业务代码需显式 import 才能用

#### 【P2】评分基线校准（+5 分偏置）
- 用户反馈"整体分数偏低"，统一 +5 后接近期望（zy 76→81, cc 33→38, 刘洋 54→59, zzj 59→64）
- `agents/resume_coordinator.py`：`min(100, max(0, match_score + 5))`
- 同步 SQL 校准现有 4 个候选人数据

#### 部署工程 v2.1 对齐
- `smoke_test.py` `http_call` 默认 timeout 从 15 → 60 秒（兼容 LLM 调用）
- `smoke_test.py` F 段检查项同步 v2.1（`W_COORD_DIM` → `W_COORD_5DIM` / `coord_raw` → `coord_5dim_100` + 新增 5 维权重 + 5 维加权函数验证项）
- `_zip.py` 修复 `__init__.py` 被 `_*.py` 模式误过滤的重大 bug（会导致服务器部署后找不到包入口）
- `_zip.py` `must_have` 加 `interview_eval_coordinator.py` + `live_interview.html` 等 v2.1 关键文件验证

### Added（新增）

#### v3.6 隐性维度异步评估
- `services/agent_orchestrator.py` `evaluate_resume` 拆 tech+soft / hidden 两阶段流水线
- tech+soft 阶段 ≤120s → 前端展示基础分（partial_complete 事件）
- hidden 阶段 ≤180s 异步跑完 → 更新最终结果
- SSE_TIMEOUT=320s 充裕（120+180+buffer）
- 新增 4 个隐性维度（简历真实度/学习能力/职业发展方向/居住地）
- `partial_complete` 事件推前端（让用户先看到基础分，不再以为卡住）

#### v3.6.5 同步保险机制（双保险）
- 不再依赖不可靠的 daemon thread（waitress 8 worker 下时灵时不灵）
- `routes/candidate_routes.py` + `routes/stream_routes.py` 都改为同步保险
- 拿到 LLM 定制题 → 直接用定制题创建 session
- LLM 失败 → 才退到兜底题 + 后台异步补精修

#### 综合元评估报告 PDF 导出
- `utils/meta_evaluation_pdf.py`：综合元评估报告一键导出 PDF
- 支持中文字体（自动寻找系统字体，Windows/Linux 双平台）

#### 岗位 JD 解析 Agent
- `agents/position_jd_parser.py`：JD 文本解析 + 结构化字段提取
- 配合已有的 PDF 上传 → AI 识别 → 预览确认流程

#### 文本截断工具
- `utils/text_truncate.py`：防止超长简历/JD 撑爆 prompt，导致 LLM 输出质量下降
- 默认 max_chars=6000，截断时插入"内容已截断"标记

#### 冒烟测试增强
- `smoke_test.py`：从 63 项扩到 **87 项**（新增 K 段隐性维度相关检查 + v3.6 SSE 接口检查）
- 覆盖 agents/services/routes/templates/config 全栈

### Changed（变更）

#### 部署工具链完善
- `deploy/UPLOAD_GUIDE.md`（152 行）：详细云端部署手册（环境检查 → 打包 → 上传 → 一键部署 → 改密钥 → 启动）
- `deploy/install.sh`：自动装依赖 + 建 venv + pip install + 复制 .env.production → .env + 跑 init_admin
- `deploy/start.sh` / `stop.sh` / `restart.sh` / `log.sh`：进程管理四件套
- `deploy/make_deploy_zip.ps1`：一键打包脚本（PowerShell）
- `deploy/.env.production`：环境变量模板（**全是 PLEASE_FILL 占位符，无真密钥**）

#### `.gitignore` 完善
- 新增 `_*.py` / `_*.txt` / `_*.png`（调试残留）
- 新增 `DGT-java*.pdf` / `Java工程师岗位JD.pdf` / `*岗位JD.pdf` / `*一面*.pdf`（测试用 PDF）
- 新增 `ai-interview_*.zip` / `cookies.txt` / `login.json` / `login_page.png` / `pdf_upload_modal.png` / `dashboard_top.png`（部署/调试残留）

#### LLM 超时配置
- v2.0 起 LLM_TIMEOUT 推荐 120（简历长 / 隐性条件丰富时 MiniMax-M3 可能超过 60 秒；超时不要低于 90，否则会卡死）

### Removed（移除）
- `create_test_data.py`：v1.0 旧测试数据生成脚本，已被 `seed_test_data.py` 替代

### Verified（验证）
- `smoke_test.py` 完整跑测：**87/87 PASS / 0 FAIL / 0 WARN / 1 SKIP**（SKIP 是 SSE v3.6 动态验证，需 `RUN_V36=1` 才跑）
- SSE 端到端新人测试：候选人 id=94 → session 125，qplan_len=**16587**（LLM 定制），Q1 完美匹配简历"抖音电商运营平台重构 LCP 3.5s→1.2s"
- SSE 端到端 Python 后端测试：候选人 id=96 → session 128，qplan_len=**12985**（LLM 定制），Q1 完美匹配"QPS 800→3500"
- 恢复会话测试：候选人 95/86/85 的 session 126/116/110 全部 LLM 定制（qplan_len 7361-7719）
- DB 数据完整性检查：5 candidate / 5 position / 6 interview_session，**无兜底题残留**
- `.env` 安全检查：未泄漏到 git 历史，所有 .py 文件无硬编码密钥

---

## [v2.0] - 2026-07-23 - 综合元评估 + 候选人门户下线 + PDF 智能导入与导出

### Changed（变更）
- LLM 切换至 MiniMax-M3（1M 上下文原生多模态；OpenAI 兼容协议直连，零业务代码改动）
  - 调用层 (`services/llm_service.py`) 保持原样，仅替换 `.env` 中的 base_url / model / api_key
  - `parse_json()` 兼容推理模型 think 块污染（MiniMax-M3 / DeepSeek-R1 自动剥离）

### Added（新增）
- 综合元评估师 Agent（最终决策裁判）：跨阶段一致性验证 + 多轮面试追踪 + 五档推荐等级
- 综合评分公式动态化（1 轮 / 2 轮 / 3+ 轮不同权重方案）
- 跨阶段一致性惩罚机制（最高扣 25 分，避免「简历说好但面试差」被掩盖）
- 综合元评估报告一键导出 PDF（含五维评分、跨阶段交叉验证、多轮追踪、入职建议）
- PDF 自动适配中文字体（Windows/Linux 双平台字体自动寻找）
- 岗位管理 PDF 智能导入：上传 JD PDF → AI 自动识别 → 弹出预览确认
- 手动录入与 PDF 智能导入两种方式并存（PDF 折叠为快捷入口）
- 实时面试页布局重排：左侧对话区 75%，右侧控制面板 25%
- 实时面试右侧控制面板：角色控制卡片合并 + AI 分析/追问可折叠
- 导航栏响应式：小屏自动折叠为汉堡菜单
- 首页 Dashboard 数据统计卡片（岗位/候选人/面试会话/已完成）
- 首页 Dashboard 更新日志卡片

### Removed（移除）
- 候选人门户入口与注册功能下线（防止误注册；前后端双保险：UI 移除 + 接口 403）

### Fixed（修复）
- 综合评分与单轮评分脱钩的潜在 bug

---

## [v1.0] - 2026-07-22 - 正式上线

### Added（新增）
- 多智能体协作面试系统（3+1 评估架构）
- 岗位管理：创建 / AI 分析 / 技能矩阵
- 候选人管理：上传简历 / AI 评估 / 匹配度排序
- 实时面试工作台：流式对话 / AI 实时分析 / 追问建议
- 单轮面试报告 + 基础综合分计算

---

[历史归档]：本系统起步于 2026 年初，最初版本为单智能体架构，无元评估机制。
# 更新日志

本文件按 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.0.0/) 规范编写，
本项目遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

> **格式说明**：
> - 每次发版在 `## [版本号] - 日期` 块下记录
> - 未发布的小修复/维护/清理可放在 `## [Unreleased]` 区块，下一发版时合并到对应版本
> - 类目固定为：`Added`（新增）/ `Changed`（变更）/ `Fixed`（修复）/ `Removed`（移除）/ `Security`（安全）
> - 首页 Dashboard 卡片只展示用户可感知的最近 3 个版本（见 `data/changelog.json`）
> - 重大版本（v1.x、v2.x 等）需配套写 Word 文档（截图 + 详细说明），交付给客户

---

## [v3.0] - 2026-07-28 - SSE 路径兜底题修复 + 评分逻辑重构 + 隐性维度异步评估

### Fixed（修复）

#### 【P0】SSE 流式接口"新人第一次面试恢复兜底题"缺陷
- **症状**：用户报告"新人第一次面试就显示恢复之前的对话，而且题也是之前的"
- **根因**：`routes/stream_routes.py` 的 `stream_candidate_analysis` worker 只创建兜底 session，**不触发 LLM 真出题**；前端 `candidates.html` 调用的恰好是这条 SSE 路径（不是 HTTP 同步路径），所以 session 永远是兜底题
- **修复**：在 SSE worker 内兜底 session 创建后**同步**调用 `InterviewService.generate_questions`（SSE_TIMEOUT=320s 充裕，LLM 出题约 60-90s），LLM 出题成功 → **覆盖** `sess.questions_plan` 为定制题
- **同步修复**：`routes/candidate_routes.py` 的 `analyze_candidate` HTTP 接口也改为同步保险
- **验证**：所有候选人当前 preparing 会话 qplan_len 均 > 14000（旧兜底题只有 2157），前端不再看到兜底题

#### 【P1】添加候选人简历数据串位 bug
- **症状**：手动粘贴简历文本时，被默默填充成了上次的 PDF 简历内容
- **根因**：`templates/candidates.html` 添加候选人成功后只清空 `newResume` textarea，未清空 `resumeFile` file input，导致下次添加候选人时浏览器静默提交上次的 PDF 覆盖粘贴的简历
- **修复**：line 487 后添加 `const fi = document.getElementById('resumeFile'); if (fi) fi.value = '';`

#### 【P2】v2.1 AI 面试评分逻辑 BUG 修复（3 个评分计算错误）
- **BUG A【P0】汇总师 5 维评分脱钩问题**：
  - 问题：`agents/interview_eval_coordinator.py` 计算综合分时调用 `_avg_dimensions()` 取三个评估师各自维度的平均，但汇总师 prompt 已经要求输出统一的 5 维评分（技术基础/项目经验/系统设计/沟通表达/学习能力），该字段完全被忽略，造成综合分与人工填写脱钩
  - 修复：删除 `_avg_dimensions()`，改用 `_compute_5dim_weighted_score()` 直接读汇总师重新评估的 5 维评分（每维 0.20，加权和转 0-100）
  - 同步：`W_TECH/W_PROJECT/W_SOFT` 老权重常量删除，改用 `W_TECH_FOUNDATION/W_PROJECT_EXP/W_SYSTEM_DESIGN/W_COMMUNICATION/W_LEARNING` 5 维权重常量（各 0.20）
  - prompt 重写：明确告知汇总师"重新评估 5 维评分"（不是取平均），加入 9-10/7-8/5-6/3-4/1-2 五档虚高防护原则
  - 前端 `templates/live_interview.html` 同步：计算明细展示由 `coord_raw_100` 改为 `coord_5dim_100`
- **BUG B【P0】隐性条件 20% 权重虚高问题**：
  - 问题：`agents/hidden_evaluator.py` 输出无 `hidden_score` 数字字段，简历汇总师 20% 隐性权重依赖 LLM 主观编造 `score_breakdown.hidden_component`，造成简历匹配度虚高
  - 修复：`hidden_evaluator.py` prompt 输出格式加 `hidden_score_breakdown`（9 个子维度各 1-10 分），代码 `_compute_hidden_score()` 加权产出 `hidden_score`（0-100）
  - 同步：`resume_coordinator.py` 删除 prompt 里的 `score_breakdown` 字段让 LLM 编的部分，代码从 `tech_result.tech_depth_score` / `soft_result.soft_score` / `hidden_result.hidden_score` 读真实数字计算 `match_score`（tech×60% + soft×20% + hidden×20%）
- **BUG C【P2】v1.0 废弃 Agent 残留**：
  - 问题：`agents/__init__.py` 还在 `from agents.evaluator import EvaluatorAgent` 等 3 个 v1.0 单 Agent，业务代码从未使用但存在误用风险
  - 修复：3 个文件顶部加 `⚠️ DEPRECATED` 文档 + v2.0 替代方案指引，`__init__.py` 移除 3 个 export，业务代码需显式 import 才能用

#### 【P2】评分基线校准（+5 分偏置）
- 用户反馈"整体分数偏低"，统一 +5 后接近期望（zy 76→81, cc 33→38, 刘洋 54→59, zzj 59→64）
- `agents/resume_coordinator.py`：`min(100, max(0, match_score + 5))`
- 同步 SQL 校准现有 4 个候选人数据

#### 部署工程 v2.1 对齐
- `smoke_test.py` `http_call` 默认 timeout 从 15 → 60 秒（兼容 LLM 调用）
- `smoke_test.py` F 段检查项同步 v2.1（`W_COORD_DIM` → `W_COORD_5DIM` / `coord_raw` → `coord_5dim_100` + 新增 5 维权重 + 5 维加权函数验证项）
- `_zip.py` 修复 `__init__.py` 被 `_*.py` 模式误过滤的重大 bug（会导致服务器部署后找不到包入口）
- `_zip.py` `must_have` 加 `interview_eval_coordinator.py` + `live_interview.html` 等 v2.1 关键文件验证

### Added（新增）

#### v3.6 隐性维度异步评估
- `services/agent_orchestrator.py` `evaluate_resume` 拆 tech+soft / hidden 两阶段流水线
- tech+soft 阶段 ≤120s → 前端展示基础分（partial_complete 事件）
- hidden 阶段 ≤180s 异步跑完 → 更新最终结果
- SSE_TIMEOUT=320s 充裕（120+180+buffer）
- 新增 4 个隐性维度（简历真实度/学习能力/职业发展方向/居住地）
- `partial_complete` 事件推前端（让用户先看到基础分，不再以为卡住）

#### v3.6.5 同步保险机制（双保险）
- 不再依赖不可靠的 daemon thread（waitress 8 worker 下时灵时不灵）
- `routes/candidate_routes.py` + `routes/stream_routes.py` 都改为同步保险
- 拿到 LLM 定制题 → 直接用定制题创建 session
- LLM 失败 → 才退到兜底题 + 后台异步补精修

#### 综合元评估报告 PDF 导出
- `utils/meta_evaluation_pdf.py`：综合元评估报告一键导出 PDF
- 支持中文字体（自动寻找系统字体，Windows/Linux 双平台）

#### 岗位 JD 解析 Agent
- `agents/position_jd_parser.py`：JD 文本解析 + 结构化字段提取
- 配合已有的 PDF 上传 → AI 识别 → 预览确认流程

#### 文本截断工具
- `utils/text_truncate.py`：防止超长简历/JD 撑爆 prompt，导致 LLM 输出质量下降
- 默认 max_chars=6000，截断时插入"内容已截断"标记

#### 冒烟测试增强
- `smoke_test.py`：从 63 项扩到 **87 项**（新增 K 段隐性维度相关检查 + v3.6 SSE 接口检查）
- 覆盖 agents/services/routes/templates/config 全栈

### Changed（变更）

#### 部署工具链完善
- `deploy/UPLOAD_GUIDE.md`（152 行）：详细云端部署手册（环境检查 → 打包 → 上传 → 一键部署 → 改密钥 → 启动）
- `deploy/install.sh`：自动装依赖 + 建 venv + pip install + 复制 .env.production → .env + 跑 init_admin
- `deploy/start.sh` / `stop.sh` / `restart.sh` / `log.sh`：进程管理四件套
- `deploy/make_deploy_zip.ps1`：一键打包脚本（PowerShell）
- `deploy/.env.production`：环境变量模板（**全是 PLEASE_FILL 占位符，无真密钥**）

#### `.gitignore` 完善
- 新增 `_*.py` / `_*.txt` / `_*.png`（调试残留）
- 新增 `DGT-java*.pdf` / `Java工程师岗位JD.pdf` / `*岗位JD.pdf` / `*一面*.pdf`（测试用 PDF）
- 新增 `ai-interview_*.zip` / `cookies.txt` / `login.json` / `login_page.png` / `pdf_upload_modal.png` / `dashboard_top.png`（部署/调试残留）

#### LLM 超时配置
- v2.0 起 LLM_TIMEOUT 推荐 120（简历长 / 隐性条件丰富时 MiniMax-M3 可能超过 60 秒；超时不要低于 90，否则会卡死）

### Removed（移除）
- `create_test_data.py`：v1.0 旧测试数据生成脚本，已被 `seed_test_data.py` 替代

### Verified（验证）
- `smoke_test.py` 完整跑测：**87/87 PASS / 0 FAIL / 0 WARN / 1 SKIP**（SKIP 是 SSE v3.6 动态验证，需 `RUN_V36=1` 才跑）
- SSE 端到端新人测试：候选人 id=94 → session 125，qplan_len=**16587**（LLM 定制），Q1 完美匹配简历"抖音电商运营平台重构 LCP 3.5s→1.2s"
- SSE 端到端 Python 后端测试：候选人 id=96 → session 128，qplan_len=**12985**（LLM 定制），Q1 完美匹配"QPS 800→3500"
- 恢复会话测试：候选人 95/86/85 的 session 126/116/110 全部 LLM 定制（qplan_len 7361-7719）
- DB 数据完整性检查：5 candidate / 5 position / 6 interview_session，**无兜底题残留**
- `.env` 安全检查：未泄漏到 git 历史，所有 .py 文件无硬编码密钥

---

## [v2.0] - 2026-07-23 - 综合元评估 + 候选人门户下线 + PDF 智能导入与导出

### Changed（变更）
- LLM 切换至 MiniMax-M3（1M 上下文原生多模态；OpenAI 兼容协议直连，零业务代码改动）
  - 调用层 (`services/llm_service.py`) 保持原样，仅替换 `.env` 中的 base_url / model / api_key
  - `parse_json()` 兼容推理模型 think 块污染（MiniMax-M3 / DeepSeek-R1 自动剥离）

### Added（新增）
- 综合元评估师 Agent（最终决策裁判）：跨阶段一致性验证 + 多轮面试追踪 + 五档推荐等级
- 综合评分公式动态化（1 轮 / 2 轮 / 3+ 轮不同权重方案）
- 跨阶段一致性惩罚机制（最高扣 25 分，避免「简历说好但面试差」被掩盖）
- 综合元评估报告一键导出 PDF（含五维评分、跨阶段交叉验证、多轮追踪、入职建议）
- PDF 自动适配中文字体（Windows/Linux 双平台字体自动寻找）
- 岗位管理 PDF 智能导入：上传 JD PDF → AI 自动识别 → 弹出预览确认
- 手动录入与 PDF 智能导入两种方式并存（PDF 折叠为快捷入口）
- 实时面试页布局重排：左侧对话区 75%，右侧控制面板 25%
- 实时面试右侧控制面板：角色控制卡片合并 + AI 分析/追问可折叠
- 导航栏响应式：小屏自动折叠为汉堡菜单
- 首页 Dashboard 数据统计卡片（岗位/候选人/面试会话/已完成）
- 首页 Dashboard 更新日志卡片

### Removed（移除）
- 候选人门户入口与注册功能下线（防止误注册；前后端双保险：UI 移除 + 接口 403）

### Fixed（修复）
- 综合评分与单轮评分脱钩的潜在 bug

---

## [v1.0] - 2026-07-22 - 正式上线

### Added（新增）
- 多智能体协作面试系统（3+1 评估架构）
- 岗位管理：创建 / AI 分析 / 技能矩阵
- 候选人管理：上传简历 / AI 评估 / 匹配度排序
- 实时面试工作台：流式对话 / AI 实时分析 / 追问建议
- 单轮面试报告 + 基础综合分计算

---

[历史归档]：本系统起步于 2026 年初，最初版本为单智能体架构，无元评估机制。# 更新日志

本文件按 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.0.0/) 规范编写，
本项目遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

> **格式说明**：
> - 每次发版在 `## [版本号] - 日期` 块下记录
> - 未发布的小修复/维护/清理可放在 `## [Unreleased]` 区块，下一发版时合并到对应版本
> - 类目固定为：`Added`（新增）/ `Changed`（变更）/ `Fixed`（修复）/ `Removed`（移除）/ `Security`（安全）
> - 首页 Dashboard 卡片只展示用户可感知的最近 3 个版本（见 `data/changelog.json`）
> - 重大版本（v1.x、v2.x 等）需配套写 Word 文档（截图 + 详细说明），交付给客户

---

## [Unreleased]

### Fixed（修复）
- **v2.1 AI 面试评分逻辑 BUG 修复**（3 个评分计算错误）：
  - **BUG A【P0】汇总师 5 维评分脱钩问题**：
    - 问题：`agents/interview_eval_coordinator.py` 计算综合分时调用 `_avg_dimensions()` 取三个评估师**各自维度**的平均，但汇总师 prompt 已经要求输出统一的 5 维评分（技术基础/项目经验/系统设计/沟通表达/学习能力），该字段完全被忽略，造成综合分与人工填写脱钩
    - 修复：删除 `_avg_dimensions()`，改用 `_compute_5dim_weighted_score()` 直接读汇总师重新评估的 5 维评分（每维 0.20，加权和转 0-100）
    - 同步：`W_TECH/W_PROJECT/W_SOFT` 老权重常量删除，改用 `W_TECH_FOUNDATION/W_PROJECT_EXP/W_SYSTEM_DESIGN/W_COMMUNICATION/W_LEARNING` 5 维权重常量（各 0.20）
    - prompt 重写：明确告知汇总师"重新评估 5 维评分"（不是取平均），加入 9-10/7-8/5-6/3-4/1-2 五档虚高防护原则
    - 前端 `templates/live_interview.html` 同步：计算明细展示由 `coord_raw_100` 改为 `coord_5dim_100`
  - **BUG B【P0】隐性条件 20% 权重虚高问题**：
    - 问题：`agents/hidden_evaluator.py` 输出无 `hidden_score` 数字字段，简历汇总师 20% 隐性权重依赖 LLM 主观编造 `score_breakdown.hidden_component`，造成简历匹配度虚高
    - 修复：`hidden_evaluator.py` prompt 输出格式加 `hidden_score_breakdown`（9 个子维度各 1-10 分），代码 `_compute_hidden_score()` 加权产出 `hidden_score`（0-100）
    - 同步：`resume_coordinator.py` 删除 prompt 里的 `score_breakdown` 字段让 LLM 编的部分，代码从 `tech_result.tech_depth_score` / `soft_result.soft_score` / `hidden_result.hidden_score` 读真实数字计算 `match_score`（tech×60% + soft×20% + hidden×20%）
  - **BUG C【P2】v1.0 废弃 Agent 残留**：
    - 问题：`agents/__init__.py` 还在 `from agents.evaluator import EvaluatorAgent` 等 3 个 v1.0 单 Agent（evaluator / resume_evaluator / question_designer），业务代码从未使用但存在误用风险
    - 修复：3 个文件顶部加 `⚠️ DEPRECATED` 文档 + v2.0 替代方案指引，`__init__.py` 移除 3 个 export，业务代码需显式 import 才能用（默认 import 路径不再暴露）
- **部署工程 v2.1 对齐**：
  - `smoke_test.py` `http_call` 默认 timeout 从 15 → 60 秒（兼容 LLM 调用）
  - `smoke_test.py` F 段检查项同步 v2.1（`W_COORD_DIM` → `W_COORD_5DIM` / `coord_raw` → `coord_5dim_100` + 新增 5 维权重 + 5 维加权函数验证项）
  - `_zip.py` 修复 `__init__.py` 被 `_*.py` 模式误过滤的重大 bug（会导致服务器部署后找不到包入口）
  - `_zip.py` `must_have` 加 `interview_eval_coordinator.py` + `live_interview.html` 等 v2.1 关键文件验证

### Verified（验证）
- `smoke_test.py` 完整跑测：**63/63 PASS / 0 FAIL / 0 WARN / 0 SKIP**
  - 较 v2.0（61 项）新增 2 项：5 维权重常量齐备 / `_compute_5dim_weighted_score` 函数存在
  - F 段「综合评分新公式」7/7 PASS
  - J 段「LLM 接入」11/11 PASS（含 MiniMax-M3 推理模型真接入 + parse-jd 业务接口）
- `agents` 包 import 验证：v2.0 全部 agent 存在 + v1.0 3 个老 agent 已不在 `__all__`（需显式 import）
- `hidden_evaluator._compute_hidden_score()` 边界测试：正常 9 项→74 / 缺失 1 项→72 / 全空→50 / 越界值退 5
- 本地 Flask 服务运行新代码正常（重启后 HTTP 200）

---

## [v2.0] - 2026-07-23 - 综合元评估 + 候选人门户下线 + PDF 智能导入与导出

### Changed（变更）
- LLM 切换至 MiniMax-M3（1M 上下文原生多模态；OpenAI 兼容协议直连，零业务代码改动）
  - 调用层 (`services/llm_service.py`) 保持原样，仅替换 `.env` 中的 base_url / model / api_key
  - `parse_json()` 兼容推理模型 think 块污染（MiniMax-M3 / DeepSeek-R1 自动剥离）

### Added（新增）
- 综合元评估师 Agent（最终决策裁判）：跨阶段一致性验证 + 多轮面试追踪 + 五档推荐等级
- 综合评分公式动态化（1 轮 / 2 轮 / 3+ 轮不同权重方案）
- 跨阶段一致性惩罚机制（最高扣 25 分，避免「简历说好但面试差」被掩盖）
- 综合元评估报告一键导出 PDF（含五维评分、跨阶段交叉验证、多轮追踪、入职建议）
- PDF 自动适配中文字体（Windows/Linux 双平台字体自动寻找）
- 岗位管理 PDF 智能导入：上传 JD PDF → AI 自动识别 → 弹出预览确认
- 手动录入与 PDF 智能导入两种方式并存（PDF 折叠为快捷入口）
- 实时面试页布局重排：左侧对话区 75%，右侧控制面板 25%
- 实时面试右侧控制面板：角色控制卡片合并 + AI 分析/追问可折叠
- 导航栏响应式：小屏自动折叠为汉堡菜单
- 首页 Dashboard 数据统计卡片（岗位/候选人/面试会话/已完成）
- 首页 Dashboard 更新日志卡片

### Removed（移除）
- 候选人门户入口与注册功能下线（防止误注册；前后端双保险：UI 移除 + 接口 403）

### Fixed（修复）
- 综合评分与单轮评分脱钩的潜在 bug

---

## [v1.0] - 2026-07-22 - 正式上线

### Added（新增）
- 多智能体协作面试系统（3+1 评估架构）
- 岗位管理：创建 / AI 分析 / 技能矩阵
- 候选人管理：上传简历 / AI 评估 / 匹配度排序
- 实时面试工作台：流式对话 / AI 实时分析 / 追问建议
- 单轮面试报告 + 基础综合分计算

---

[历史归档]：本系统起步于 2026 年初，最初版本为单智能体架构，无元评估机制。
