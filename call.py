"""
统一的 LLM 客户端 - 封装所有 LLM API 调用逻辑

本文件提供：
1. LLMConfig - LLM 配置数据类
2. LLMResponse - 统一响应格式
3. LLMClient - 统一的 LLM 客户端，支持流式/非流式请求
"""

import json
import aiohttp
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Callable


@dataclass
class LLMConfig:
    """LLM 配置"""
    api_url: str
    model: str
    api_key: Optional[str] = None
    timeout: int = 60


@dataclass
class LLMResponse:
    """统一响应格式"""
    content: Optional[str] = None
    tool_calls: Optional[List[Dict]] = None
    finish_reason: str = "stop"
    raw: Optional[Dict] = field(default=None, repr=False)
    
    @property
    def is_error(self) -> bool:
        """是否为错误响应"""
        return self.finish_reason == "error"
    
    @property
    def has_tool_calls(self) -> bool:
        """是否包含工具调用"""
        return bool(self.tool_calls)


class LLMClient:
    """
    统一的 LLM 客户端
    
    支持：
    - 流式/非流式请求
    - Function Calling
    - 自定义参数
    - 统一错误处理
    
    使用示例：
        client = LLMClient(LLMConfig(api_url, model, api_key))
        
        # 非流式请求
        response = await client.chat(messages)
        
        # 流式请求（带回调）
        response = await client.chat(
            messages, 
            stream=True,
            on_content=lambda c: print(c, end='')
        )
        
        # 带工具调用
        response = await client.chat(
            messages,
            tools=TOOLS_SCHEMA,
            tool_choice="auto"
        )
    """
    
    def __init__(self, config: LLMConfig):
        self.config = config
    
    def _build_headers(self) -> Dict[str, str]:
        """构建请求头"""
        headers = {"Content-Type": "application/json"}
        if self.config.api_key:
            headers["Authorization"] = f"Bearer {self.config.api_key}"
        return headers
    
    async def chat(
        self,
        messages: List[Dict],
        *,
        model: Optional[str] = None,
        tools: Optional[List[Dict]] = None,
        tool_choice: str = "auto",
        temperature: float = 0.7,
        max_tokens: int = 4000,
        stream: bool = False,
        timeout: Optional[int] = None,
        extra_params: Optional[Dict] = None,
        on_content: Optional[Callable[[str], None]] = None
    ) -> LLMResponse:
        """
        统一的聊天接口
        
        Args:
            messages: 消息列表
            model: 模型名称（可选，覆盖 config 中的默认值）
            tools: 工具定义（可选）
            tool_choice: 工具选择策略（"auto", "none", "required"）
            temperature: 温度（0-2）
            max_tokens: 最大 token 数
            stream: 是否流式输出
            timeout: 超时时间（秒），None 则使用 config 中的默认值
            extra_params: 额外参数（如 {"thinking": "disabled"}）
            on_content: 流式内容回调函数，每收到内容片段时调用
            
        Returns:
            LLMResponse: 统一的响应对象
        """
        payload = {
            "model": model or self.config.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": stream
        }
        
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = tool_choice
        
        if extra_params:
            payload.update(extra_params)
        
        actual_timeout = timeout or self.config.timeout
        aio_timeout = aiohttp.ClientTimeout(total=actual_timeout)
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.config.api_url,
                    json=payload,
                    headers=self._build_headers(),
                    timeout=aio_timeout
                ) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        return LLMResponse(
                            content=f"API错误 [{response.status}]: {error_text}",
                            finish_reason="error"
                        )
                    
                    if stream:
                        return await self._handle_stream(response, on_content)
                    else:
                        return await self._handle_response(response)
                        
        except aiohttp.ClientError as e:
            return LLMResponse(
                content=f"网络请求失败: {str(e)}",
                finish_reason="error"
            )
        except Exception as e:
            return LLMResponse(
                content=f"连接错误: {str(e)}",
                finish_reason="error"
            )
    
    async def _handle_response(self, response: aiohttp.ClientResponse) -> LLMResponse:
        """处理非流式响应"""
        data = await response.json()
        
        if not data:
            return LLMResponse(content="API返回空响应", finish_reason="error")
        
        choices = data.get("choices", [])
        if not choices:
            return LLMResponse(content="API响应缺少choices", finish_reason="error")
        
        choice = choices[0]
        message = choice.get("message", {})
        
        return LLMResponse(
            content=message.get("content"),
            tool_calls=message.get("tool_calls"),
            finish_reason=choice.get("finish_reason", "stop"),
            raw=data
        )
    
    async def _handle_stream(
        self,
        response: aiohttp.ClientResponse,
        on_content: Optional[Callable[[str], None]]
    ) -> LLMResponse:
        """处理流式响应 - 与原版 paw.py 保持一致"""
        content_chunks: List[str] = []
        tool_calls_dict: Dict[int, Dict] = {}
        finish_reason = "stop"
        has_content = False

        try:
            async for line in response.content:
                line = line.decode('utf-8').strip()
                if not line or not line.startswith('data: '):
                    continue

                if line == 'data: [DONE]':
                    break

                try:
                    json_str = line[6:]  # 移除 'data: ' 前缀
                    chunk = json.loads(json_str)

                    if 'choices' not in chunk or len(chunk['choices']) == 0:
                        continue

                    delta = chunk['choices'][0].get('delta', {})
                    finish_reason = chunk['choices'][0].get('finish_reason', finish_reason)

                    # 处理内容（流式打印）
                    if 'content' in delta and delta['content']:
                        content_text = delta['content']
                        # 首次输出时去除前导换行
                        if not has_content:
                            content_text = content_text.lstrip('\n')
                            if not content_text:
                                continue
                            has_content = True
                        content_chunks.append(content_text)

                        if on_content:
                            on_content(content_text)

                    # 处理 tool_calls（累积）
                    if 'tool_calls' in delta:
                        for tc_delta in delta['tool_calls']:
                            idx = tc_delta.get('index', 0)
                            if idx not in tool_calls_dict:
                                tool_calls_dict[idx] = {
                                    'id': '',
                                    'type': 'function',
                                    'function': {'name': '', 'arguments': ''}
                                }

                            if 'id' in tc_delta:
                                tool_calls_dict[idx]['id'] = tc_delta['id']
                            if 'function' in tc_delta:
                                if 'name' in tc_delta['function']:
                                    tool_calls_dict[idx]['function']['name'] += tc_delta['function']['name']
                                if 'arguments' in tc_delta['function']:
                                    tool_calls_dict[idx]['function']['arguments'] += tc_delta['function']['arguments']

                except json.JSONDecodeError:
                    continue
        except Exception:
            # 回调函数可能抛出异常（如停止信号），直接返回当前结果
            pass

        # 组装最终结果
        full_content = ''.join(content_chunks) if content_chunks else None
        tool_calls = list(tool_calls_dict.values()) if tool_calls_dict else None

        return LLMResponse(
            content=full_content,
            tool_calls=tool_calls,
            finish_reason=finish_reason
        )
