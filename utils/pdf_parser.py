import PyPDF2
import io
from utils.logger import logger


def extract_text_from_pdf(file_stream):
    """从 PDF 文件流中提取文本

    Args:
        file_stream: 上传文件的字节流

    Returns:
        str: 提取的文本内容，失败时返回 None
    """
    try:
        reader = PyPDF2.PdfReader(file_stream)
        text = ''
        for page in reader.pages:
            page_text = page.extract_text()
            if page_text:
                text += page_text + '\n'

        if text.strip():
            logger.info(f'PDF 解析成功，共 {len(reader.pages)} 页，提取 {len(text)} 字符')
            return text.strip()
        else:
            logger.warning('PDF 解析完成但未提取到文本（可能是扫描件）')
            return None

    except Exception as e:
        logger.error(f'PDF 解析失败: {e}')
        return None
