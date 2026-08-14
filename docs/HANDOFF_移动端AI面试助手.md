# 移动端 AI 面试助手 — 交接文档

> 最近更新：2026-08-14
> 接手人：你自己 / 下一个工程师
> 状态：后端两条路径全部跑通；Unity 客户端未开始

---

## 一句话总结

HTTP 路径（mobile_routes.py）和 WebSocket 路径（xiaozhi_bridge.py）的**后端都已完整可用并通过端到端测试**。Unity 工程那块没碰过，下一步从 Phase 2 开始。

---

## 项目位置

- 仓库根：`./AI-Interview-Agent/`
- **HTTP 接口**（方案 A，按计划）：`routes/mobile_routes.py`（4 个接口）
- **WebSocket 接口**（方案 B，xiaozhi-unity 默认模式）：`services/xiaozhi_bridge.py`
- **依赖清单**：`requirements_xiaozhi.txt`（WebSocket 路径额外依赖）
- **端到端测试**：
  - `tests/test_mobile_e2e.py` — HTTP 路径（positions/questions/chat/result）✅ 已入库
  - `_local_e2e.py` — WebSocket 路径（ASR+LLM+TTS，需先 `python services/xiaozhi_bridge.py` 启动）⚠ 被 .gitignore 排除，本地保留
- 详细计划：`docs/plan_mobile.md`（本地保留，未入库）

---

## 已完成（Phase 0+1 + 路径 B 后端）

### Phase 0：项目初始化
- 直接在现有 AI-Interview-Agent 仓库内开发（没独立 git submodule 化）
- 新增文件全部以 routes/、services/、requirements_ 命名

### Phase 1：后端 4 个 HTTP 接口 ✅
| 接口 | 方法 | 路径 | 验证状态 |
|---|---|---|---|
| 岗位列表 | GET | `/api/mobile/positions` | ✅ |
| 拉题 + 建会话 | POST | `/api/mobile/questions` | ✅（耗时 30-240s，依赖 LLM 出题） |
| 对话反馈 | POST | `/api/mobile/chat` | ✅（耗时 ~30s，3 个 Agent 并行） |
| 结束面试 | POST | `/api/mobile/result` | ✅（耗时 ~70s，返回 14 字段报告） |

**额外特性**：
- X-Demo-Token 鉴权（默认 token: `mobile-demo-2026`，生产替换）
- CORS 全局支持（演示用）
- 自动 reuse 同 device_id+岗位 的候选人

### 路径 B（计划外，实验性）：xiaozhi WebSocket 后端 ✅
- 文件：`services/xiaozhi_bridge.py`（879 行）
- 实现：OpusCodec (48k→16k 重采样) + 讯飞 ASR + DeepSeek LLM + Edge TTS
- 协议：xiaozhi-unity 原生 WebSocket（`ws://0.0.0.0:8089/xiaozhi/v1/`）
- 联调通过：`_local_e2e.py --audio <wav>` 能完整跑通 STT → LLM → TTS
- 已知限制：客户端 TTS 播放（PyAV 解码裸 Opus 包）已修复但未在本地真机验证声音输出

---

## 未开始（Phase 2-9）

| Phase | 内容 | 工作量 | 备注 |
|---|---|---|---|
| 2 | Unity 工程准备 | 半天 | 需 Unity 2022.3.59f1 LTS |
| 3 | HttpProtocol.cs 实现 | 1 天 | 按计划模板，post 到 3 个 HTTP 接口 |
| 4 | sherpa-onnx ASR 集成 | 1 天 | 计划写客户端本地 ASR，但当前 WebSocket 后端已是替代方案 |
| 5 | UI 改造 | 1.5 天 | 启动页/选岗/答题/结果 4 页 |
| 6 | TTS + 3D 形象 | 1 天 | Edge TTS + VRM + uLipSync |
| 7 | 真机联调 | 1 天 | 安卓手机连本地 Flask |
| 8 | APK 打包 | 半天 | arm64，预计 50-80 MB |
| 9 | 演示准备 | 半天 | 话术 + 应急 + 录屏 |

---

## 怎么跑起来

### HTTP 路径
```bash
# 1. 主项目依赖（已有）
pip install -r deploy/requirements_full.txt

# 2. 启动 Flask
python app.py
# → 服务监听 ws://0.0.0.0:8088

# 3. 端到端测试（HTTP 路径）
python tests/test_mobile_e2e.py
# → 全跑约 4-5 分钟（出题 + 1 轮对话 + result）
# → 加 --skip-result 可只验证 questions/chat
# → 加 --device-id devXXX 避免和已有数据冲突
```

### WebSocket 路径（路径 B）
```bash
# 1. 额外依赖
pip install -r requirements_xiaozhi.txt

# 2. 配置 .env（已有 XFYUN_API_KEY / LLM 配置）

# 3. 启动 xiaozhi 后端
python services/xiaozhi_bridge.py
# → 服务监听 ws://0.0.0.0:8089/xiaozhi/v1/

# 4. 联调测试（需要 16k mono s16le WAV）
python _local_e2e.py --audio new_voice_16k.wav
# → 输出 STT/LLM/TTS 全链路结果
```

---

## 已知问题 & 注意事项

### 已修复
- **OpusCodec 48kHz vs ASR 16kHz**：PyAV Opus 内部固定 48kHz，原 `decoder.rate=16000` 被忽略，导致讯飞接收到的音频被理解为 3x 拉伸。已加 `AudioResampler(48k → 16k)`。
- **TurnRecognizer.stop() 返回空**：客户端 listen_stop 太早时讯飞回调没就位。改为 `stop() + sleep(0.6) + get_text()` 三步走。
- **TTS 播放 ffmpeg 解码失败**：ffmpeg 的 `-f opus/-f ogg` 不识别裸 Opus packet。改用 PyAV 直接走 libopus codec。

### 待关注
- **chat 接口 score 字段**：当前 chat 返回的 feedback dict 里 score 字段是空字符串（因为 score 在子字段里）。需要在 mobile_routes.py chat 函数里调整字段提取逻辑。
- **超时**：客户端 HTTP 请求要 300s+ 超时（出题 30-240s，chat ~30s，result ~70s）。
- **LLM 缓存**：相同岗位 + resume 组合会命中 LLM-CACHE，重复跑测试会很快。
- **生产 token**：`_expected_token()` 默认 `mobile-demo-2026`，生产前必须改。

---

## 下次接手第一步

1. 装 Unity 2022.3.59f1 LTS（参考 Phase 2）
2. `git submodule add https://github.com/SylarLi/xiaozhi-unity.git client` 拉到独立目录（如果决定走 WebSocket 路径，submodule 仓库里直接有 HttpProtocol.cs 模板可参考）
3. 跑一次 `python tests/test_mobile_e2e.py --skip-result` 确认 HTTP 路径本地正常（~3 分钟）
4. 选一条路径（HTTP 或 WebSocket）开始 Phase 3

---

## 提问优先级

如果只能问一个问题，**先问：方案 A（HTTP）还是方案 B（WebSocket）？**
- HTTP：简单、计划已写好、复用现有 Flask
- WebSocket：流式实时、原生 xiaozhi-unity 风格、需要 Opus 编解码
