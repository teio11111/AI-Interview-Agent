import logging
import sys

# 配置日志格式
formatter = logging.Formatter(
    '[%(asctime)s] %(levelname)s [%(name)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

# 控制台输出
handler = logging.StreamHandler(sys.stdout)
handler.setFormatter(formatter)

# 获取根 logger
logger = logging.getLogger('ai_interview')
logger.setLevel(logging.DEBUG)
logger.addHandler(handler)
