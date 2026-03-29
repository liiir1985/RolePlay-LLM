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
        print("可用模型列表：")
        for model in self.client.models.list():
            print(f"名称: {model.name}")
        self.model_name = model_name

    def process_batch(
        self, 
        lines: List[str], 
        main_characters: List[str],
        current_context: Dict
    ) -> Optional[BatchResponse]:
        """Process a batch of lines using LLM to extract structured data."""
        
        all_known = current_context.get('known_characters', main_characters)
        num_lines = len(lines)
        
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
1. 请根据这{num_lines}行原始文本，提取并生成一系列数据块 (data_blocks)。
2. **核心原则**：DataBlock 的目的是结构化分割原文。**严禁对原文进行概括、删减。文本内容必须与原文意思完全对等。**
3. **颗粒度与合并规则**：
    - **以“句子”为最小颗粒度**。严禁将原文中的一个完整句子拆分为两个 DataBlock。
    - **禁止跨句合并**：如果两个不同的句子涉及不同的人，必须拆分为独立的两个 DataBlock。
    - **同句保留**：如果一个完整句子中同时出现了多个人的行为，应当作为一个整体保留在一个 DataBlock 中（actor 填入主要行为者）。
4. **行数分配**：为每个 DataBlock 分配一个 `line_count` (整数)，代表该块在原 story.txt 中大约占用的行数。**这{num_lines}行处理完后，所有 data_blocks 的 line_count 总和必须等于 {num_lines}。**
5. **数据块类型与填充说明**：
    - narrative: 旁白、环境描写、客观描述。内容填入 `content`。**必须保留原文，严禁概括。若内容包含“我”等第一人称代词，必须归类为该角色对应的 action、thought 或 dialogue。**
    - dialogue: 角色对话内容。提取说话人填入 `speaker`，对话内容填入 `content`。
        - **必须使用全名**。
        - **绝对严禁跨句合并多个人的说话内容**。如果原文中不同句子的对话来自不同人（例如：“早安。”“早。”），也必须拆分为独立的 dialogue 块。
        - **内容必须保留对话原文（不含引号）。**
    - action: 角色行为/动作。主体 `actor` 和目标 `target` **必须使用全名**。内容填入 `content`。
        - **禁止跨句合并**：如果不同句子描述了不同人的行为（如“A拍了拍B。B回过头。”），必须拆分为两个独立的 action 块。
        - **改写规则**：如果原文是第一人称（如“我走过去”），必须通过上下文判定“我”是谁，并改写为【第三人称】（如“佐藤走过去”）。除此之外，严禁概括，保留所有细节描述。
    - thought: 角色内心活动。主体 `actor` **必须使用全名**。内容填入 `content`。
        - **改写规则**：必须通过上下文判定“我”是谁，并改写为该角色的【第一人称】内心独白（如“我也许该走了”）。必须保留原文语气和细节，严禁概括。
    - status_update: 角色状态变更。角色名 `character` **必须使用全名**。
        - **位置更新规则**：当场景变更或识别到角色处于新地点时，必须为当前场景内的【所有出现角色】分别生成独立的 status_update 块来更新他们的 `location`。
        - **状态栏可用字段**：`stamina`, `mental`, `location`, `status_desc`, `identity`, `temperament`, `pose` 以及衣着字段 (`outerwear` 等)。
    - relationship_update / item_update: 角色名和相关目标**必须使用全名**。
    - scene_change: 识别并记录场景切换，输出新场景名称 `new_scene`。**场景切换后必须紧跟当前场景所有人的 location 更新。**
6. **局部合并逻辑**：仅当相邻两个块属于【完全相同的 dataType】且涉及【同一个、仅一个相同的全名角色】时，才可将其所属的多个连续句子合并（使用 \\n 分隔）。
7. **前情提提要**：在 `updated_plot_summary` 中提供最新的故事简述。在此明确指出“我”当前代指的具体全名。
8. **名字规范**：
    - 在所有字段中，严禁缩写或代称（如“他”、“她”、“妈妈”、“老师”），必须使用“已知角色全名列表”中的全名。
    - **真名优先级**：如果角色全名为人称（如“莉莉的妈妈”），当该角色的真名在后续情节中已知后（如“佐藤美代子”），请在后续的所有数据块中将其替换为真名。
    - 如发现新角色，请输出其在文中出现的全名。
9. 必须返回纯 JSON 格式。
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
