"""Tool for converting text JSONL files into ChatML format with LLM-generated system prompts.

This script traverses a directory recursively, handles file discovery, progress tracking,
and resumable execution. The actual data processing logic is delegated to specific
processor implementations.
"""

import argparse
import json
import logging
import os
import random
import sys
from pathlib import Path
from tqdm import tqdm

# Import the processor logic
try:
    # Try relative import first
    from .chatml_processor import ChatMLProcessor, SystemPromptGenerator
    from .roleplay_processor import RolePlayProcessor
except ImportError:
    # Fallback to absolute or direct import if run as a script
    sys.path.append(os.path.dirname(os.path.abspath(__file__)))
    from chatml_processor import ChatMLProcessor, SystemPromptGenerator
    from roleplay_processor import RolePlayProcessor

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def count_file_lines(file_path: Path) -> int:
    """Quickly count the number of lines in a file."""
    count = 0
    try:
        with open(file_path, "rb") as f:
            for line in f:
                count += 1
    except Exception:
        pass
    return count

def main():
    parser = argparse.ArgumentParser(
        description="Convert text JSONL files using a specific data processor."
    )
    parser.add_argument("input_dir", type=str, help="Path to directory containing .jsonl files")
    parser.add_argument("output_dir", type=str, nargs='?', default="data/sft", help="Directory to save the converted files (default: data/sft)")
    parser.add_argument(
        "--base-url", 
        type=str, 
        default="http://127.0.0.1:8081/v1", 
        help="Base URL for the OpenAI-compatible API"
    )
    parser.add_argument(
        "--model", 
        type=str, 
        default="qwen", 
        help="Name of the model to use for prompt generation"
    )
    parser.add_argument(
        "--api-key",
        type=str,
        default="sk-no-key",
        help="API key for the OpenAI-compatible service"
    )
    parser.add_argument(
        "--include-keywords",
        type=str,
        default="[2398, 3724, 2356, 2419, 4076, 3618, 3123, 2025, 2237, 3126, 3946, 4423, 3247, 4060, 3037, 4325, 2071, 4211, 3006, 3223, 4208, 3968, 2461, 2477, 2228, 3455, 2440, 4043, 2211, 4115,2139, 3176, 4503, 4469, 2198, 4223, 2403, 4069, 3579, 2264, 3716, 4436, 4461, 4454, 3723, 3949, 2005, 3496, 4455, 3886, 3029, 4309, 3958, 3068, 3758, 4360, 3571, 3079, 2349, 4329]",
        help="JSON array of strings/numbers that filenames must contain, in processing order."
    )
    parser.add_argument(
        "--processor",
        type=str,
        choices=["chatml", "roleplay"],
        default="roleplay",
        help="The data processor to use (chatml or roleplay)"
    )
    parser.add_argument(
        "--random-n",
        type=int,
        default=None,
        help="Randomly sample N entries across all filtered files for processing."
    )

    args = parser.parse_args()

    input_path = Path(args.input_dir)
    output_path = Path(args.output_dir)

    if not input_path.is_dir():
        logger.error(f"Input directory not found: {args.input_dir}")
        sys.exit(1)

    # Find all .jsonl files recursively
    all_jsonl_files = list(input_path.glob("**/*.jsonl"))
    if not all_jsonl_files:
        logger.warning(f"No .jsonl files found in {args.input_dir}")
        return

    # Parse keywords
    try:
        keywords = json.loads(args.include_keywords)
        if not isinstance(keywords, list):
            logger.error("--include-keywords must be a JSON array")
            sys.exit(1)
        # Convert all keywords to strings for matching
        keywords = [str(k) for k in keywords]
    except json.JSONDecodeError:
        logger.error(f"Failed to parse --include-keywords as JSON: {args.include_keywords}")
        sys.exit(1)

    # Filter and sort files based on keywords
    jsonl_files = []
    seen_files = set()
    
    if keywords:
        logger.info(f"Filtering files based on {len(keywords)} keywords in order...")
        for kw in keywords:
            # Find files containing this keyword in their name
            matching_files = [f for f in all_jsonl_files if kw in f.name and f not in seen_files]
            # Optional: sort matching files for this specific keyword alphabetically
            matching_files.sort(key=lambda x: x.name)
            
            for f in matching_files:
                jsonl_files.append(f)
                seen_files.add(f)
        
        if not jsonl_files:
            logger.warning("No files matched any of the provided keywords.")
            return
    else:
        jsonl_files = all_jsonl_files

    # Count total entries for progress bar
    logger.info("Counting total entries across all files...")
    total_entries = sum(count_file_lines(f) for f in jsonl_files)
    
    logger.info(f"Filtered to {len(jsonl_files)} files with {total_entries} total entries. Initializing generator and processor...")
    
    # Initialize the specific processor implementation
    if args.processor == "roleplay":
        processor = RolePlayProcessor(
            base_url=args.base_url,
            model_name=args.model,
            api_key=args.api_key
        )
    else:
        generator = SystemPromptGenerator(
            base_url=args.base_url, 
            model_name=args.model,
            api_key=args.api_key
        )
        processor = ChatMLProcessor(generator)

    if args.random_n is not None:
        logger.info(f"Sampling {args.random_n} random entries...")
        all_entries = []
        for file_path in jsonl_files:
            num_lines = count_file_lines(file_path)
            for i in range(num_lines):
                all_entries.append((file_path, i))
        
        sampled_entries = random.sample(all_entries, min(len(all_entries), args.random_n))
        # Sort by file path then line index to optimize sequential reading
        sampled_entries.sort()
        
        output_file = output_path / "sampled_output.jsonl"
        output_path.mkdir(parents=True, exist_ok=True)
        
        logger.info(f"Processing {len(sampled_entries)} sampled entries to {output_file}...")
        
        with tqdm(total=len(sampled_entries), desc="Sampling entries") as pbar:
            current_file = None
            f_in = None
            try:
                with open(output_file, "w", encoding="utf-8") as f_out:
                    for file_path, line_idx in sampled_entries:
                        if file_path != current_file:
                            if f_in:
                                f_in.close()
                            current_file = file_path
                            f_in = open(file_path, "r", encoding="utf-8")
                            last_idx = -1
                        
                        # Move to the desired line
                        # Since sampled_entries is sorted by line_idx, we can just continue calling next()
                        for _ in range(line_idx - last_idx):
                            line = f_in.readline()
                        last_idx = line_idx
                        
                        if line:
                            try:
                                data = json.loads(line.strip())
                                processed_data = processor.process(data)
                                if processed_data:
                                    f_out.write(json.dumps(processed_data, ensure_ascii=False) + "\n")
                                    f_out.flush()
                            except Exception as e:
                                logger.error(f"Error processing sampled line in {file_path}: {e}")
                        
                        pbar.update(1)
            finally:
                if f_in:
                    f_in.close()
        
        logger.info(f"Sampled processing complete. Results saved to {output_file}")
        return

    # Original sequential processing loop
    with tqdm(total=total_entries, desc="Processing entries") as pbar:
        try:
            for file_path in jsonl_files:
                # Determine relative output path
                rel_path = file_path.relative_to(input_path)
                target_file = output_path / rel_path
                target_file.parent.mkdir(parents=True, exist_ok=True)

                # Check current progress for this file
                processed_in_file = 0
                if target_file.exists():
                    processed_in_file = count_file_lines(target_file)
                
                if processed_in_file > 0:
                    pbar.update(processed_in_file)
                
                # If everything in this file is processed, skip
                input_file_lines = count_file_lines(file_path)
                if processed_in_file >= input_file_lines:
                    continue

                mode = "a" if processed_in_file > 0 else "w"
                with open(file_path, "r", encoding="utf-8") as f_in, \
                     open(target_file, mode, encoding="utf-8") as f_out:
                    
                    # Skip already processed lines
                    for _ in range(processed_in_file):
                        next(f_in, None)

                    for line in f_in:
                        line = line.strip()
                        if not line:
                            pbar.update(1)
                            continue
                        
                        try:
                            data = json.loads(line)
                            
                            processed_data = processor.process(data)
                            if processed_data:
                                f_out.write(json.dumps(processed_data, ensure_ascii=False) + "\n")
                                f_out.flush() # Ensure it's written in case of interruption
                            
                        except json.JSONDecodeError:
                            logger.error(f"Failed to parse JSON line in {file_path}")
                        except Exception as e:
                            logger.error(f"Error processing line in {file_path}: {e}")
                        finally:
                            pbar.update(1)
                            
        except KeyboardInterrupt:
            logger.warning("\nProcessing interrupted by user. Progress saved.")
            logger.info("You can resume later by running the same command.")
            sys.exit(0)
        except Exception as e:
            logger.error(f"Unexpected error during processing: {e}")
            raise

    logger.info(f"Successfully processed files. Output saved to {args.output_dir}")

if __name__ == "__main__":
    main()
