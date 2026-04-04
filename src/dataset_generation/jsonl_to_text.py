import argparse
import json
import os
import sys
from typing import Any, Dict, List, Optional
from tqdm import tqdm


def flatten_messages(messages: List[Dict[str, str]]) -> str:
    """Flatten a list of ChatML messages into a single string.

    Args:
        messages: List of message dictionaries with 'role' and 'content'.

    Returns:
        A concatenated string in the format 'role:content\n...'.
    """
    lines = []
    for msg in messages:
        role = msg.get("role", "unknown")
        content = msg.get("content", "")
        reasoning = msg.get("reasoning", "")
        
        if reasoning:
            lines.append(f"{role}:\n{reasoning}\n{content}")
        else:
            lines.append(f"{role}:{content}")
    return "\n".join(lines)


def process_file(input_file: str, output_file: str) -> None:
    """Process a single JSONL file, flattening messages to text.

    Args:
        input_file: Path to the input JSONL file.
        output_file: Path to the output JSONL file.
    """
    os.makedirs(os.path.dirname(output_file), exist_ok=True)

    with open(input_file, "r", encoding="utf-8") as f_in, \
         open(output_file, "w", encoding="utf-8") as f_out:
        
        for line_idx, line in enumerate(f_in, 1):
            line = line.strip()
            if not line:
                continue
            
            try:
                data = json.loads(line)
                if "messages" not in data:
                    print(f"Error: Missing 'messages' field in {input_file} at line {line_idx}", file=sys.stderr)
                    continue
                
                messages = data["messages"]
                if not isinstance(messages, list):
                    print(f"Error: 'messages' field is not a list in {input_file} at line {line_idx}", file=sys.stderr)
                    continue
                
                flattened_text = flatten_messages(messages)
                output_data = {"text": flattened_text}
                
                f_out.write(json.dumps(output_data, ensure_ascii=False) + "\n")
                
            except json.JSONDecodeError:
                print(f"Error: Failed to parse JSON in {input_file} at line {line_idx}", file=sys.stderr)
            except Exception as e:
                print(f"Error: Unexpected error processing {input_file} at line {line_idx}: {e}", file=sys.stderr)


def main():
    parser = argparse.ArgumentParser(description="Convert JSONL files: flatten 'messages' field into a single 'text' field.")
    parser.add_argument("input_dir", type=str, help="Directory containing input JSONL files.")
    parser.add_argument("--output_dir", type=str, default="data/processed/converted", help="Directory to save converted JSONL files (default: data/processed/converted).")
    parser.add_argument("--suffix", type=str, default=".jsonl", help="File suffix to process (default: .jsonl).")

    args = parser.parse_args()

    input_dir = os.path.abspath(args.input_dir)
    output_dir = os.path.abspath(args.output_dir)

    if not os.path.isdir(input_dir):
        print(f"Error: Input directory does not exist: {input_dir}", file=sys.stderr)
        sys.exit(1)

    # Collect all matching files
    files_to_process = []
    for root, _, filenames in os.walk(input_dir):
        for filename in filenames:
            if filename.endswith(args.suffix):
                input_path = os.path.join(root, filename)
                # Calculate relative path to maintain structure
                rel_path = os.path.relpath(input_path, input_dir)
                output_path = os.path.join(output_dir, rel_path)
                files_to_process.append((input_path, output_path))

    if not files_to_process:
        print(f"No files with suffix '{args.suffix}' found in {input_dir}")
        return

    print(f"Found {len(files_to_process)} files to process.")
    
    for input_file, output_file in tqdm(files_to_process, desc="Processing files"):
        process_file(input_file, output_file)

    print(f"Processing completed. Results saved to: {output_dir}")


if __name__ == "__main__":
    main()
