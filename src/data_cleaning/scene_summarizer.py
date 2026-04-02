import os
import argparse
import logging
import re
from pathlib import Path
from google import genai
from google.genai import types
from src.data_cleaning.config import GEMINI_API_KEY, DEFAULT_MODEL

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class SceneSummarizer:
    """
    Sequentially summarizes scene files in a directory using Gemini.
    Passes the summary of the previous scene as the 'preface' of the next.
    """
    
    def __init__(self, api_key: str = GEMINI_API_KEY, model_name: str = DEFAULT_MODEL):
        """
        Initialize the summarizer with Gemini API client.
        
        Args:
            api_key: Gemini API Key.
            model_name: The Gemini model to use.
        """
        self.client = genai.Client(api_key=api_key)
        self.model_name = model_name
        self.current_preface = ""

    def summarize_scene(self, preface: str, body: str) -> str:
        """
        Sends context (preface) and scene body to Gemini and returns a concise summary.
        
        Args:
            preface: Summary of previous scenes.
            body: Content of the current scene.
            
        Returns:
            A concise summary of the current scene.
        """
        system_instruction = (
            "你是一个专精于角色扮演故事的总结专家。我会给你一段“前情提要”和一段“当前正文”。\n"
            "请将提供的“前情提要”与“当前正文”结合起来，生成一个涵盖至今为止核心剧情进展和角色状态的简洁总结，需要确保前情提要里的内容是否已在总结中体现。\n"
            "这个总结将作为下一段的前情提要。\n"
            "仅返回总结内容，不要包含任何引导语、解释或废话。\n"
        )

        system_instruction2 = ("""
# Role
# Role
你是一位极其严谨的 AI 数据工程师。你的任务是对给定的“小说/剧本原始文本”进行**无损的切片手术**，并将其转化为标准的 **OpenAI/ChatML 格式 JSON** 样本。同时，你需要为其注入用于强化学习的“系统设定”和“思维链（CoT）”。

# Core Rules & Constraints (绝对铁律)

### 1. 原文零篡改原则（Zero-Modification）
- **禁止任何润色、删减或增加**：你提取到 `user` 和 `assistant` 字段中的非 think 文本，拼接起来必须与原始文本**一字不差**（包括所有的标点符号、换行、全半角符号）。
- 你的工作仅仅是**“划分归属权”**，绝不允许替原作者改写哪怕一个字。
- 你需要编辑的内容为正文部分的内容，前情提要用来生成系统提示词
- **划分界限**：
  - `user` 角色：**仅**包含【用户扮演角色】直接产生的文字（该角色的对话、该角色的心理活动、明确主语是该角色的动作）。
  - `assistant` 角色：包含**所有剩余内容**（上帝视角的旁白叙事、环境描写、其他配角的戏份、以及【AI重点扮演角色】的言行和心理）。

### 2. System Prompt 沉浸原则
- `system` 角色的内容是给**最终训练出的 AI** 看的。
- **绝对禁止**在 `system` 中出现诸如“user角色包含什么”、“你需要切分文本”、“输出JSON”这类数据处理和切分指令。
- `system` 必须是一段沉浸式的设定声明，包含：职责定位（DM兼NPC）、双方扮演身份、世界观隐性规则，以及要求开启 think 标签的设定。
- 系统提示词需要考虑前情提要的内容并体现其内容，但是系统提示词中不应该包含正文部分的情节。

### 3. 思维链 (CoT) 自由发散原则
- 只能在 `assistant` 角色的 `content` 原文内容**之前**，插入一段由你原创的 `<think>...</think>`。
- **思考内容要求**：你需要以 DM 和该角色的双重身份，推演**为什么会发生接下来的原文情节**。思考维度可自由发散（如：玩家行为触发了哪条规则？当前场景的氛围该如何转场？角色的表层动作掩盖了怎样的深层心理？）。思考内容需要至少200字

# Output Format
你必须输出合法的纯 JSON 代码，格式严格如下：

{
  "messages": [
    {
      "role": "system",
      "content": "[Thought: Medium]..."
    },
    {
      "role": "user",
      "content": "【严格照抄原文中属于用户的片段】"
    },
    {
      "role": "assistant",
      "content": "<think>\n【由你原创：发散性的逻辑推演与心理分析】\n</think>\n【严格照抄原文中接续的旁白、配角或核心角色的片段】"
    }
    // 根据原文交互顺序，继续无损交替切割
  ]
}

---
# Input Data

- **【用户/Human】扮演的角色**：桐崎冬马
- **【大模型/AI】重点扮演的核心角色**：九条桃华
            """
        )
        
        #prompt = f"## 前情提要\n{preface if preface else '（无）'}\n\n# 当前正文\n{body}"
        prompt = f"# 当前正文\n{body}"
        
        try:
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction2,
                    temperature=0.7,
                ),
            )
            return response.text.strip()
        except Exception as e:
            logger.error(f"Error calling Gemini: {e}")
            return "（总结失败）"

    def _natural_key(self, text: str):
        """
        Helper for natural sorting of filenames (e.g., 2.txt before 10.txt).
        """
        return [int(c) if c.isdigit() else c.lower() for c in re.split(r'(\d+)', text)]

    def process_directory(self, directory_path: str):
        """
        Processes all .txt files in the directory in natural alphabetical order.
        Overwrites each file with its preface, body, and summary.
        
        Args:
            directory_path: Path to the directory containing scene files.
        """
        path = Path(directory_path)
        if not path.is_dir():
            logger.error(f"Directory not found: {directory_path}")
            return

        # Get all .txt files and sort them naturally
        files = sorted(
            [f for f in path.glob("*.txt") if f.is_file()],
            key=lambda x: self._natural_key(x.name)
        )

        if not files:
            logger.info("No .txt files found in the specified directory.")
            return

        logger.info(f"Found {len(files)} files to process in {path}")

        # Create output directory within the source directory
        output_dir = path / "summarized"
        output_dir.mkdir(exist_ok=True)
        logger.info(f"Saving processed files to: {output_dir}")

        for file_path in files:
            logger.info(f"Processing file: {file_path.name}")
            
            try:
                # Read original content as body
                with open(file_path, 'r', encoding='utf-8') as f:
                    body = f.read().strip()

                if not body:
                    logger.warning(f"File {file_path.name} is empty. Skipping.")
                    continue

                # Generate summary
                summary = self.summarize_scene(self.current_preface, body)
                
                # Format output exactly as requested
                new_content = (
                    f"##前情提要\n{self.current_preface}\n\n"
                    f"##正文\n{body}\n\n"
                    f"##总结\n{summary}"
                )
                
                # Save to the summarized subdirectory
                output_file = output_dir / file_path.name
                with open(output_file, 'w', encoding='utf-8', newline='\n') as f:
                    f.write(new_content)
                
                logger.info(f"Successfully processed {file_path.name}")
                
                # Update preface for the next file
                self.current_preface = summary
                
            except Exception as e:
                logger.error(f"Failed to process {file_path.name}: {e}")

def main():
    parser = argparse.ArgumentParser(description="Dataset tool for sequential scene summarization.")
    parser.add_argument("directory", help="The directory containing scene .txt files.")
    parser.add_argument("--model", default=DEFAULT_MODEL, help=f"Gemini model to use (default: {DEFAULT_MODEL}).")
    args = parser.parse_args()

    summarizer = SceneSummarizer(model_name=args.model)
    summarizer.process_directory(args.directory)

if __name__ == "__main__":
    main()
