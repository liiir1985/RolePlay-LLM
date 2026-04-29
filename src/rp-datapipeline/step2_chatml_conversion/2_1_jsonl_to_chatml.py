import argparse
import json
import random
import re
from pathlib import Path
from typing import List, Optional, Dict, Any, Tuple
import traceback

from pydantic import BaseModel, Field

from ..utils.llm_client import LLMClient, ChatMessage


# ── Pydantic Models ──

class TaskDescriptionResponse(BaseModel):
    task_description: str = Field(description="生成的角色扮演任务描述")


class SummaryResponse(BaseModel):
    summary: str = Field(description="总结后的文本，不超过500字符")


# ── System Prompts ──

TASK_DESCRIPTION_SYSTEM_PROMPT = """你是一个角色扮演任务描述生成器。

你的任务：
根据提供的信息，生成一个随机化的角色扮演任务描述。

要求：
1. 每次生成的描述措辞要有所不同，不要使用固定模板
2. 必须包含以下核心信息：
   - 明确说明：**用户（对话中的user）扮演的角色是{用户角色}**
   - 明确说明：**AI（对话中的assistant/你）扮演除了{用户角色}以外的所有角色**
   - 明确说明：**AI需要负责剧情的推进**
   - 说明使用第一人称还是第三人称书写
3. **重要警告**：绝对不能搞反角色分配！
   - 错误示例："你将化身为{用户角色}"（这是错误的！AI不应该扮演用户角色）
   - 错误示例："我将扮演其他角色"（这是错误的！用户不应该扮演其他角色）
   - 正确示例："用户扮演{用户角色}，你扮演其他角色"
4. 输出JSON格式，包含task_description字段

正确格式示例（但措辞要随机变化）：
"你是一个专业的角色扮演专家，请根据给定的世界观和角色设定，进行角色扮演。用户扮演的角色为{用户角色}，你将扮演除了{用户角色}以外的所有角色，并负责剧情的推进。请以{人称}进行书写。"
"""

REASONING_CONTENT_SYSTEM_PROMPT = """你是一个角色扮演思考过程分析助手。

你的任务：
根据提供的对话历史和目标回应，模拟角色从历史对话推导出目标回应的完整思考过程。

思考顺序：
1. 回应角色判断：
   - 首先思考："根据对话历史和剧情发展，接下来应该让谁做出回应？"
   - 分析当前对话的语境，判断哪个角色应该接话
   - 得出结论：应该由哪个角色做出回应

2. 环境状况分析：
   - 核心动机对齐："根据全局档案，该角色的终极目标是什么？在当前的具体场景下，他的短期目的是什么？"
   - 人设约束检查："这个角色绝对不能做什么？绝对不能说什么样的话？"

3. 局势与信息差分析：
   - "当前对话进展到哪一步了？对方抛出了什么信息？有什么是对方不知道、但该角色知道的？"

4. 行动策略制定：
   - "为了实现上述目标并维持人设，该角色接下来应该采取什么战术（转移话题、施压、示弱）？应该用什么语气？"
   - "该角色应该表达什么核心意思？"

5. 角色第一视角思考（对即将发言的角色）：
   - 瞬时情绪反应："面对刚才发生的事情（对方的话语、动作），{角色本名}心里的第一感觉是什么？"
   - 未说出口的潜台词："{角色本名}心里真正在盘算什么？有什么真相或抱怨是{角色本名}现在不能直接说出来的？"
   - 理智与情感的冲突："{角色本名}本能想怎么做？但为了大局，{角色本名}不得不怎么做？"

要求：
1. 直接输出Markdown格式的思考过程，不要输出JSON
2. 思考过程的标题和组织方式可以自由发挥，不要使用固定模板
3. 要深入分析角色的内心活动，不要只是表面描述
4. 格式为Markdown，可以使用标题、列表、段落等任意元素
5. **重要**：思考过程中禁止使用"我"、"你"、"他"、"她"等人称代词来指代任何角色，必须使用角色的本名。例如：不要说"我心里想..."，而要说"张三心里想..."；不要说"他感到..."，而要说"李四感到..."
6. **重要**：思考过程应该描述"如何推导出这个目标回应"，而不是直接引用或复述目标回应的内容。例如：不要说"所以张三说'你好'"，而是要说"张三观察到...，因此决定...，意图是..."
7. **绝对禁止**：不要添加任何开场白或确认性话语。例如：不要说"好的，我来分析一下"、"让我们一步步推导"、"我将按照以下步骤思考"等。直接开始输出思考过程的内容。
8. 生成的思考过程要少于1500个中文字或英文词
9. 思考的过程可以从英语和简体中文中选择一种
10. 直接输出最终思考过程，不要应答我的要求，不要添加任何开场白
"""

SUMMARY_SYSTEM_PROMPT = """你是一个专业的文本摘要助手。

你的任务：
将提供的长文本总结为不超过500字符的摘要。

要求：
1. 保持原文的关键信息和时间顺序
2. 不要添加原文没有的内容
3. 输出JSON格式，包含summary字段
4. 总结后的文本必须不超过500字符
"""


# ── Core Logic ──

class ChatMLConverter:
    def __init__(self, llm_client: Optional[LLMClient] = None):
        self.llm_client = llm_client or LLMClient()

    def generate_task_description(
        self,
        user_role: str,
        is_first_person: bool
    ) -> str:
        """生成随机化的角色扮演任务描述。"""
        person = "第一人称" if is_first_person else "第三人称"
        
        user_prompt = f"""请生成一个角色扮演任务描述。

用户扮演的角色：{user_role}
人称：{person}

请输出JSON格式，包含task_description字段。"""

        messages = [
            ChatMessage(role="system", content=TASK_DESCRIPTION_SYSTEM_PROMPT),
            ChatMessage(role="user", content=user_prompt)
        ]

        try:
            response = self.llm_client.chat_with_json_response(
                messages=messages,
                response_model=TaskDescriptionResponse
            )
            return response.task_description
        except Exception as e:
            print(f"  任务描述生成失败，使用默认模板: {e}")
            return f"你是一个专业的角色扮演专家，请根据给定的世界观和角色设定，进行角色扮演。用户扮演的角色为{user_role}，你将扮演除了{user_role}以外的所有角色，并负责剧情的推进。请以{person}进行书写。"

    def summarize_context(self, text: str, max_chars: int = 500) -> str:
        """将长文本总结为不超过max_chars字符的摘要。"""
        if len(text) <= max_chars:
            return text

        user_prompt = f"""请将以下文本总结为不超过{max_chars}字符的摘要。

【原文】
{text}"""

        messages = [
            ChatMessage(role="system", content=SUMMARY_SYSTEM_PROMPT),
            ChatMessage(role="user", content=user_prompt)
        ]

        try:
            response = self.llm_client.chat_with_json_response(
                messages=messages,
                response_model=SummaryResponse
            )
            summary = response.summary
            if len(summary) > max_chars:
                summary = summary[:max_chars]
            return summary
        except Exception as e:
            print(f"  前情提要总结失败: {e}")
            return text[:max_chars]

    def generate_reasoning_content(
        self,
        history_messages: List[Dict[str, Any]],
        current_message: Dict[str, Any]
    ) -> str:
        """为assistant消息生成reasoning_content。"""
        history_text = ""
        for i, msg in enumerate(history_messages):
            role = msg.get("role", "")
            content = msg.get("content", "")
            history_text += f"[{role} {i+1}]\n{content}\n\n"

        current_content = current_message.get("content", "")
        current_speakers = current_message.get("speakers", [])
        speakers_str = "、".join(current_speakers) if current_speakers else "旁白"

        user_prompt = f"""【对话历史】
{history_text}

【目标回应】
说话者：{speakers_str}
内容：{current_content}

请根据以上对话历史，模拟{speakers_str}和旁白从历史对话推导出上述目标回应的完整思考过程。

请按照指定的思考顺序，生成详细的推导思考过程（Markdown格式）。

重要提醒：
- 思考过程应该描述"如何推导出这个目标回应"，而不是直接引用或复述目标回应的内容
- 而是要说"{speakers_str}观察到...，因此决定...，意图是..."
- 思考过程应该是从历史对话到目标回应的推导链条，解释为什么会得出这个回应
- **绝对禁止**：不要添加任何开场白或确认性话语。例如：不要说"好的，我来分析一下"、"让我们一步步推导"、"我将按照以下步骤思考"等。直接开始输出思考过程的内容。"""

        messages = [
            ChatMessage(role="system", content=REASONING_CONTENT_SYSTEM_PROMPT),
            ChatMessage(role="user", content=user_prompt)
        ]

        try:
            response = self.llm_client.chat_completion(messages=messages)
            return response.content.strip()
        except Exception as e:
            print(f"  Reasoning Content生成失败: {e}")
            return ""


# ── Helper Functions ──

def collect_jsonl_files(input_dir: Path) -> List[Tuple[Path, str]]:
    """收集所有 *_dialogue.jsonl 文件，返回 (文件路径, 书籍目录名) 列表。"""
    jsonl_files = []
    
    for item in sorted(input_dir.iterdir()):
        if item.is_dir():
            book_name = item.name
            for jsonl_file in sorted(item.glob("*_dialogue.jsonl")):
                jsonl_files.append((jsonl_file, book_name))
    
    if list(input_dir.glob("*_dialogue.jsonl")):
        for jsonl_file in sorted(input_dir.glob("*_dialogue.jsonl")):
            jsonl_files.append((jsonl_file, ""))
    
    return jsonl_files


def sample_files(files: List[Tuple[Path, str]], sample_count: int) -> List[Tuple[Path, str]]:
    """随机抽样文件。"""
    if sample_count <= 0 or len(files) <= sample_count:
        return files
    
    random.shuffle(files)
    return files[:sample_count]


def get_stem_from_jsonl(jsonl_path: Path) -> str:
    """从 *_dialogue.jsonl 路径中提取 stem（去掉 _dialogue.jsonl 后缀）。"""
    name = jsonl_path.name
    if name.endswith("_dialogue.jsonl"):
        return name[:-15]
    return name


def load_characters_info(book_dir: Path, stem: str) -> Optional[Dict[str, Any]]:
    """加载 {stem}_characters.json 文件。"""
    char_file = book_dir / f"{stem}_characters.json"
    if not char_file.exists():
        return None
    
    try:
        with open(char_file, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"  读取 {char_file.name} 失败: {e}")
        return None


def load_facts_info(book_dir: Path, stem: str) -> Optional[Dict[str, Any]]:
    """加载 {stem}_facts.json 文件。"""
    facts_file = book_dir / f"{stem}_facts.json"
    if not facts_file.exists():
        return None
    
    try:
        with open(facts_file, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"  读取 {facts_file.name} 失败: {e}")
        return None


def load_world_settings(book_dir: Path) -> str:
    """加载 world_settings.md 文件。"""
    ws_file = book_dir / "world_settings.md"
    if not ws_file.exists():
        return ""
    
    try:
        with open(ws_file, 'r', encoding='utf-8') as f:
            return f.read()
    except Exception as e:
        print(f"  读取 world_settings.md 失败: {e}")
        return ""


def load_character_profiles(book_dir: Path, character_names: List[str]) -> Dict[str, str]:
    """加载指定角色的设定文件。"""
    profiles = {}
    for char_name in character_names:
        safe_name = re.sub(r'[\\/:*?"<>|]', '_', char_name)
        profile_file = book_dir / f"{safe_name}.md"
        if profile_file.exists():
            try:
                with open(profile_file, 'r', encoding='utf-8') as f:
                    profiles[char_name] = f.read()
            except Exception as e:
                print(f"  读取 {safe_name}.md 失败: {e}")
    return profiles


def count_character_appearances(book_dir: Path) -> Dict[str, int]:
    """统计每个角色出现在多少个分段中。"""
    appearance_count = {}
    for char_file in sorted(book_dir.glob("*_characters.json")):
        try:
            with open(char_file, 'r', encoding='utf-8') as f:
                char_data = json.load(f)
            characters = char_data.get("characters", []) if isinstance(char_data, dict) else []
            unique_chars = set(name.strip() for name in characters if isinstance(name, str) and name.strip())
            for name in unique_chars:
                appearance_count[name] = appearance_count.get(name, 0) + 1
        except Exception:
            continue
    return appearance_count


def get_most_frequent_character(appearance_count: Dict[str, int]) -> Optional[str]:
    """获取出场频率最高的角色。"""
    if not appearance_count:
        return None
    
    sorted_chars = sorted(appearance_count.items(), key=lambda x: x[1], reverse=True)
    return sorted_chars[0][0]


def load_jsonl_records(jsonl_path: Path) -> List[Dict[str, Any]]:
    """加载JSONL文件中的所有记录。"""
    records = []
    try:
        with open(jsonl_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line:
                    records.append(json.loads(line))
    except Exception as e:
        print(f"  读取 {jsonl_path.name} 失败: {e}")
    return records


def convert_to_chatml_messages(
    records: List[Dict[str, Any]],
    user_role: str
) -> List[Dict[str, Any]]:
    """将JSONL记录转换为ChatML消息列表（带role分配）。"""
    messages = []
    for record in records:
        speaker = record.get("speaker", "")
        content = record.get("content", "")
        is_dialog = record.get("is_dialog", False)
        
        if speaker == user_role:
            role = "user"
        else:
            role = "assistant"
        
        messages.append({
            "role": role,
            "content": content,
            "speaker": speaker,
            "is_dialog": is_dialog
        })
    
    return messages


def merge_adjacent_messages(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """合并相邻role相同的消息。"""
    if not messages:
        return []
    
    merged = []
    current_role = None
    current_content = []
    current_speakers = set()
    
    for msg in messages:
        role = msg.get("role", "")
        content = msg.get("content", "")
        speaker = msg.get("speaker", "")
        
        if current_role is None:
            current_role = role
            current_content = [content]
            if speaker:
                current_speakers.add(speaker)
        elif current_role == role:
            current_content.append(content)
            if speaker:
                current_speakers.add(speaker)
        else:
            merged.append({
                "role": current_role,
                "content": "\n".join(current_content),
                "speakers": list(current_speakers)
            })
            current_role = role
            current_content = [content]
            current_speakers = set()
            if speaker:
                current_speakers.add(speaker)
    
    if current_role is not None and current_content:
        merged.append({
            "role": current_role,
            "content": "\n".join(current_content),
            "speakers": list(current_speakers)
        })
    
    return merged


def adjust_first_message_role(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """如果第一条消息是assistant，改为user。"""
    if not messages:
        return messages
    
    adjusted = messages.copy()
    if adjusted[0].get("role") == "assistant":
        adjusted[0] = adjusted[0].copy()
        adjusted[0]["role"] = "user"
    
    return adjusted


def build_context_summary(
    book_dir: Path,
    target_stem: str,
    converter: ChatMLConverter
) -> str:
    """构建前情提要（累加目标段落之前所有段落的summary）。"""
    all_facts_files = sorted(book_dir.glob("*_facts.json"))
    all_summaries = []
    target_index = -1
    
    for i, facts_file in enumerate(all_facts_files):
        stem = facts_file.stem[:-6] if facts_file.stem.endswith("_facts") else facts_file.stem
        if stem == target_stem:
            target_index = i
            break
        
        try:
            with open(facts_file, 'r', encoding='utf-8') as f:
                facts_data = json.load(f)
            summary = facts_data.get("summary", "")
            if summary:
                all_summaries.append(summary)
        except Exception:
            continue
    
    if not all_summaries:
        return ""
    
    accumulated_text = "\n".join(all_summaries)
    
    if len(accumulated_text) > 700:
        print(f"  前情提要超过700字符，调用LLM总结...")
        return converter.summarize_context(accumulated_text, 500)
    
    return accumulated_text


def process_jsonl_file(
    jsonl_path: Path,
    book_dir: Path,
    book_name: str,
    output_dir: Path,
    converter: ChatMLConverter
) -> bool:
    """处理单个JSONL文件。"""
    stem = get_stem_from_jsonl(jsonl_path)
    print(f"\n  处理文件: {jsonl_path.name}")
    
    char_info = load_characters_info(book_dir, stem)
    if char_info is None:
        print(f"    跳过：缺少 {stem}_characters.json")
        return False
    
    facts_info = load_facts_info(book_dir, stem)
    if facts_info is None:
        print(f"    跳过：缺少 {stem}_facts.json")
        return False
    
    world_settings = load_world_settings(book_dir)
    if not world_settings:
        print(f"    警告：缺少 world_settings.md")
    
    is_pov = char_info.get("is_pov", False)
    pov_name = char_info.get("pov_name", "")
    segment_characters = char_info.get("characters", [])
    
    if is_pov and pov_name:
        user_role = pov_name
        is_first_person = True
    else:
        appearance_count = count_character_appearances(book_dir)
        user_role = get_most_frequent_character(appearance_count)
        if not user_role and segment_characters:
            user_role = segment_characters[0]
        is_first_person = False
    
    if not user_role:
        print(f"    跳过：无法确定用户角色")
        return False
    
    print(f"    用户角色: {user_role}")
    
    all_characters = set(segment_characters)
    all_characters.add(user_role)
    
    character_profiles = load_character_profiles(book_dir, list(all_characters))
    
    context_summary = build_context_summary(book_dir, stem, converter)
    
    task_description = converter.generate_task_description(user_role, is_first_person)
    
    system_content_parts = [
        "【任务描述】",
        task_description,
        "",
        "【世界观设定】",
        world_settings if world_settings else "无",
    ]
    
    if character_profiles:
        system_content_parts.append("")
        system_content_parts.append("【角色设定】")
        for char_name, profile in character_profiles.items():
            system_content_parts.append(f"## {char_name}")
            system_content_parts.append(profile)
            system_content_parts.append("")
    
    if context_summary:
        system_content_parts.append("")
        system_content_parts.append("【前情提要】")
        system_content_parts.append(context_summary)
    
    system_content = "\n".join(system_content_parts)
    
    jsonl_records = load_jsonl_records(jsonl_path)
    if not jsonl_records:
        print(f"    跳过：JSONL文件为空")
        return False
    
    chatml_messages = convert_to_chatml_messages(jsonl_records, user_role)
    
    merged_messages = merge_adjacent_messages(chatml_messages)
    
    adjusted_messages = adjust_first_message_role(merged_messages)
    
    final_messages = [
        {
            "role": "system",
            "content": system_content
        }
    ]
    
    history_for_reasoning = [
        {"role": "system", "content": system_content}
    ]
    
    for msg in adjusted_messages:
        role = msg.get("role", "")
        content = msg.get("content", "")
        speakers = msg.get("speakers", [])
        
        if role == "assistant":
            reasoning_content = converter.generate_reasoning_content(
                history_messages=history_for_reasoning,
                current_message=msg
            )
            
            final_msg = {
                "role": "assistant",
                "content": content
            }
            if reasoning_content:
                final_msg["reasoning_content"] = reasoning_content
            
            final_messages.append(final_msg)
            history_for_reasoning.append({"role": "assistant", "content": content})
        else:
            final_messages.append({
                "role": "user",
                "content": content
            })
            history_for_reasoning.append({"role": "user", "content": content})
    
    if book_name:
        book_output_dir = output_dir / book_name
    else:
        book_output_dir = output_dir
    
    book_output_dir.mkdir(parents=True, exist_ok=True)
    
    output_file = book_output_dir / f"{stem}_chatml.json"
    output_data = {
        "messages": final_messages
    }
    
    try:
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(output_data, f, ensure_ascii=False, indent=2)
        print(f"    成功生成: {output_file.name} ({len(final_messages)} 条消息)")
        return True
    except Exception as e:
        print(f"    保存失败: {e}")
        return False


def process_book_directory(
    book_dir: Path,
    book_name: str,
    output_dir: Path,
    converter: ChatMLConverter,
    sample_count: int
) -> int:
    """处理书籍目录中的JSONL文件。"""
    print(f"\n处理书籍目录: {book_dir.name if book_name else '根目录'}")
    
    jsonl_files = list(book_dir.glob("*_dialogue.jsonl"))
    if not jsonl_files:
        print(f"  未找到JSONL文件，跳过")
        return 0
    
    files_with_book = [(f, book_name) for f in jsonl_files]
    sampled_files = sample_files(files_with_book, sample_count)
    
    print(f"  共 {len(jsonl_files)} 个JSONL文件，抽样处理 {len(sampled_files)} 个")
    
    processed_count = 0
    for jsonl_path, bn in sampled_files:
        try:
            if process_jsonl_file(jsonl_path, book_dir, bn or book_name, output_dir, converter):
                processed_count += 1
        except Exception as e:
            print(f"  处理 {jsonl_path.name} 时出错: {e}")
            traceback.print_exc()
    
    return processed_count


def main():
    parser = argparse.ArgumentParser(description='JSONL转ChatML训练集')
    parser.add_argument(
        '--input', '-i',
        required=True,
        help='输入目录路径（包含按书名划分的子目录）'
    )
    parser.add_argument(
        '--output', '-o',
        required=True,
        help='输出目录路径'
    )
    parser.add_argument(
        '--sample-count',
        type=int,
        default=10,
        help='每本书随机抽样处理的JSONL文件数量（默认：10，0表示处理所有）'
    )

    args = parser.parse_args()

    input_dir = Path(args.input)
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    if not input_dir.exists() or not input_dir.is_dir():
        print(f"错误: 输入目录 {input_dir} 不存在或不是一个目录")
        return

    llm_client = LLMClient()
    converter = ChatMLConverter(llm_client=llm_client)

    total_processed = 0
    books_processed = 0

    for item in sorted(input_dir.iterdir()):
        if item.is_dir() and item != output_dir:
            try:
                count = process_book_directory(
                    item, item.name, output_dir, converter, args.sample_count
                )
                total_processed += count
                if count > 0:
                    books_processed += 1
            except Exception as e:
                print(f"处理目录 {item.name} 时出错: {e}")
                traceback.print_exc()

    if list(input_dir.glob("*_dialogue.jsonl")):
        print(f"\n在 {input_dir.name} 根目录下发现JSONL文件")
        try:
            count = process_book_directory(
                input_dir, "", output_dir, converter, args.sample_count
            )
            total_processed += count
            if count > 0:
                books_processed += 1
        except Exception as e:
            print(f"处理根目录时出错: {e}")
            traceback.print_exc()

    print(f"\n全部处理完成！")
    print(f"  处理书籍目录数: {books_processed}")
    print(f"  成功处理文件数: {total_processed}")
    print(f"  输出目录: {output_dir}")


if __name__ == '__main__':
    main()
