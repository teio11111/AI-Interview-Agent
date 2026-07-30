"""通用工具。"""
from datetime import datetime, timedelta, timezone


BEIJING_TIMEZONE = timezone(timedelta(hours=8), 'Asia/Shanghai')


def beijing_now():
    """返回无时区标记的北京时间，兼容 MySQL DATETIME 字段。"""
    return datetime.now(BEIJING_TIMEZONE).replace(tzinfo=None)
