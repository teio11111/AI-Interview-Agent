"""常量定义"""
import os

# 面试会话状态
class SessionStatus:
    PREPARING = 'preparing'
    IN_PROGRESS = 'in_progress'
    COMPLETED = 'completed'

# 匹配度评分等级
class MatchLevel:
    HIGH = '高匹配（80-100）'
    MEDIUM = '中等匹配（60-79）'
    LOW = '低匹配（0-59）'

# 错误码
class ErrorCode:
    NOT_FOUND = 404
    BAD_REQUEST = 400
    INTERNAL_ERROR = 500
    LLM_ERROR = 502

# 【v4.1 演示前】LLM 调用缓存（跨模块共享常量）
# 背景：services/llm_service.py 之前在模块顶层定义，现在集中到此便于其他模块引用
LLM_CACHE_TTL = int(os.getenv('LLM_CACHE_TTL', '300'))  # 5 分钟
LLM_CACHE_MAX = int(os.getenv('LLM_CACHE_MAX', '200'))  # 最多 200 条
