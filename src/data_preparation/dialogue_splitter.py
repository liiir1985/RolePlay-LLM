"""Utility for splitting JSONL text fields into multiple lines based on Chinese quotations.

This tool is designed for cleaning novel datasets where dialogue and narration are
mixed on single lines. It splits the 'text' field by identifying Chinese quotation
marks (“” and 「」) and placing each quoted segment and non-quoted segment on its own line.
"""

import argparse
import json
import logging
import os
import re
import sys
from pathlib import Path
from typing import List, Optional

from tqdm import tqdm

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def split_dialogue(text: str) -> str:
    """Splits text into multiple lines based on Chinese quotes and ellipses.

    Segments inside “” or 「」 will be on their own lines.
    Segments between quotes (narration) will be split after 3+ dots or periods.
    Additionally, multiple Chinese periods (。。) in narration will be reduced to one.
    
    If the resulting line count is < 3, a fallback rule splits narration by '。'.

    Args:
        text: The input text to split.

    Returns:
        The split text with segments separated by newlines.
    """
    if not text:
        return ""

    # Regex to capture quoted segments (including the quotes)
    pattern = r'([“「].*?[”」])'
    
    # Split the text, keeping the delimiters (the quotes)
    parts = re.split(pattern, text)
    
    # Intermediate representation to track narration vs dialogue
    # List of (is_narration: bool, content: str)
    processed_segments = []
    for i, part in enumerate(parts):
        if not part.strip():
            continue
        
        if i % 2 == 0:
            # Narration part - Rule 1 & 2
            temp_text = re.sub(r'(\.{3,}|。{3,})', r'\1\n', part)
            for sub_line in temp_text.split('\n'):
                sub_line = sub_line.strip()
                if sub_line:
                    # Replace 2 or more Chinese periods with a single one
                    cleaned_line = re.sub(r'。{2,}', '。', sub_line)
                    processed_segments.append((True, cleaned_line))
        else:
            # Dialogue part
            processed_segments.append((False, part.strip()))
    
    # Check if we need the fallback rule (Total lines < 3)
    if len(processed_segments) < 3:
        final_lines = []
        for is_narration, content in processed_segments:
            if is_narration:
                # Rule 3 Fallback: Split by ordinary periods or exclamation marks
                # Use regex to split after '。', '！' or '!', keeping the punctuation
                sub_splits = re.sub(r'([。！!])(?!["”」]|$)', r'\1\n', content)
                for s in sub_splits.split('\n'):
                    if s.strip():
                        final_lines.append(s.strip())
            else:
                final_lines.append(content)
    else:
        final_lines = [seg[1] for seg in processed_segments]
    
    return "\n".join(final_lines)


def process_file(input_path: Path, output_path: Path) -> None:
    """Processes a single JSONL file, splitting the text field in each entry.

    Args:
        input_path: Path to the input JSONL file.
        output_path: Path to the output JSONL file.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    try:
        with open(input_path, "r", encoding="utf-8") as f_in, \
             open(output_path, "w", encoding="utf-8") as f_out:
            
            for line_number, line in enumerate(f_in, 1):
                line = line.strip()
                if not line:
                    continue
                
                try:
                    data = json.loads(line)
                    if "text" in data:
                        original_text = data["text"]
                        data["text"] = split_dialogue(original_text)
                    
                    f_out.write(json.dumps(data, ensure_ascii=False) + "\n")
                    
                except json.JSONDecodeError:
                    logger.error(f"Failed to parse JSON in {input_path} at line {line_number}")
                except Exception as e:
                    logger.error(f"Unexpected error in {input_path} at line {line_number}: {e}")
                    
    except Exception as e:
        logger.error(f"Failed to open files for processing: {e}")


def main() -> None:
    """Main execution entry point for the dialogue splitter CLI."""
    parser = argparse.ArgumentParser(
        description="Split JSONL 'text' field into multiple lines based on Chinese quotations."
    )
    parser.add_argument(
        "input",
        type=str,
        help="Path to input JSONL file or directory containing JSONL files."
    )
    parser.add_argument(
        "--output",
        type=str,
        default="data/splited",
        help="Output directory (default: data/splited)."
    )
    parser.add_argument(
        "--recursive",
        action="store_true",
        help="Search for .jsonl files recursively if input is a directory."
    )
    parser.add_argument(
        "--suffix",
        type=str,
        default=".jsonl",
        help="Filter files by suffix if input is a directory (default: .jsonl)."
    )

    args = parser.parse_args()

    input_path = Path(args.input)
    output_root = Path(args.output)

    if not input_path.exists():
        logger.error(f"Input path does not exist: {args.input}")
        sys.exit(1)

    files_to_process: List[tuple[Path, Path]] = []

    if input_path.is_file():
        # Single file processing
        rel_output = output_root / input_path.name
        files_to_process.append((input_path, rel_output))
    else:
        # Directory processing
        pattern = f"**/*{args.suffix}" if args.recursive else f"*{args.suffix}"
        for f in input_path.glob(pattern):
            if f.is_file():
                # Maintain relative structure in output directory
                rel_path = f.relative_to(input_path)
                target_path = output_root / rel_path
                files_to_process.append((f, target_path))

    if not files_to_process:
        logger.warning(f"No files found to process in {args.input}")
        return

    logger.info(f"Found {len(files_to_process)} files to process.")
    
    for in_file, out_file in tqdm(files_to_process, desc="Processing files"):
        process_file(in_file, out_file)

    logger.info(f"Processing complete. Output saved to {output_root}")


if __name__ == "__main__":
    main()
