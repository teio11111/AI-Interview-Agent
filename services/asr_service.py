"""讯飞实时语音转写服务 - 支持说话人分离（角色分离）"""
import os
import json
import time
import hmac
import hashlib
import base64
import websocket
import threading
from urllib.parse import urlencode, quote
from datetime import datetime
from utils.logger import logger


class XfyunASRService:
    """讯飞实时语音转写服务
    
    支持：
    - 实时语音转写
    - 说话人分离/角色分离（区分面试官/候选人）
    - 流式返回识别结果
    """
    
    def __init__(self):
        self.app_id = os.getenv('XFYUN_APP_ID')
        self.api_key = os.getenv('XFYUN_API_KEY')
        self.ws_url = "wss://rtasr.xfyun.cn/v1/ws"
        
        if not self.app_id or not self.api_key:
            logger.warning("讯飞语音识别配置缺失，请检查 XFYUN_APP_ID 和 XFYUN_API_KEY")
    
    def _get_signature(self, ts: str) -> str:
        """生成讯飞鉴权签名
        
        算法: signa = HmacSHA1(MD5(appid + ts), apiKey) 再 base64 编码
        官方文档: https://www.xfyun.cn/doc/asr/rtasr/API.html
        """
        # 1. baseString = appid + ts 拼接
        base_string = self.app_id + ts
        # 2. 对baseString做MD5
        md5_hash = hashlib.md5(base_string.encode('utf-8')).hexdigest()
        # 3. 以apiKey为key对MD5结果做HMAC-SHA1
        hmac_sha1 = hmac.new(
            self.api_key.encode('utf-8'),
            md5_hash.encode('utf-8'),
            hashlib.sha1
        ).digest()
        # 4. Base64编码 + URL编码（避免+/=在URL中被截断）
        signa = base64.b64encode(hmac_sha1).decode('utf-8')
        return quote(signa, safe='')
    
    def create_session(self, session_id: str, on_result=None, on_speaker_change=None):
        """创建实时识别会话
        
        Args:
            session_id: 会话ID
            on_result: 识别结果回调 (text, speaker, is_final)
            on_speaker_change: 说话人切换回调 (speaker)
            
        Returns:
            ASRSession 对象
        """
        return ASRSession(
            service=self,
            session_id=session_id,
            on_result=on_result,
            on_speaker_change=on_speaker_change
        )


class ASRSession:
    """讯飞实时语音识别会话"""
    
    def __init__(self, service: XfyunASRService, session_id: str, 
                 on_result=None, on_speaker_change=None):
        self.service = service
        self.session_id = session_id
        self.on_result = on_result
        self.on_speaker_change = on_speaker_change
        
        self.ws = None
        self.is_running = False
        self.connected = False
        self.current_speaker = None
        self.result_buffer = []
        
    def start(self):
        """开始识别"""
        if not self.service.app_id or not self.service.api_key:
            logger.error("讯飞 APPID 或 APIKey 未配置")
            return False
            
        # 构建鉴权URL
        ts = str(int(time.time()))
        signa = self.service._get_signature(ts)
        
        # 讯飞实时转写URL（signa已经URL编码过，直接拼接）
        # 官方文档(标准版): roleType=2 开启角色分离
        ws_url = (f"{self.service.ws_url}?appid={self.service.app_id}"
                  f"&ts={ts}&signa={signa}"
                  f"&roleType=2")
        
        logger.info(f"[ASR] 讯飞 APPID={self.service.app_id}, 开启角色分离")
        
        try:
            self.ws = websocket.WebSocketApp(
                ws_url,
                on_message=self._on_message,
                on_error=self._on_error,
                on_close=self._on_close,
                on_open=self._on_open
            )
            
            self.is_running = True
            ws_thread = threading.Thread(target=self.ws.run_forever, daemon=True)
            ws_thread.start()
            
            # 等待连接建立
            time.sleep(2)
            
            if self.connected:
                logger.info(f"[ASR] 会话 {self.session_id} 已启动，讯飞WebSocket已连接")
            else:
                logger.warning(f"[ASR] 会话 {self.session_id} WebSocket未连接，可能鉴权有误")
            
            return True
            
        except Exception as e:
            logger.error(f"[ASR] 启动失败: {e}", exc_info=True)
            return False
    
    def send_audio(self, audio_data: bytes):
        """发送音频数据
        
        讯飞要求：PCM 16kHz 16bit 单声道，每次发送不超过1280字节
        
        Args:
            audio_data: PCM 16kHz 16bit 单声道音频数据
        """
        if self.ws and self.is_running and self.connected:
            try:
                # 讯飞要求每次发送不超过1280字节，需要分片
                chunk_size = 1280
                for i in range(0, len(audio_data), chunk_size):
                    chunk = audio_data[i:i + chunk_size]
                    self.ws.send(chunk, opcode=websocket.ABNF.OPCODE_BINARY)
                    # 讯飞建议每帧之间间隔40ms，但实际测试中可以连续发送
                logger.debug(f"[ASR] 发送音频: {len(audio_data)} bytes ({(len(audio_data) + chunk_size - 1) // chunk_size} chunks)")
            except Exception as e:
                logger.error(f"[ASR] 发送音频失败: {e}")
        else:
            logger.warning(f"[ASR] 无法发送音频: ws={self.ws is not None}, running={self.is_running}, connected={self.connected}")
    
    def stop(self):
        """停止识别"""
        self.is_running = False
        if self.ws:
            try:
                # 发送结束帧
                self.ws.send('{"end": true}')
                time.sleep(0.5)
                self.ws.close()
            except:
                pass
        logger.info(f"[ASR] 会话 {self.session_id} 已停止")
    
    def _on_open(self, ws):
        logger.info(f"[ASR] 讯飞WebSocket已连接")
        self.connected = True
    
    def _on_message(self, ws, message):
        """处理讯飞识别结果
        
        讯飞返回格式:
        {
            "action": "result",
            "data": "{\"cn\":{\"st\":{\"rt\":[{\"ws\":[{\"cw\":[{\"w\":\"字\"}]}],\"rl\":\"0\"}]}}}"
        }
        """
        try:
            msg = json.loads(message)
            action = msg.get('action', '')
            
            if action == 'started':
                logger.info("[ASR] 讯飞会话已开始")
                return
            
            if action == 'error':
                code = msg.get('code', '')
                desc = msg.get('desc', '')
                logger.error(f"[ASR] 讯飞错误: code={code}, desc={desc}")
                return
            
            if action != 'result':
                return
            
            # 解析data字段（是JSON字符串）
            data_str = msg.get('data', '')
            if not data_str:
                return
            
            data = json.loads(data_str)
            cn = data.get('cn', {})
            st = cn.get('st', {})
            
            # 判断是否为最终结果
            # 官方文档: type "0"=最终结果(一句话结束,增量), "1"=中间结果(实时预览,累积)
            is_final = st.get('type', '1') == '0'
            
            # 提取文本和说话人
            rt_list = st.get('rt', [])
            # 诊断：每10条打印一次原始st结构，看rl到底在哪
            if not hasattr(self, '_dbg_count'):
                self._dbg_count = 0
            self._dbg_count += 1
            if self._dbg_count % 10 == 1:
                logger.info(f"[ASR-RAW] st={json.dumps(st, ensure_ascii=False)[:300]}")
            for rt in rt_list:
                # 拼接文字，同时从cw(词)层级提取rl角色编号
                # 官方文档: rl只在角色切换时变化(1或2)，其余时值为0
                # 注意: rl在cw层级而非rt层级！
                text = ''
                cw_rl = '0'
                ws_list = rt.get('ws', [])
                for ws_item in ws_list:
                    cw_list = ws_item.get('cw', [])
                    for cw in cw_list:
                        text += cw.get('w', '')
                        r = str(cw.get('rl', '0'))
                        if r != '0':
                            cw_rl = r  # 取本句中出现的非0角色编号
                
                # 确定说话人: rl=1/2表示新说话人开始, rl=0表示同一人继续
                if cw_rl != '0':
                    speaker = cw_rl
                else:
                    speaker = self.current_speaker or '1'
                
                if not text.strip():
                    continue
                
                # 诊断日志：查看讯飞实际返回的type和rl值
                logger.info(f"[ASR] type={st.get('type')} rl={cw_rl} spk={speaker} final={is_final} text={text[:20]}")
                
                # 检测说话人切换
                if speaker != self.current_speaker:
                    prev_speaker = self.current_speaker
                    self.current_speaker = speaker
                    if self.on_speaker_change:
                        self.on_speaker_change(speaker)
                    logger.info(f"[ASR] 说话人切换: {prev_speaker} -> {speaker}")
                
                # 回调识别结果（附带音频时间轴bg/ed，供前端停顿检测用）
                if self.on_result:
                    self.on_result(text, speaker, is_final, st.get('bg'), st.get('ed'))
                
                # 最终结果存入buffer
                if is_final:
                    self.result_buffer.append({
                        'text': text,
                        'speaker': speaker,
                        'timestamp': datetime.now().isoformat()
                    })
                
        except Exception as e:
            logger.error(f"[ASR] 处理消息失败: {e}, 原始消息: {message[:200]}", exc_info=True)
    
    def _on_error(self, ws, error):
        logger.error(f"[ASR] 讯飞WebSocket错误: {error}")
    
    def _on_close(self, ws, close_status_code, close_msg):
        logger.info(f"[ASR] 讯飞WebSocket已关闭 (code={close_status_code}, msg={close_msg})")
        self.is_running = False
        self.connected = False
    
    def get_results(self):
        """获取所有识别结果"""
        return self.result_buffer


# 全局单例
_asr_service = None

def get_asr_service():
    """获取语音识别服务单例"""
    global _asr_service
    if _asr_service is None:
        _asr_service = XfyunASRService()
    return _asr_service
