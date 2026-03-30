import os
import logging
import argparse
import time
from pathlib import Path
from typing import List
from src.data_cleaning.preprocessor.simple_annotator import SimpleAnnotator, SimpleBatchResponse

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class DatasetPreprocessor:
    """Orchestrates the preprocessing of a dataset."""
    
    def __init__(self, input_file: Path, batch_size: int = 100):
        """Initializes the preprocessor.
        
        Args:
            input_file: Path to the input story.txt file.
            batch_size: Number of lines to process per LLM call.
        """
        self.input_file = input_file
        self.batch_size = batch_size
        self.annotator = SimpleAnnotator()
        
        # Output directory: a subdirectory in the same folder as the input file
        self.output_dir = input_file.parent / "processed_scenes"
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        self.current_scene_idx = 1
        self.current_scene_lines: List[str] = []

    def save_current_scene(self):
        """Saves the accumulated lines into a scene file."""
        if not self.current_scene_lines:
            return
            
        output_path = self.output_dir / f"{self.current_scene_idx}.txt"
        with open(output_path, "w", encoding="utf-8") as f:
            f.write("\n".join(self.current_scene_lines))
        
        logger.info(f"Saved scene {self.current_scene_idx} to {output_path} ({len(self.current_scene_lines)} lines)")
        self.current_scene_idx += 1
        self.current_scene_lines = []

    def process(self):
        """Reads the input file and processes it in batches."""
        if not self.input_file.exists():
            logger.error(f"Input file not found: {self.input_file}")
            return

        with open(self.input_file, "r", encoding="utf-8") as f:
            all_lines = f.readlines()
        
        total_lines = len(all_lines)
        logger.info(f"Loaded {total_lines} lines from {self.input_file}")
        
        current_idx = 0
        while current_idx < total_lines:
            end_idx = min(current_idx + self.batch_size, total_lines)
            batch = all_lines[current_idx:end_idx]
            
            logger.info(f"Processing lines {current_idx + 1} to {end_idx}...")
            
            # Retry logic for LLM calls
            response = None
            for attempt in range(3):
                response = self.annotator.process_batch(batch)
                if response:
                    break
                logger.warning(f"Batch processing failed (attempt {attempt + 1}). Retrying in 5s...")
                time.sleep(5)
            
            if not response:
                logger.error(f"Failed to process batch starting at line {current_idx + 1} after 3 attempts. Skipping or using original lines?")
                # Fallback: keep original if LLM fails after retries
                for line in batch:
                    self.current_scene_lines.append(line.strip())
                current_idx = end_idx
                continue

            # Process LLM response segments
            for i, segment in enumerate(response.segments):
                # Replace literal \n with actual newlines
                processed_segment = segment.replace("\\n", "\n")
                
                if i > 0:
                    # Subsequent segments mean a new scene started in this batch
                    self.save_current_scene()
                
                self.current_scene_lines.append(processed_segment)
            
            current_idx = end_idx
            
        # Save the last scene
        self.save_current_scene()
        logger.info("Processing complete.")

def main():
    parser = argparse.ArgumentParser(description="Dataset Preprocessing Tool for RolePlay-LLM")
    parser.add_argument("input_file", help="Path to the story.txt file")
    parser.add_argument("--batch_size", type=int, default=100, help="Number of lines per batch (default 100)")
    
    args = parser.parse_args()
    input_file = Path(args.input_file)
    
    preprocessor = DatasetPreprocessor(input_file, args.batch_size)
    preprocessor.process()

if __name__ == "__main__":
    main()
