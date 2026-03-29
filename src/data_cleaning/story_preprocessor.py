import os
import json
import logging
import argparse
from pathlib import Path
from src.data_cleaning.preprocessor.processor import StoryProcessor
from src.data_cleaning.config import DEFAULT_BATCH_SIZE

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("preprocessing.log", encoding="utf-8"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

def load_main_characters(input_dir: Path) -> list:
    index_file = input_dir / "index.json"
    if not index_file.exists():
        logger.error(f"index.json not found in {input_dir}")
        return []
    
    with open(index_file, "r", encoding="utf-8") as f:
        data = json.load(f)
        chars = data.get("characters", {})
        if isinstance(chars, dict):
            return list(chars.keys())
        elif isinstance(chars, list):
            return chars
        return []

def main():
    parser = argparse.ArgumentParser(description="RolePlay-LLM Dataset Preprocessing Tool")
    parser.add_argument("input_dir", help="Directory containing index.json and story.txt")
    parser.add_argument("--batch_size", type=int, default=200, help="Batch size for LLM processing (default 200)")
    
    args = parser.parse_args()
    input_dir = Path(args.input_dir)
    
    if not input_dir.exists():
        logger.error(f"Input directory does not exist: {input_dir}")
        return

    main_chars = load_main_characters(input_dir)
    if not main_chars:
        logger.error("No main characters found in index.json. Aborting.")
        return

    logger.info(f"Main characters identified: {main_chars}")
    
    processor = StoryProcessor(
        input_dir=input_dir,
        main_characters=main_chars,
        batch_size=args.batch_size
    )
    
    try:
        processor.process_story()
        if not processor.interrupt_handler.interrupted:
            logger.info("Processing completed successfully.")
        else:
            logger.warning("Processing interrupted by user.")
    except Exception as e:
        logger.exception(f"An unexpected error occurred: {e}")

if __name__ == "__main__":
    main()
