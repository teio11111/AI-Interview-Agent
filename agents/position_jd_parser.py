"""岗位 JD 解析 Agent - 从 JD 文本提取结构化字段

用途：管理员上传 PDF/粘贴 JD 后，自动识别出：
- name: 岗位名称
- jd_content: 整理后的 JD 全文（清理乱码/重复）
- tech_requirements: 技术要求（逗号分隔字符串）
"""
from agents.base_agent import BaseAgent
import json


class PositionJdParserAgent(BaseAgent):
    """岗位 JD 解析师

    职责：从 JD 文本中提取结构化字段，让管理员可以一键创建岗位。
    """

    AGENT_NAME = "岗位 JD 解析师"

    SYSTEM_PROMPT = """你是「岗位 JD 解析师」，专门从原始 JD 文本中提取结构化字段。

你的核心能力：
- 从混乱的 JD 文本（可能含 PDF 提取的乱码、重复段落）中识别关键信息
- 提取岗位名称、技术要求、完整 JD 描述
- 清理与规范化文本（去除重复行、合并相似要求）

工作原则：
- **岗位名称**：取最权威的职位名（如"Python 后端开发工程师"），不要带公司名前缀
- **技术要求**：必须是从 JD 中明确提到的，不要凭空添加；按"语言/框架/数据库/中间件/工具"分类提取，使用规范的英文名（如 Python、FastAPI、MySQL、Redis、Kafka、Docker、Kubernetes）
- **JD 内容**：保留原文核心信息，删除乱码/页眉页脚/重复段落；如果原 JD 已有"岗位职责"与"任职要求"分段，保留该结构

请始终以严格的 JSON 格式输出，不要输出任何解释性文字。"""

    def parse(self, raw_text):
        """从 JD 文本提取结构化字段

        Args:
            raw_text: JD 全文（可能来自 PDF 提取，含乱码）

        Returns:
            dict: {name, jd_content, tech_requirements}，失败返回 None
        """
        if not raw_text or not raw_text.strip():
            return None

        prompt = f"""## 任务
从以下 JD 文本中提取结构化字段。

## JD 原始文本
{raw_text[:5000]}

## 输出格式（严格 JSON）

{{
    "name": "岗位名称（如：Python后端开发工程师）",
    "jd_content": "整理后的 JD 全文（保留岗位职责、任职要求等结构，删除乱码与重复）",
    "tech_requirements": "技术要求，逗号分隔（如：Python, FastAPI, MySQL, Redis, Docker, Kubernetes）"
}}

注意：
- name：取最权威的职位名，不要带公司名/地点前缀
- tech_requirements：仅包含 JD 中**明确提到**的技术栈，使用规范英文名，按逗号分隔
- jd_content：保留原 JD 的"岗位职责"/"任职要求"等结构，删除 PDF 提取产生的乱码字符、页眉页脚、重复段落
- 如果原文没有清晰的"岗位职责"/"任职要求"分段，请基于内容合理组织"""
        result = self.think_json(prompt)
        if not isinstance(result, dict):
            return None
        # 兜底：LLM 偶尔会漏字段
        result.setdefault('name', '')
        result.setdefault('jd_content', raw_text.strip())
        result.setdefault('tech_requirements', '')
        # 清理 tech_requirements：去重 + 规范
        if result['tech_requirements']:
            techs = [t.strip() for t in result['tech_requirements'].replace('，', ',').split(',') if t.strip()]
            seen = set()
            unique = []
            for t in techs:
                key = t.lower()
                if key not in seen:
                    seen.add(key)
                    unique.append(t)
            result['tech_requirements'] = ', '.join(unique)
        return result