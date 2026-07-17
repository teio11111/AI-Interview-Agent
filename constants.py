"""常量定义"""

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
