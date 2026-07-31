import os
import logging
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))


class Config:
    """应用配置"""

    # Flask 基础配置
    # 【v4.1 演示前】SECRET_KEY 生产环境必须从 .env 覆盖，默认值仅开发模式
    SECRET_KEY = os.getenv('SECRET_KEY', 'dev-secret-key-change-in-production')
    _IS_DEFAULT_SECRET = (SECRET_KEY == 'dev-secret-key-change-in-production')
    DEBUG = os.getenv('FLASK_DEBUG', '0') == '1'

    # MySQL 数据库配置
    SQLALCHEMY_DATABASE_URI = (
        f"mysql+pymysql://{os.getenv('DB_USER', 'root')}:{os.getenv('DB_PASSWORD', 'Root123456')}"
        f"@{os.getenv('DB_HOST', 'localhost')}:{os.getenv('DB_PORT', '3306')}"
        f"/{os.getenv('DB_NAME', 'ai_interview')}"
        f"?charset=utf8mb4"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # LLM API 配置
    LLM_API_URL = os.getenv('LLM_API_URL', 'https://api.openai.com/v1/chat/completions')
    LLM_API_KEY = os.getenv('LLM_API_KEY', 'your-api-key-here')
    LLM_MODEL = os.getenv('LLM_MODEL', 'gpt-3.5-turbo')
    LLM_TIMEOUT = int(os.getenv('LLM_TIMEOUT', '90'))

    # 文件上传配置
    MAX_CONTENT_LENGTH = 10 * 1024 * 1024  # 10MB

    @classmethod
    def warn_if_insecure(cls, logger=None):
        """【v4.1 演示前】启动时安全检查，输出 warning 日志（不报错）

        Args:
            logger: 外部传入的 logger 实例，默认走项目 ai_interview logger
        """
        # 延迟导入避免 config 模块加载顺序问题
        if logger is None:
            from utils.logger import logger as _logger
            logger = _logger
        if cls._IS_DEFAULT_SECRET:
            logger.warning(
                '[配置] SECRET_KEY 使用默认值（仅开发模式）。'
                '生产环境请在 .env 中设置 SECRET_KEY=随机长字符串'
            )
        if cls.DEBUG:
            logger.warning('[配置] FLASK_DEBUG=1，开启调试模式（生产环境请设为 0）')
