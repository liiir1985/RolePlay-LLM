import json
import logging
import re
from typing import List, Optional
from openai import OpenAI

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class TextClassifier:
    """Classifies text segments into RolePlay categories using a local LLM."""

    CATEGORIES = {
        "dialogue": "高密度对话与互动",
        "action": "环境交互与动作描写",
        "monologue": "深度心理与独白",
        "lore": "世界观设定与宏大叙事",
        "character": "人物介绍",
        "system": "面板/系统音"
    }

    def __init__(self, base_url: str = "http://localhost:8000/v1", model_name: str = "qwen"):
        """Initialize the classifier.

        Args:
            base_url: The base URL for the OpenAI-compatible API.
            model_name: The name of the model to use.
        """
        self.client = OpenAI(
            base_url=base_url,
            api_key="not-needed"  # Local LLM usually doesn't need a real key
        )
        self.model_name = model_name

    def _get_system_prompt(self) -> str:
        """Returns the system prompt for classification."""
        prompt = (
            "你是一个文本分类助手。请根据以下类别对提供的文本切片进行分类。文本可以属于一个或多个类别。\n\n"
            "类别列表：\n"
            "1. dialogue (高密度对话与互动): 包含大量引号（“”、「」等）、角色快速交锋、强烈情绪或口癖。\n"
            "2. action (环境交互与动作描写): 重点在于角色探索、战斗或对突发事件的肢体反应。\n"
            "3. monologue (深度心理与独白): 大段角色内心戏、动机剖析、情感挣扎。\n"
            "4. lore (世界观设定与宏大叙事): 对设定、历史、地理或背景的客观描述。\n"
            "5. character (人物介绍): 包含角色简介、属性等介绍性旁白。\n"
            "6. system (面板/系统音): 网游属性面板 [力量: 99] 或系统提示音。\n\n"
            "要求：\n"
            "- 必须仅返回一个 JSON 数组，包含对应类别的英文名。\n"
            "- 例如: [\"monologue\", \"lore\"]\n"
            "- 只返回最匹配的1-2个类别。不要超过2个类别\n"
            "- 对于dialogue，只有当文本主要由dialogue构成时才归类为该类型"
            "- 不要返回任何其他解释性文字。"
        )
        return prompt

    def classify(self, text: str) -> List[str]:
        """Classify a piece of text.

        Args:
            text: The text string to classify.

        Returns:
            A list of matching category names.
        """
        if not text.strip():
            return []

        try:
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": self._get_system_prompt()},
                    {"role": "user", "content": f"请分类以下文本：\n\n{text}"}
                ],
                max_tokens=32768,
                temperature=0.7,
                top_p=0.8,
                presence_penalty=1.5,
                extra_body={
                    "top_k": 20,
                    "chat_template_kwargs": {"enable_thinking": False},
                }
            )
            
            content = response.choices[0].message.content.strip()
            logger.info(f"LLM response: {content}")
            # Extract JSON array using regex in case LLM adds markdown or chatter
            match = re.search(r'\[.*\]', content, re.DOTALL)
            if match:
                try:
                    categories = json.loads(match.group(0))
                    if isinstance(categories, list):
                        # Validate categories are within our allowed list
                        return [c for c in categories if c in self.CATEGORIES]
                except json.JSONDecodeError:
                    logger.error(f"Failed to parse LLM response as JSON: {content}")
            else:
                logger.error(f"No JSON array found in LLM response: {content}")
                
        except Exception as e:
            logger.error(f"Error calling LLM API: {e}")
            
        return []
