"""xiaozhi-unity WebSocket 协议桥接服务。

该服务只负责将 xiaozhi-unity 的原生 WebSocket 协议接入现有项目：
1. 校验握手、鉴权和 hello 消息；
2. 将客户端的 Opus 音频交给讯飞实时 ASR；
3. 将识别文本交给 OpenAI 兼容的 LLM 接口；
4. 通过 Edge TTS 生成语音并编码为 Opus 返回客户端。

本地联调时可直接使用以下默认配置：
    WebSocket: ws://<电脑局域网 IP>:8089/xiaozhi/v1/
    Token:     test-token
"""
from __future__ import annotations

import argparse
import asyncio
from hmac import compare_digest
import io
import json
import os
import ssl
import subprocess
import sys
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

# 允许直接执行 services/xiaozhi_bridge.py，也能正常导入项目模块。
_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

try:
    from dotenv import load_dotenv
    load_dotenv(_PROJECT_ROOT / ".env")
except Exception:
    pass

import requests
from services.asr_service import get_asr_service
from utils.logger import logger


class XiaozhiBridgeError(RuntimeError):
    """协议或运行时错误。"""


@dataclass
class XiaozhiSettings:
    """从环境变量读取桥接服务配置。"""

    host: str = "0.0.0.0"
    port: int = 8089
    path: str = "/xiaozhi/v1/"
    access_token: str = "test-token"
    input_sample_rate: int = 16000
    output_sample_rate: int = 24000
    frame_duration_ms: int = 60
    llm_api_url: str = ""
    llm_api_key: str = ""
    llm_model: str = ""
    llm_timeout: int = 90
    tts_enabled: bool = True
    tts_voice: str = "zh-CN-XiaoxiaoNeural"
    max_history: int = 12
    max_message_size: int = 2 * 1024 * 1024
    ssl_cert: str = ""
    ssl_key: str = ""
    interview_role: str = "技术面试官"
    position_name: str = ""
    position_requirements: str = ""
    resume_text: str = ""

    @classmethod
    def from_config(cls) -> "XiaozhiSettings":
        """读取配置，兼容直接使用环境变量或现有 LLM 配置。"""
        def env_bool(name: str, default: bool) -> bool:
            value = os.getenv(name)
            if value is None:
                return default
            return value.strip().lower() in {"1", "true", "yes", "on"}

        def env_int(name: str, default: int) -> int:
            try:
                return int(os.getenv(name, str(default)))
            except (TypeError, ValueError):
                return default

        return cls(
            host=os.getenv("XIAOZHI_WS_HOST", "0.0.0.0"),
            port=env_int("XIAOZHI_WS_PORT", 8089),
            path=os.getenv("XIAOZHI_WS_PATH", "/xiaozhi/v1/"),
            access_token=os.getenv("XIAOZHI_ACCESS_TOKEN", "test-token"),
            input_sample_rate=env_int("XIAOZHI_INPUT_SAMPLE_RATE", 16000),
            output_sample_rate=env_int("XIAOZHI_OUTPUT_SAMPLE_RATE", 24000),
            frame_duration_ms=env_int("XIAOZHI_FRAME_DURATION_MS", 60),
            llm_api_url=os.getenv("XIAOZHI_LLM_API_URL")
            or os.getenv("LLM_API_URL", "https://api.openai.com/v1/chat/completions"),
            llm_api_key=os.getenv("XIAOZHI_LLM_API_KEY") or os.getenv("LLM_API_KEY", ""),
            llm_model=os.getenv("XIAOZHI_LLM_MODEL") or os.getenv("LLM_MODEL", "gpt-3.5-turbo"),
            llm_timeout=env_int("XIAOZHI_LLM_TIMEOUT", 90),
            tts_enabled=env_bool("XIAOZHI_TTS_ENABLED", True),
            tts_voice=os.getenv("XIAOZHI_TTS_VOICE", "zh-CN-XiaoxiaoNeural"),
            max_history=env_int("XIAOZHI_MAX_HISTORY", 12),
            max_message_size=env_int("XIAOZHI_MAX_MESSAGE_SIZE", 2 * 1024 * 1024),
            ssl_cert=os.getenv("XIAOZHI_SSL_CERT", ""),
            ssl_key=os.getenv("XIAOZHI_SSL_KEY", ""),
            interview_role=os.getenv("XIAOZHI_INTERVIEW_ROLE", "技术面试官"),
            position_name=os.getenv("XIAOZHI_POSITION_NAME", ""),
            position_requirements=os.getenv("XIAOZHI_POSITION_REQUIREMENTS", ""),
            resume_text=os.getenv("XIAOZHI_RESUME_TEXT", ""),
        )


class OpusCodec:
    """Opus 编解码适配器。

    客户端发送的是 16 kHz、单声道、60 ms 的裸 Opus 包；服务端返回
    24 kHz、单声道、60 ms 的 Opus 包。输入包用 PyAV/FFmpeg 解码，
    TTS PCM 用 imageio-ffmpeg 编码，避免依赖系统是否预装 libopus。

    注意：Opus 内部采样率固定为 48 kHz，PyAV 的 Opus 解码器会
    以 48 kHz 输出 frame，需要通过 AudioResampler 重采样到
    业务需要的 16 kHz 后再送 ASR。
    """

    def __init__(self, input_rate: int, output_rate: int, frame_duration_ms: int):
        self.input_rate = input_rate
        self.output_rate = output_rate
        self.input_frame_size = input_rate * frame_duration_ms // 1000
        self.output_frame_size = output_rate * frame_duration_ms // 1000
        self._decoder: Any = None
        self._resampler: Any = None
        self._ffmpeg: str = ""
        self._load()

    @property
    def available(self) -> bool:
        return self._decoder is not None and bool(self._ffmpeg)

    def _load(self) -> None:
        try:
            import av
            import imageio_ffmpeg

            decoder = av.CodecContext.create("opus", "r")
            # Opus 内部固定 48 kHz，设置 rate=48000 让解码输出符合实际。
            decoder.rate = 48000
            decoder.layout = "mono"
            decoder.format = "s16"
            self._decoder = decoder
            self._ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
        except Exception as exc:  # pragma: no cover - 取决于本机运行环境
            logger.warning(f"[xiaozhi] Opus 初始化失败: {exc}")

    def _get_resampler(self) -> Any:
        """延迟创建 48kHz → input_rate 的重采样器。"""
        if self._resampler is None:
            import av
            self._resampler = av.AudioResampler(
                format="s16",
                layout="mono",
                rate=self.input_rate,
            )
        return self._resampler

    def decode(self, packet: bytes) -> Optional[bytes]:
        if not self.available:
            raise XiaozhiBridgeError("未安装或无法加载 PyAV/FFmpeg，无法解码客户端音频")
        try:
            frames = list(self._decoder.decode(self._make_packet(packet)))
        except Exception as exc:
            # PyAV 会在解码器需要更多输入时抛 EAGAIN/EOF，静默忽略。
            logger.debug(f"[xiaozhi] Opus decode 跳过: {exc}")
            return None
        if not frames:
            return None
        try:
            resampler = self._get_resampler()
        except Exception as exc:
            logger.warning(f"[xiaozhi] resampler 创建失败: {exc}")
            return None
        pcm_chunks: list[bytes] = []
        for frame in frames:
            try:
                resampled_list = resampler.resample(frame)
            except Exception as exc:
                logger.debug(f"[xiaozhi] resample 跳过: {exc}")
                continue
            if not isinstance(resampled_list, list):
                resampled_list = [resampled_list]
            for rf in resampled_list:
                if rf is None:
                    continue
                frame_bytes = bytes(rf.planes[0])
                sample_bytes = rf.samples * 2
                pcm_chunks.append(frame_bytes[:sample_bytes])
        return b"".join(pcm_chunks) or None

    @staticmethod
    def _make_packet(packet: bytes) -> Any:
        import av

        return av.Packet(packet)

    def encode(self, pcm: bytes) -> list[bytes]:
        if not self.available:
            raise XiaozhiBridgeError("未安装或无法加载 FFmpeg，无法编码回复音频")
        frame_bytes = self.output_frame_size * 2
        if not pcm:
            return []
        command = [
            self._ffmpeg,
            "-nostdin",
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "s16le",
            "-ar",
            str(self.output_rate),
            "-ac",
            "1",
            "-i",
            "pipe:0",
            "-c:a",
            "libopus",
            "-application",
            "voip",
            "-frame_duration",
            str(self.output_frame_size * 1000 // self.output_rate),
            "-f",
            "ogg",
            "pipe:1",
        ]
        result = subprocess.run(
            command,
            input=pcm,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        if result.returncode != 0:
            error = result.stderr.decode("utf-8", errors="ignore")[-500:]
            raise XiaozhiBridgeError(f"Opus 编码失败: {error}")

        try:
            import av

            container = av.open(io.BytesIO(result.stdout))
            packets: list[bytes] = []
            for packet in container.demux():
                if packet.size == 0:
                    continue
                encoded = bytes(packet)
                # Ogg Opus 的元数据包以 OpusHead/OpusTags 开头。
                if encoded.startswith((b"OpusHead", b"OpusTags")):
                    continue
                if encoded:
                    packets.append(encoded)
            return packets
        except Exception as exc:
            raise XiaozhiBridgeError(f"解析 Opus 输出失败: {exc}") from exc


class TurnRecognizer:
    """将一个 listen 周期映射到一个讯飞实时 ASR 会话。"""

    def __init__(self, on_result: Callable[[str, bool], None]):
        self._service = get_asr_service()
        self._on_result = on_result
        self._session: Any = None
        self._lock = threading.RLock()
        self._segments: list[str] = []
        self._text = ""
        self._configured = bool(
            getattr(self._service, "app_id", None)
            and getattr(self._service, "api_key", None)
        )

    @property
    def configured(self) -> bool:
        return self._configured

    def start(self) -> bool:
        with self._lock:
            self._segments.clear()
            self._text = ""
        if not self._configured:
            logger.warning("[xiaozhi] XFYUN_APP_ID/XFYUN_API_KEY 未配置，ASR 不可用")
            return False

        def on_result(text: str, speaker: str, is_final: bool, bg: Any = None, ed: Any = None):
            text = (text or "").strip()
            if not text:
                return
            with self._lock:
                if is_final:
                    self._segments.append(text)
                    self._text = "".join(self._segments)
                else:
                    # 中间结果用于界面实时显示，最终结果仍以 stop 后为准。
                    self._text = self._text or text
                current_text = self._text
            try:
                self._on_result(current_text, is_final)
            except Exception as exc:
                logger.warning(f"[xiaozhi] ASR 回调发送失败: {exc}")

        def on_speaker_change(speaker: str):
            logger.debug(f"[xiaozhi] ASR speaker={speaker}")

        self._session = self._service.create_session(
            session_id=uuid.uuid4().hex,
            on_result=on_result,
            on_speaker_change=on_speaker_change,
        )
        try:
            started = self._session.start()
        except Exception as exc:
            logger.error(f"[xiaozhi] ASR 启动失败: {exc}")
            self._session = None
            return False
        if not started:
            self._session = None
        return bool(started)

    def feed(self, pcm: bytes) -> None:
        if not pcm or not self._configured:
            return
        with self._lock:
            session = self._session
        if session is not None:
            session.send_audio(pcm)

    def get_text(self) -> str:
        """读取当前累积的识别文本（不关心是否 stop）。"""
        with self._lock:
            return self._text.strip()

    def stop(self) -> str:
        with self._lock:
            session = self._session
            self._session = None
        if session is not None:
            try:
                session.stop()
            except Exception as exc:
                logger.warning(f"[xiaozhi] ASR 停止失败: {exc}")
        # 讯飞 stop 内部会先发送结束帧，回调可能稍后到达。
        deadline = time.monotonic() + 0.8
        while time.monotonic() < deadline:
            with self._lock:
                if self._text:
                    break
            time.sleep(0.05)
        with self._lock:
            return self._text.strip()


class InterviewLLM:
    """最小可用的 OpenAI 兼容对话客户端。"""

    PLACEHOLDER_KEYS = {"", "your-api-key-here", "YOUR_API_KEY", "test-token"}

    def __init__(self, settings: XiaozhiSettings):
        self.settings = settings

    @property
    def configured(self) -> bool:
        return bool(
            self.settings.llm_api_url
            and self.settings.llm_api_key
            and self.settings.llm_api_key not in self.PLACEHOLDER_KEYS
        )

    def _system_prompt(self) -> str:
        position = self.settings.position_name or "未指定岗位"
        requirements = self.settings.position_requirements or "根据候选人回答动态判断"
        resume = self.settings.resume_text or "暂无候选人简历"
        return (
            f"你是一名专业、友善、严谨的中文{self.settings.interview_role}。"
            f"当前岗位：{position}。岗位要求：{requirements}。\n"
            f"候选人简历摘要：{resume}\n"
            "请根据候选人的回答自然推进面试：默认提出一个聚焦岗位能力的追问，"
            "必要时先给出一句简短反馈，再提出问题；一次只输出 1~3 句，"
            "不要输出 JSON、Markdown 表格、评分或内部思考过程。"
        )

    def ask(self, history: list[dict[str, str]]) -> Optional[str]:
        if not self.configured:
            logger.warning("[xiaozhi] LLM 未配置，识别到文本后不会生成面试回复")
            return None
        messages = [{"role": "system", "content": self._system_prompt()}]
        messages.extend(history)
        payload = {
            "model": self.settings.llm_model,
            "messages": messages,
            "temperature": 0.6,
            "max_tokens": 512,
        }
        headers = {
            "Authorization": f"Bearer {self.settings.llm_api_key}",
            "Content-Type": "application/json",
        }
        try:
            response = requests.post(
                self.settings.llm_api_url,
                headers=headers,
                json=payload,
                timeout=self.settings.llm_timeout,
            )
            response.raise_for_status()
            body = response.json()
            content = (body.get("choices") or [{}])[0].get("message", {}).get("content")
            return (content or "").strip() or None
        except Exception as exc:
            logger.error(f"[xiaozhi] LLM 调用失败: {exc}")
            return None


class SpeechSynthesizer:
    """Edge TTS + ffmpeg + Opus 的异步语音合成器。"""

    def __init__(self, settings: XiaozhiSettings):
        self.settings = settings
        self._ffmpeg: str = ""

    @property
    def available(self) -> bool:
        if not self.settings.tts_enabled:
            return False
        try:
            import edge_tts  # noqa: F401
            import imageio_ffmpeg  # noqa: F401

            self._ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
            return True
        except Exception:
            return False

    def _synthesize_sync(self, text: str) -> bytes:
        if not self.available:
            return b""

        import edge_tts
        import imageio_ffmpeg

        audio = bytearray()
        async def collect_audio() -> None:
            communicate = edge_tts.Communicate(text, voice=self.settings.tts_voice)
            async for chunk in communicate.stream():
                if chunk.get("type") == "audio":
                    audio.extend(chunk.get("data", b""))

        asyncio.run(collect_audio())
        if not audio:
            return b""

        command = [
            self._ffmpeg or imageio_ffmpeg.get_ffmpeg_exe(),
            "-nostdin",
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "mp3",
            "-i",
            "pipe:0",
            "-f",
            "s16le",
            "-ac",
            "1",
            "-ar",
            str(self.settings.output_sample_rate),
            "pipe:1",
        ]
        result = subprocess.run(
            command,
            input=bytes(audio),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        if result.returncode != 0:
            error = result.stderr.decode("utf-8", errors="ignore")[-500:]
            raise XiaozhiBridgeError(f"TTS 音频转 PCM 失败: {error}")
        return result.stdout

    async def synthesize_pcm(self, text: str) -> bytes:
        return await asyncio.to_thread(self._synthesize_sync, text)


@dataclass
class XiaozhiSession:
    """一个 WebSocket 客户端连接对应的面试会话。"""

    websocket: Any
    settings: XiaozhiSettings
    loop: asyncio.AbstractEventLoop
    path: str
    device_id: str = ""
    client_id: str = ""
    session_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    llm: Any = None
    codec: Any = None
    tts: Any = None
    recognizer: Any = None
    history: list[dict[str, str]] = field(default_factory=list)
    listening: bool = False
    processing: bool = False
    aborted: bool = False
    tts_task: Optional[asyncio.Task] = None

    def __post_init__(self) -> None:
        self.llm = InterviewLLM(self.settings)
        self.codec = OpusCodec(
            self.settings.input_sample_rate,
            self.settings.output_sample_rate,
            self.settings.frame_duration_ms,
        )
        self.tts = SpeechSynthesizer(self.settings)
        self.recognizer = TurnRecognizer(self._emit_asr_result)

    async def _send_json(self, payload: dict[str, Any]) -> None:
        if self.websocket is None or self.websocket.state.name != "OPEN":
            return
        await self.websocket.send(
            json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        )

    async def _send_bytes(self, payload: bytes) -> None:
        if self.websocket is None or self.websocket.state.name != "OPEN":
            return
        await self.websocket.send(payload)

    def _emit_asr_result(self, text: str, is_final: bool) -> None:
        """从 ASR 工作线程安全地回到 WebSocket 事件循环。"""
        if not text:
            return
        try:
            asyncio.run_coroutine_threadsafe(
                self._send_json({"type": "stt", "text": text, "is_final": is_final}),
                self.loop,
            )
        except Exception as exc:
            logger.debug(f"[xiaozhi] 忽略已关闭连接的 ASR 回调: {exc}")

    async def _send_hello(self) -> None:
        await self._send_json(
            {
                "type": "hello",
                "session_id": self.session_id,
                "transport": "websocket",
                "audio_params": {
                    "format": "opus",
                    "sample_rate": self.settings.output_sample_rate,
                    "channels": 1,
                    "frame_duration": self.settings.frame_duration_ms,
                },
            }
        )

    async def _start_listening(self) -> None:
        if self.listening:
            return
        self.listening = True
        self.aborted = False
        started = await asyncio.to_thread(self.recognizer.start)
        if not started and self.recognizer.configured:
            await self._send_json(
                {
                    "type": "alert",
                    "status": "error",
                    "message": "讯飞语音识别启动失败，请检查配置。",
                    "emotion": "sad",
                }
            )

    async def _stop_listening(self) -> None:
        if not self.listening:
            return
        self.listening = False
        # 先调 stop 发结束帧并等待讯飞返回最终结果
        await asyncio.to_thread(self.recognizer.stop)
        # 额外补一个等待周期，让回调完全到位
        await asyncio.sleep(0.6)
        # 直接读 TurnRecognizer 内部的最新文本（不再依赖 stop() 返回值）
        text = await asyncio.to_thread(self.recognizer.get_text)
        logger.info(f"[xiaozhi] ASR 最终文本: {text!r}")
        if not text:
            return
        if self.processing:
            return
        self.processing = True
        try:
            self.history.append({"role": "user", "content": text})
            self._trim_history()
            await self._send_json({"type": "stt", "text": text, "is_final": True})
            response = await asyncio.to_thread(self.llm.ask, self.history)
            if not response:
                await self._send_json(
                    {
                        "type": "alert",
                        "status": "error",
                        "message": "LLM 未配置或调用失败。",
                        "emotion": "sad",
                    }
                )
                return
            self.history.append({"role": "assistant", "content": response})
            self._trim_history()
            await self._send_json({"type": "llm", "emotion": "neutral"})
            self.tts_task = asyncio.create_task(self._speak(response))
            try:
                await self.tts_task
            finally:
                self.tts_task = None
        finally:
            self.processing = False

    def _trim_history(self) -> None:
        limit = max(2, self.settings.max_history * 2)
        if len(self.history) > limit:
            del self.history[:-limit]

    async def _speak(self, text: str) -> None:
        self.aborted = False
        await self._send_json({"type": "tts", "state": "start"})
        await self._send_json({"type": "tts", "state": "sentence_start", "text": text})
        try:
            if self.tts.available and self.codec.available:
                pcm = await self.tts.synthesize_pcm(text)
                for packet in self.codec.encode(pcm):
                    if self.aborted:
                        break
                    await self._send_bytes(packet)
            elif self.tts.available:
                logger.warning("[xiaozhi] TTS 可用但 Opus 不可用，仅发送控制消息")
        except Exception as exc:
            logger.error(f"[xiaozhi] TTS 失败: {exc}")
            await self._send_json(
                {
                    "type": "alert",
                    "status": "warning",
                    "message": "语音合成失败，已保留文字回复。",
                    "emotion": "sad",
                }
            )
        finally:
            if self.websocket is not None and self.websocket.state.name == "OPEN":
                await self._send_json({"type": "tts", "state": "stop"})

    async def _handle_client_hello(self, raw: str) -> None:
        """校验客户端 hello，避免把非 xiaozhi 连接当成音频会话。"""
        try:
            message = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise XiaozhiBridgeError("hello 不是有效 JSON") from exc
        if not isinstance(message, dict) or message.get("type") != "hello":
            raise XiaozhiBridgeError("首条消息必须是 hello")
        if message.get("transport") != "websocket":
            raise XiaozhiBridgeError("不支持的传输类型")
        if str(message.get("version")) != "1":
            raise XiaozhiBridgeError("不支持的协议版本")
        audio_params = message.get("audio_params")
        if isinstance(audio_params, dict):
            if audio_params.get("format") not in (None, "opus"):
                raise XiaozhiBridgeError("目前只支持 Opus 音频")
            if audio_params.get("channels", 1) != 1:
                raise XiaozhiBridgeError("目前只支持单声道音频")

    async def _handle_text(self, raw: str) -> None:
        try:
            message = json.loads(raw)
        except json.JSONDecodeError:
            logger.warning(f"[xiaozhi] 忽略非 JSON 文本消息: {raw[:200]}")
            return
        if not isinstance(message, dict):
            return
        message_type = message.get("type")
        if message_type == "hello":
            return
        if message_type == "listen":
            state = str(message.get("state", "")).lower()
            if state == "start":
                await self._start_listening()
            elif state == "stop":
                await self._stop_listening()
        elif message_type == "abort":
            self.aborted = True
            if self.tts_task and not self.tts_task.done():
                self.tts_task.cancel()
        elif message_type == "iot":
            # 当前 MVP 不控制实体设备，明确回传空命令集。
            await self._send_json(
                {"type": "iot", "session_id": self.session_id, "commands": []}
            )

    async def _handle_audio(self, packet: bytes) -> None:
        if not self.listening or not packet:
            return
        pcm = self.codec.decode(packet)
        if pcm is None:
            return
        await asyncio.to_thread(self.recognizer.feed, pcm)

    async def run(self) -> None:
        hello_received = False
        async for raw_message in self.websocket:
            if not hello_received:
                if isinstance(raw_message, bytes):
                    raise XiaozhiBridgeError("首条消息不能是二进制音频")
                try:
                    await self._handle_client_hello(raw_message)
                except XiaozhiBridgeError as exc:
                    await self.websocket.close(code=1008, reason=str(exc)[:120])
                    return
                hello_received = True
                await self._send_hello()
                continue
            if isinstance(raw_message, bytes):
                await self._handle_audio(raw_message)
            else:
                await self._handle_text(raw_message)


def _build_ssl_context(settings: XiaozhiSettings) -> Optional[ssl.SSLContext]:
    if not settings.ssl_cert or not settings.ssl_key:
        return None
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(settings.ssl_cert, settings.ssl_key)
    return context


def _normalize_path(path: Any) -> str:
    value = str(path or "/")
    if not value.startswith("/"):
        value = "/" + value
    return value.rstrip("/") or "/"


def _get_headers(websocket: Any) -> Any:
    """统一获取握手请求头，兼容新旧版本 websockets。"""
    request = getattr(websocket, "request", None)
    if request is not None:
        headers = getattr(request, "headers", None)
        if headers is not None:
            return headers
    return getattr(websocket, "request_headers", {}) or {}


def _authorized(websocket: Any, settings: XiaozhiSettings) -> bool:
    headers = _get_headers(websocket)
    try:
        authorization = headers.get("Authorization", "") or ""
    except Exception:
        authorization = ""
    expected = f"Bearer {settings.access_token}"
    return bool(authorization) and compare_digest(authorization, expected)


def _resolve_request_path(websocket: Any) -> str:
    """兼容新旧版本 websockets，统一获取请求路径。"""
    request = getattr(websocket, "request", None)
    if request is not None:
        path = getattr(request, "path", None)
        if path:
            return str(path)
    return str(getattr(websocket, "path", "/") or "/")


async def websocket_handler(websocket: Any, settings: XiaozhiSettings) -> None:
    """处理单个原生 WebSocket 连接。"""
    path = _resolve_request_path(websocket)
    if _normalize_path(path) != _normalize_path(settings.path):
        await websocket.close(code=1008, reason="invalid path")
        return
    if not _authorized(websocket, settings):
        logger.warning("[xiaozhi] 拒绝未通过鉴权的 WebSocket 连接")
        await websocket.close(code=1008, reason="unauthorized")
        return

    headers = _get_headers(websocket)
    session = XiaozhiSession(
        websocket=websocket,
        settings=settings,
        loop=asyncio.get_running_loop(),
        path=_normalize_path(path),
        device_id=str(headers.get("Device-Id", "") or ""),
        client_id=str(headers.get("Client-Id", "") or ""),
    )
    logger.info(
        f"[xiaozhi] 连接建立: device={session.device_id or '-'} "
        f"client={session.client_id or '-'} session={session.session_id}"
    )
    try:
        await session.run()
    except Exception as exc:
        logger.warning(f"[xiaozhi] 连接结束: {exc}")
    finally:
        session.listening = False
        if session.recognizer is not None:
            try:
                await asyncio.to_thread(session.recognizer.stop)
            except Exception:
                pass
        logger.info(f"[xiaozhi] 连接关闭: session={session.session_id}")


async def serve(settings: XiaozhiSettings) -> None:
    try:
        import websockets
    except ImportError as exc:
        raise XiaozhiBridgeError(
            "缺少 websockets，请先执行 pip install -r requirements_xiaozhi.txt"
        ) from exc

    ssl_context = _build_ssl_context(settings)
    scheme = "wss" if ssl_context else "ws"
    endpoint = f"{scheme}://0.0.0.0:{settings.port}{settings.path}"
    logger.info(f"[xiaozhi] 服务启动: {endpoint}")
    logger.info(
        f"[xiaozhi] ASR={'已配置' if os.getenv('XFYUN_APP_ID') and os.getenv('XFYUN_API_KEY') else '未配置'} "
        f"LLM={'已配置' if InterviewLLM(settings).configured else '未配置'} "
        f"TTS={'已配置' if SpeechSynthesizer(settings).available else '未配置'}"
    )

    async def handler(websocket: Any) -> None:
        await websocket_handler(websocket, settings)

    async with websockets.serve(
        handler,
        settings.host,
        settings.port,
        ssl=ssl_context,
        max_size=settings.max_message_size,
        ping_interval=20,
        ping_timeout=20,
    ):
        await asyncio.Future()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="xiaozhi-unity WebSocket 协议桥接服务")
    parser.add_argument("--host", default=os.getenv("XIAOZHI_WS_HOST", "0.0.0.0"))
    parser.add_argument("--port", type=int, default=int(os.getenv("XIAOZHI_WS_PORT", "8089")))
    parser.add_argument("--path", default=os.getenv("XIAOZHI_WS_PATH", "/xiaozhi/v1/"))
    parser.add_argument("--token", default=os.getenv("XIAOZHI_ACCESS_TOKEN", "test-token"))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    settings = XiaozhiSettings.from_config()
    settings.host = args.host
    settings.port = args.port
    settings.path = args.path
    if args.token:
        settings.access_token = args.token
    try:
        asyncio.run(serve(settings))
    except KeyboardInterrupt:
        logger.info("[xiaozhi] 服务已停止")
    except XiaozhiBridgeError as exc:
        logger.error(f"[xiaozhi] {exc}")
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
