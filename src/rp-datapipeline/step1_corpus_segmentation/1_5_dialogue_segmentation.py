import argparse
import json
import re
from pathlib import Path
from typing import List, Optional, Dict, Any
import traceback

from pydantic import BaseModel, Field

from ..utils.llm_client import LLMClient, ChatMessage


# ── Pydantic Models ──

class SpeakerAnnotation(BaseModel):
    line_number: int = Field(description="行号（从1开始）")
    speaker: str = Field(description="说话者的本名")


class DialogueAnnotationResponse(BaseModel):
    speakers: List[SpeakerAnnotation] = Field(description="识别出说话者的行号和说话者名字的键值对数组，说话者为空则不输出")


class SummaryResponse(BaseModel):
    summary: str = Field(description="总结后的文本，不超过500字符")


# ── System Prompts ──

DIALOGUE_ANNOTATION_SYSTEM_PROMPT = f"""你是一个专业的小说对话分析助手。

你的任务：
根据提供的出场角色列表、POV信息、前情提要、已处理文本和带行号的文本行，识别每一行的说话者。

输出要求：
1. 必须输出JSON格式，包含一个speakers数组
2. 数组中每个元素包含line_number（行号）和speaker（说话者本名）
3. 只输出识别出说话者的行，说话者为空或无法确定的行不输出

判断规则：
- 说话者识别：根据上下文判断是谁说的话，如果无法确定则不输出该行
- 第一人称"我"对应的角色名已在POV信息中给出
- 旁白或叙述性文本不输出

你必须输出以下JSON结构的数据：
{DialogueAnnotationResponse.model_json_schema()}
"""

SUMMARY_SYSTEM_PROMPT = """你是一个专业的文本摘要助手。

你的任务：
将提供的长文本总结为500字符左右的摘要。

要求：
1. 保持原文的关键信息和时间顺序
2. 不要添加原文没有的内容
3. 输出JSON格式，包含summary字段
4. 总结后的文本必须不超过500字符
"""


# ── Core Logic ──

class DialogueSegmenter:
    def __init__(self, llm_client: Optional[LLMClient] = None, batch_size: int = 50):
        self.llm_client = llm_client or LLMClient()
        self.batch_size = batch_size

    def split_text_by_dialogue(self, text: str) -> List[str]:
        """
        将文本按对话边界拆分。
        支持的引号格式：""、""、「」、『』、（）
        例如："ff."abc."gg." 拆分为 ["\"ff.\"", "abc.", "\"gg.\""]
        """
        lines = text.split('\n')
        result = []

        # 匹配各种引号对的正则
        # 顺序很重要：先匹配长的模式
        quote_patterns = [
            (r'「[^「」]*」', '「', '」'),
            (r'『[^『』]*』', '『', '』'),
            (r'（[^（）]*）', '（', '）'),
            (r'"[^"]*"', '"', '"'),
            (r'"[^"]*"', '"', '"'),
        ]

        for line in lines:
            if not line.strip():
                result.append(line)
                continue

            # 检查是否需要拆分
            needs_split = False
            for pattern, _, _ in quote_patterns:
                if re.search(pattern, line):
                    # 检查是否有多个引号对，或者引号对之外还有内容
                    matches = list(re.finditer(pattern, line))
                    if len(matches) > 1:
                        needs_split = True
                        break
                    elif len(matches) == 1:
                        # 检查引号对前后是否有内容
                        match = matches[0]
                        if match.start() > 0 or match.end() < len(line):
                            needs_split = True
                            break

            if not needs_split:
                result.append(line)
                continue

            # 需要拆分，按对话边界拆分
            parts = []
            current_pos = 0

            # 找出所有对话边界
            all_matches = []
            for pattern, open_q, close_q in quote_patterns:
                for match in re.finditer(pattern, line):
                    all_matches.append((match.start(), match.end(), match.group()))

            # 按位置排序
            all_matches.sort(key=lambda x: x[0])

            # 去重重叠的匹配
            filtered_matches = []
            last_end = 0
            for start, end, content in all_matches:
                if start >= last_end:
                    filtered_matches.append((start, end, content))
                    last_end = end

            # 拆分
            for start, end, content in filtered_matches:
                if start > current_pos:
                    # 对话前的旁白部分
                    parts.append(line[current_pos:start])
                # 对话部分
                parts.append(content)
                current_pos = end

            if current_pos < len(line):
                # 最后的旁白部分
                parts.append(line[current_pos:])

            # 添加非空的部分
            for part in parts:
                if part:
                    result.append(part)

        return result

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
            # 确保不超过限制
            if len(summary) > max_chars:
                summary = summary[:max_chars]
            return summary
        except Exception as e:
            print(f"  前情提要总结失败: {e}")
            # 失败时返回截断的原文
            return text[:max_chars]

    def annotate_lines(
        self,
        lines: List[str],
        characters_str: str,
        pov_info: str,
        context_summary: str
    ) -> Optional[Dict[int, str]]:
        """
        标注文本行，识别每行的说话者。
        分批处理，每批batch_size行。
        返回字典：行号(从0开始) -> speaker名字
        """
        all_annotations: Dict[int, str] = {}
        total_lines = len(lines)
        processed_lines: List[str] = []  # 已处理的文本行（不带行号）

        for batch_start in range(0, total_lines, self.batch_size):
            batch_end = min(batch_start + self.batch_size, total_lines)
            batch_lines = lines[batch_start:batch_end]
            batch_size_actual = len(batch_lines)

            # 组装带行号的文本
            numbered_lines = []
            for i, line in enumerate(batch_lines, 1):
                numbered_lines.append(f"{i}: {line}")
            numbered_text = "\n".join(numbered_lines)

            # 组装已处理的文本行（不带行号）
            processed_text = "\n".join(processed_lines) if processed_lines else "无"

            # 组装用户提示
            user_prompt = f"""请分析以下文本行，识别每行的说话者。

【出场角色列表】
{characters_str}

【POV信息】
{pov_info if pov_info else "本段落为第三人称视角"}

【前情提要】
{context_summary if context_summary else "无"}

【已处理文本】
{processed_text}

【文本行（共{batch_size_actual}行）】
{numbered_text}

请输出JSON格式的speakers数组。"""

            messages = [
                ChatMessage(role="system", content=DIALOGUE_ANNOTATION_SYSTEM_PROMPT),
                ChatMessage(role="user", content=user_prompt)
            ]

            # 重试机制
            max_retries = 10
            last_error = None

            for attempt in range(max_retries):
                try:
                    response = self.llm_client.chat_with_json_response(
                        messages=messages,
                        response_model=DialogueAnnotationResponse
                    )

                    # 将返回的数组转换为字典（行号 -> speaker）
                    for annotation in response.speakers:
                        # 转换为全局行号（从0开始）
                        global_line_num = batch_start + annotation.line_number - 1
                        all_annotations[global_line_num] = annotation.speaker

                    # 将当前batch的文本行添加到已处理列表，供后续batch使用
                    processed_lines.extend(batch_lines)
                    break

                except Exception as e:
                    last_error = e
                    if attempt < max_retries - 1:
                        print(f"  第{attempt + 1}次尝试失败，重试中...: {e}")
                        continue
                    else:
                        print(f"  标注失败，已重试{max_retries}次: {last_error}")
                        return None

        return all_annotations


# ── Helper Functions ──

def get_segment_stems(book_dir: Path) -> List[str]:
    """获取所有有对应 .txt 文件的分段 stem，按文件名排序。"""
    txt_files = sorted(book_dir.glob("*.txt"))
    stems = []
    for txt_file in txt_files:
        stem = txt_file.stem
        # 排除已生成的输出文件
        if stem.endswith("_characters") or stem.endswith("_facts") or stem.endswith("_dialogue"):
            continue
        char_file = book_dir / f"{stem}_characters.json"
        facts_file = book_dir / f"{stem}_facts.json"
        if char_file.exists() and facts_file.exists():
            stems.append(stem)
    return stems


def load_name_alias_map(book_dir: Path) -> Dict[str, List[str]]:
    """从 characters.json 加载 name -> alias 列表的映射。"""
    characters_file = book_dir / "characters.json"
    name_alias_map: Dict[str, List[str]] = {}
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


def build_characters_str(characters: List[str], name_alias_map: Dict[str, List[str]]) -> str:
    """组装出场角色列表字符串。"""
    char_str_list = []
    for char_name in characters:
        aliases = name_alias_map.get(char_name, [])
        if aliases:
            aliases_str = "、".join(aliases)
            char_str_list.append(f"{char_name}（别称：{aliases_str}）")
        else:
            char_str_list.append(char_name)
    return "\n".join(char_str_list) if char_str_list else "无明确出场角色"


def merge_annotated_lines(
    lines: List[str],
    annotations: Dict[int, str]
) -> List[Dict[str, Any]]:
    """
    合并连续相同speaker的行。
    合并规则：
    - speaker相同则合并
    - content合并时添加换行符
    - 没有speaker标注的行视为旁白（空speaker）
    """
    if not lines:
        return []

    result: List[Dict[str, Any]] = []
    current_speaker: Optional[str] = None
    current_content: List[str] = []

    for i, line in enumerate(lines):
        speaker = annotations.get(i, "")

        # 判断是否需要新建记录
        need_new = False
        if current_speaker is None:
            need_new = True
        elif current_speaker != speaker:
            need_new = True

        if need_new:
            # 保存当前记录
            if current_speaker is not None and current_content:
                result.append({
                    "speaker": current_speaker,
                    "content": "\n".join(current_content)
                })
            # 开始新记录
            current_speaker = speaker
            current_content = [line]
        else:
            # 追加到当前记录
            current_content.append(line)

    # 保存最后一条记录
    if current_speaker is not None and current_content:
        result.append({
            "speaker": current_speaker,
            "content": "\n".join(current_content)
        })

    return result


def process_book_directory(
    book_dir: Path,
    output_dir: Path,
    segmenter: DialogueSegmenter,
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
        print(f"  未找到有效的分段文件，跳过")
        return 0

    # 加载角色名称映射
    name_alias_map = load_name_alias_map(book_dir)

    # ── 处理每个分段 ──
    processed_count = 0
    accumulated_text = ""
    summarized_context: Optional[str] = None

    for i, stem in enumerate(segment_stems):
        output_file = book_output_dir / f"{stem}_dialogue.json"

        # 读取当前段落的 summary，用于后续段落的前情提要（无论是否跳过都要维护）
        facts_file = book_dir / f"{stem}_facts.json"
        current_summary = ""
        try:
            with open(facts_file, 'r', encoding='utf-8') as f:
                facts_data = json.load(f)
            current_summary = facts_data.get("summary", "")
        except Exception as e:
            print(f"  读取 {facts_file.name} 失败: {e}")

        if output_file.exists():
            print(f"  跳过已处理片段: {stem}")
            if current_summary and not summarized_context:
                accumulated_text = (accumulated_text + "\n" + current_summary).strip() if accumulated_text else current_summary
            continue

        print(f"  处理片段: {stem}")

        # 计算当前段落的前情提要（i>0 时才有）
        if i == 0:
            context_summary = ""
        elif summarized_context:
            context_summary = summarized_context
        elif len(accumulated_text) > 700:
            print(f"  前情提要超过700字符，调用LLM总结...")
            summarized_context = segmenter.summarize_context(accumulated_text, 500)
            context_summary = summarized_context
        else:
            context_summary = accumulated_text

        # 加载必要文件
        txt_file = book_dir / f"{stem}.txt"
        char_file = book_dir / f"{stem}_characters.json"

        try:
            # 读取文本
            with open(txt_file, 'r', encoding='utf-8') as f:
                raw_text = f.read()

            # 读取角色信息
            with open(char_file, 'r', encoding='utf-8') as f:
                char_data = json.load(f)

            segment_characters = char_data.get("characters", []) if isinstance(char_data, dict) else []
            is_pov = char_data.get("is_pov", False) if isinstance(char_data, dict) else False
            pov_name = char_data.get("pov_name", "") if isinstance(char_data, dict) else ""

            # 组装POV信息
            if is_pov and pov_name:
                pov_info = f"本段落以第一人称视角书写，其中的\"我\"指的是\"{pov_name}\""
                # 将第一人称主角加入出场角色列表
                if pov_name not in segment_characters:
                    segment_characters.insert(0, pov_name)
            else:
                pov_info = ""

            # 组装出场角色列表
            characters_str = build_characters_str(segment_characters, name_alias_map)

            # 拆分文本行（按对话边界）
            split_lines = segmenter.split_text_by_dialogue(raw_text)

            if not split_lines:
                print(f"    无有效文本行，跳过")
            else:
                print(f"    拆分后共 {len(split_lines)} 行")

                # 调用LLM标注
                annotations = segmenter.annotate_lines(
                    lines=split_lines,
                    characters_str=characters_str,
                    pov_info=pov_info,
                    context_summary=context_summary
                )

                if annotations is None:
                    print(f"    标注失败，跳过")
                else:
                    # 合并连续相同speaker的行
                    merged_records = merge_annotated_lines(split_lines, annotations)

                    # 输出JSON
                    output_data = {
                        "context_summary": context_summary,
                        "messages": merged_records
                    }
                    with open(output_file, 'w', encoding='utf-8') as f:
                        json.dump(output_data, f, ensure_ascii=False, indent=2)

                    processed_count += 1
                    print(f"    成功生成: {output_file.name} ({len(merged_records)} 条记录)")

        except Exception as e:
            print(f"  处理 {stem} 时出错: {e}")
            traceback.print_exc()

        # 累积当前段落的 summary 供后续段落使用
        if current_summary and not summarized_context:
            accumulated_text = (accumulated_text + "\n" + current_summary).strip() if accumulated_text else current_summary

    return processed_count


def main():
    parser = argparse.ArgumentParser(description='对话切分与JSON数据集生成')
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
        '--batch-size',
        type=int,
        default=50,
        help='每批处理的行数（默认：50）'
    )

    args = parser.parse_args()

    input_dir = Path(args.input)
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    if not input_dir.exists() or not input_dir.is_dir():
        print(f"错误: 输入目录 {input_dir} 不存在或不是一个目录")
        return

    llm_client = LLMClient()
    segmenter = DialogueSegmenter(llm_client=llm_client, batch_size=args.batch_size)

    total_processed = 0
    books_processed = 0

    # 先处理子目录
    for item in sorted(input_dir.iterdir()):
        if item.is_dir() and item != output_dir:
            try:
                count = process_book_directory(item, output_dir, segmenter, is_root=False)
                total_processed += count
                books_processed += 1
            except Exception as e:
                print(f"处理目录 {item.name} 时出错: {e}")
                traceback.print_exc()

    # 如果输入目录下直接有 txt 文件，也当作一个书籍目录处理
    if list(input_dir.glob("*.txt")):
        print(f"在 {input_dir.name} 根目录下发现 txt 文件，将其作为单独的书籍目录处理")
        try:
            count = process_book_directory(input_dir, output_dir, segmenter, is_root=True)
            total_processed += count
            books_processed += 1
        except Exception as e:
            print(f"处理根目录 {input_dir.name} 时出错: {e}")
            traceback.print_exc()

    print(f"\n全部处理完成！")
    print(f"  处理书籍目录数: {books_processed}")
    print(f"  成功处理片段数: {total_processed}")
    print(f"  输出目录: {output_dir}")


if __name__ == '__main__':
    main()
