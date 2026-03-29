from typing import List, Optional
from pydantic import BaseModel, Field

class CharacterProfile(BaseModel):
    name: str = Field(..., description="角色名")
    identity: str = Field(..., description="核心身份，如：没落贵族的末裔、表面温柔的杀手")
    impression: str = Field(..., description="年龄/视觉印象，包括岁数、压迫感或亲和力")

class CorePersonality(BaseModel):
    keywords: List[str] = Field(..., description="三个性格关键词")
    logic: str = Field(..., description="行为逻辑，核心！例如：遇到危险时优先牺牲他人")
    ethics: str = Field(..., description="道德基准，如：不杀妇孺、极致的守序中庸")

class LinguisticFingerprint(BaseModel):
    tone: str = Field(..., description="语调，如：慵懒的、短促有力的")
    habit: str = Field(..., description="口癖/习惯，如：喜欢用反问句、说话末尾带“...吧”")
    address: str = Field(..., description="对自己和对他人的称谓，如“阁下”、“那家伙”、“杂鱼”")

class KnowledgeBoundary(BaseModel):
    known: List[str] = Field(..., description="角色精通的领域")
    bias: str = Field(..., description="未知/偏解，他由于出身或性格，会对什么产生误解")

class CharacterCard(BaseModel):
    profile: CharacterProfile = Field(..., description="基础信息")
    personality: CorePersonality = Field(..., description="性格内核")
    linguistic_fingerprint: LinguisticFingerprint = Field(..., description="语言指纹")
    knowledge_boundary: KnowledgeBoundary = Field(..., description="知识边界")
    sample_dialogue: List[str] = Field(..., description="2-3句最能代表灵魂的台词")

class NovelAnnotation(BaseModel):
    worldview: str = Field(..., description="开篇时的世界观介绍，大约300字")
    characters: List[CharacterCard] = Field(..., description="主要角色的角色卡列表")
    unknown: bool = Field(False, description="如果该作品不是已知的作品，则如实返回 true")
