"""语音识别 WebSocket 路由"""
from flask import Blueprint, request, jsonify
import json
import base64
from extensions import socketio
from services.asr_service import get_asr_service
from utils.logger import logger

asr_bp = Blueprint('asr', __name__, url_prefix='/api/asr')

# 存储活跃的识别会话
active_sessions = {}


@asr_bp.route('/start', methods=['POST'])
def start_session():
    """开始语音识别会话"""
    data = request.get_json()
    session_id = data.get('session_id')
    
    if not session_id:
        return jsonify({'code': 400, 'msg': '缺少 session_id'}), 400
    
    asr = get_asr_service()
    
    # 创建识别会话
    def on_result(text, speaker, is_final, bg=None, ed=None):
        """识别结果回调"""
        socketio.emit('asr_result', {
            'session_id': session_id,
            'text': text,
            'speaker': speaker,  # 说话人角色ID
            'is_final': is_final,
            'bg': bg,  # 句子在音频中的开始时间(ms)
            'ed': ed   # 句子在音频中的结束时间(ms)
        }, room=session_id)
    
    def on_speaker_change(speaker):
        """说话人切换回调"""
        socketio.emit('speaker_change', {
            'session_id': session_id,
            'speaker': speaker
        }, room=session_id)
    
    session = asr.create_session(
        session_id=session_id,
        on_result=on_result,
        on_speaker_change=on_speaker_change
    )
    
    if session.start():
        active_sessions[session_id] = session
        return jsonify({'code': 200, 'msg': '识别会话已启动'})
    else:
        return jsonify({'code': 500, 'msg': '启动失败，请检查配置'}), 500


@asr_bp.route('/stop', methods=['POST'])
def stop_session():
    """停止语音识别会话"""
    data = request.get_json()
    session_id = data.get('session_id')
    
    if session_id in active_sessions:
        active_sessions[session_id].stop()
        del active_sessions[session_id]
        return jsonify({'code': 200, 'msg': '识别会话已停止'})
    
    return jsonify({'code': 404, 'msg': '会话不存在'}), 404


@asr_bp.route('/audio', methods=['POST'])
def receive_audio():
    """接收音频数据（HTTP 方式，备用）"""
    data = request.get_json()
    session_id = data.get('session_id')
    audio_base64 = data.get('audio')
    
    if session_id not in active_sessions:
        return jsonify({'code': 404, 'msg': '会话不存在'}), 404
    
    try:
        audio_data = base64.b64decode(audio_base64)
        active_sessions[session_id].send_audio(audio_data)
        return jsonify({'code': 200, 'msg': 'ok'})
    except Exception as e:
        return jsonify({'code': 500, 'msg': str(e)}), 500


@asr_bp.route('/results/<session_id>', methods=['GET'])
def get_results(session_id):
    """获取识别结果"""
    if session_id in active_sessions:
        results = active_sessions[session_id].get_results()
        return jsonify({'code': 200, 'data': results})
    
    return jsonify({'code': 404, 'msg': '会话不存在'}), 404
