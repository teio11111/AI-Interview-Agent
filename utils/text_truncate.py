"""文本截断工具：防止超长简历/JD 把 prompt 撑爆，导致 LLM 输出质量下降"""
import re


def truncate_for_prompt(text, max_chars=6000, marker='\n...[内容已截断]...\n'):
    """截断长文本供 LLM prompt 使用

    策略：
    - 超过 max_chars 时，从头部和尾部各保留 max_chars // 2
    - 中间用 marker 替换（保留头尾比丢掉头更合理：简历头有姓名/求职意向，尾有项目经历）

    Args:
        text: 原始文本
        max_chars: 最大字符数（默认 6000）
        marker: 截断标记

    Returns:
        str: 截断后的文本
    """
    if text is None or not isinstance(text, str):
        return ''
    text = text.strip()
    if len(text) <= max_chars:
        return text

    half = max_chars // 2
    head = text[:half]
    tail = text[-half:]
    return f"{head}{marker}{tail}"


def truncate_json_for_prompt(data, max_chars=2500, marker='\n...[内容已截断]...\n'):
    """把 dict / list 序列化为 JSON 后再截断，比 truncate_for_prompt 更安全（保证中间不是半个 JSON 块）

    Args:
        data: dict / list / 其他可序列化对象
        max_chars: 最大字符数（默认 2500）
        marker: 截断标记

    Returns:
        str: 截断后的 JSON 字符串
    """
    if data is None:
        return ''
    try:
        import json
        if isinstance(data, str):
            text = data
        else:
            text = json.dumps(data, ensure_ascii=False, indent=2)
    except (TypeError, ValueError):
        text = str(data)

    return truncate_for_prompt(text, max_chars=max_chars, marker=marker)


def clean_resume_text(text):
    """清理简历文本：移除多余空白行，统一换行符

    避免 PDF 解析脏数据（连续空行、混合 \\r\\n 等）撑爆 prompt
    """
    if not text or not isinstance(text, str):
        return text or ''
    # 统一换行符
    text = text.replace('\r\n', '\n').replace('\r', '\n')
    # 把连续 3+ 空行压成 2 个换行（保留段落分隔）
    text = re.sub(r'\n{3,}', '\n\n', text)
    # 行内多余空格压缩
    text = re.sub(r'[ \t]+', ' ', text)
    return text.strip()
