from typing import List, Optional, Dict, Literal
from pydantic import BaseModel, Field

# Using regular BaseModel to reduce chances of additionalProperties showing up in schema
class CharacterClothing(BaseModel):
    outerwear: str = ""
    top: str = ""
    bottom: str = ""
    socks: str = ""
    shoes: str = ""

class CharacterStatus(BaseModel):
    stamina: str = "100/100"
    mental: str = "100/100"
    location: str = "" # 大地点/小地点/具体位置
    status_desc: str = "" # 角色长期目标，近期目标和当前状态
    identity: str = "" # 职业身份
    clothing: CharacterClothing = Field(default_factory=CharacterClothing)
    temperament: str = "" # 气质神态
    pose: str = "" # 当前姿势

class Relationship(BaseModel):
    target_character: str
    opinion: str = "" # 对该角色的看法
    events: List[str] = Field(default_factory=list) # 重要事件

class CharacterItem(BaseModel):
    name: str
    state: str = ""

class PlotSummary(BaseModel):
    content: str = Field(description="当前剧情的前情提要")

class StatusUpdateFields(BaseModel):
    stamina: Optional[str] = Field(None, description="体力等级 (如 '80/100')")
    mental: Optional[str] = Field(None, description="精神等级 (如 '90/100')")
    location: Optional[str] = Field(None, description="位置 (填入 '大地点/小地点/具体位置')")
    status_desc: Optional[str] = Field(None, description="目标与状态 (包含长期目标、近期目标和当前状态的简述)")
    identity: Optional[str] = Field(None, description="职业或身份")
    temperament: Optional[str] = Field(None, description="气质神态")
    pose: Optional[str] = Field(None, description="当前姿势")
    # Clothing
    outerwear: Optional[str] = Field(None, description="外套")
    top: Optional[str] = Field(None, description="上装")
    bottom: Optional[str] = Field(None, description="下装")
    socks: Optional[str] = Field(None, description="袜子")
    shoes: Optional[str] = Field(None, description="鞋子")

# Flattened Data Block for Gemini Compatibility
class DataBlock(BaseModel):
    dataType: Literal[
        "narrative", "dialogue", "action", "thought", 
        "status_update", "relationship_update", "item_update", "scene_change"
    ]
    line_count: int = Field(1, description="此块内容在原 story.txt 中大约占用的行数 (用于精确计算 start_line 和 end_line)")
    
    # Fields for 'narrative', 'dialogue', 'action', 'thought'
    content: Optional[str] = Field(None, description="原文内容或人称转换后的内容")
    
    # Fields for 'dialogue'
    speaker: Optional[str] = Field(None, description="说话人全名 (用于 dialogue)")
    
    # Fields for 'action', 'thought'
    actor: Optional[str] = Field(None, description="动作或想法的主体全名 (用于 action, thought)")
    target: Optional[str] = Field(None, description="动作的目标对象全名 (用于 action, 可选)")
    
    # Fields for 'status_update'
    character: Optional[str] = Field(None, description="发生状态变更的角色名 (用于 status_update, relationship_update, item_update)")
    updates: Optional[StatusUpdateFields] = Field(None, description="状态变更的具体字段 (用于 status_update)")
    
    # Fields for 'relationship_update'
    # target (already defined above)
    opinion: Optional[str] = Field(None, description="对目标角色看法的新描述 (用于 relationship_update)")
    new_event: Optional[str] = Field(None, description="新增的重要关系事件 (用于 relationship_update)")
    
    # Fields for 'item_update'
    item_name: Optional[str] = Field(None, description="道具名称 (用于 item_update)")
    action: Optional[Literal["add", "remove", "modify"]] = Field(None, description="道具操作类型 (用于 item_update)")
    new_state: Optional[str] = Field(None, description="道具的新状态 (用于 item_update)")
    
    # Fields for 'scene_change'
    new_scene: Optional[str] = Field(None, description="新场景的名称 (用于 scene_change)")

class StorySceneFile(BaseModel):
    start_line: int
    end_line: int
    plot_summary: str
    character_states: Dict[str, CharacterStatus]
    character_relationships: Dict[str, List[Relationship]]
    character_items: Dict[str, List[CharacterItem]]
    data_blocks: List[DataBlock]
