import argparse
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Dict, Any, Optional

from .config import get_config


@dataclass
class StepInfo:
    step_id: str
    module_name: str
    description: str
    default_input: Optional[str] = None
    default_output: Optional[str] = None
    default_params: Dict[str, Any] = field(default_factory=dict)


STEP_REGISTRY: Dict[str, StepInfo] = {}


def register_step(
    step_id: str,
    module_name: str,
    description: str,
    default_input: Optional[str] = None,
    default_output: Optional[str] = None,
    default_params: Optional[Dict[str, Any]] = None
):
    STEP_REGISTRY[step_id] = StepInfo(
        step_id=step_id,
        module_name=module_name,
        description=description,
        default_input=default_input,
        default_output=default_output,
        default_params=default_params or {}
    )


def _init_step_registry():
    config = get_config()
    
    register_step(
        step_id="1_1",
        module_name="src.rp-datapipeline.step1_corpus_segmentation.1_1_scene_segmentation",
        description="场景切换切分：使用LLM将原文按照场景切换切分",
        default_input=config.raw_data_dir,
        default_output=f"{config.processed_data_dir}/1_1_scene_segmentation",
        default_params={
            "chunk_size": 2000,
            "min_segment_chars": 2000
        }
    )
    
    register_step(
        step_id="1_2",
        module_name="src.rp-datapipeline.step1_corpus_segmentation.1_2_character_extraction",
        description="角色名字和Alias提取：从切分后的场景文本中提取角色名字和Alias",
        default_input=f"{config.processed_data_dir}/1_1_scene_segmentation",
        default_output=f"{config.processed_data_dir}/1_1_scene_segmentation",
        default_params={}
    )
    
    register_step(
        step_id="1_3",
        module_name="src.rp-datapipeline.step1_corpus_segmentation.1_3_scene_context_extraction",
        description="场景事实与上下文提炼：提取环境设定、角色表现设定及段落事实总结",
        default_input=f"{config.processed_data_dir}/1_1_scene_segmentation",
        default_output=f"{config.processed_data_dir}/1_1_scene_segmentation",
        default_params={}
    )
    
    register_step(
        step_id="1_4",
        module_name="src.rp-datapipeline.step1_corpus_segmentation.1_4_world_character_profiles",
        description="世界观设定与角色设定提取：从分段事实中提取世界观和主要角色设定",
        default_input=f"{config.processed_data_dir}/1_1_scene_segmentation",
        default_output=f"{config.processed_data_dir}/1_1_scene_segmentation",
        default_params={
            "min_appearance_pct": 20
        }
    )

    register_step(
        step_id="1_5",
        module_name="src.rp-datapipeline.step1_corpus_segmentation.1_5_dialogue_segmentation",
        description="对话切分与JSON数据集生成：识别对话和旁白，标注说话者，生成JSON格式数据集",
        default_input=f"{config.processed_data_dir}/1_1_scene_segmentation",
        default_output=f"{config.processed_data_dir}/1_1_scene_segmentation",
        default_params={
            "batch_size": 50
        }
    )

    register_step(
        step_id="2_1",
        module_name="src.rp-datapipeline.step2_chatml_conversion.2_1_jsonl_to_chatml",
        description="JSON转ChatML训练集：将JSON数据集转换为ChatML格式，包含system提示、角色分配和reasoning_content补全",
        default_input=f"{config.processed_data_dir}/1_1_scene_segmentation",
        default_output=f"{config.processed_data_dir}/2_1_chatml_conversion",
        default_params={
            "sample_count": 10
        }
    )


_init_step_registry()


def list_steps():
    print("可用的步骤：")
    print("-" * 60)
    for step_id, info in sorted(STEP_REGISTRY.items()):
        print(f"  {step_id}: {info.description}")
        if info.default_input:
            print(f"    默认输入: {info.default_input}")
        if info.default_output:
            print(f"    默认输出: {info.default_output}")
        if info.default_params:
            print(f"    默认参数: {info.default_params}")
        print()


def build_command(
    step_info: StepInfo,
    input_path: Optional[str],
    output_path: Optional[str],
    extra_args: List[str]
) -> List[str]:
    cmd = [sys.executable, "-m", step_info.module_name]
    
    if input_path:
        cmd.extend(["--input", input_path])
    elif step_info.default_input:
        cmd.extend(["--input", step_info.default_input])
    
    if output_path:
        cmd.extend(["--output", output_path])
    elif step_info.default_output:
        cmd.extend(["--output", step_info.default_output])
    
    for key, value in step_info.default_params.items():
        arg_key = key.replace("_", "-")
        if isinstance(value, bool):
            if value:
                cmd.append(f"--{arg_key}")
        else:
            cmd.extend([f"--{arg_key}", str(value)])
    
    cmd.extend(extra_args)
    
    return cmd


def run_step(
    step_id: str,
    input_path: Optional[str] = None,
    output_path: Optional[str] = None,
    extra_args: Optional[List[str]] = None
) -> int:
    if step_id not in STEP_REGISTRY:
        print(f"错误: 未找到步骤 '{step_id}'")
        print()
        list_steps()
        return 1
    
    step_info = STEP_REGISTRY[step_id]
    extra_args = extra_args or []
    
    cmd = build_command(step_info, input_path, output_path, extra_args)
    
    print(f"执行步骤: {step_id}")
    print(f"描述: {step_info.description}")
    print(f"命令: {' '.join(cmd)}")
    print("-" * 60)
    
    result = subprocess.run(cmd)
    
    print("-" * 60)
    if result.returncode == 0:
        print(f"步骤 {step_id} 执行成功！")
    else:
        print(f"步骤 {step_id} 执行失败，返回码: {result.returncode}")
    
    return result.returncode


def main():
    parser = argparse.ArgumentParser(
        description="Roleplay数据集处理流水线入口",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 列出所有可用步骤
  python -m src.rp-datapipeline.run --list
  
  # 运行步骤1_1（使用默认参数）
  python -m src.rp-datapipeline.run --step 1_1
  
  # 运行步骤1_1，指定输入输出
  python -m src.rp-datapipeline.run --step 1_1 --input data/raw --output data/processed/1_1_scene_segmentation
  
  # 运行步骤1_1，传递额外参数
  python -m src.rp-datapipeline.run --step 1_1 -- --chunk-size 3000 --min-scene-chars 200
        """
    )
    
    parser.add_argument(
        "--list", "-l",
        action="store_true",
        help="列出所有可用的步骤"
    )
    parser.add_argument(
        "--step", "-s",
        type=str,
        help="要运行的步骤编号（如：1_1）"
    )
    parser.add_argument(
        "--input", "-i",
        type=str,
        help="输入路径（覆盖默认值）"
    )
    parser.add_argument(
        "--output", "-o",
        type=str,
        help="输出路径（覆盖默认值）"
    )
    parser.add_argument(
        "extra_args",
        nargs=argparse.REMAINDER,
        help="传递给具体步骤的额外参数（使用 -- 分隔）"
    )
    
    args = parser.parse_args()
    
    if args.list:
        list_steps()
        return
    
    if not args.step:
        print("错误: 请指定要运行的步骤")
        print()
        parser.print_help()
        return
    
    extra_args = args.extra_args
    if extra_args and extra_args[0] == "--":
        extra_args = extra_args[1:]
    
    return_code = run_step(
        step_id=args.step,
        input_path=args.input,
        output_path=args.output,
        extra_args=extra_args
    )
    
    sys.exit(return_code)


if __name__ == "__main__":
    main()
