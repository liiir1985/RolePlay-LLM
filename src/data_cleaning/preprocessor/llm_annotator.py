import logging
from typing import List, Optional, Dict
from google import genai
from google.genai import types
from pydantic import BaseModel
from src.data_cleaning.config import GEMINI_API_KEY, DEFAULT_MODEL
from .models import DataBlock

logger = logging.getLogger(__name__)

class BatchResponse(BaseModel):
    data_blocks: List[DataBlock]
    updated_plot_summary: str

def clean_schema(schema: dict):
    """Recursively remove 'additionalProperties' from the JSON schema."""
    if isinstance(schema, dict):
        schema.pop("additionalProperties", None)
        for value in schema.values():
            clean_schema(value)
    elif isinstance(schema, list):
        for item in schema:
            clean_schema(item)
    return schema

class LLMAnnotator:
    def __init__(self, api_key: str = GEMINI_API_KEY, model_name: str = DEFAULT_MODEL):
        self.client = genai.Client(api_key=api_key)
        self.model_name = model_name

    def process_batch(
        self, 
        lines: List[str], 
        main_characters: List[str],
        current_context: Dict
    ) -> Optional[BatchResponse]:
        """Process a batch of lines using LLM to extract structured data."""
        
        all_known = current_context.get('known_characters', main_characters)
        
        system_instruction = f"""你是一个顶级的视觉小说和角色扮演游戏脚本专家。你的任务是将提供的原始故事文本转换为结构化的数据集。

已知角色全名列表：{', '.join(all_known)}

当前角色状态：
{current_context.get('character_states', '无')}

当前人际关系：
{current_context.get('character_relationships', '无')}

当前道具：
{current_context.get('character_items', '无')}

当前前情提要：
{current_context.get('plot_summary', '无')}

规则：
1. 请根据这200行原始文本，提取并生成一系列数据块 (data_blocks)。
2. **核心原则**：DataBlock 的目的是结构化分割原文。**严禁对原文进行概括、删减。文本内容必须与原文意思完全对等。**
            - `identity`: 职业或身份
            - `temperament`: 气质神态
            - `pose`: 当前姿势
            - **衣着相关**：`outerwear` (外套), `top` (上装), `bottom` (下装), `socks` (袜子), `shoes` (鞋子)
    - relationship_update: 人际关系变更。角色名填入 `character`，目标角色填入 `target`，新看法填入 `opinion`，新事件填入 `new_event`。
    - item_update: 道具变更。角色名填入 `character`，道具名填入 `item_name`，操作填入 `action` ("add"/"remove"/"modify")，新状态填入 `new_state`。
    - scene_change: 场景切换。新场景名填入 `new_scene`。**识别到场景切换后，请务必更新在该场景中出现的角色的 location。**
4. **合并规则**：相邻数据块如果属于【同一类型】且涉及【同一个、仅一个相同的角色】，必须合并为一条。对话内容合并时使用 \\n 分隔。**严禁合并不同发言人的对话。**
5. **前情提提要**：在 `updated_plot_summary` 中提供最新的故事简述。如果识别到第一人称“我”的身份，请在此处指明“我”指代的是谁。
6. **字段填充**：对于每个数据块，只填充与该 `dataType` 相关的字段，其余字段保持为 null。
7. **一致性**：一旦识别到“我”的身份（如 健），在后续的整个处理过程中，请保持该身份的一致性，直至有明确的视角切换。
8. 必须返回纯 JSON 格式。
"""

        prompt = "以下是需要处理的文本内容：\n\n" + "\n".join(lines)

        # Generate clean schema
        raw_schema = BatchResponse.model_json_schema()
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
                return None
            
            return BatchResponse.model_validate_json(response.text)
        except Exception as e:
            logger.error(f"Error processing batch: {e}")
            return None
