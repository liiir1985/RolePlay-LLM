import logging
from typing import List, Optional
from google import genai
from google.genai import types
from pydantic import BaseModel, Field
from src.data_cleaning.config import GEMINI_API_KEY, DEFAULT_MODEL

logger = logging.getLogger(__name__)

class SimpleBatchResponse(BaseModel):
    """Response from the LLM for a batch of lines, split by scene changes."""
    segments: List[str] = Field(..., description="按场景分割后的处理后文本段。第一个段属于当前场景，后续段均标志着新场景的开始。")

def clean_schema(schema: dict):
    """Recursively remove 'additionalProperties' from the JSON schema for Gemini compatibility."""
    if isinstance(schema, dict):
        schema.pop("additionalProperties", None)
        for value in schema.values():
            clean_schema(value)
    elif isinstance(schema, list):
        for item in schema:
            clean_schema(item)
    return schema

class SimpleAnnotator:
    """Handles LLM-based reformatting of story text."""
    
    def __init__(self, api_key: str = GEMINI_API_KEY, model_name: str = DEFAULT_MODEL):
        """Initializes the Gemini client.
        
        Args:
            api_key: The Gemini API key.
            model_name: The name of the model to use.
        """
        self.client = genai.Client(api_key=api_key)
        self.model_name = model_name

    def process_batch(self, lines: List[str]) -> Optional[SimpleBatchResponse]:
        """Processes a batch of lines using LLM and returns text segments.
        
        Args:
            lines: A list of raw text lines.
            
        Returns:
            A SimpleBatchResponse object containing text segments.
        """
        num_lines = len(lines)
        
        system_instruction = f"""你是一个专业的小说脚本预处理专家。你的任务是将提供的{num_lines}行原始文本进行格式化重写，并根据场景变化进行分割。

格式化规则：
1. **对话处理**：如果当前行是对话，统一修改为【说话人】「对话内容」的格式。如果原文没有明确说明说话人，请根据上下文推断，并填入正确的全名。
2. **心理活动处理**：如果当前行是心理活动，统一修改为【说话人】（心里想的内容）。同样需要根据上下文推断说话人全名。
   - **人称转换**：必须改写为以该说话人为“第一人称”的心理活动（例如：“他觉得有点冷” 改写为 “【某人】（我觉得有点冷）”）。只修改人称，不要修改原意。
3. **旁白处理**：如果旁白使用了第一人称“我”，必须改写为以“第三人称”叙述的句子（例如：“我走进了房间” 改写为 “佐藤走进了房间”）。
4. **混合行处理（重要）**：如果一行原文中同时包含了心理活动/对话和叙述性文字，**必须将其拆分为多行输出**。
   - 例如：`我心想世上真是无奇不有，于是把拍扁的蚊子丢进垃圾桶，随后前往客厅。`
   - 应改写为：
     ```
     【桐崎冬马】（世上真是无奇不有。）
     桐崎冬马于是把拍扁的蚊子丢进垃圾桶，随后前往客厅。
     ```
5. **其余情况**：如果不符合上述规则，请保留原句内容。

分割与输出规则：
1. **场景变更识别**：识别文本中的场景变更点（例如：时间跳转、地点变更、明显的分段线）。
2. **段落分割**：将这{num_lines}行文本处理后，根据场景变更点分割成一个字符串数组 (`segments`)。
   - 如果这{num_lines}行中没有场景变化，`segments` 应该只包含一个元素（即处理后的完整文本）。
   - 如果发生了一次场景变化，`segments` 应该包含两个元素：第一部分是变化前的内容，第二部分是变化后的内容（从发生变化的那一行开始）。
   - 如果发生了多次变化，依此类推。
3. **完整性**：所有 `segments` 中包含的文本合并后，必须涵盖这{num_lines}行对应的所有内容，严禁删减情节。

输出格式：纯 JSON，符合 SimpleBatchResponse 结构。
"""

        prompt = "以下是需要顺序处理的文本内容：\n\n" + "\n".join(
            [f"Line {i+1}: {line.strip()}" for i, line in enumerate(lines)]
        )

        raw_schema = SimpleBatchResponse.model_json_schema()
        cleaned_schema = clean_schema(raw_schema)

        try:
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    response_mime_type="application/json",
                    response_schema=cleaned_schema,
                ),
            )
            
            if not response.text:
                logger.error("LLM returned empty response.")
                return None
            
            result = SimpleBatchResponse.model_validate_json(response.text)
            return result
        except Exception as e:
            logger.error(f"Error calling LLM: {e}")
            return None
