import requests
import json
import re
import time
import random
import hashlib
from flask import current_app
from utils.logger import logger
from constants import LLM_CACHE_TTL, LLM_CACHE_MAX


# 【v4.1】LLM 调用结果缓存（5 分钟 TTL）
# 背景：演示时重复点击同候选人，重跑 LLM 浪费 1-3 分钟
# 修复：相同 prompt 5 分钟内复用上次结果，<0.1s 返回
# 【v4.1 演示前】TTL/MAX 抽到 constants.py 便于跨模块共享
_LLM_CACHE = {}  # {hash: (content, timestamp)}


def _get_llm_cache_key(system_prompt, user_prompt):
    h = hashlib.md5((system_prompt + '|' + user_prompt).encode('utf-8')).hexdigest()
    return h


def _get_cached_llm(key):
    if key in _LLM_CACHE:
        content, ts = _LLM_CACHE[key]
        if time.time() - ts < LLM_CACHE_TTL:
            logger.info(f'[LLM-CACHE] hit (age={time.time()-ts:.1f}s)')
            return content
        else:
            del _LLM_CACHE[key]
    return None


def _set_cached_llm(key, content):
    if len(_LLM_CACHE) >= LLM_CACHE_MAX:
        # 简单 LRU：删最老的 50 条
        oldest = sorted(_LLM_CACHE.items(), key=lambda x: x[1][1])[:50]
        for k, _ in oldest:
            del _LLM_CACHE[k]
    _LLM_CACHE[key] = (content, time.time())


class LlmService:
    """LLM API 调用服务（核心工具类）

    【v3.0 关键修复】加入 retry 机制
      背景：之前 LLM 调用 1 次失败就丢弃，导致 3 个 evaluator 并行时 3 个一起超时 → 简历评估全空。
      修复：失败重试 3 次（指数退避 1s/2s/4s），覆盖限流、临时不可用、超时。
    """

    @staticmethod
    def chat(system_prompt, user_prompt, max_retries=3):
        """调用 LLM API（带 retry 机制）

        Args:
            system_prompt: 系统角色定义
            user_prompt: 用户指令（含上下文数据）
            max_retries: 最大重试次数（默认 3 次）

        Returns:
            str: LLM 返回的文本内容，失败返回 None
        """
        # 【v4.1】缓存检查：同 prompt 5 分钟内直接返回
        _cache_key = _get_llm_cache_key(system_prompt, user_prompt)
        _cached = _get_cached_llm(_cache_key)
        if _cached is not None:
            return _cached

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
            'temperature': 0.2,
            'max_tokens': 8192,  # 【v3.1 修复】hidden 输出 13665 字符被 4096 截断，导致 JSON 未闭合解析失败
        }

        last_error = None
        for attempt in range(1, max_retries + 1):
            t0 = time.time()
            try:
                logger.info(f'[LLM] 调用 attempt {attempt}/{max_retries}, prompt长度={len(user_prompt)}')
                response = requests.post(api_url, headers=headers, json=payload, timeout=timeout)
                response.raise_for_status()
                result = response.json()
                content = (result.get('choices') or [{}])[0].get('message', {}).get('content') or ''
                if content and content.strip():
                    elapsed = round(time.time() - t0, 1)
                    logger.info(f'[LLM] 成功 attempt {attempt}, 返回 {len(content)} 字符, 耗时 {elapsed}s')
                    # 【v4.1】写缓存
                    _set_cached_llm(_cache_key, content)
                    return content
                last_error = '空内容'
                logger.warning(f'[LLM] attempt {attempt} 返回空内容')
            except requests.exceptions.Timeout as e:
                last_error = f'Timeout: {e}'
                logger.warning(f'[LLM] attempt {attempt} 超时: {e}')
            except Exception as e:
                last_error = f'{type(e).__name__}: {e}'
                logger.warning(f'[LLM] attempt {attempt} 失败: {e}')

            # 【v3.1 智能退避】指数 3s/10s/30s
            # 背景：LLM 服务端在并发/慢响应情况下连续失败，无脑 1s/2s/4s 会继续打爆 LLM
            # 修复：首次失败（多为限流）短等 3s；连续失败（多为服务慢）长等 10s/30s 让 LLM 喘息
            if attempt < max_retries:
                # 根据当前错误类型调整退避
                if isinstance(last_error, str) and last_error.startswith('Timeout'):
                    backoff = 3 if attempt == 1 else (10 if attempt == 2 else 30)
                else:
                    backoff = 2 ** attempt
                backoff += random.uniform(0, 1)  # 防 thundering herd
                logger.info(f'[LLM] {backoff:.1f}s 后重试...')
                time.sleep(backoff)

        logger.error(f'[LLM] 全部 {max_retries} 次尝试均失败: {last_error}')
        return None

    @staticmethod
    def parse_json(llm_response):
        """从 LLM 返回内容中提取 JSON

        兼容 MiniMax-M3 / DeepSeek-R1 等推理模型：
        这类模型会把思考过程以 <think>...</think> 或 <think>...</think> 块放在 content 字段，
        会污染 JSON 解析。本函数会在解析前先剥离这些思考块。

        Args:
            llm_response: LLM 返回的文本（可能包含非 JSON 内容）

        Returns:
            dict: 解析后的字典，失败返回 None
        """
        if not llm_response:
            return None

        # 【MiniMax-M3 / DeepSeek-R1 兼容】剥离思考块
        # 移除 <think>...</think> / <think>...</think> 等模型思考痕迹
        cleaned = re.sub(r'<think>[\s\S]*?</think>', '', llm_response, flags=re.IGNORECASE)
        cleaned = re.sub(r'<think>[\s\S]*?</think>', '', cleaned, flags=re.IGNORECASE)
        cleaned = cleaned.strip()

        # 尝试直接解析（剥离思考块后的版本）
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            pass

        # 尝试提取 JSON 块（markdown 代码块），优先匹配 ```json\n{...}\n```
        # 【v3.1 改进】如果 markdown 内部 JSON 被截断，保留 inner 内容供后续修复逻辑使用
        # （之前会 cleaned.replace(match.group(0), '', 1) 丢掉内容，导致被截断 JSON 无法修复）
        for _ in range(3):
            match = re.search(r'```(?:json)?\s*([\s\S]*?)```', cleaned)
            if match:
                inner = match.group(1).strip()
                # 代码块内可能仍有 think 块，再剥一次
                inner = re.sub(r'<think>[\s\S]*?</think>', '', inner, flags=re.IGNORECASE)
                inner = re.sub(r'<think>[\s\S]*?</think>', '', inner, flags=re.IGNORECASE)
                try:
                    return json.loads(inner.strip())
                except json.JSONDecodeError:
                    # 【v3.1】不删 markdown 包裹，而是用 inner 作为新的 cleaned 走修复逻辑
                    cleaned = inner.strip()
                    break
            break

        # 尝试提取花括号内容（用 stack 找匹配的 {...}，避免贪婪匹配）
        # 从 cleaned 里逐字符扫，统计 { 和 } 深度，找到第一个完整配对的 JSON
        def _extract_balanced_json(text):
            """从 text 中找到第一个完整配对的 {...} JSON 块（按括号深度匹配）"""
            start = text.find('{')
            if start == -1:
                return None
            depth = 0
            in_str = False
            escape = False
            for i in range(start, len(text)):
                c = text[i]
                if escape:
                    escape = False
                    continue
                if c == '\\' and in_str:
                    escape = True
                    continue
                if c == '"':
                    in_str = not in_str
                    continue
                if in_str:
                    continue
                if c == '{':
                    depth += 1
                elif c == '}':
                    depth -= 1
                    if depth == 0:
                        return text[start:i+1]
            return None

        json_block = _extract_balanced_json(cleaned)
        if json_block:
            try:
                return json.loads(json_block)
            except json.JSONDecodeError as e:
                logger.error(f'花括号块 JSON 解析失败 (col={e.colno}, char={e.pos}): '
                             f'{json_block[max(0,e.pos-50):e.pos+50]!r}')

        # 【v3.1 截断修复】补全未闭合的 JSON
        # 背景：max_tokens 限制可能让 LLM 输出被截断，括号没闭合。
        # 策略：删除最后一个未闭合括号之后的内容，补全缺失的 ] 和 } 后再尝试解析。
        def _try_fix_unescaped_quotes(text):
            """【v4.2】修复字符串内的未转义双引号

            场景：LLM 在 JSON 字符串值中输出未转义的双引号（常见为中文文本中
            的引号包裹词，如"主导""推动"），导致原括号匹配器误判为字符串结束。

            策略：状态机扫描。当在字符串内遇到"时，跳过后续空白，
            如果下一个字符是 , } ] : 等 JSON 分隔符，则认为是字符串结束，
            否则当作字面引号，转义为 \\"。

            Returns:
                str: 修复后的文本（可能未变动），解析失败返回 None。
            """
            result = []
            i = 0
            n = len(text)
            in_string = False
            modified = False

            while i < n:
                c = text[i]
                if not in_string:
                    if c == '"':
                        in_string = True
                        result.append(c)
                        i += 1
                    else:
                        result.append(c)
                        i += 1
                    continue

                # --- 在字符串内部 ---
                if c == '\\':
                    # 已是转义序列，直接复制
                    result.append(c)
                    if i + 1 < n:
                        result.append(text[i + 1])
                        i += 2
                    else:
                        i += 1
                elif c == '"':
                    # 判断这个"是不是真正的字符串结束符
                    j = i + 1
                    while j < n and text[j] in ' \t\n\r':
                        j += 1
                    if j < n and text[j] in ',}]:':
                        # 真正的字符串结束符
                        in_string = False
                        result.append(c)
                        i += 1
                    else:
                        # 未转义双引号，转义之
                        result.append('\\"')
                        modified = True
                        i += 1
                else:
                    result.append(c)
                    i += 1

            return ''.join(result) if modified else None

        def _try_repair_truncated_json(text):
            """补全被截断的 JSON：定位截断点，删除末尾不全部分，补全闭合括号。"""
            # 【v3.1】去掉 markdown 包裹（保留 inner），避免把 ``` 当成 JSON 内容
            text = re.sub(r'^\s*```(?:json)?\s*', '', text)
            text = re.sub(r'\s*```\s*$', '', text)

            # 第一遍扫描：找未闭合括号和未闭合字符串的起始位置
            stack = []  # [(char, pos), ...] 未闭合的 { [
            str_start = -1  # 当前未闭合字符串的起始位置
            in_str = False
            escape = False
            for i, c in enumerate(text):
                if escape:
                    escape = False
                    continue
                if c == '\\' and in_str:
                    escape = True
                    continue
                if c == '"':
                    if in_str:
                        str_start = -1  # 字符串已闭合
                    else:
                        str_start = i  # 记录当前字符串起点（未闭合则保留）
                    in_str = not in_str
                    continue
                if in_str:
                    continue
                if c in '{[':
                    stack.append((c, i))
                elif c == '}':
                    if stack and stack[-1][0] == '{':
                        stack.pop()
                elif c == ']':
                    if stack and stack[-1][0] == '[':
                        stack.pop()

            if not stack and str_start == -1:
                return None  # 完整 JSON，没有截断

            # 【v4.2 修复】截断点逻辑：
            # 1) 如果存在未闭合字符串：在该字符串起点处截断（保留前面的全部内容）
            # 2) 否则（括号未闭合）：保留全部内容
            if str_start != -1:
                truncated = text[:str_start]
            else:
                truncated = text

            # 去掉尾部残留的孤立的 key（例：..."hidden_summary": 或 ..."hidden_summary"）
            # 同时处理 key 后可能有 : 或 : <残缺值> 的情况
            truncated = re.sub(r',?\s*"[^"]*"\s*(?::\s*(?:"[^"]*"?)?)?\s*$', '', truncated)
            # 去掉尾部残留的 , : 或空白（避免产生 invalid JSON）
            truncated = re.sub(r'[\s,:]*$', '', truncated)

            # 重新统计 truncated 里的括号深度（决定要补多少闭合）
            depth_curly = 0
            depth_square = 0
            in_str2 = False
            escape2 = False
            for c in truncated:
                if escape2:
                    escape2 = False
                    continue
                if c == '\\' and in_str2:
                    escape2 = True
                    continue
                if c == '"':
                    in_str2 = not in_str2
                    continue
                if in_str2:
                    continue
                if c == '{':
                    depth_curly += 1
                elif c == '}':
                    depth_curly -= 1
                elif c == '[':
                    depth_square += 1
                elif c == ']':
                    depth_square -= 1

            # 补全闭合括号
            repaired = truncated + (']' * depth_square) + ('}' * depth_curly)
            try:
                return json.loads(repaired)
            except json.JSONDecodeError:
                return None

        repaired = _try_repair_truncated_json(cleaned)
        if repaired is not None:
            logger.warning(f'[JSON 修复] 成功补全被截断的 JSON（cleaned_len={len(cleaned)}）')
            return repaired

        # 【v4.2 增强容错】修复字符串内的未转义双引号
        # 背景：LLM 偶尔会在字符串值里写中文双引号包围的词（如"主导""推动"），
        # 原括号匹配器会把这些"当作字符串结束符，导致 depth 错乱解析失败。
        # 策略：状态机扫描字符串值，如果遇到非分隔符后续的"则转义为\\"
        fixed = _try_fix_unescaped_quotes(cleaned)
        if fixed and fixed != cleaned:
            try:
                result_obj = json.loads(fixed)
                logger.warning(f'[JSON 修复] 修复未转义引号后解析成功（cleaned_len={len(cleaned)}）')
                return result_obj
            except json.JSONDecodeError:
                pass

        logger.error(f'无法从 LLM 响应中解析 JSON（剥离思考块后仍失败）: cleaned_len={len(cleaned)} cleaned_full={cleaned!r}')
        return None
