import argparse
import json
from pathlib import Path
from typing import List, Dict, Any, Optional
import traceback

from pydantic import BaseModel, Field

from ..utils.llm_client import LLMClient, ChatMessage

class CharacterFact(BaseModel):
    name: str = Field(description="角色的本名")
    facts: List[str] = Field(description="该角色在该段落中的事实表现列表，包括但不限于关键决定、性格特征、关系变化等")
    representative_quote: str = Field(description="该角色在该段落中最能代表其角色特点的一句原文发言，如果该角色在段落中没有发言则为空字符串")

class SceneContextResponse(BaseModel):
    environment_facts: List[str] = Field(description="提取的环境/世界观设定（人物行为和对话之外的客观场景、环境特点、引起的客观变化等）")
    character_facts: List[CharacterFact] = Field(description="提取的角色设定列表，每一个出场角色对应一个对象")
    summary: str = Field(description="这段文字的总结，包含关键信息的基础上尽量简洁，不要运用过多的修辞手法和感受描述，记录fact即可")

SYSTEM_PROMPT = f"""你是一个专业的剧情分析助手，擅长从小说片段中提取客观事实、环境设定以及角色表现。

你的任务：
根据提供的出场角色列表和段落原文，提取以下信息并以JSON格式返回：
1. environment_facts (环境/世界观设定)：关注人物行为和对话之外的内容，如什么样的场景，环境有什么特点，是否因为人物的行为产生了客观变化，以及在世界观层面是否有什么独特的设定。
2. character_facts (角色表现设定)：针对出场角色，提取他们在该段落中的表现。例如：该角色做出了什么关键决定，展现了什么性格特征，与别人的关系是否有发生什么变化。同时提取该角色最能代表其角色特点的一句原文发言（直接引用原文，如无发言则留空）。为每一个角色建立一条记录，包含角色的本名、对应的表现设定列表和代表性发言。
3. summary (段落总结)：这段文字的客观总结，包含关键信息的基础上尽量简洁，不要运用过多的修辞手法和感受描述，记录fact即可。

请严格保证客观性，不需要过多修辞。

你必须输出以下JSON结构的数据：
{SceneContextResponse.model_json_schema()}
"""


class SceneContextExtractor:
    def __init__(self, llm_client: Optional[LLMClient] = None):
        self.llm_client = llm_client or LLMClient()

    def extract_context(self, characters_str: str, scene_text: str, pov_name: Optional[str] = None) -> Optional[SceneContextResponse]:
        pov_hint = ""
        if pov_name:
            pov_hint = f"\n\n注意：本段落以第一人称视角书写，其中的\"我\"指的是\"{pov_name}\"。请在角色表现设定中也为\"{pov_name}\"建立记录。"

        user_prompt = f"""请分析以下小说段落并提取信息。{pov_hint}

【出场角色列表】
{characters_str}

【段落原文】
{scene_text}"""

        messages = [
            ChatMessage(role="system", content=SYSTEM_PROMPT),
            ChatMessage(role="user", content=user_prompt)
        ]

        try:
            response = self.llm_client.chat_with_json_response(
                messages=messages,
                response_model=SceneContextResponse
            )
            return response
        except Exception as e:
            print(f"  LLM提炼失败: {e}")
            return None


def process_book_directory(
    book_dir: Path,
    output_dir: Path,
    extractor: SceneContextExtractor,
    is_root: bool = False
) -> int:
    print(f"处理书籍目录: {book_dir.name}")
    
    # 加载整本书的角色字典 (characters.json)
    book_characters_file = book_dir / "characters.json"
    character_aliases_map = {}
    if book_characters_file.exists():
        try:
            with open(book_characters_file, 'r', encoding='utf-8') as f:
                char_data = json.load(f)
                for char in char_data:
                    name = char.get("name")
                    aliases = char.get("alias", [])
                    if name:
                        character_aliases_map[name] = aliases
        except Exception as e:
            print(f"  读取 characters.json 失败: {e}")
    else:
        print(f"  未找到 characters.json，将仅使用分段角色列表")

    # 遍历所有场景文本文件
    scene_files = sorted(book_dir.glob("*.txt"))
    processed_count = 0
    
    # 如果是直接在根目录找到的txt文件，不要再多创建一层同名目录
    if is_root:
        book_output_dir = output_dir
    else:
        book_output_dir = output_dir / book_dir.name
    
    book_output_dir.mkdir(parents=True, exist_ok=True)

    for scene_file in scene_files:
        base_name = scene_file.stem
        segment_char_file = book_dir / f"{base_name}_characters.json"
        facts_output_file = book_output_dir / f"{base_name}_facts.json"
        
        # 如果已经处理过，可以选择跳过
        if facts_output_file.exists():
            print(f"  跳过已处理片段: {base_name}")
            continue

        # 读取场景原文
        with open(scene_file, 'r', encoding='utf-8') as f:
            scene_text = f.read().strip()
            
        if not scene_text:
            continue

        # 读取分段角色列表（新格式：{"is_pov": bool, "pov_name": str, "characters": [...]})
        segment_characters = []
        pov_name = None
        if segment_char_file.exists():
            try:
                with open(segment_char_file, 'r', encoding='utf-8') as f:
                    char_data = json.load(f)
                if isinstance(char_data, dict):
                    segment_characters = char_data.get("characters", [])
                    if char_data.get("is_pov") and char_data.get("pov_name"):
                        pov_name = char_data["pov_name"]
                        # 将第一人称主角加入出场角色列表（如果尚未包含）
                        if pov_name not in segment_characters:
                            segment_characters.insert(0, pov_name)
                else:
                    # 兼容旧格式（纯列表）
                    segment_characters = char_data
            except Exception as e:
                print(f"  读取 {segment_char_file.name} 失败: {e}")
        else:
            print(f"  跳过: 未找到分段角色列表文件 {segment_char_file.name}")
            continue
        
        # 组装出场角色字符串： 本名（别称：别名A、别名B……）
        char_str_list = []
        for char_name in segment_characters:
            aliases = character_aliases_map.get(char_name, [])
            if aliases:
                aliases_str = "、".join(aliases)
                char_str_list.append(f"{char_name}（别称：{aliases_str}）")
            else:
                char_str_list.append(char_name)
        
        characters_str = "\n".join(char_str_list) if char_str_list else "无明确出场角色"
        
        print(f"  处理片段: {base_name} ({len(scene_text)} 字符)")
        
        # 提取上下文
        result = extractor.extract_context(characters_str, scene_text, pov_name=pov_name)
        if result:
            # 保存为JSON
            with open(facts_output_file, 'w', encoding='utf-8') as f:
                json.dump(result.model_dump(), f, ensure_ascii=False, indent=2)
            processed_count += 1
            print(f"    成功提取并保存至: {facts_output_file.name}")
        else:
            print(f"    提取失败: {base_name}")

    return processed_count


def main():
    parser = argparse.ArgumentParser(
        description='使用LLM从场景段落中提取事实与上下文设定'
    )
    parser.add_argument(
        '--input', '-i',
        required=True,
        help='输入目录路径（包含按书名划分的子目录）'
    )
    parser.add_argument(
        '--output', '-o',
        required=True,
        help='输出目录路径（通常与输入目录相同）'
    )
    
    args = parser.parse_args()
    
    input_dir = Path(args.input)
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    if not input_dir.exists() or not input_dir.is_dir():
        print(f"错误: 输入目录 {input_dir} 不存在或不是一个目录")
        return
        
    llm_client = LLMClient()
    extractor = SceneContextExtractor(llm_client=llm_client)
    
    total_processed = 0
    books_processed = 0
    
    # 遍历书籍子目录（或者直接在当前目录处理）
    # 由于 1_1_scene_segmentation 可能产生的情况是：
    # 1. 产生子目录（如 3026.novel/3026.novel_000.txt）
    # 2. 或者直接在当前目录下输出文件
    # 我们兼容这两种情况
    
    # 先处理可能存在的子目录
    for item in input_dir.iterdir():
        if item.is_dir() and item != output_dir:
            try:
                count = process_book_directory(item, output_dir, extractor, is_root=False)
                total_processed += count
                books_processed += 1
            except Exception as e:
                print(f"处理目录 {item.name} 时出错: {e}")
                traceback.print_exc()

    # 如果输入目录下直接就有 txt 文件，也把它当作一个书籍目录处理
    if list(input_dir.glob("*.txt")):
        print(f"在 {input_dir.name} 根目录下发现 txt 文件，将其作为单独的书籍目录处理")
        try:
            count = process_book_directory(input_dir, output_dir, extractor, is_root=True)
            total_processed += count
            books_processed += 1
        except Exception as e:
            print(f"处理根目录 {input_dir.name} 时出错: {e}")
            traceback.print_exc()

    print(f"\n全部处理完成！")
    print(f"  处理书籍目录数: {books_processed}")
    print(f"  成功提炼场景片段数: {total_processed}")
    print(f"  输出目录: {output_dir}")


if __name__ == '__main__':
    main()
