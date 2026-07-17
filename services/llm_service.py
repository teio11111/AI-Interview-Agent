import requests
import json
import re
from flask import current_app
from utils.logger import logger


class LlmService:
    """LLM API 调用服务（核心工具类）"""

    @staticmethod
    def chat(system_prompt, user_prompt):
        """调用 LLM API

        Args:
            system_prompt: 系统角色定义
            user_prompt: 用户指令（含上下文数据）

        Returns:
            str: LLM 返回的文本内容，失败返回 None
        """
        api_url = current_app.config['LLM_API_URL']
        api_key = current_app.config['LLM_API_KEY']
        model = current_app.config['LLM_MODEL']
        timeout = current_app.config['LLM_TIMEOUT']

        headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {api_key}'
        }

        payload = {
            'model': model,
            'messages': [
                {'role': 'system', 'content': system_prompt},
                {'role': 'user', 'content': user_prompt}
            ],
            'temperature': 0.7
        }

        logger.info(f'调用 LLM API: model={model}, prompt长度={len(user_prompt)}')

        try:
            response = requests.post(api_url, headers=headers, json=payload, timeout=timeout)
            response.raise_for_status()

            result = response.json()
            content = result['choices'][0]['message']['content']
            logger.info(f'LLM 响应成功，返回 {len(content)} 字符')
            return content

        except requests.exceptions.Timeout:
            logger.error('LLM API 调用超时')
            return None
        except Exception as e:
            logger.error(f'LLM API 调用失败: {e}')
            return None

    @staticmethod
    def parse_json(llm_response):
        """从 LLM 返回内容中提取 JSON

        Args:
            llm_response: LLM 返回的文本（可能包含非 JSON 内容）

        Returns:
            dict: 解析后的字典，失败返回 None
        """
        if not llm_response:
            return None

        # 尝试直接解析
        try:
            return json.loads(llm_response)
        except json.JSONDecodeError:
            pass

        # 尝试提取 JSON 块
        match = re.search(r'```(?:json)?\s*([\s\S]*?)```', llm_response)
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                pass

        # 尝试提取花括号内容
        match = re.search(r'\{[\s\S]*\}', llm_response)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                pass

        logger.error(f'无法从 LLM 响应中解析 JSON: {llm_response[:200]}...')
        return None
