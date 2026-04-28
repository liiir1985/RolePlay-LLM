import argparse
import json
from pathlib import Path
from typing import List, Optional, Dict, Any

from ..utils.llm_client import LLMClient, ChatMessage


SCENE_DETECTION_SYSTEM_PROMPT = """你是一个专业的文本分析助手，擅长识别小说中的场景切换。

场景定义：
- 时空没有大范围变动的一段剧情
- 或者是一段不可分割的连续时间的连续行动的描写

场景切换的常见特征：
1. 时间发生明显变化（如"第二天"、"三年后"等）
2. 地点发生明显变化（如从"教室"切换到"家里"）
3. 整体文章叙事视角发生明显转换（仅当文章的POV切换，比如旁白提到的“我”所指代的角色变了）
4. 章节或场景分隔符（如"* * *"、"---"等）

你的任务：
分析给定的文本段落，找出所有发生场景切换的行号。

输出要求：
- 输出JSON对象，必须包含 `scene_changes` 字段，其值为整数数组
- 行号从1开始计数
- 如果没有场景切换，`scene_changes` 返回空数组[]

示例输出：
{
  "scene_changes": [5, 12, 28]
}
"""


class LLMBasedSceneSegmenter:
    def __init__(
        self,
        chunk_size: int = 2000,
        llm_client: Optional[LLMClient] = None,
        min_scene_chars: int = 100
    ):
        self.chunk_size = chunk_size
        self.llm_client = llm_client or LLMClient()
        self.min_scene_chars = min_scene_chars
    
    def _split_into_chunks(self, text: str) -> List[str]:
        chunks = []
        start = 0
        text_length = len(text)
        
        while start < text_length:
            end = min(start + self.chunk_size, text_length)
            
            if end < text_length:
                last_newline = text.rfind('\n', start, end)
                if last_newline > start:
                    end = last_newline + 1
            
            chunk = text[start:end]
            chunks.append(chunk)
            start = end
        
        return chunks
    
    def _add_line_numbers(self, text: str, start_line: int = 1) -> str:
        lines = text.split('\n')
        numbered_lines = []
        
        for i, line in enumerate(lines):
            line_num = start_line + i
            numbered_lines.append(f"{line_num}: {line}")
        
        return '\n'.join(numbered_lines)
    
    def _detect_scene_boundaries_with_llm(
        self,
        numbered_text: str,
        chunk_start_line: int
    ) -> List[int]:
        user_prompt = f"""请分析以下文本，找出所有发生场景切换的行号。

文本内容（行号: 文本内容）：
{numbered_text}

请只输出JSON，包含场景切换的行号。如果没有场景切换，返回空数组。"""

        messages = [
            ChatMessage(role="system", content=SCENE_DETECTION_SYSTEM_PROMPT),
            ChatMessage(role="user", content=user_prompt)
        ]
        
        schema = {
            "name": "scene_segmentation",
            "schema": {
                "type": "object",
                "properties": {
                    "scene_changes": {
                        "type": "array",
                        "items": {
                            "type": "integer"
                        },
                        "description": "发生场景切换的行号列表，如果没有切换则为空数组"
                    }
                },
                "required": ["scene_changes"],
                "additionalProperties": False
            },
            "strict": True
        }
        
        try:
            response = self.llm_client.chat_with_json_response(
                messages=messages,
                json_schema=schema
            )
            
            if isinstance(response, dict) and "scene_changes" in response:
                boundaries = response["scene_changes"]
            elif isinstance(response, list):
                boundaries = response
            else:
                boundaries = []
            
            if not isinstance(boundaries, list):
                boundaries = []
            
            valid_boundaries = []
            for b in boundaries:
                if isinstance(b, int) and b > 0:
                    valid_boundaries.append(b)
                elif isinstance(b, str) and b.isdigit():
                    valid_boundaries.append(int(b))
            
            return sorted(set(valid_boundaries))
        
        except Exception as e:
            print(f"  LLM调用失败: {e}")
            return []
    
    def _merge_adjacent_boundaries(
        self,
        boundaries: List[int],
        min_distance: int = 5
    ) -> List[int]:
        if len(boundaries) <= 1:
            return boundaries
        
        merged = [boundaries[0]]
        
        for boundary in boundaries[1:]:
            if boundary - merged[-1] >= min_distance:
                merged.append(boundary)
        
        return merged
    
    def segment(self, content: str, source_file: str) -> List[Dict[str, Any]]:
        lines = content.split('\n')
        total_lines = len(lines)
        
        chunks = self._split_into_chunks(content)
        
        all_boundaries = set()
        all_boundaries.add(1)
        all_boundaries.add(total_lines + 1)
        
        current_line = 1
        
        for chunk_idx, chunk in enumerate(chunks):
            chunk_lines = chunk.split('\n')
            chunk_line_count = len(chunk_lines)
            
            numbered_chunk = self._add_line_numbers(chunk, current_line)
            
            print(f"  处理chunk {chunk_idx + 1}/{len(chunks)} (行 {current_line}-{current_line + chunk_line_count - 1})")
            
            chunk_boundaries = self._detect_scene_boundaries_with_llm(
                numbered_chunk,
                current_line
            )
            
            for boundary in chunk_boundaries:
                if current_line <= boundary <= current_line + chunk_line_count:
                    all_boundaries.add(boundary)
            
            current_line += chunk_line_count
        
        sorted_boundaries = sorted(all_boundaries)
        sorted_boundaries = self._merge_adjacent_boundaries(sorted_boundaries)
        
        scenes = []
        base_name = Path(source_file).stem
        
        for i in range(len(sorted_boundaries) - 1):
            start_line = sorted_boundaries[i]
            end_line = sorted_boundaries[i + 1] - 1
            
            if start_line > end_line:
                continue
            
            scene_lines = lines[start_line - 1:end_line]
            scene_content = '\n'.join(scene_lines)
            stripped_content = scene_content.strip()
            
            if not stripped_content or len(stripped_content) < self.min_scene_chars:
                continue
            
            scene = {
                "scene_id": f"{base_name}_{i:03d}",
                "source_file": source_file,
                "start_line": start_line,
                "end_line": end_line,
                "content": stripped_content,
                "char_count": len(stripped_content)
            }
            
            scenes.append(scene)
        
        return scenes


def process_file(
    input_path: Path,
    output_dir: Path,
    segmenter: LLMBasedSceneSegmenter
) -> int:
    with open(input_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    print(f"处理文件: {input_path.name}")
    print(f"  文件大小: {len(content)} 字符")
    
    scenes = segmenter.segment(content, input_path.name)
    
    base_name = input_path.stem
    
    for scene in scenes:
        scene_file = output_dir / f"{base_name}_{scene['scene_id'].split('_')[-1]}.txt"
        with open(scene_file, 'w', encoding='utf-8') as f:
            f.write(scene['content'])
        
        print(f"  输出: {scene_file.name} (行 {scene['start_line']}-{scene['end_line']}, {scene['char_count']} 字符)")
    
    return len(scenes)


def main():
    parser = argparse.ArgumentParser(
        description='使用LLM将轻小说原文按照场景切换切分'
    )
    parser.add_argument(
        '--input', '-i',
        required=True,
        help='输入目录或文件路径'
    )
    parser.add_argument(
        '--output', '-o',
        required=True,
        help='输出目录路径'
    )
    parser.add_argument(
        '--chunk-size',
        type=int,
        default=2000,
        help='每个chunk的字符数（默认：2000）'
    )
    parser.add_argument(
        '--min-scene-chars',
        type=int,
        default=100,
        help='最小场景字符数（默认：100）'
    )
    
    args = parser.parse_args()
    
    input_path = Path(args.input)
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    llm_client = LLMClient()
    segmenter = LLMBasedSceneSegmenter(
        chunk_size=args.chunk_size,
        llm_client=llm_client,
        min_scene_chars=args.min_scene_chars
    )
    
    if input_path.is_file():
        files = [input_path]
    else:
        files = list(input_path.glob('*.txt'))
    
    total_scenes = 0
    processed_files = 0
    
    for file_path in files:
        try:
            scene_count = process_file(file_path, output_dir, segmenter)
            total_scenes += scene_count
            processed_files += 1
            print(f"  切分出 {scene_count} 个场景")
        except Exception as e:
            print(f"  处理失败: {e}")
            import traceback
            traceback.print_exc()
    
    print(f"\n处理完成！")
    print(f"  处理文件数: {processed_files}")
    print(f"  总场景数: {total_scenes}")
    print(f"  输出目录: {output_dir}")


if __name__ == '__main__':
    main()
