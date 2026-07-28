"""Agent 基类 - 所有智能体的公共能力"""
from services.llm_service import LlmService
from utils.logger import logger


class BaseAgent:
    """智能体基类
    
    每个 Agent 必须定义:
    - AGENT_NAME: 智能体名称
    - SYSTEM_PROMPT: 角色定义（你是谁、你的专长、你的工作风格）
    """
    AGENT_NAME = "BaseAgent"
    SYSTEM_PROMPT = ""

    def __init__(self):
        """初始化 Agent"""
        if not self.SYSTEM_PROMPT:
            raise ValueError(f"{self.AGENT_NAME} 未定义 SYSTEM_PROMPT")

    def think(self, prompt, temperature=0.2):
        """执行思考（调用 LLM）

        Args:
            prompt: 任务指令（已填充数据的完整 prompt）
            temperature: 创造性参数（0-1）。评估/分析任务统一 0.2 保证稳定性。

        Returns:
            str: LLM 原始响应文本
        """
        logger.info(f'[{self.AGENT_NAME}] 开始思考，prompt长度={len(prompt)}')
        response = LlmService.chat(self.SYSTEM_PROMPT, prompt)
        if response:
            logger.info(f'[{self.AGENT_NAME}] 思考完成，返回 {len(response)} 字符')
        else:
            logger.error(f'[{self.AGENT_NAME}] 思考失败')
        return response

    def think_json(self, prompt, temperature=0.2):
        """执行思考并返回结构化 JSON

        Args:
            prompt: 任务指令
            temperature: 创造性参数

        Returns:
            dict: 解析后的 JSON，失败返回 None
        """
        response = self.think(prompt, temperature)
        result = LlmService.parse_json(response)
        if result:
            logger.info(f'[{self.AGENT_NAME}] JSON 解析成功')
        else:
            logger.error(f'[{self.AGENT_NAME}] JSON 解析失败')
        return result

    def summarize(self, data):
        """将数据转为文本摘要（供其他 Agent 使用）

        Args:
            data: 要摘要的数据

        Returns:
            str: 文本摘要
        """
        if isinstance(data, dict):
            import json
            return json.dumps(data, ensure_ascii=False, indent=2)
        return str(data) if data else '暂无'
