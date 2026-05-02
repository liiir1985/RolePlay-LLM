import argparse
import json
from pathlib import Path
from typing import List, Dict, Any
import copy


def generate_no_reasoning_version(messages: List[Dict[str, Any]]) -> Dict[str, Any]:
    """生成不带reasoning的版本：将所有reasoning_content设为空字符串，并在system消息前添加[THINKING:OFF]"""
    result_messages = []
    for i, msg in enumerate(messages):
        new_msg = copy.deepcopy(msg)

        # 如果是assistant消息，确保reasoning_content为空字符串
        if new_msg.get("role") == "assistant":
            new_msg["reasoning_content"] = ""

        # 如果是第一条system消息，在content前添加[THINKING:OFF]
        if i == 0 and new_msg.get("role") == "system":
            new_msg["content"] = "[THINKING:OFF]\n" + new_msg["content"]

        result_messages.append(new_msg)

    return {"messages": result_messages}


def generate_progressive_reasoning_versions(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """生成带reasoning的渐进版本：从前往后遍历，每次多前进到一条assistant消息，
    只保留最后一条assistant消息的reasoning_content"""
    versions = []
    
    # 找到所有assistant消息的索引
    assistant_indices = []
    for i, msg in enumerate(messages):
        if msg.get("role") == "assistant":
            assistant_indices.append(i)
    
    if not assistant_indices:
        return versions
    
    # 为每个assistant消息生成一个版本
    for target_idx in assistant_indices:
        # 截取到当前assistant消息（包含）
        current_messages = messages[:target_idx + 1]

        # 检查最后一条assistant消息前是否有user消息
        has_user_before_last_assistant = False
        for i in range(len(current_messages) - 1):
            if current_messages[i].get("role") == "user":
                has_user_before_last_assistant = True
                break

        # 复制消息并处理reasoning_content
        result_messages = []
        for i, msg in enumerate(current_messages):
            new_msg = copy.deepcopy(msg)

            # 如果是第一条system消息，在content前添加[THINKING:ON]
            if i == 0 and new_msg.get("role") == "system":
                new_msg["content"] = "[THINKING:ON]\n" + new_msg["content"]

            # 如果是assistant消息
            if new_msg.get("role") == "assistant":
                if i == target_idx:
                    # 最后一条assistant：确保有reasoning_content字段
                    if "reasoning_content" not in new_msg or new_msg["reasoning_content"] is None:
                        new_msg["reasoning_content"] = ""
                else:
                    # 前面的assistant：删除reasoning_content字段
                    if "reasoning_content" in new_msg:
                        del new_msg["reasoning_content"]

            result_messages.append(new_msg)

        # 如果最后一条assistant前没有user消息，在最后插入一个空的user消息
        if not has_user_before_last_assistant:
            # 在最后一条assistant消息前插入空user消息
            empty_user = {"role": "user", "content": ""}
            result_messages.insert(-1, empty_user)

        versions.append({"messages": result_messages})
    
    return versions


def process_json_file(json_path: Path, output_dir: Path) -> int:
    """处理单个JSON文件，生成对应的JSONL文件
    
    Returns:
        生成的样本数量
    """
    print(f"\n处理文件: {json_path}")
    
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception as e:
        print(f"  读取失败: {e}")
        return 0
    
    messages = data.get("messages", [])
    if not messages:
        print(f"  跳过：消息列表为空")
        return 0

    # 检查是否包含role=user的消息
    has_user_message = any(msg.get("role") == "user" for msg in messages)
    if not has_user_message:
        print(f"  跳过：没有role=user的消息")
        return 0

    # 生成所有版本
    all_versions = []
    
    # 1. 不带reasoning的版本
    no_reasoning_version = generate_no_reasoning_version(messages)
    all_versions.append(no_reasoning_version)
    
    # 2. 带reasoning的渐进版本
    progressive_versions = generate_progressive_reasoning_versions(messages)
    all_versions.extend(progressive_versions)
    
    # 确定输出路径
    # 如果json_path在子目录中，保持相同的目录结构
    relative_path = json_path.relative_to(json_path.parent.parent)
    output_subdir = output_dir / relative_path.parent
    output_subdir.mkdir(parents=True, exist_ok=True)
    
    # 生成JSONL文件名（去掉_chatml.json后缀，加上.jsonl）
    stem = json_path.stem.replace("_chatml", "")
    output_file = output_subdir / f"{stem}.jsonl"
    
    # 写入JSONL文件
    try:
        with open(output_file, 'w', encoding='utf-8') as f:
            for version in all_versions:
                json_line = json.dumps(version, ensure_ascii=False)
                f.write(json_line + '\n')
        
        print(f"  成功生成: {output_file.name} ({len(all_versions)} 个样本)")
        return len(all_versions)
    except Exception as e:
        print(f"  保存失败: {e}")
        return 0


def collect_json_files(input_dir: Path) -> List[Path]:
    """收集所有 *_chatml.json 文件"""
    json_files = []

    # 遍历所有子目录
    for item in sorted(input_dir.iterdir()):
        if item.is_dir():
            for json_file in sorted(item.glob("*_chatml.json")):
                json_files.append(json_file)

    # 也检查根目录
    for json_file in sorted(input_dir.glob("*_chatml.json")):
        json_files.append(json_file)

    return json_files


def main():
    parser = argparse.ArgumentParser(description='将ChatML格式的JSON文件拆分为带/不带reasoning的JSONL训练集')
    parser.add_argument(
        '--input', '-i',
        required=True,
        help='输入目录路径（包含 *_chatml.json 文件）'
    )
    parser.add_argument(
        '--output', '-o',
        required=True,
        help='输出目录路径'
    )

    args = parser.parse_args()

    input_dir = Path(args.input)
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    if not input_dir.exists() or not input_dir.is_dir():
        print(f"错误: 输入目录 {input_dir} 不存在或不是一个目录")
        return

    # 收集所有JSON文件
    json_files = collect_json_files(input_dir)

    if not json_files:
        print(f"错误: 在 {input_dir} 中未找到任何 *_chatml.json 文件")
        return

    print(f"找到 {len(json_files)} 个JSON文件")

    # 处理所有文件
    total_samples = 0
    success_count = 0

    for json_file in json_files:
        samples = process_json_file(json_file, output_dir)
        if samples > 0:
            success_count += 1
            total_samples += samples

    print(f"\n处理完成！")
    print(f"  成功处理: {success_count}/{len(json_files)} 个文件")
    print(f"  生成样本总数: {total_samples}")
    print(f"  输出目录: {output_dir}")


if __name__ == '__main__':
    main()
