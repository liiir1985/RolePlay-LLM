import json
import logging
import re
from typing import Dict, Optional
from openai import OpenAI
from .base_processor import BaseDataProcessor

logger = logging.getLogger(__name__)

class SystemPromptGenerator:
    """Generates randomized light novel writer system prompts using an LLM."""

    def __init__(self, base_url: str = "http://localhost:8081/v1", model_name: str = "qwen", api_key: str = "not-needed"):
        """Initialize the generator.

        Args:
            base_url: The base URL for the OpenAI-compatible API.
            model_name: The name of the model to use.
            api_key: The API key for the LLM service.
        """
        self.client = OpenAI(
            base_url=base_url,
            api_key=api_key
        )
        self.model_name = model_name

    def generate_prompt(self, context: Optional[str] = None) -> str:
        """Call LLM to generate a randomized system prompt for a light novel writer,
        optionally matching the style of the provided context.

        Args:
            context: Optional text context to match the style of.

        Returns:
            A string containing the generated system prompt.
        """
        instruction = (
            "请为一个AI助手生成一段**系统提示词**（System Prompt）。\n\n"
            "**要求：**\n"
            "1. 描述该AI为一个专业的日式轻小说作家。\n"
        )
        
        if context:
            instruction += (
                "2. **关键：** 观察提供的参考文本片的文风、语气和人设特色，生成一个与之相符且具有个性的口吻描述。\n"
                "3. 提示词内容应明确指出，助手将以上述分析出的特定口吻和风格对用户的开篇进行续写，并要求产出的内容在文本质感、用词习惯和叙事叙述上与参考文本中的样片高度一致。\n"
                "4. 尽可能丰富地描述工作内容，包括但不限于文风要求，且描述需与参考文本的调性一致。\n"
            )
        else:
            instruction += (
                "2. 使用随机的语气或人设口吻。\n"
                "3. 提示词内容应要求助手按照日式轻小说的风格对用户提供的文字进行续写。\n"
                "4. 尽可能丰富地描述其工作内容和写作要求。\n"
            )

        instruction += (
            "5. **只输出生成的系统提示词文本**，不要包含任何额外解释、引号或前言。\n"
            "6. 提示词应包含类似‘你将以[分析出的口吻]继续创作’的描述。\n"
            "7. **重要：生成的系统提示词文本长度必须控制在200字以内。**"
        )

        if context:
            # Truncate context to keep prompt size reasonable
            sample_text = context[:300] if len(context) > 300 else context
            instruction += f"\n\n**参考文本片段：**\n{sample_text}"

        try:
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {"role": "user", "content": instruction}
                ],
                max_tokens=32768,
                temperature=0.8,
                top_p=0.8,
                presence_penalty=1.5,
                extra_body={
                    "top_k": 20,
                    "chat_template_kwargs": {"enable_thinking": False},
                }
            )
            content = response.choices[0].message.content.strip()
            # Remove any potential markdown fencing
            content = re.sub(r'^```[a-zA-Z]*\n?', '', content)
            content = re.sub(r'\n?```$', '', content)
            return content.strip()
        except Exception as e:
            logger.error(f"Error calling LLM API for system prompt: {e}")
            return "你是一个专业的日式轻小说作家。请按照日式轻小说的风格，对用户提供的文字进行续写，注重情感表达和环境描写。"

class ChatMLProcessor(BaseDataProcessor):
    """Processes text entries into ChatML format with LLM-generated system prompts."""

    def __init__(self, generator: SystemPromptGenerator):
        """Initialize with a system prompt generator.
        
        Args:
            generator: The SystemPromptGenerator instance to use.
        """
        self.generator = generator

    def process(self, data: Dict) -> Optional[Dict]:
        """Split text and wrap into ChatML messages format.
        
        Args:
            data: The raw data entry.
            
        Returns:
            A dictionary with 'messages' key, or None if text is missing.
        """
        text = data.get("text", "")
        if not text:
            return None
            
        lines = text.splitlines()
        
        # Split: first 10 lines to user, rest to assistant
        user_content = "\n".join(lines[:10])
        assistant_content = "\n".join(lines[10:]) if len(lines) > 10 else ""

        # Generate the system prompt using LLM, passing assistant content as style reference
        system_prompt = self.generator.generate_prompt(context=assistant_content)

        return {
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
                {"role": "assistant", "content": assistant_content}
            ]
        }
