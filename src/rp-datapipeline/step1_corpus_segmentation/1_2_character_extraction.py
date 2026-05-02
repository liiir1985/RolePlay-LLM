import argparse
import json
from pathlib import Path
from typing import List, Optional, Dict, Any, Set, Tuple
from dataclasses import dataclass

from pydantic import BaseModel

from ..utils.llm_client import LLMClient, ChatMessage


CHARACTER_EXTRACTION_SYSTEM_PROMPT = """从小说文本中提取人物角色名称，并判断叙事视角，输出包含characters、is_first_person、first_person_name字段的JSON对象。

characters是二维数组，每个子数组是一个角色。
is_first_person表示文本是否以第一人称视角（"我"）书写。
first_person_name表示第一人称"我"对应的角色称呼。如果不是第一人称视角，则为空字符串。如果是第一人称视角：
  - 如果能从文本中判断"我"是谁，必须使用已知角色列表或本次提取出的角色称呼中的其中一个
  - 如果无法判断具体是谁，但能判断性别/年龄特征，使用合适的代词（如"女孩"、"少女"、"少年"、"男孩"、"男人"、"女人"等）
  - 如果完全无法判断任何特征，则为空字符串
  - **重要**：如果提供了"已知主角名"，但文本中的"我"明显与该名字冲突（如性别、年龄不符），则忽略已知主角名，改用合适的代词或空字符串

核心规则：
1. 只能输出在【当前文本内容】中实际出场了的角色称呼。严禁输出在已知角色列表中但未在当前文本中出现的角色！
2. 根据上下文语义判断名称归属。同一角色的不同称呼（姓名、姓氏、名字、外号、绰号等）放入同一子数组，不同角色放入不同子数组。注意：仅仅同时出现在文本中不代表是同一角色，必须有明确的语义关联。
3. 如果当前文本中出场的某角色已在已知列表中，输出时必须包含至少一个已知称呼，以便代码合并。但绝不能仅仅因为角色在已知列表中就将其输出。
4. 排除：人称代词、模糊描述、泛指、单独的亲属称谓、单独的职业。与具体名字结合的除外（如"张医生"保留）。

示例1：
文本："冬马、美来和浅宫美来一起出现了。"
分析："美来"是"浅宫美来"的一部分→同一角色。"冬马"与"浅宫美来"无关联→不同角色。第三人称叙述。
输出：{"characters": [["冬马"], ["浅宫美来", "美来"]], "is_first_person": false, "first_person_name": ""}

示例2：
已知角色：[["浅宫美来", "美来"], ["冬马"], ["七濑春辉"]]
文本："浅宫和冬马走进教室，七濑正在看书。"
分析：三人都出现了。"浅宫"是"浅宫美来"的新称呼→附带已知称呼。"冬马"本身是已知称呼→直接输出。"七濑"是"七濑春辉"的新称呼→附带已知称呼。第三人称叙述。
输出：{"characters": [["浅宫美来", "浅宫"], ["冬马"], ["七濑春辉", "七濑"]], "is_first_person": false, "first_person_name": ""}

示例3：
已知角色：[["张三", "铁拳"], ["李四"], ["王五"]]
文本："铁拳走进擂台，对手已经等候多时。"
分析："铁拳"是"张三"的绰号，出场了。"李四"和"王五"在已知角色中，但未在当前文本中出场，严禁输出。第三人称叙述。
输出：{"characters": [["张三", "铁拳"]], "is_first_person": false, "first_person_name": ""}

示例4：
已知角色：[["浅宫美来", "美来"], ["冬马"]]
文本："我走进教室，看到冬马正在和美来聊天。冬马转过头对我说：'春辉，你来晚了。'"
分析：第一人称视角。"我"被冬马称为"春辉"→first_person_name为"春辉"。"春辉"是新角色。
输出：{"characters": [["冬马"], ["美来"], ["春辉"]], "is_first_person": true, "first_person_name": "春辉"}

示例5：
文本："我走在回家的路上，街道上空无一人。"
分析：第一人称视角，但无法判断"我"是谁，也无法判断性别/年龄特征。
输出：{"characters": [], "is_first_person": true, "first_person_name": ""}

示例6：
文本："我脱下校服，换上了便装。镜子里的少女看起来有些疲惫。"
分析：第一人称视角。无法判断具体名字，但从"少女"可知是年轻女性。
输出：{"characters": [], "is_first_person": true, "first_person_name": "少女"}

示例7：
已知主角名：张三（男性名字）
文本："我整理了一下裙子，对着镜子检查妆容。作为一个高中女生，外表还是很重要的。"
分析：第一人称视角。已知主角名是"张三"（男性），但文本中"我"明显是女性（裙子、妆容、高中女生），产生冲突。忽略已知主角名，使用"女孩"。
输出：{"characters": [], "is_first_person": true, "first_person_name": "女孩"}

只输出JSON对象。
"""


CHARACTER_GROUPING_REVIEW_PROMPT = """检查以下角色名称分组是否有归类错误，输出包含characters字段的JSON对象。

需要修正的两类错误：
1. 不同角色被错误合并到同一组：如["小张","张明","小李"]→"小李"应该和"李四"相关而非"张明"
2. 同一角色被错误拆分到不同组：如[["藤田诗织"],["藤田"],["诗织"]]→应合并为[["藤田诗织","藤田","诗织"]]

如果没有错误，原样输出即可。只输出JSON对象。
"""


FORMAL_NAME_IDENTIFICATION_SYSTEM_PROMPT = """你是一个专业的文本分析助手，擅长识别人物名称的正式程度。

你的任务：
从给定的角色名称列表中，选择该角色的本名作为主要名称（name），其余作为别名（alias）。

判断规则：
1. 本名是指角色的真实姓名（姓+名），不附带任何敬称、后缀或称谓
   - "如月结衣" 是本名，"如月结衣同学" 不是（带了"同学"后缀）
   - "张三" 是本名，"张三先生" 不是（带了"先生"后缀）
2. 优先级：本名（姓+名）> 姓氏+称呼 > 昵称/别名 > 称号
3. 如果列表中没有明确的本名，选择最接近本名的称呼

输出要求：
- 输出JSON对象，包含两个字段：
  - "name": 字符串，该角色的本名
  - "alias": 字符串数组，其余的名称（不包含name）

示例：

输入：["如月结衣同学", "结衣", "如月结衣", "如月同学", "如月"]
输出：
{
  "name": "如月结衣",
  "alias": ["如月结衣同学", "结衣", "如月同学", "如月"]
}

输入：["张三", "小张", "三哥"]
输出：
{
  "name": "张三",
  "alias": ["小张", "三哥"]
}

输入：["小A"]
输出：
{
  "name": "小A",
  "alias": []
}

注意：只输出JSON对象，不要输出其他内容。
"""


class CharacterExtractionResponse(BaseModel):
    characters: List[List[str]]
    is_first_person: bool = False
    first_person_name: str = ""


class CharacterGroupingReviewResponse(BaseModel):
    characters: List[List[str]]


class FormalNameResponse(BaseModel):
    name: str
    alias: List[str]


@dataclass
class SegmentExtractionResult:
    """单段文本的角色提取结果"""
    characters: List[List[str]]
    # 每个角色组（对应characters的相同索引）中各个称呼的出现频率
    character_frequencies: List[Dict[str, int]]
    is_first_person: bool = False
    first_person_name: str = ""


PERSONAL_PRONOUNS = {
    "我", "你", "他", "她", "它",
    "我们", "咱们", "你们", "他们", "她们", "它们",
    "自己", "自个儿", "人家", "别人", "旁人",
    "大伙", "大家", "诸位", "各位", "列位"
}


KINSHIP_TERMS = {
    "父亲", "母亲", "爸爸", "妈妈", "爸", "妈", "爹", "娘",
    "爷爷", "奶奶", "外公", "外婆", "姥爷", "姥姥",
    "哥哥", "姐姐", "弟弟", "妹妹", "哥", "姐", "弟", "妹",
    "儿子", "女儿", "孩子", "儿女",
    "叔叔", "阿姨", "伯父", "伯母", "舅舅", "舅妈",
    "姑姑", "姑父", "姨夫", "姨妈", "婶婶", "姨",
    "侄子", "侄女", "外甥", "外甥女",
    "表哥", "表弟", "表姐", "表妹", "堂哥", "堂弟", "堂姐", "堂妹",
    "岳父", "岳母", "公公", "婆婆", "继父", "继母",
    "养父", "养母", "义父", "义母"
}


FUZZY_DESCRIPTION_KEYWORDS = {
    "那个", "这个", "某个", "某一",
    "穿", "戴", "拿", "持", "握",
    "一", "几", "数",
    "男人", "女人", "老人", "小孩", "孩子", "年轻人", "中年人", "老年人",
    "众人", "大伙", "大家", "人们", "人群",
    "医生", "老师", "教授", "警察", "学生", "工人", "农民", "司机",
    "先生", "女士", "小姐", "太太", "夫人"
}


class CharacterExtractor:
    def __init__(self, llm_client: Optional[LLMClient] = None):
        self.llm_client = llm_client or LLMClient()
    
    def filter_invalid_names(self, names: List[str]) -> List[str]:
        filtered = []
        for name in names:
            name_stripped = name.strip()
            if not name_stripped:
                continue
            
            if name_stripped in PERSONAL_PRONOUNS:
                continue
            
            if name_stripped in KINSHIP_TERMS:
                continue
            
            is_kinship_without_name = False
            for kinship in KINSHIP_TERMS:
                if name_stripped.endswith(kinship):
                    prefix = name_stripped[:-len(kinship)]
                    if prefix in {"", "的", "之"}:
                        is_kinship_without_name = True
                        break
            
            if is_kinship_without_name:
                continue
            
            is_fuzzy = False
            for keyword in FUZZY_DESCRIPTION_KEYWORDS:
                if keyword in name_stripped:
                    if len(name_stripped) <= len(keyword) + 1:
                        is_fuzzy = True
                        break
            
            if is_fuzzy:
                continue
            
            filtered.append(name_stripped)
        
        return filtered
    
    def deduplicate_names(self, names: List[str]) -> List[str]:
        seen: Set[str] = set()
        result = []
        for name in names:
            if name not in seen:
                seen.add(name)
                result.append(name)
        return result
    
    @staticmethod
    def _has_name_overlap(names_a: List[str], names_b: List[str]) -> bool:
        """检查两组名称是否有精确匹配或子串包含关系"""
        for a in names_a:
            for b in names_b:
                if a == b:
                    return True
                # 子串包含关系（至少2个字符的名称才检查，避免单字误匹配）
                if len(a) >= 2 and len(b) >= 2:
                    if a in b or b in a:
                        return True
        return False

    def merge_character_names(
        self,
        existing_characters: List[List[str]],
        new_characters: List[List[str]],
        existing_frequencies: Optional[List[Dict[str, int]]] = None,
        new_frequencies: Optional[List[Dict[str, int]]] = None,
        # 用于控制是否执行别名数量剪枝。为了避免新称呼立刻被淘汰，改为在外部累计连续N个segment都超过阈值后再传true
        enable_pruning: bool = False,
        # 指定哪些索引的角色需要被剪枝。如果为空且 enable_pruning 为 True，则默认检查所有角色
        prune_indices: Optional[Set[int]] = None
    ) -> Tuple[List[List[str]], List[Dict[str, int]]]:
        merged = [list(char) for char in existing_characters]
        
        # 初始化频率字典，如果没传则给空的字典列表
        merged_freqs = []
        if existing_frequencies:
            merged_freqs = [{k: v for k, v in freq.items()} for freq in existing_frequencies]
        else:
            merged_freqs = [{} for _ in existing_characters]
            
        new_freqs_list = []
        if new_frequencies:
            new_freqs_list = new_frequencies
        else:
            new_freqs_list = [{} for _ in new_characters]
        
        # 记录现有的合并映射，以便外部跟踪剪枝索引
        # 注意：此处发生合并时，如果涉及到 prune_indices，则在二次合并后 prune_indices 也要更新
        
        for new_char, new_freq in zip(new_characters, new_freqs_list):
            if not new_char:
                continue
            
            filtered_new = self.filter_invalid_names(new_char)
            if not filtered_new:
                continue
            
            deduplicated_new = self.deduplicate_names(filtered_new)
            if not deduplicated_new:
                continue
            
            # 为了防止把原本不相关的两组人错误合并，我们寻找匹配的最佳项，但不跨组合并
            best_match_idx = -1
            max_overlap = 0
            
            for i, existing_char in enumerate(merged):
                overlap_count = 0
                for a in existing_char:
                    for b in deduplicated_new:
                        if a == b or (len(a) >= 2 and len(b) >= 2 and (a in b or b in a)):
                            overlap_count += 1
                
                if overlap_count > max_overlap:
                    max_overlap = overlap_count
                    best_match_idx = i
            
            if best_match_idx != -1:
                # 找到了最佳匹配组，只合并到这个组中
                all_names = merged[best_match_idx] + deduplicated_new
                merged[best_match_idx] = self.deduplicate_names(all_names)
                
                # 合并频率
                for name in deduplicated_new:
                    merged_freqs[best_match_idx][name] = merged_freqs[best_match_idx].get(name, 0) + new_freq.get(name, 1)
            else:
                # 没有找到匹配的组，作为新角色添加
                merged.append(deduplicated_new)
                freq_dict = {}
                for name in deduplicated_new:
                    freq_dict[name] = new_freq.get(name, 1)
                merged_freqs.append(freq_dict)
        
        # 处理别名数量限制
        if enable_pruning:
            for i, char_group in enumerate(merged):
                if len(char_group) > 6:
                    if prune_indices is not None and i not in prune_indices:
                        continue
                        
                    freq_dict = merged_freqs[i]
                    
                    # 计算排名
                    # 频率排名 (从大到小, 名次越小说明频率越高)
                    freq_sorted = sorted(char_group, key=lambda x: freq_dict.get(x, 0), reverse=True)
                    freq_rank = {name: rank for rank, name in enumerate(freq_sorted)}
                    
                    # 长度排名 (从大到小, 名次越小说明长度越长)
                    len_sorted = sorted(char_group, key=len, reverse=True)
                    len_rank = {name: rank for rank, name in enumerate(len_sorted)}
                    
                    # 计算总排名分数：频率排名 + 长度排名。 分数越小越需要保留
                    score = {name: freq_rank[name] + len_rank[name] for name in char_group}
                    
                    # 按照分数从小到大排序，保留前 6 个
                    kept_names = sorted(char_group, key=lambda x: score[x])[:6]
                    
                    # 更新当前组和频率字典
                    merged[i] = kept_names
                    merged_freqs[i] = {k: v for k, v in freq_dict.items() if k in kept_names}
        
        return merged, merged_freqs
    
    def extract_characters_from_segment(
        self,
        text: str,
        known_characters: Optional[List[List[str]]] = None,
        known_pov_name: Optional[str] = None,
        chunk_size: int = 2000
    ) -> SegmentExtractionResult:
        # 如果文本很长，则分块提取，避免LLM注意力不够
        chunks = []
        if len(text) > chunk_size:
            # 尽量在换行处截断
            lines = text.split('\n')
            current_chunk = []
            current_len = 0
            for line in lines:
                if current_len + len(line) > chunk_size and current_chunk:
                    chunks.append('\n'.join(current_chunk))
                    current_chunk = [line]
                    current_len = len(line)
                else:
                    current_chunk.append(line)
                    current_len += len(line) + 1 # +1 for newline
            if current_chunk:
                chunks.append('\n'.join(current_chunk))
        else:
            chunks = [text]

        all_chunk_characters = []
        is_first_person_any = False
        first_person_name_final = ""

        # 为了避免 chunk 提取出来的角色有遗漏，我们逐步合并到 known_characters 中
        current_known = []
        current_freqs = []
        if known_characters:
            current_known = [list(char) for char in known_characters]
            current_freqs = [{} for _ in known_characters]

        for chunk_idx, chunk_text in enumerate(chunks):
            known_names_str = ""
            if current_known:
                known_names_str = "已知角色列表（仅供参考和合并同名角色，严禁输出未在下方【文本内容】中出场的已知角色）：\n"
                for i, char_names in enumerate(current_known):
                    if char_names:
                        known_names_str += f"- 角色{i+1}: {', '.join(char_names)}\n"
                known_names_str += "\n"

            known_pov_str = ""
            if known_pov_name:
                known_pov_str = f"已知主角名：{known_pov_name}\n注意：如果文本中的第一人称'我'与已知主角名产生明显冲突（如性别、年龄不符），请忽略已知主角名，改用合适的代词或留空。\n\n"

            user_prompt = f"""请从以下文本中提取所有出场的人物角色名称。

{known_names_str}{known_pov_str}【文本内容】：
{chunk_text}

请按照规则提取角色名称，输出JSON对象。"""

            messages = [
                ChatMessage(role="system", content=CHARACTER_EXTRACTION_SYSTEM_PROMPT),
                ChatMessage(role="user", content=user_prompt)
            ]
            
            try:
                response = self.llm_client.chat_with_json_response(
                    messages=messages,
                    response_model=CharacterExtractionResponse
                )
                
                if isinstance(response, CharacterExtractionResponse):
                    if response.is_first_person:
                        is_first_person_any = True
                    if response.first_person_name.strip():
                        first_person_name_final = response.first_person_name.strip()
                        
                    result = []
                    result_freqs = []
                    for item in response.characters:
                        if isinstance(item, list):
                            filtered = self.filter_invalid_names(item)
                            if filtered:
                                deduplicated = self.deduplicate_names(filtered)
                                result.append(deduplicated)
                                result_freqs.append({name: 1 for name in deduplicated})
                    
                    if result:
                        # 汇总当前 chunk 的结果，并将其加入到当前 known_characters 供后续 chunk 参考
                        all_chunk_characters.extend(result)
                        current_known, current_freqs = self.merge_character_names(
                            current_known, result, current_freqs, result_freqs
                        )

            except Exception as e:
                print(f"  LLM角色提取失败(Chunk {chunk_idx+1}/{len(chunks)}): {e}")

        # 最后将所有 chunk 提取到的角色统一合并一次
        final_characters = []
        final_frequencies = []
        if all_chunk_characters:
            # 对于最终合并，将每一个都视为新出现的一次
            all_chunk_freqs = [{name: 1 for name in char_group} for char_group in all_chunk_characters]
            final_characters, final_frequencies = self.merge_character_names([], all_chunk_characters, [], all_chunk_freqs)

        return SegmentExtractionResult(
            characters=final_characters,
            character_frequencies=final_frequencies,
            is_first_person=is_first_person_any,
            first_person_name=first_person_name_final
        )
    
    def _review_character_grouping(self, characters: List[List[str]]) -> List[List[str]]:
        """调用LLM检查角色名称分组是否有明显归类错误"""
        if len(characters) <= 1 and all(len(c) <= 1 for c in characters):
            return characters
        
        user_prompt = f"角色名称分组：{json.dumps(characters, ensure_ascii=False)}"
        
        messages = [
            ChatMessage(role="system", content=CHARACTER_GROUPING_REVIEW_PROMPT),
            ChatMessage(role="user", content=user_prompt)
        ]
        
        try:
            response = self.llm_client.chat_with_json_response(
                messages=messages,
                response_model=CharacterGroupingReviewResponse
            )
            
            if not isinstance(response, CharacterGroupingReviewResponse):
                return characters
            
            response = response.characters
            
            reviewed = []
            for item in response:
                if isinstance(item, list):
                    filtered = self.filter_invalid_names(item)
                    if filtered:
                        reviewed.append(self.deduplicate_names(filtered))
            
            return reviewed if reviewed else characters

        except Exception as e:
            print(f"  LLM分组校验失败，使用原始结果: {e}")
            return characters

    def identify_formal_name(self, character_names: List[str]) -> Dict[str, Any]:
        if not character_names:
            return {"name": "", "alias": []}
        
        if len(character_names) == 1:
            return {"name": character_names[0], "alias": []}
        
        names_str = ", ".join(f'"{name}"' for name in character_names)
        
        user_prompt = f"""请从以下角色名称列表中选择最正式的名称作为name，其余作为alias。

角色名称列表：[{names_str}]

请输出JSON对象，包含name和alias字段。"""

        messages = [
            ChatMessage(role="system", content=FORMAL_NAME_IDENTIFICATION_SYSTEM_PROMPT),
            ChatMessage(role="user", content=user_prompt)
        ]
        
        try:
            response = self.llm_client.chat_with_json_response(
                messages=messages,
                response_model=FormalNameResponse
            )
            
            if isinstance(response, FormalNameResponse):
                name = response.name
                alias = response.alias
                
                if not isinstance(alias, list):
                    alias = []
                
                if name not in character_names:
                    name = character_names[0]
                
                alias = [a for a in alias if a in character_names and a != name]
                
                return {"name": name, "alias": alias}
            
            return {"name": character_names[0], "alias": character_names[1:]}
        
        except Exception as e:
            print(f"  LLM正式名称识别失败: {e}")
            return {"name": character_names[0], "alias": character_names[1:]}


def process_book_directory(
    book_dir: Path,
    output_dir: Path,
    extractor: CharacterExtractor,
    is_root: bool = False
) -> Dict[str, Any]:
    print(f"处理书籍目录: {book_dir.name}")
    
    segment_files = sorted(book_dir.glob("*.txt"))
    
    if not segment_files:
        print(f"  未找到分段文件")
        return {}
        
    # 确保保存到与输入相同的书籍子目录中
    if is_root:
        book_output_dir = output_dir
    else:
        book_output_dir = output_dir / book_dir.name
        
    book_output_dir.mkdir(parents=True, exist_ok=True)
    
    # segment_cache 存储每段的提取结果（包含POV信息）
    segment_cache: Dict[str, SegmentExtractionResult] = {}
    all_characters: List[List[str]] = []
    all_frequencies: List[Dict[str, int]] = []
    # 记录每个角色组连续称呼超过6个的 segment 计数，结构：{特征键(tuple) : 连续次数}
    consecutive_over_limit_counts: Dict[tuple, int] = {}
    existing_formal_map: Dict[tuple, Dict] = {}
    
    # 尝试加载已有的 characters.json 以维持上下文，避免增量处理时丢失旧数据
    characters_output = book_output_dir / "characters.json"
    if characters_output.exists():
        try:
            with open(characters_output, 'r', encoding='utf-8') as f:
                existing_formal = json.load(f)
            for item in existing_formal:
                if isinstance(item, dict) and "name" in item:
                    # 按照之前保存的逻辑重构 known_characters
                    char_group = [item["name"]] + item.get("alias", [])
                    all_characters.append(char_group)
                    
                    # 恢复频率字典（如果有保存）
                    freqs = item.get("frequencies", {})
                    if not freqs:
                        # 如果没有保存过频率，默认都给 1
                        freqs = {name: 1 for name in char_group}
                    all_frequencies.append(freqs)
                    
                    # 恢复连续计数（如果有保存）
                    consecutive_count = item.get("consecutive_over_limit", 0)
                    consecutive_over_limit_counts[tuple(sorted(char_group))] = consecutive_count
                    
                    existing_formal_map[tuple(sorted(char_group))] = item
            print(f"  已加载现有角色列表: {len(all_characters)} 个角色")
        except Exception as e:
            print(f"  加载现有角色列表失败: {e}")
    
    # POV 跟踪：记录本书已确认的主角名（称呼）
    book_pov_name: str = ""
    # 记录哪些段是第一人称但未识别主角名的，后续需要回填
    pending_pov_segments: List[str] = []
    
    for segment_file in segment_files:
        segment_char_file = book_output_dir / f"{segment_file.stem}_characters.json"
        if segment_char_file.exists():
            print(f"  跳过已存在的分段: {segment_file.name}")
            # 尝试从中提取已确认的主角名，辅助后续片段
            if not book_pov_name:
                try:
                    with open(segment_char_file, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        if data.get("is_pov") and data.get("pov_name"):
                            book_pov_name = data["pov_name"]
                except Exception:
                    pass
            continue
            
        print(f"  处理分段: {segment_file.name}")
        
        with open(segment_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        extraction_result = extractor.extract_characters_from_segment(
            text=content,
            known_characters=all_characters if all_characters else None,
            known_pov_name=book_pov_name if book_pov_name else None
        )
        
        segment_cache[segment_file.stem] = extraction_result
        
        if extraction_result.characters:
            # 第一步，仅做合并，但不执行剪枝，拿到最新的称呼列表
            all_characters, all_frequencies = extractor.merge_character_names(
                all_characters,
                extraction_result.characters,
                all_frequencies,
                extraction_result.character_frequencies,
                enable_pruning=False
            )
            
            # 第二步，检查当前合并后的每个角色称呼数量
            # 记录需要被剪枝的角色的索引
            prune_indices = set()
            new_consecutive_counts = {}
            
            for idx, char_group in enumerate(all_characters):
                group_key = tuple(sorted(char_group))
                # 检查旧的计次记录中是否有包含关系
                prev_count = 0
                # 由于 char_group 可能在本次合并中增加了新名字，特征键会变，所以需要遍历找子集或者直接根据前一次记录查找
                # 但因为 all_characters 是动态更新的，最准确的是维护一个映射或通过遍历匹配
                for old_key, count in consecutive_over_limit_counts.items():
                    # 只要旧集合是新集合的子集（或者有交集），说明是同一个角色进化来的
                    if set(old_key).intersection(set(char_group)):
                        prev_count = max(prev_count, count)
                
                if len(char_group) > 6:
                    current_count = prev_count + 1
                    if current_count >= 5:
                        # 连续5个segment超标，触发剪枝
                        prune_indices.add(idx)
                        current_count = 0 # 剪枝后重置
                    new_consecutive_counts[group_key] = current_count
                else:
                    new_consecutive_counts[group_key] = 0
            
            # 更新字典
            consecutive_over_limit_counts = new_consecutive_counts
            
            # 第三步，如果存在需要剪枝的角色，则再调用一次剪枝（传入空的新增列表，仅为了触发内部的 prune 逻辑）
            if prune_indices:
                all_characters, all_frequencies = extractor.merge_character_names(
                    all_characters,
                    [],
                    all_frequencies,
                    [],
                    enable_pruning=True,
                    prune_indices=prune_indices
                )
                
                # 剪枝后名称变了，需要更新 consecutive_over_limit_counts 中的键
                final_counts = {}
                for idx, char_group in enumerate(all_characters):
                    group_key = tuple(sorted(char_group))
                    # 尝试从之前的 new_consecutive_counts 恢复
                    count = 0
                    for old_key, old_count in consecutive_over_limit_counts.items():
                        if set(old_key).intersection(set(char_group)):
                            count = max(count, old_count)
                    final_counts[group_key] = count
                consecutive_over_limit_counts = final_counts
        
        # POV 处理
        if extraction_result.is_first_person:
            if extraction_result.first_person_name:
                # 当前段识别出了主角名
                detected_pov = extraction_result.first_person_name

                if not book_pov_name:
                    # 第一次确认主角名，回填之前未识别的段
                    book_pov_name = detected_pov
                    backfill_count = len(pending_pov_segments)
                    for pending_stem in pending_pov_segments:
                        segment_cache[pending_stem].first_person_name = book_pov_name
                    pending_pov_segments.clear()
                    print(f"    确认主角名: {book_pov_name}，已回填 {backfill_count} 段")
                else:
                    # 检查是否发生POV角色变更
                    # 需要判断detected_pov是否与book_pov_name指向同一角色
                    is_same_character = False

                    # 在all_characters中查找这两个名字是否属于同一角色组
                    detected_group = None
                    book_group = None
                    for char_group in all_characters:
                        if detected_pov in char_group:
                            detected_group = char_group
                        if book_pov_name in char_group:
                            book_group = char_group

                    # 如果两个名字在同一个角色组中，说明是同一角色的不同称呼
                    if detected_group is not None and book_group is not None and detected_group is book_group:
                        is_same_character = True

                    if is_same_character:
                        # 同一角色，保持使用已确认的名字
                        extraction_result.first_person_name = book_pov_name
                    else:
                        # POV角色发生变更
                        print(f"    检测到POV角色变更: {book_pov_name} -> {detected_pov}")
                        book_pov_name = detected_pov
                        # 清空待回填列表，因为之前的段可能是另一个POV
                        pending_pov_segments.clear()
            else:
                # 第一人称但无法识别主角名
                if book_pov_name:
                    # 已有之前确认的主角名，需要检查是否与当前文本产生逻辑冲突
                    is_consistent, suggested_pronoun = extractor.check_pov_conflict(content, book_pov_name)

                    if is_consistent:
                        # 没有冲突，继承使用之前的主角名
                        extraction_result.first_person_name = book_pov_name
                    else:
                        # 发生冲突，说明POV角色变更了
                        if suggested_pronoun:
                            # 使用建议的代词作为新的POV名字
                            print(f"    检测到POV角色变更（冲突）: {book_pov_name} -> {suggested_pronoun}")
                            book_pov_name = suggested_pronoun
                            extraction_result.first_person_name = suggested_pronoun
                            pending_pov_segments.clear()
                        else:
                            # 无法判断特征，标记为待回填
                            print(f"    检测到POV角色变更（冲突），但无法确定新POV特征")
                            book_pov_name = ""
                            pending_pov_segments.append(segment_file.stem)
                else:
                    # 标记为待回填
                    pending_pov_segments.append(segment_file.stem)
        
        print(f"    提取到 {len(extraction_result.characters)} 个角色"
              f"{', 第一人称' if extraction_result.is_first_person else ''}"
              f"{', 主角: ' + extraction_result.first_person_name if extraction_result.first_person_name else ''}")
    
    print(f"  识别正式名称...")
    formal_characters = []
    name_to_formal: Dict[str, str] = {}
    
    for i, char_names in enumerate(all_characters):
        if not char_names:
            continue
        
        cache_key = tuple(sorted(char_names))
        if cache_key in existing_formal_map:
            formal_info = existing_formal_map[cache_key]
            # 始终使用最新的频率数据
            formal_info["frequencies"] = all_frequencies[i]
            formal_info["consecutive_over_limit"] = consecutive_over_limit_counts.get(cache_key, 0)
        else:
            formal_info = extractor.identify_formal_name(char_names)
            formal_info["frequencies"] = all_frequencies[i]
            formal_info["consecutive_over_limit"] = consecutive_over_limit_counts.get(cache_key, 0)
            
        formal_characters.append(formal_info)
        
        formal_name = formal_info["name"]
        for name in char_names:
            name_to_formal[name] = formal_name
    
    characters_output = book_output_dir / "characters.json"
    with open(characters_output, 'w', encoding='utf-8') as f:
        json.dump(formal_characters, f, ensure_ascii=False, indent=2)
    print(f"  输出: {characters_output.relative_to(output_dir.parent)}")
    
    for segment_stem, seg_result in segment_cache.items():
        formal_names_for_segment = []
        for char_names in seg_result.characters:
            if char_names:
                for name in char_names:
                    formal_name = name_to_formal.get(name, name)
                    if formal_name and formal_name not in formal_names_for_segment:
                        formal_names_for_segment.append(formal_name)
        
        formal_names_for_segment = extractor.deduplicate_names(formal_names_for_segment)
        
        # 将 pov_name 转换为正式名称
        pov_formal_name = ""
        if seg_result.first_person_name:
            pov_formal_name = name_to_formal.get(seg_result.first_person_name, seg_result.first_person_name)
        
        segment_output = {
            "is_pov": seg_result.is_first_person,
            "pov_name": pov_formal_name,
            "characters": formal_names_for_segment
        }
        
        segment_char_file = book_output_dir / f"{segment_stem}_characters.json"
        with open(segment_char_file, 'w', encoding='utf-8') as f:
            json.dump(segment_output, f, ensure_ascii=False, indent=2)
        print(f"  输出: {segment_char_file.relative_to(output_dir.parent)}")
    
    return {
        "book_dir": str(book_dir),
        "total_characters": len(formal_characters),
        "segments_processed": len(segment_cache)
    }

def main():
    parser = argparse.ArgumentParser(
        description='使用LLM从场景分段中提取角色名称'
    )
    parser.add_argument(
        '--input', '-i',
        required=True,
        help='输入目录路径（包含书籍子目录，每个子目录包含场景分段txt文件）'
    )
    parser.add_argument(
        '--output', '-o',
        required=True,
        help='输出目录路径（角色文件将直接保存在此目录）'
    )
    
    args = parser.parse_args()
    
    input_path = Path(args.input)
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    llm_client = LLMClient()
    extractor = CharacterExtractor(llm_client=llm_client)
    
    book_dirs = [d for d in input_path.iterdir() if d.is_dir() and d != output_dir]
    
    total_books = 0
    total_characters = 0
    
    for book_dir in book_dirs:
        try:
            result = process_book_directory(book_dir, output_dir, extractor, is_root=False)
            if result:
                total_books += 1
                total_characters += result.get("total_characters", 0)
                print(f"  完成: {result.get('total_characters', 0)} 个角色, {result.get('segments_processed', 0)} 个分段")
        except Exception as e:
            print(f"  处理失败: {e}")
            import traceback
            traceback.print_exc()
            
    if list(input_path.glob("*.txt")):
        try:
            print(f"在 {input_path.name} 根目录下发现 txt 文件，将其作为单独的书籍目录处理")
            result = process_book_directory(input_path, output_dir, extractor, is_root=True)
            if result:
                total_books += 1
                total_characters += result.get("total_characters", 0)
                print(f"  完成: {result.get('total_characters', 0)} 个角色, {result.get('segments_processed', 0)} 个分段")
        except Exception as e:
            print(f"  处理根目录失败: {e}")
            import traceback
            traceback.print_exc()
    
    print(f"\n处理完成！")
    print(f"  处理书籍数: {total_books}")
    print(f"  总角色数: {total_characters}")
    print(f"  输出目录: {output_dir}")


if __name__ == '__main__':
    main()
