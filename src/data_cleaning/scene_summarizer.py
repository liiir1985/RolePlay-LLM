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
        
        prompt = f"## 前情提要\n{preface if preface else '（无）'}\n\n# 当前正文\n{body}"
        
        try:
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction,
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
                    f"#正文\n{body}\n\n"
                    f"#总结\n{summary}"
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
