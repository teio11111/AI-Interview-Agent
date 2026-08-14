# AI-Interview-Agent 项目交接报告

> 生成日期：2026-08-14
> 状态：v4.4.2 + 移动端后端两条路径已就绪；Unity 客户端未开始
> 远端仓库：`git.dgtis.com/dgtai/oai-interview.git`
> 本地路径：`C:\Users\Teio\Desktop\AI-Interview-Agent`

---

## TL;DR（30 秒看懂）

- **是什么**：多智能体协作 AI 面试官系统（Flask + LLM）
- **当前版本**：v4.4.2（基线 tag `v4.4.2-pre-mobile`）+ 移动端两条后端路径
- **跑起来**：`cp .env.example .env` → 填密钥 → `python app.py` → 访问 `:8088`
- **最大风险点**：见 §7.3（LLM 稳定性、SSE 卡死、限流）
- **最优先做**：见 §8.1（移动端 Unity 客户端 Phase 2-9）

---

## 1. 项目是什么

### 1.1 一句话定位
给 HR / 面试官用的多智能体 AI 面试助手，支持：
- **岗位管理**（JD 解析、技能矩阵）
- **候选人简历分析**（PDF / 文本简历 → AI 评估 → 匹配度）
- **实时面试工作台**（流式对话、AI 追问建议、AI 实时分析）
- **面试报告**（3+1 多智能体评估 + 综合元评估）
- **多账号 + 操作审计**（5 个面试官账号、所有操作可追溯）
- **移动端后端**（HTTP + WebSocket 两条路径，Unity 客户端待开始）

### 1.2 核心价值
减少 HR 主观判断偏差，提供**结构化、可追溯、多维度交叉验证**的面试评估。

### 1.3 目标用户
内部 HR 团队、中小公司面试官；主要场景：技术岗位初筛到中面。

---

## 2. 技术栈

| 层 | 技术 |
|---|---|
| 后端 | Flask + waitress（8 worker） |
| 数据库 | MySQL 8 + SQLAlchemy ORM |
| 异步/流 | Server-Sent Events (SSE) |
| 实时通信 | Socket.IO（实时面试 ASR 流） |
| LLM | DeepSeek-v4-Flash（默认）/ MiniMax-M3（历史）/ 兼容 OpenAI 协议 |
| ASR | 讯飞实时转写（WebSocket） |
| TTS | Edge TTS（移动端路径） |
| 前端 | 原生 HTML/JS + Bootstrap，**无 SPA 框架** |
| 部署 | bash 脚本（Linux 云端） / waitress（Windows 本地） |
| 测试 | pytest + 自定义 `smoke_test.py`（87 项）+ 单元测试 |

### 2.1 Python 版本
3.11+（依赖里有 3.14 测试场景）。

### 2.2 端口约定
| 端口 | 用途 |
|---|---|
| **8088** | Flask HTTP（主服务，含 9 个蓝图） |
| **8089** | xiaozhi WebSocket（移动端路径 B） |
| **8090** | OTA mock（**仅打包 APK 时临时用**，平时不起） |

---

## 3. 仓库结构

```
AI-Interview-Agent/
├── agents/          22 个智能体定义（每个文件一个 Agent，单文件原则）
├── services/        6 个业务服务（编排、LLM、ASR、面试、简历、xiaozhi）
├── routes/          9 个 Flask 蓝图（auth/candidate/position/interview/asr/audit/stream/mobile）
├── repositories/    数据访问层
├── models/          SQLAlchemy ORM 模型
├── prompts/         LLM prompt 模板
├── utils/           工具（PDF、文本截断、logger、beijing_now、审计）
├── templates/       Jinja2 HTML 模板
├── static/          静态资源（CSS/JS/视频）
├── tests/           单元 + e2e 测试（test_extract_score/test_merge_hidden/test_mobile_e2e）
├── deploy/          部署工具链（install/start/stop/zip/UPLOAD_GUIDE）
├── docs/            项目文档（HANDOFF 等）
├── fonts/           PDF 中文字体
├── config/          配置加载
├── app.py           Flask 应用入口
├── .env.example     环境变量模板（⚠️ 必读）
├── requirements.txt / requirements_xiaozhi.txt / requirements_full.txt
├── CHANGELOG.md     ⚠️ 有重复（v3.1 出现 3 次），维护流程问题
├── 阶段总结_v4.4.2.md   阶段总结
└── 移动端流程图.md      移动端流程
```

### 3.1 关键文件
| 文件 | 作用 |
|---|---|
| `app.py` | Flask 工厂 + 9 个蓝图注册 |
| `services/agent_orchestrator.py` | **多智能体编排核心**，所有面试/简历/出题流程都走这里 |
| `services/llm_service.py` | **LLM 调用 + parse_json**，兼容推理模型 think 块 |
| `agents/base_agent.py` | 所有 Agent 基类 |
| `services/xiaozhi_bridge.py` | 移动端 WebSocket 后端 |
| `routes/mobile_routes.py` | 移动端 4 个 HTTP 接口（含 `_extract_score`） |
| `routes/stream_routes.py` | SSE 流式接口（出题 + 简历分析） |
| `deploy/UPLOAD_GUIDE.md` | 云端部署手册（152 行） |

---

## 4. 版本演化时间线

| 版本 | 日期 | 关键内容 |
|---|---|---|
| v1.0 | 2026-07-22 | 多智能体架构正式上线（3+1 评估） |
| v2.0 | 2026-07-23 | 综合元评估 + 候选人门户下线 + PDF 智能导入导出 |
| v3.0 | 2026-07-28 | SSE 兜底题修复 + 评分重构 + 隐性维度异步 |
| v3.1 | 2026-07-28 | 多账号 + 操作审计 |
| v3.2 | 2026-07-28 | 代码精简 + 安全加固 |
| v3.3 | 2026-07-29 | 项目级北京时间（云服务器 UTC 偏移 8h 修复） |
| v4.0 | 2026-08-03 | 双流音频 + AI 语义匹配 + 安全加固 |
| v4.1 | 2026-08-05 | 冒烟测试扩到 87 项 + 演示前冲刺 |
| v4.2 | 2026-08-07 | LLM 分析卡死三大根因根治 |
| v4.3 | 2026-08-09 | 彻底删除兜底题 + v4.3.1/v4.3.2 隐性评估修复 |
| v4.4 | 2026-08-10 | 两段式拆分（评估 + 出题手动触发） |
| v4.4.1 | 2026-08-11 | 出题完成后自动跳转到面试工作台 |
| v4.4.2 | 2026-08-12 | 出题 SSE 心跳 + 总超时保护 |
| **移动端** | **2026-08-13~14** | **HTTP 路径 + WebSocket 路径后端**（commit 7d69b47 + 45bc629） |

**最新 git tag**：`v4.4.2-pre-mobile`（移动端前的稳定基线）  
⚠️ 历史 tag 很少（只有这一个），未来发版应补打 tag。

---

## 5. 开发流程

### 5.1 本地启动

#### 5.1.1 一次性环境准备
```bash
# 前置：Python 3.11+, MySQL 8（root / Root123456 / ai_interview）
#       DeepSeek API key、讯飞 ASR 密钥

cp .env.example .env
# 编辑 .env 填入真密钥
```

#### 5.1.2 装依赖
```bash
pip install -r deploy/requirements_full.txt
# 移动端还需要：
pip install -r requirements_xiaozhi.txt
```

#### 5.1.3 启动
```bash
# 主服务（Flask + waitress，端口 8088）
python app.py

# 移动端 WebSocket 后端（端口 8089，可选）
python services/xiaozhi_bridge.py
```

访问：`http://localhost:8088`，账号 `admin1 ~ admin5` / 密码 `123456`。

### 5.2 加新功能的标准流程

1. **理解需求** → 读 `CHANGELOG.md` + `docs/HANDOVER.md` + 相关 HANDOFF
2. **找参照** → 在 `agents/`、`routes/`、`services/` 找类似功能
3. **写代码** → 复用 `base_agent.py`，遵守**单文件一 Agent** 原则
4. **写 prompt** → 放在 `prompts/` 目录
5. **本地验证** → 启动 Flask，浏览器/Postman 走一遍
6. **跑测试** → `python smoke_test.py`
7. **更新文档** → `CHANGELOG.md` + 阶段总结

### 5.3 测试

```bash
# 单元测试（1 秒级）
python tests/test_extract_score.py    # 19/19 PASS
python tests/test_merge_hidden.py

# e2e 测试（4-5 分钟，需 Flask 在跑）
python tests/test_mobile_e2e.py --skip-result --chat-rounds 1

# 完整冒烟（87 项，需 LLM 在线）
python smoke_test.py
```

### 5.4 部署到云端

详见 `deploy/UPLOAD_GUIDE.md`（152 行完整手册）。

```bash
# 本地打包（不含 .env / .pyc / 测试 PDF）
python deploy/make_deploy_zip.ps1
# → 生成 ai-interview_*.zip

# 上传到云端
scp ai-interview_*.zip user@server:/path/

# 云端部署
ssh user@server
cd /path && unzip ai-interview_*.zip
cd AI-Interview-Agent
bash deploy/install.sh          # 装依赖 + 初始化
# 编辑 .env（**云端密钥不同**）
bash deploy/start.sh           # 启动
tail -f logs/flask.log         # 验证
```

### 5.5 Git 提交规范

观察到的 commit message 风格：
```
<type>(<scope>): <subject>

<body（可选）>
```
- **type**：`feat` / `fix` / `refactor` / `docs` / `chore` / 测试代码无 prefix
- **scope**：模块名（移动端 / SSE / 评分 / 部署...）

示例：
- `feat(移动端): 后端两条路径完整可用 + 完整交接文档`
- `fix(移动端): chat 接口 score 字段鲁棒提取 + 交互式联调循环`
- `v4.4.2 出题 SSE 增加心跳进度与总超时保护（最小修改）`

⚠️ **风格不统一**：有的带 `vX.X` 前缀，有的不带；建议未来统一。

### 5.6 分支策略
- 只有 `master` 分支
- 一个 tag：`v4.4.2-pre-mobile`
- 未来发版建议打 tag（`v4.5`, `v5.0-mobile` 等）

---

## 6. 核心模块速通

### 6.1 多智能体协作架构

**核心入口**：`services/agent_orchestrator.py`

**协作模式**（22 个 Agent，单文件原则）：
| 流程 | Agent 组合 |
|---|---|
| **简历评估**（3 并行 + 1 汇总）| tech_evaluator + soft_evaluator + hidden_evaluator → resume_coordinator |
| **出题**（3 并行 + 1 选题官）| project_questioner + skill_questioner + weakness_questioner → question_coordinator |
| **面试对话**（2 顾问 + 1 主面试官）| tech_interviewer + soft_interviewer → interviewer |
| **面试报告**（3 评估师 + 1 汇总）| interview_project_eval + interview_tech_eval + interview_soft_eval → interview_eval_coordinator |
| **板块切分**（单 Agent）| topic_segmenter |
| **综合元评估**（最终决策）| comprehensive_meta_evaluator |

**核心方法**：`agent_orchestrator._run_parallel(agents_map, common_args, on_progress)` —— 用 `ThreadPoolExecutor` 并行调用多个 Agent。

### 6.2 一次完整面试的流程

```
出题（30-240s）—— 3 出题师并行 + 选题官筛选
  ↓
面试多轮对话（每轮 30s）—— 主面试官实时追问
  ↓
结束面试
  ↓
板块切分（topic_segmenter，约 5-10s）
  ↓
3 评估师并行 + 1 汇总（约 60-90s）
  ↓
综合元评估（comprehensive_meta_evaluator，约 30-60s）
  ↓
PDF 报告导出
```

### 6.3 LLM 调用与故障处理

**核心**：`services/llm_service.py`

**关键设计**：
- `parse_json(llm_response)`：**先剥离 think 块**（兼容 MiniMax-M3 / DeepSeek-R1 等推理模型），再 `json.loads`
- 失败 → 重试 3 次（带退避）
- 单条 LLM 调用有 `LLM_TIMEOUT=120s` 保护

**⚠️ 已知坑**：LLM 返回 JSON 超长会被截断（如选题官返回 1901 字符未完）。当前靠 `parse_json` 失败重试 + 兜底题缓解。**建议**：未来减少每题字段大小或拆批。

### 6.4 SSE 流式接口

**核心**：`routes/stream_routes.py`

**两类 SSE**：
- **简历评估流**：`/api/candidates/<id>/analyze/stream` → emit `partial_complete`（基础分）→ `complete`（最终分含隐藏维度）
- **出题流**：`/api/candidates/<id>/interview/stream` → 选题官三轮迭代 → emit `progress`/`complete`/`error`

**超时**：`SSE_TIMEOUT=180s` / `SSE_LONG_TIMEOUT=320s`

**⚠️ 已知坑**：v3.6 之前 daemon thread 异步跑在 waitress 8 worker 下时灵时不灵。**已修复**：改为同步保险 + 后台异步备份（v3.6.5）。

### 6.5 移动端两条路径

#### HTTP 路径（`routes/mobile_routes.py`）
4 个接口 + `X-Demo-Token` 鉴权 + CORS：
- `GET /api/mobile/positions` —— 岗位列表（即时）
- `POST /api/mobile/questions` —— 拉题 + 建会话（30-240s）
- `POST /api/mobile/chat` —— AI 反馈（~30s，**含 `_extract_score` 鲁棒提取**）
- `POST /api/mobile/result` —— 结束面试 + 报告（~70s）

#### WebSocket 路径（`services/xiaozhi_bridge.py`）
xiaozhi-unity 原生协议：
```
麦克风 → Opus 包 → 讯飞 ASR → DeepSeek → Edge TTS → Opus 包 → 扬声器
```
监听 `ws://0.0.0.0:8089/xiaozhi/v1/`

**修复历史**：
- OpusCodec 48kHz 内部固定 → 加 48k→16k 重采样
- TurnRecognizer.stop() 返回空 → stop + sleep(0.6) + get_text()
- ffmpeg 不识别裸 Opus packet → 改用 PyAV libopus codec
- chat score 字段空 → `_extract_score` 5 层兜底

#### Unity 客户端（**待开始**，Phase 2-9）

---

## 7. 已知问题 & 注意事项

### 7.1 已修复（按时间倒序）

- ✅ OpusCodec 48k vs ASR 16k 重采样（移动端）
- ✅ ffmpeg 不识别裸 Opus packet（改用 PyAV libopus）
- ✅ chat score 字段空字符串（`_extract_score` 5 层兜底）
- ✅ 出题 SSE 卡死（v4.4.2 心跳 + 总超时）
- ✅ LLM 分析卡死（v4.2 三大根因：parse_json 容错 + 超时 + worker 取消）
- ✅ 隐性维度 20% 权重虚高（v2.1 `hidden_score_breakdown` 9 子维度加权）
- ✅ SSE 兜底题（v3.0 同步保险）
- ✅ 候选人门户下线（v2.0）
- ✅ 云服务器时间 UTC+0 偏移（v3.3 项目级 TZ = Asia/Shanghai）
- ✅ Socket.IO CDN 在云端被防火墙挡（v4.0 本地化）
- ✅ ASR 双说话人识别重复（讯飞 TTS 文本回声）
- ✅ 云端 ASR 结果不显示（v4.0 `connect_error` 诊断 + 自动重连）

### 7.2 待关注

| 优先级 | 问题 | 建议 |
|---|---|---|
| **P0** | **Unity 客户端未开始**（Phase 2-9） | 见 §8.1 |
| P1 | **CHANGELOG.md 重复写入**（v3.1 出现 3 次） | 下次更新前手动去重，或写自动化校验 |
| P1 | **没有 README.md**（新手只能看 .env.example 摸索） | 见 §8.2 |
| P1 | **LLM JSON 超长被截断**（选题官返回 1901+ 字符） | 减 prompt 长度 / 拆批 / 加 max_tokens 限制 |
| P2 | **生产 token `mobile-demo-2026` 是默认** | 上线前必须改（`MOBILE_DEMO_TOKEN` 环境变量） |
| P2 | **xiaozhi_bridge 默认 LLM 用 `gpt-3.5-turbo`** | .env 已给 XIAOZHI_LLM_* 覆盖，部署时确认 |
| P3 | **Git tag 只有 `v4.4.2-pre-mobile` 一个** | 下次发版打 tag |
| P3 | **远端 URL 含明文密码**（`zhangzj:2wsx.asdf@`） | 生产前改 SSH 或 Token |
| P3 | **HANDOFF 移动端文档过期**（已修的 bug 仍标"待关注"） | 见 §8.2 |

### 7.3 最大风险点（接手时重点关注）

1. **LLM 调用是命脉** —— 所有核心功能都依赖 LLM 稳定返回。任何 LLM JSON 解析失败、超时、限流都会直接影响用户体验。
   - **优先做**：加 LLM 调用监控 + 自动降级到更便宜的模型
2. **SSE 流式接口是体验关键** —— 卡死/超时用户立刻感受到。
   - **优先做**：加客户端超时提示 + 服务端心跳 + 自动重连（部分已做）
3. **移动端路径与主项目共用 LLM 配额** —— 多设备同时跑可能撞限流。
   - **优先做**：加 LLM-CACHE（已部分有）和请求队列

---

## 8. 待做清单

### 8.1 P0：移动端 Unity 客户端

按计划 Phase 2-9：
- Phase 2：Unity 工程准备（半天）
- Phase 3：`HttpProtocol.cs` 实现（1 天）
- Phase 4：sherpa-onnx ASR 集成（1 天，**可选**——已有讯飞 ASR 替代）
- Phase 5：UI 改造（1.5 天）
- Phase 6：TTS + 3D 形象 + uLipSync（1 天）
- Phase 7：真机联调（1 天）
- Phase 8：APK 打包（半天，预计 50-80 MB）
- Phase 9：演示准备（半天）

**预计总工作量**：5-7 天纯工作时间

**现成资源**：
- `C:\Users\Teio\Desktop\XiaozhiInterview\` —— xiaozhi-unity 开源项目，已出 APK（170 MB）
- APK 默认连 `wss://api.tenclass.net/xiaozhi/v1/`，需改 `Assets/Settings/AppPresets.asset` 的 `_webSocketUrl` 指到本地后端再重打包
- 详细见 `docs/HANDOFF_移动端AI面试助手.md`

### 8.2 P1：文档维护

- **补 README.md**（根目录快速入门：1-2 页）
- **更新 `docs/HANDOFF_移动端AI面试助手.md`**：
  - 删除已过期的"待关注：chat score 字段"
  - 标记"E2E-4 交互式循环完成"
  - 补充"_extract_score"测试位置
- **CHANGELOG.md 去重**（v3.1 出现 3 次，机械工作）

### 8.3 中长期 roadmap（建议）

- LLM 调用监控 + 自动降级（不同模型间 failover）
- LLM-CACHE 命中统计 + 可视化
- ASR 结果自动校准（识别错误候选字）
- 移动端真实麦克风录音端到端验证（Unity APK 装到手机）
- 远端 URL 改 SSH/Token（移除明文密码）
- models/ 目录如果被 .gitignore 排除需要修正

---

## 9. 关键资源链接

### 9.1 代码位置

| 文件 | 作用 |
|---|---|
| `app.py` | Flask 应用入口 |
| `services/agent_orchestrator.py` | 多智能体编排核心 |
| `services/llm_service.py` | LLM 调用 + JSON 解析 |
| `services/xiaozhi_bridge.py` | 移动端 WebSocket 后端 |
| `routes/mobile_routes.py` | 移动端 HTTP 接口 |
| `routes/stream_routes.py` | SSE 流式接口 |
| `agents/base_agent.py` | 所有 Agent 基类 |
| `agents/comprehensive_meta_evaluator.py` | 综合元评估 |
| `agents/question_coordinator.py` | 选题官 |

### 9.2 文档位置

| 文件 | 作用 |
|---|---|
| `CHANGELOG.md` | 版本变更日志（⚠️ 有重复） |
| `阶段总结_v4.4.2.md` | 阶段总结 |
| `移动端流程图.md` | 移动端流程 |
| `docs/HANDOFF_移动端AI面试助手.md` | 移动端交接文档 |
| `docs/HANDOVER.md` | **本文件**，项目级交接 |
| `deploy/UPLOAD_GUIDE.md` | 云端部署手册（152 行） |
| `.env.example` | 环境变量模板（必读） |

### 9.3 远端仓库

```
origin  http://zhangzj:2wsxasdf@git.dgtis.com/dgtai/oai-interview.git
```

⚠️ URL 包含用户名密码（已公开在仓库里），**生产前应改为 SSH 或 Token**。

### 9.4 关键命令速查

```bash
# 启动
python app.py                                  # 主服务 :8088
python services/xiaozhi_bridge.py              # 移动端 :8089

# 测试
python smoke_test.py                           # 完整冒烟 87 项
python tests/test_extract_score.py             # score 提取 19 项
python tests/test_mobile_e2e.py --skip-result  # 移动端 HTTP 路径

# 本地联调
python _local_e2e.py                           # WebSocket 路径麦克风联调

# 部署
python deploy/make_deploy_zip.ps1              # 打包
bash deploy/install.sh                         # 云端装环境
bash deploy/start.sh                           # 云端启动
bash deploy/log.sh                             # 看日志
```

---

## 10. 接手第一步建议

### 10.1 第一天（4 小时）

1. **通读文档**（1 小时）
   - 本文件 §1-4
   - `CHANGELOG.md` 最近 5 个版本
   - `docs/HANDOFF_移动端AI面试助手.md`
2. **跑起来**（1 小时）
   - 按 §5.1 装依赖 + 启动 Flask
   - 浏览器访问 :8088，登录 admin1/123456
   - 创建岗位 → 创建候选人 → 走完一次面试
3. **跑测试**（30 分钟）
   - `python smoke_test.py` 看 87 项过不过
   - `python tests/test_extract_score.py` 看 19 项
4. **理解架构**（1.5 小时）
   - 读 `services/agent_orchestrator.py`（核心）
   - 读 `agents/base_agent.py`（基类）
   - 在浏览器打断点跟一个 LLM 调用

### 10.2 第二天（4 小时）

5. **找一个小 bug 或改进点开始改**（建议方向）
   - CHANGELOG 去重（机械工作，熟悉代码结构）
   - 补 README.md
   - 加一个 LLM 调用监控
6. **commit + push**（30 分钟）
   - 按 §5.5 规范写 commit message
   - `git push origin master`

### 10.3 第三天起

7. **优先 P0：移动端 Unity 客户端**（如接手时还没人做）
   - 按 §8.1 + `docs/HANDOFF_移动端AI面试助手.md` 启动 Phase 2

---

## 11. 维护窗口建议

- **每周**：跑一次 `smoke_test.py`，确认 87 项全过
- **每月**：检查 `.env` 密钥是否需要轮换；检查 LLM 限流是否撞墙
- **每季度**：扫 git log 看 `CHANGELOG.md` 重复情况；备份数据库；打新版本 tag

---

## 12. 给接手者的最后一句话

本项目核心是 **LLM 多智能体协作**，命脉是 LLM 稳定性。  
所有功能都依赖 LLM 返回结构化 JSON + 长上下文（候选人简历、岗位 JD、对话历史）。  
**遇到任何问题，先问"是 LLM 返回的问题吗？"** —— 大概率是。  
其他都是工程实现细节。

> 文档生成：2026-08-14  
> 生成者：AI 助手（基于 git log + 现有文档 + 实地调研自动整理）  
> 状态：v4.4.2 + 移动端两条后端路径  
> 适用对象：下一位接手本项目的工程师