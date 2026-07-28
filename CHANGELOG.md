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
