import time
import json
from typing import Optional, List, Dict, Any, Iterator
from dataclasses import dataclass, asdict

from openai import OpenAI, APIError, APIConnectionError, RateLimitError
from openai.types.chat import ChatCompletionMessageParam

from ..config import LLMConfig, get_config


@dataclass
class ChatMessage:
    role: str
    content: str
    
    def to_dict(self) -> ChatCompletionMessageParam:
        return {"role": self.role, "content": self.content}


@dataclass
class ChatCompletionResponse:
    content: str
    model: str
    usage: Dict[str, int]
    finish_reason: str


class LLMClient:
    def __init__(self, config: Optional[LLMConfig] = None):
        self.config = config or get_config().llm
        self._client: Optional[OpenAI] = None
    
    @property
    def client(self) -> OpenAI:
        if self._client is None:
            self._client = OpenAI(
                api_key=self.config.api_key or None,
                base_url=self.config.base_url,
                timeout=self.config.timeout,
            )
        return self._client
    
    def _build_messages(
        self,
        messages: List[ChatMessage],
    ) -> List[ChatCompletionMessageParam]:
        return [m.to_dict() for m in messages]
    
    def chat_completion(
        self,
        messages: List[ChatMessage],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        **kwargs
    ) -> ChatCompletionResponse:
        last_error: Optional[Exception] = None
        
        for attempt in range(self.config.max_retries):
            try:
                response = self.client.chat.completions.create(
                    model=self.config.model,
                    messages=self._build_messages(messages),
                    temperature=temperature if temperature is not None else self.config.temperature,
                    max_tokens=max_tokens if max_tokens is not None else self.config.max_tokens,
                    **kwargs
                )
                
                choice = response.choices[0]
                usage = response.usage
                usage_dict = {
                    "prompt_tokens": usage.prompt_tokens if usage else 0,
                    "completion_tokens": usage.completion_tokens if usage else 0,
                    "total_tokens": usage.total_tokens if usage else 0,
                }
                
                return ChatCompletionResponse(
                    content=choice.message.content or "",
                    model=response.model,
                    usage=usage_dict,
                    finish_reason=choice.finish_reason or "stop"
                )
            
            except (APIError, APIConnectionError, RateLimitError) as e:
                last_error = e
                if attempt < self.config.max_retries - 1:
                    wait_time = self.config.retry_delay * (2 ** attempt)
                    time.sleep(wait_time)
                    continue
                raise
        
        raise last_error or Exception("Failed to execute request after all retries")
    
    def chat_completion_stream(
        self,
        messages: List[ChatMessage],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        **kwargs
    ) -> Iterator[str]:
        last_error: Optional[Exception] = None
        
        for attempt in range(self.config.max_retries):
            try:
                stream = self.client.chat.completions.create(
                    model=self.config.model,
                    messages=self._build_messages(messages),
                    temperature=temperature if temperature is not None else self.config.temperature,
                    max_tokens=max_tokens if max_tokens is not None else self.config.max_tokens,
                    stream=True,
                    **kwargs
                )
                
                for chunk in stream:
                    if chunk.choices and chunk.choices[0].delta.content:
                        yield chunk.choices[0].delta.content
                return
            
            except (APIError, APIConnectionError, RateLimitError) as e:
                last_error = e
                if attempt < self.config.max_retries - 1:
                    wait_time = self.config.retry_delay * (2 ** attempt)
                    time.sleep(wait_time)
                    continue
                raise
        
        raise last_error or Exception("Failed to execute streaming request after all retries")
    
    def simple_chat(
        self,
        user_message: str,
        system_message: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        **kwargs
    ) -> str:
        messages: List[ChatMessage] = []
        
        if system_message:
            messages.append(ChatMessage(role="system", content=system_message))
        
        messages.append(ChatMessage(role="user", content=user_message))
        
        response = self.chat_completion(
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs
        )
        
        return response.content
    
    def chat_with_json_response(
        self,
        messages: List[ChatMessage],
        json_schema: Optional[Dict[str, Any]] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        **kwargs
    ) -> Any:
        if json_schema:
            kwargs["response_format"] = {
                "type": "json_schema",
                "json_schema": json_schema
            }
            
        response = self.chat_completion(
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs
        )
        
        content = response.content.strip()
        # 移除可能存在的 markdown json 标记
        if content.startswith("```json"):
            content = content[7:]
        if content.startswith("```"):
            content = content[3:]
        if content.endswith("```"):
            content = content[:-3]
        content = content.strip()
        
        try:
            return json.loads(content)
        except json.JSONDecodeError as e:
            raise ValueError(f"Failed to parse JSON response: {e}\nResponse: {response.content}")
    
    def close(self):
        if self._client is not None:
            self._client.close()
            self._client = None
    
    def __enter__(self) -> "LLMClient":
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


_llm_client: Optional[LLMClient] = None


def get_llm_client() -> LLMClient:
    global _llm_client
    if _llm_client is None:
        _llm_client = LLMClient()
    return _llm_client
