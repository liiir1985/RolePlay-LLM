import argparse
import json
import re
from pathlib import Path
from typing import List, Optional
import traceback

from ..utils.llm_client import LLMClient, ChatMessage


# ── System prompts ──

WORLD_SETTINGS_SYSTEM_PROMPT = """你是一个专业的轻小说/网络小说分析助手。

你将收到一部作品按顺序排列的各段落摘要。请根据这些摘要，提取该作品的世界观设定信息，直接以Markdown格式输出。

需要涵盖的信息点（但标题措辞和组织方式请自由发挥，不要使用固定模板）：
1. 基础简介：概述作品的基本背景，包括时代、世界类型、核心冲突等
2. 特殊概念和专有名词解释：作品中独特的概念、术语、力量体系、组织机构等。只提取作品特有的设定，不要包含常见的通用概念
3. 重要地点解释：故事中频繁出现或对剧情有重要影响的场景/地点及其描述

要求：
- 直接输出Markdown格式的设定文档，不要输出JSON
- 各信息点的标题命名请随机化，不要每次都使用一样的措辞
- 格式灵活自然，可以用标题、列表、段落等任意Markdown元素
- 保持客观，基于提供的摘要内容进行提取，不要臆测
- 不要包含具体角色的设定、性格、经历等信息，只关注世界观层面的客观设定
"""

CHARACTER_PROFILE_SYSTEM_PROMPT = """你是一个专业的角色分析助手。

你将收到一个角色在作品各场景中的行为表现、事实记录和代表性台词。请根据这些信息，提取该角色的人物设定，直接以Markdown格式输出。

需要涵盖的信息点（但标题措辞和组织方式请自由发挥，不要使用固定模板）：
1. 姓名
2. 基础信息：核心身份（职业、身份、立场等）、视觉印象/年龄
3. 性格内核：性格关键词、核心设定、行为习惯、道德基准
4. 语言习惯：语调风格、口癖、对他人的称谓方式
5. 人际关系：与其他主要角色的关系
6. 人物弧光：角色的成长变化特质，关注性格和能力的演变方向，不要写具体事件
7. 典型台词：从提供的各场景"典型台词"中，挑选10句最能体现该角色性格和特点的台词。必须从提供的台词中选取，不要自行编造，不要增加任何评价或者解析和任何其他内容，原封不动输出

要求：
- 直接输出Markdown格式的角色设定文档，不要输出JSON
- 各信息点的标题命名请随机化，不要每次都使用一样的措辞
- 格式灵活自然，可以用标题、列表、段落等任意Markdown元素
- 只记录客观设定，不要加入任何主观评价、解读或分析性语言
- 人物弧光关注成长特质，不要描述具体情节事件
- 典型台词必须从提供的原文台词中选取，不要增加任何评价或者解析和任何其他内容，原封不动输出
"""


# ── Core logic ──

class WorldCharacterProfileExtractor:
    def __init__(self, llm_client: Optional[LLMClient] = None):
        self.llm_client = llm_client or LLMClient()

    def extract_world_settings(self, summaries_text: str) -> Optional[str]:
        user_prompt = f"""请根据以下按顺序排列的段落摘要，提取作品的世界观设定。

【段落摘要】
{summaries_text}"""

        messages = [
            ChatMessage(role="system", content=WORLD_SETTINGS_SYSTEM_PROMPT),
            ChatMessage(role="user", content=user_prompt)
        ]

        try:
            response = self.llm_client.chat_completion(messages=messages)
            return response.content.strip()
        except Exception as e:
            print(f"  世界观设定提取失败: {e}")
            return None

    def extract_character_profile(
        self,
        scenes_text: str
    ) -> Optional[str]:
        user_prompt = f"""请根据以下角色在各场景中的表现信息，提取该角色的全面人物设定。

{scenes_text}"""

        messages = [
            ChatMessage(role="system", content=CHARACTER_PROFILE_SYSTEM_PROMPT),
            ChatMessage(role="user", content=user_prompt)
        ]

        try:
            response = self.llm_client.chat_completion(messages=messages)
            return response.content.strip()
        except Exception as e:
            print(f"  角色设定提取失败: {e}")
            return None


def get_segment_stems(book_dir: Path) -> List[str]:
    """获取所有有对应 .txt 文件的分段 stem，按文件名排序。"""
    txt_files = sorted(book_dir.glob("*.txt"))
    stems = []
    for txt_file in txt_files:
        stem = txt_file.stem
        char_file = book_dir / f"{stem}_characters.json"
        if char_file.exists():
            stems.append(stem)
    return stems


def load_name_alias_map(book_dir: Path) -> dict:
    """从 characters.json 加载 name -> alias 列表的映射。"""
    characters_file = book_dir / "characters.json"
    name_alias_map = {}
    if characters_file.exists():
        try:
            with open(characters_file, 'r', encoding='utf-8') as f:
                char_data = json.load(f)
            for char in char_data:
                name = char.get("name", "")
                if isinstance(name, str):
                    name = name.strip()
                aliases = char.get("alias", [])
                if isinstance(aliases, list):
                    aliases = [a.strip() for a in aliases if isinstance(a, str) and a.strip()]
                if name:
                    name_alias_map[name] = aliases
        except Exception as e:
            print(f"  读取 characters.json 失败: {e}")
    return name_alias_map


def count_character_appearances(book_dir: Path, segment_stems: List[str]) -> dict:
    """统计每个角色出现在多少个分段中。返回 {角色名: 出现次数}。"""
    appearance_count = {}
    for stem in segment_stems:
        char_file = book_dir / f"{stem}_characters.json"
        if not char_file.exists():
            continue
        try:
            with open(char_file, 'r', encoding='utf-8') as f:
                char_data = json.load(f)
            characters = char_data.get("characters", []) if isinstance(char_data, dict) else []
            unique_chars = set(name.strip() for name in characters if isinstance(name, str) and name.strip())
            for name in unique_chars:
                appearance_count[name] = appearance_count.get(name, 0) + 1
        except Exception as e:
            print(f"  读取 {char_file.name} 失败: {e}")
    return appearance_count


def filter_main_characters(appearance_count: dict, total_segments: int, min_appearance_pct: float) -> List[str]:
    """根据出场段落百分比筛选主要角色，返回按出场次数降序排列的角色列表。"""
    min_appearances = max(1, int(total_segments * min_appearance_pct / 100))
    main_chars = [
        name for name, count in appearance_count.items()
        if count >= min_appearances
    ]
    main_chars.sort(key=lambda n: appearance_count[n], reverse=True)
    return main_chars, min_appearances


def collect_summaries(book_dir: Path, segment_stems: List[str]) -> str:
    """按顺序收集所有 facts 文件中的 summary，拼接为文本。"""
    summaries = []
    for stem in segment_stems:
        facts_file = book_dir / f"{stem}_facts.json"
        if not facts_file.exists():
            continue
        try:
            with open(facts_file, 'r', encoding='utf-8') as f:
                facts_data = json.load(f)
            summary = facts_data.get("summary", "")
            if summary:
                summaries.append(summary)
        except Exception as e:
            print(f"  读取 {facts_file.name} 失败: {e}")
    return "\n".join(summaries)


def build_character_scenes_text(
    book_dir: Path,
    segment_stems: List[str],
    character_name: str,
    aliases: List[str],
    other_main_characters: List[str]
) -> str:
    """为指定角色构建场景输入文本。"""
    alias_str = "，".join(aliases) if aliases else "无"
    other_chars_str = "，".join(other_main_characters) if other_main_characters else "无"

    header = f"角色名：{character_name}，别称：{alias_str}\n"
    header += f"其他主要角色：{other_chars_str}\n"

    scene_blocks = []
    scene_index = 0

    for stem in segment_stems:
        facts_file = book_dir / f"{stem}_facts.json"
        if not facts_file.exists():
            continue
        try:
            with open(facts_file, 'r', encoding='utf-8') as f:
                facts_data = json.load(f)
        except Exception:
            continue

        # 查找角色是否出现在 character_facts 中
        character_facts_list = facts_data.get("character_facts", [])
        char_entry = None
        for cf in character_facts_list:
            cf_name = cf.get("name", "")
            if isinstance(cf_name, str) and cf_name.strip() == character_name:
                char_entry = cf
                break

        if char_entry is None:
            continue

        scene_index += 1
        env_facts = facts_data.get("environment_facts", [])
        char_facts = char_entry.get("facts", [])
        representative_quote = char_entry.get("representative_quote", "")

        block_lines = [f"\nScene {scene_index}:"]
        block_lines.append("环境：")
        for ef in env_facts:
            block_lines.append(f"-{ef}")
        block_lines.append("")
        block_lines.append("行为：")
        for cf in char_facts:
            block_lines.append(f"-{cf}")

        if representative_quote:
            block_lines.append("")
            block_lines.append(f"典型台词：{representative_quote}")

        scene_blocks.append("\n".join(block_lines))

    if not scene_blocks:
        return ""

    return header + "\n".join(scene_blocks)


def process_book_directory(
    book_dir: Path,
    output_dir: Path,
    extractor: WorldCharacterProfileExtractor,
    min_appearance_pct: float,
    is_root: bool = False
) -> int:
    print(f"\n处理书籍目录: {book_dir.name}")

    if is_root:
        book_output_dir = output_dir
    else:
        book_output_dir = output_dir / book_dir.name

    book_output_dir.mkdir(parents=True, exist_ok=True)

    # 获取分段 stem 列表
    segment_stems = get_segment_stems(book_dir)
    if not segment_stems:
        print(f"  未找到分段文件，跳过")
        return 0

    # 加载角色名称映射
    name_alias_map = load_name_alias_map(book_dir)

    # ── 1. 主要角色筛选 ──
    print(f"  统计角色出场次数...")
    appearance_count = count_character_appearances(book_dir, segment_stems)
    total_segments = len(segment_stems)
    main_characters, min_appearances = filter_main_characters(appearance_count, total_segments, min_appearance_pct)

    filtered_characters = [
        name for name in appearance_count
        if name not in main_characters
    ]

    print(f"  主要角色 (出场≥{min_appearances}段, 即≥{min_appearance_pct}%的{total_segments}段):")
    for name in main_characters:
        aliases = name_alias_map.get(name, [])
        alias_info = f" (别称: {', '.join(aliases)})" if aliases else ""
        print(f"    - {name}{alias_info} [{appearance_count[name]}段]")

    if filtered_characters:
        print(f"  过滤掉的角色:")
        for name in filtered_characters:
            print(f"    - {name} [{appearance_count[name]}段]")

    # ── 2. 世界观设定提取 ──
    ws_output_file = book_output_dir / "world_settings.md"
    if ws_output_file.exists():
        print(f"  跳过世界观设定: world_settings.md 已存在")
    else:
        print(f"  提取世界观设定...")
        summaries_text = collect_summaries(book_dir, segment_stems)
        if summaries_text:
            ws_result = extractor.extract_world_settings(summaries_text)
            if ws_result:
                with open(ws_output_file, 'w', encoding='utf-8') as f:
                    f.write(ws_result)
                print(f"    保存至: {ws_output_file.name}")
            else:
                print(f"    世界观设定提取失败")
        else:
            print(f"    无摘要数据可用于世界观提取")

    # ── 3. 角色设定提取 ──
    processed_characters = 0
    for char_name in main_characters:
        safe_name = re.sub(r'[\\/:*?"<>|]', '_', char_name)
        cp_output_file = book_output_dir / f"{safe_name}.md"
        if cp_output_file.exists():
            print(f"  跳过角色设定: {char_name} ({safe_name}.md 已存在)")
            processed_characters += 1
            continue

        print(f"  提取角色设定: {char_name}")
        aliases = name_alias_map.get(char_name, [])
        other_mains = [n for n in main_characters if n != char_name]

        scenes_text = build_character_scenes_text(
            book_dir, segment_stems, char_name, aliases, other_mains
        )

        if not scenes_text:
            print(f"    无场景数据，跳过")
            continue

        cp_result = extractor.extract_character_profile(scenes_text=scenes_text)

        if cp_result:
            with open(cp_output_file, 'w', encoding='utf-8') as f:
                f.write(cp_result)
            processed_characters += 1
            print(f"    保存至: {cp_output_file.name}")
        else:
            print(f"    角色设定提取失败: {char_name}")

    print(f"  完成: 世界观设定 + {processed_characters} 个角色设定")
    return processed_characters


def main():
    parser = argparse.ArgumentParser(description='提取世界观设定与主要角色设定')
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
    parser.add_argument(
        '--min-appearance-pct',
        type=float,
        default=20,
        help='主要角色最少出场段落百分比（默认：20）'
    )

    args = parser.parse_args()

    input_dir = Path(args.input)
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    if not input_dir.exists() or not input_dir.is_dir():
        print(f"错误: 输入目录 {input_dir} 不存在或不是一个目录")
        return

    llm_client = LLMClient()
    extractor = WorldCharacterProfileExtractor(llm_client=llm_client)

    total_characters = 0
    books_processed = 0

    # 先处理子目录
    for item in sorted(input_dir.iterdir()):
        if item.is_dir() and item != output_dir:
            try:
                count = process_book_directory(item, output_dir, extractor, args.min_appearance_pct, is_root=False)
                total_characters += count
                books_processed += 1
            except Exception as e:
                print(f"处理目录 {item.name} 时出错: {e}")
                traceback.print_exc()

    # 如果输入目录下直接有 txt 文件，也当作一个书籍目录处理
    if list(input_dir.glob("*.txt")):
        print(f"在 {input_dir.name} 根目录下发现 txt 文件，将其作为单独的书籍目录处理")
        try:
            count = process_book_directory(input_dir, output_dir, extractor, args.min_appearance_pct, is_root=True)
            total_characters += count
            books_processed += 1
        except Exception as e:
            print(f"处理根目录 {input_dir.name} 时出错: {e}")
            traceback.print_exc()

    print(f"\n全部处理完成！")
    print(f"  处理书籍目录数: {books_processed}")
    print(f"  成功提取角色设定数: {total_characters}")
    print(f"  输出目录: {output_dir}")


if __name__ == '__main__':
    main()
