import PyPDF2
import io
import re
from utils.logger import logger


def _clean_pdf_extracted_text(text):
    """清洗 PyPDF2 提取的 PDF 文本

    PyPDF2 在处理部分特殊 PDF（特别是非标准嵌入字体 / 扫描件+文字层 / 翻译文档）
    时会出现三类常见问题：
    1. 字符级切碎：每个字符独占一行（avg 非空行长 < 5）
    2. 单词级切碎：每个英文单词独占一行 + 大量空行（avg 非空行长 5-15 且空行占比 > 30%）
    3. 末尾 hash 漏出：PDF 字体子集化时的字体 ID 字符串被当成文本读取

    本函数通过行密度启发式自动识别并修复：
    - 字符级切碎 → 合并连续非空行为段落（无空格连接，保留数字紧凑）
    - 单词级切碎 → 合并连续非空行为段落（空格连接，恢复 "Bank of America"）
    - 末尾出现 2 次以上的同一 hash 字符串 → 全部删除
    - 中文字符之间的孤立空格 → 循环去干净

    Args:
        text: PyPDF2 提取的原始文本

    Returns:
        str: 清洗后的文本
    """
    if not text:
        return text

    lines = text.split(chr(10))
    non_empty = [l for l in lines if l.strip()]
    if not non_empty:
        return text

    non_empty_count = len(non_empty)
    empty_count = len(lines) - non_empty_count
    empty_ratio = empty_count / len(lines) if lines else 0
    avg_non_empty_len = len(text.strip()) / non_empty_count

    # 模式判断
    is_char_shred = avg_non_empty_len < 5
    is_word_shred = (5 <= avg_non_empty_len < 15) and empty_ratio > 0.3

    cleaned = text
    if is_char_shred or is_word_shred:
        # 选 join 策略：字符级无空格（防数字被切），单词级用空格（恢复词边界）
        joiner = '' if is_char_shred else ' '
        # 策略：PyPDF2 字符级切碎时，用空格行（只含空格）分隔同一行的不同列
        # 真空行（空字符串）才是 PDF 原本的段落分隔
        # 所以：空格行 = 列分隔 → flush + 换行；真空行 = 段落分隔 → flush + 空行
        groups = []
        cur_lines = []
        for l in lines:
            if l == '':
                # 真空行 = 段落分隔
                if cur_lines:
                    groups.append(joiner.join(cur_lines))
                    groups.append(chr(10) * 2)
                    cur_lines = []
                groups.append('')
            elif l.strip() == '':
                # 空格行：单空格 = 词间空格（join），多空格 = 列分隔（flush）
                if len(l) <= 1:
                    # 单空格 → 词间空格，不 flush
                    if cur_lines:
                        cur_lines.append(' ')
                else:
                    # 多空格 → 列分隔
                    if cur_lines:
                        groups.append(joiner.join(cur_lines))
                        groups.append(chr(10))
                        cur_lines = []
            else:
                # 非空行：累积
                cur_lines.append(l.strip())
        if cur_lines:
            groups.append(joiner.join(cur_lines))
        cleaned = ''.join(groups)
        # 合并多余空行
        cleaned = re.sub(chr(10) + '{3,}', chr(10) * 2, cleaned)
        # Collapse 连续空格为单个空格（保留列分隔的可读性）
        cleaned = re.sub(r' {2,}', ' ', cleaned)
        # 后处理：去掉中文字符之间的孤立空格（“拥 有 5 年” → “拥有5年”）
        # 循环多次直到稳定（中间可能有数字/符号隔断，需迭代）
        for _ in range(10):
            new = re.sub(r'([\u4e00-\u9fff])\s+([\u4e00-\u9fff])', r'\1\2', cleaned)
            if new == cleaned:
                break
            cleaned = new
        # 全大写标题（如 SUMMARY）后跟非大写内容时加换行
        cleaned = re.sub(r'([A-Z]{3,})\s+([a-z\u4e00-\u9fff])', r'\1' + chr(10) + r'\2', cleaned)
        # bullet 点 ● 前加换行（让每个 bullet 独立成行）
        cleaned = re.sub(r'(?<!\n)●', chr(10) + '●', cleaned)
        # ● 后的换行变空格（让 bullet 和内容在同一行）
        cleaned = re.sub(r'●\s*' + chr(10), '● ', cleaned)
        # 非 bullet 行的句号后加换行（bullet 行的句号不加，避免拆分 bullet 内容）
        _lines = cleaned.split(chr(10))
        _result = []
        for _l in _lines:
            if _l.strip().startswith('●'):
                _result.append(_l)
            else:
                _result.append(re.sub(r'。(?![\s]*●)', '。' + chr(10), _l))
        cleaned = chr(10).join(_result)
        # 合并多余空行 + 去行首多余空格
        cleaned = re.sub(chr(10) + '{3,}', chr(10) * 2, cleaned)
        cleaned = re.sub(chr(10) + ' +', chr(10), cleaned)

    # 去末尾 hash 重复（任意 30+ 字符的同一串出现 ≥2 次 → 删干净）
    # 这种串特征：字母数字混合 + 偶含 - 或 _，长度通常 32+
    for _ in range(3):
        m = re.search(r'([A-Za-z0-9\-_]{32,})', cleaned)
        if not m:
            break
        token = m.group(1)
        # 统计出现次数
        if cleaned.count(token) >= 2:
            cleaned = cleaned.replace(token, '')
        else:
            break
    cleaned = re.sub(chr(10) + '{3,}', chr(10) * 2, cleaned)
    cleaned = cleaned.strip()

    if cleaned != text:
        mode = '字符级' if is_char_shred else ('单词级' if is_word_shred else 'N/A')
        logger.info(f'PDF 文本后处理清洗 [{mode}切碎]：{len(text)} → {len(cleaned)} 字符（avg 行长 {avg_non_empty_len:.1f}, 空行率 {empty_ratio:.0%}）')

    return cleaned


def extract_text_from_pdf(file_stream):
    """从 PDF 文件流中提取文本

    包含 PyPDF2 后处理清洗（处理字符级切碎 + 末尾 hash 漏出）。

    Args:
        file_stream: 上传文件的字节流

    Returns:
        str: 提取并清洗后的文本内容，失败时返回 None
    """
    try:
        reader = PyPDF2.PdfReader(file_stream)
        text = ''
        for page in reader.pages:
            page_text = page.extract_text()
            if page_text:
                text += page_text + '\n'

        if text.strip():
            text = _clean_pdf_extracted_text(text.strip())
            logger.info(f'PDF 解析成功，共 {len(reader.pages)} 页，提取 {len(text)} 字符')
            return text
        else:
            logger.warning('PDF 解析完成但未提取到文本（可能是扫描件）')
            return None

    except Exception as e:
        logger.error(f'PDF 解析失败: {e}')
        return None
