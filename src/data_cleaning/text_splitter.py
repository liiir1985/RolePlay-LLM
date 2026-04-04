import os
import json
import random
import logging
import argparse
from pathlib import Path
from typing import List, Generator

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class TextSplitter:
    """Processes text files into randomized length segments split at line breaks.
    
    Attributes:
        min_len (int): Minimum character length for a segment.
        max_len (int): Maximum character length for a segment.
    """
    
    def __init__(self, min_len: int = 2000, max_len: int = 4000):
        """Initializes the TextSplitter with length constraints.
        
        Args:
            min_len: Minimum segment length.
            max_len: Maximum segment length.
        """
        self.min_len = min_len
        self.max_len = max_len

    def split_file(self, file_path: Path) -> Generator[str, None, None]:
        """Reads a file and yields segments of random length between min_len and max_len.
        
        Args:
            file_path: Path to the text file to split.
            
        Yields:
            Text segments as strings.
        """
        buffer = ""
        target_len = random.randint(self.min_len, self.max_len)
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                for line in f:
                    # If current buffer + next line exceeds max_len
                    if len(buffer) + len(line) > self.max_len:
                        if len(buffer) >= self.min_len:
                            # Flush current buffer if it meets min_len
                            yield buffer.strip()
                            buffer = line
                            target_len = random.randint(self.min_len, self.max_len)
                        else:
                            # Buffer is too small but adding line exceeds max_len.
                            # To avoid splitting in middle of line, we must include the line.
                            # This segment will technically exceed max_len.
                            buffer += line
                            yield buffer.strip()
                            buffer = ""
                            target_len = random.randint(self.min_len, self.max_len)
                    # If current buffer + next line hits or exceeds random target (but stays <= max_len)
                    elif len(buffer) + len(line) >= target_len:
                        buffer += line
                        yield buffer.strip()
                        buffer = ""
                        target_len = random.randint(self.min_len, self.max_len)
                    else:
                        # Continue accumulating
                        buffer += line
            
            # Flush remaining buffer
            if buffer.strip():
                yield buffer.strip()
                
        except Exception as e:
            logger.error(f"Error processing {file_path}: {e}")

    def process_directory(self, input_dir: Path, output_dir: Path, max_segments_per_file: int = 0):
        """Processes all .txt files in a directory and saves to corresponding .jsonl files.
        
        Args:
            input_dir: Directory containing text files.
            output_dir: Directory to save .jsonl files.
            max_segments_per_file: If > 0, shasrds output into multiple files of this many segments.
        """
        output_dir.mkdir(parents=True, exist_ok=True)
        
        txt_files = list(input_dir.glob("*.txt"))
        if not txt_files:
            logger.warning(f"No .txt files found in {input_dir}")
            return

        for txt_file in txt_files:
            file_stem = txt_file.stem
            logger.info(f"Processing {txt_file}...")
            
            segments = []
            for segment in self.split_file(txt_file):
                if segment:
                    segments.append(segment)
            
            if not segments:
                continue

            # Calculate shards
            if max_segments_per_file > 0 and len(segments) > max_segments_per_file:
                for i in range(0, len(segments), max_segments_per_file):
                    shard_idx = i // max_segments_per_file
                    output_path = output_dir / f"{file_stem}_part{shard_idx}.jsonl"
                    self._write_jsonl(segments[i : i + max_segments_per_file], output_path)
                    logger.info(f"Saved {len(segments[i : i + max_segments_per_file])} segments to {output_path}")
            else:
                output_path = output_dir / f"{file_stem}.jsonl"
                self._write_jsonl(segments, output_path)
                logger.info(f"Saved {len(segments)} segments to {output_path}")

    def _write_jsonl(self, segments: List[str], output_path: Path):
        """Writes a list of segments to a .jsonl file.
        
        Args:
            segments: List of text segments.
            output_path: File path to save to.
        """
        with open(output_path, 'w', encoding='utf-8') as out_f:
            for segment in segments:
                json.dump({"text": segment}, out_f, ensure_ascii=False)
                out_f.write("\n")

def main():
    """CLI entry point for the text splitting tool."""
    parser = argparse.ArgumentParser(description="Split .txt files into individual jsonl segments for RolePlay-LLM.")
    parser.add_argument("input_dir", type=str, help="Directory containing .txt files")
    parser.add_argument("--output_dir", "-o", type=str, default="data/processed/output/", 
                        help="Output directory (default: data/processed/output/)")
    parser.add_argument("--min_len", type=int, default=2000, help="Minimum segment length (default: 2000)")
    parser.add_argument("--max_len", type=int, default=4000, help="Maximum segment length (default: 4000)")
    parser.add_argument("--max_segments", type=int, default=0, 
                        help="Max segments per jsonl file (0 = no sharding, default: 0)")
    
    args = parser.parse_args()
    
    input_dir = Path(args.input_dir)
    output_dir = Path(args.output_dir)
    
    if not input_dir.is_dir():
        logger.error(f"Input directory does not exist: {input_dir}")
        return

    splitter = TextSplitter(min_len=args.min_len, max_len=args.max_len)
    splitter.process_directory(input_dir, output_dir, max_segments_per_file=args.max_segments)

if __name__ == "__main__":
    main()
