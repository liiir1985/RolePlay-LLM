import argparse
import json
import random
from pathlib import Path
from typing import List, Optional, Dict, Any

from pydantic import BaseModel

from ..utils.llm_client import LLMClient, ChatMessage


SCENE_DETECTION_SYSTEM_PROMPT = """你是一个专业的文本分析助手，擅长识别小说中的场景切换。

场景定义：
- 时空没有大范围变动的一段剧情
- 或者是一段连续时间的连续行动的描写

场景切换的常见特征：
1. 时间发生明显变化（如"第二天"、"三年后"等）
2. 地点发生明显变化（如从"教室"切换到"家里"）

不应该被切分的情况：
- 地点虽然发生了变化，但是在较短的连续时间内发生的一系列动作，例如：一队警察对嫌犯进行抓捕，从室外进入屋内，穿过几个房间把嫌犯压在了地上

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
或者：
{
  "scene_changes": []
}

"""


class SceneSegmentationResponse(BaseModel):
    scene_changes: List[int]


class LLMBasedSceneSegmenter:
    def __init__(
        self,
        chunk_size: int = 2000,
        llm_client: Optional[LLMClient] = None,
        min_segment_chars: int = 2000
    ):
        self.chunk_size = chunk_size
        self.llm_client = llm_client or LLMClient()
        self.min_segment_chars = min_segment_chars
    
    def _split_into_chunks_by_lines(self, lines: List[str]) -> List[List[str]]:
        chunks = []
        current_chunk = []
        current_length = 0
        
        for line in lines:
            # 加上换行符的长度
            line_length = len(line) + 1
            
            if current_length + line_length > self.chunk_size and current_chunk:
                chunks.append(current_chunk)
                current_chunk = [line]
                current_length = line_length
            else:
                current_chunk.append(line)
                current_length += line_length
                
        if current_chunk:
            chunks.append(current_chunk)
            
        return chunks
    
    def _add_line_numbers(self, lines: List[str], start_line: int = 1) -> str:
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
        
        try:
            response = self.llm_client.chat_with_json_response(
                messages=messages,
                response_model=SceneSegmentationResponse
            )
            
            if isinstance(response, SceneSegmentationResponse):
                boundaries = response.scene_changes
            elif isinstance(response, dict) and "scene_changes" in response:
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
        
        chunks = self._split_into_chunks_by_lines(lines)
        
        all_boundaries = set()
        all_boundaries.add(1)
        all_boundaries.add(total_lines + 1)
        
        current_line = 1
        
        for chunk_idx, chunk_lines in enumerate(chunks):
            chunk_line_count = len(chunk_lines)
            
            numbered_chunk = self._add_line_numbers(chunk_lines, current_line)
            
            print(f"  处理chunk {chunk_idx + 1}/{len(chunks)} (行 {current_line}-{current_line + chunk_line_count - 1})")
            
            chunk_boundaries = self._detect_scene_boundaries_with_llm(
                numbered_chunk,
                current_line
            )
            
            for boundary in chunk_boundaries:
                # 确保边界在当前 chunk 的合理范围内，并且不是强制第一行
                if current_line < boundary <= current_line + chunk_line_count:
                    all_boundaries.add(boundary)
            
            current_line += chunk_line_count
        
        sorted_boundaries = sorted(all_boundaries)
        sorted_boundaries = self._merge_adjacent_boundaries(sorted_boundaries)
        
        # 根据 min_segment_chars 合并过短的片段
        if self.min_segment_chars > 0:
            merged_boundaries = [sorted_boundaries[0]]
            current_start = sorted_boundaries[0]
            
            for boundary in sorted_boundaries[1:-1]:
                segment_lines = lines[current_start - 1:boundary - 1]
                segment_content = '\n'.join(segment_lines).strip()
                if len(segment_content) >= self.min_segment_chars:
                    merged_boundaries.append(boundary)
                    current_start = boundary
                    
            merged_boundaries.append(sorted_boundaries[-1])
            
            # 处理最后一段如果过短的情况
            if len(merged_boundaries) > 2:
                last_segment_lines = lines[merged_boundaries[-2] - 1:merged_boundaries[-1] - 1]
                if len('\n'.join(last_segment_lines).strip()) < self.min_segment_chars:
                    merged_boundaries.pop(-2)
                    
            sorted_boundaries = merged_boundaries
        
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
            
            if not stripped_content:
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
    base_name = input_path.stem
    file_output_dir = output_dir / base_name
    
    if file_output_dir.exists():
        print(f"输出目录已存在，跳过文件: {input_path.name}")
        return 0

    with open(input_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    print(f"处理文件: {input_path.name}")
    print(f"  文件大小: {len(content)} 字符")
    
    scenes = segmenter.segment(content, input_path.name)
    
    # 为当前原始文件创建一个子目录
    file_output_dir.mkdir(parents=True, exist_ok=True)
    
    for scene in scenes:
        scene_file = file_output_dir / f"{scene['scene_id']}.txt"
        with open(scene_file, 'w', encoding='utf-8') as f:
            f.write(scene['content'])
        
        print(f"  输出: {scene_file.relative_to(output_dir)} (行 {scene['start_line']}-{scene['end_line']}, {scene['char_count']} 字符)")
    
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
        '--min-segment-chars',
        type=int,
        default=2000,
        help='合并后的片段最小字符数（默认：2000）'
    )
    parser.add_argument(
        '--sample-files',
        type=int,
        default=0,
        help='随机抽取处理的txt文件数量，0表示全部处理（默认：0）'
    )
    
    args = parser.parse_args()
    
    input_path = Path(args.input)
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    llm_client = LLMClient()
    segmenter = LLMBasedSceneSegmenter(
        chunk_size=args.chunk_size,
        llm_client=llm_client,
        min_segment_chars=args.min_segment_chars
    )
    
    if input_path.is_file():
        files = [input_path]
    else:
        files = list(input_path.glob('*.txt'))
        if args.sample_files > 0 and len(files) > args.sample_files:
            files = random.sample(files, args.sample_files)
            print(f"随机抽取了 {args.sample_files} 个文件进行处理")
    
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
