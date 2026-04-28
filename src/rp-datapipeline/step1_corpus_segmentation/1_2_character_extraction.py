import argparse
import json
from pathlib import Path
from typing import List, Optional, Dict, Any, Set

from pydantic import BaseModel

from ..utils.llm_client import LLMClient, ChatMessage


CHARACTER_EXTRACTION_SYSTEM_PROMPT = """从小说文本中提取人物角色名称，输出包含characters字段的JSON对象，characters是二维数组，每个子数组是一个角色。

核心规则：
1. 输出当前文本中出现的所有角色称呼（不限于新称呼）。
2. 根据上下文语义判断名称归属。同一角色的不同称呼（姓名、姓氏、名字、外号、绰号等）放入同一子数组，不同角色放入不同子数组。注意：仅仅同时出现在文本中不代表是同一角色，必须有明确的语义关联。
3. 如果某角色已在已知列表中，输出时必须包含至少一个已知称呼，以便代码合并。
4. 排除：人称代词、模糊描述、泛指、单独的亲属称谓、单独的职业。与具体名字结合的除外（如"张医生"保留）。

示例1：
文本："冬马、美来和浅宫美来一起出现了。"
分析："美来"是"浅宫美来"的一部分→同一角色。"冬马"与"浅宫美来"无关联→不同角色。
输出：{"characters": [["冬马"], ["浅宫美来", "美来"]]}

示例2：
已知角色：[["浅宫美来", "美来"], ["冬马"], ["七濑春辉"]]
文本："浅宫和冬马走进教室，七濑正在看书。"
分析：三人都出现了。"浅宫"是"浅宫美来"的新称呼→附带已知称呼。"冬马"本身是已知称呼→直接输出。"七濑"是"七濑春辉"的新称呼→附带已知称呼。
输出：{"characters": [["浅宫美来", "浅宫"], ["冬马"], ["七濑春辉", "七濑"]]}

示例3：
文本："铁拳张三走进擂台，对手李四已经等候多时。"
分析："铁拳"是"张三"的绰号→同一角色。"李四"是不同角色。
输出：{"characters": [["张三", "铁拳"], ["李四"]]}

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
从给定的角色名称列表中，选择最正式的名称作为该角色的主要名称（name），其余作为别名（alias）。

判断正式程度的规则：
1. 完整姓名 > 姓氏+称呼 > 昵称/别名 > 称号
   - 例如："张三" > "张先生" > "小张" > "三哥"
   
2. 如果只有一个名称，那么它就是正式名称

输出要求：
- 输出JSON对象，包含两个字段：
  - "name": 字符串，最正式的名称
  - "alias": 字符串数组，其余的名称（按出现顺序排列，不包含name）

示例：

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


class CharacterGroupingReviewResponse(BaseModel):
    characters: List[List[str]]


class FormalNameResponse(BaseModel):
    name: str
    alias: List[str]


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
        new_characters: List[List[str]]
    ) -> List[List[str]]:
        merged = [list(char) for char in existing_characters]
        
        for new_char in new_characters:
            if not new_char:
                continue
            
            filtered_new = self.filter_invalid_names(new_char)
            if not filtered_new:
                continue
            
            deduplicated_new = self.deduplicate_names(filtered_new)
            if not deduplicated_new:
                continue
            
            found = False
            for i, existing_char in enumerate(merged):
                if self._has_name_overlap(existing_char, deduplicated_new):
                    all_names = existing_char + deduplicated_new
                    merged[i] = self.deduplicate_names(all_names)
                    found = True
                    break
            
            if not found:
                merged.append(deduplicated_new)
        
        # 二次合并：检查merged内部是否有因新增名称产生的跨组包含关系
        changed = True
        while changed:
            changed = False
            for i in range(len(merged)):
                for j in range(i + 1, len(merged)):
                    if self._has_name_overlap(merged[i], merged[j]):
                        merged[i] = self.deduplicate_names(merged[i] + merged[j])
                        merged.pop(j)
                        changed = True
                        break
                if changed:
                    break
        
        return merged
    
    def extract_characters_from_segment(
        self,
        text: str,
        known_characters: Optional[List[List[str]]] = None
    ) -> List[List[str]]:
        known_names_str = ""
        if known_characters:
            known_names_str = "已出现的角色名称（每个子数组代表同一个角色的不同称呼）：\n"
            for i, char_names in enumerate(known_characters):
                if char_names:
                    known_names_str += f"- 角色{i+1}: {', '.join(char_names)}\n"
            known_names_str += "\n"
        
        user_prompt = f"""请从以下文本中提取所有出现的人物角色名称。

{known_names_str}文本内容：
{text}

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
            
            if not isinstance(response, CharacterExtractionResponse):
                return []
            
            response = response.characters
            
            result = []
            for item in response:
                if isinstance(item, list):
                    filtered = self.filter_invalid_names(item)
                    if filtered:
                        deduplicated = self.deduplicate_names(filtered)
                        result.append(deduplicated)
            
            # if result:
            #     result = self._review_character_grouping(result)
            
            return result
        
        except Exception as e:
            print(f"  LLM角色提取失败: {e}")
            return []
    
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
    extractor: CharacterExtractor
) -> Dict[str, Any]:
    print(f"处理书籍目录: {book_dir.name}")
    
    segment_files = sorted(book_dir.glob("*.txt"))
    
    if not segment_files:
        print(f"  未找到分段文件")
        return {}
    
    segment_cache: Dict[str, List[List[str]]] = {}
    all_characters: List[List[str]] = []
    
    for segment_file in segment_files:
        print(f"  处理分段: {segment_file.name}")
        
        with open(segment_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        segment_characters = extractor.extract_characters_from_segment(
            text=content,
            known_characters=all_characters if all_characters else None
        )
        
        segment_cache[segment_file.stem] = segment_characters
        
        if segment_characters:
            all_characters = extractor.merge_character_names(all_characters, segment_characters)
        
        print(f"    提取到 {len(segment_characters)} 个角色")
    
    print(f"  识别正式名称...")
    formal_characters = []
    name_to_formal: Dict[str, str] = {}
    
    for char_names in all_characters:
        if not char_names:
            continue
        
        formal_info = extractor.identify_formal_name(char_names)
        formal_characters.append(formal_info)
        
        formal_name = formal_info["name"]
        for name in char_names:
            name_to_formal[name] = formal_name
    
    characters_output = output_dir / "characters.json"
    with open(characters_output, 'w', encoding='utf-8') as f:
        json.dump(formal_characters, f, ensure_ascii=False, indent=2)
    print(f"  输出: {characters_output.relative_to(output_dir.parent)}")
    
    for segment_stem, segment_chars in segment_cache.items():
        formal_names_for_segment = []
        for char_names in segment_chars:
            if char_names:
                for name in char_names:
                    formal_name = name_to_formal.get(name, name)
                    if formal_name and formal_name not in formal_names_for_segment:
                        formal_names_for_segment.append(formal_name)
        
        formal_names_for_segment = extractor.deduplicate_names(formal_names_for_segment)
        
        segment_char_file = output_dir / f"{segment_stem}_characters.json"
        with open(segment_char_file, 'w', encoding='utf-8') as f:
            json.dump(formal_names_for_segment, f, ensure_ascii=False, indent=2)
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
    
    book_dirs = [d for d in input_path.iterdir() if d.is_dir()]
    
    if not book_dirs:
        if any(input_path.glob("*.txt")):
            book_dirs = [input_path]
        else:
            print(f"未找到任何书籍目录或txt文件: {input_path}")
            return
    
    total_books = 0
    total_characters = 0
    
    for book_dir in book_dirs:
        try:
            result = process_book_directory(book_dir, output_dir, extractor)
            if result:
                total_books += 1
                total_characters += result.get("total_characters", 0)
                print(f"  完成: {result.get('total_characters', 0)} 个角色, {result.get('segments_processed', 0)} 个分段")
        except Exception as e:
            print(f"  处理失败: {e}")
            import traceback
            traceback.print_exc()
    
    print(f"\n处理完成！")
    print(f"  处理书籍数: {total_books}")
    print(f"  总角色数: {total_characters}")
    print(f"  输出目录: {output_dir}")


if __name__ == '__main__':
    main()
