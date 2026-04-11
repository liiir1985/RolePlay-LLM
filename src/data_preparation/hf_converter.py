"""Module for converting JSONL files into a Hugging Face dataset format for Unsloth.

This tool recursively finds all .jsonl files, combines them, and saves the result
in a Hugging Face compatible directory structure including Parquet files and metadata.
"""

import argparse
import logging
import json
from pathlib import Path
from typing import List, Optional
import sys
import os
from tqdm import tqdm

# Ensure src is in path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from datasets import load_dataset
from src.utils.classifier import TextClassifier

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def convert_jsonl_to_hf(
    input_dir: str,
    output_dir: Optional[str] = None,
    dataset_name: str = "dataset",
    recursive: bool = True,
    classify: bool = False,
    base_url: str = "http://localhost:8000/v1",
    model_name: str = "qwen",
    start_id: int = 1
) -> None:
    """Loads all .jsonl files and converts them into a Hugging Face Parquet dataset.

    Args:
        input_dir: Path to directory containing .jsonl files.
        output_dir: Base output directory. If None, defaults to data/<dataset_name>.
        dataset_name: Name of the dataset (used for folder name and metadata).
        recursive: Whether to search for .jsonl files recursively.
        classify: Whether to perform LLM-based classification.
        base_url: Base URL for the OpenAI-compatible API.
        model_name: Name of the model to use for classification.
        start_id: Starting ID for the dataset.
    """
    input_path = Path(input_dir)
    
    # Resolve output directory
    if output_dir:
        output_path = Path(output_dir)
    else:
        output_path = Path("data") / dataset_name

    if not input_path.is_dir():
        logger.error(f"Input directory not found: {input_dir}")
        return

    # Find all .jsonl files
    pattern = "**/*.jsonl" if recursive else "*.jsonl"
    jsonl_files = [str(f) for f in input_path.glob(pattern)]

    if not jsonl_files:
        logger.warning(f"No .jsonl files found in {input_dir} (recursive={recursive})")
        return

    logger.info(f"Found {len(jsonl_files)} .jsonl files. Loading...")

    try:
        # Load multiple JSONL files as a single dataset split
        dataset = load_dataset("json", data_files=jsonl_files, split="train")
        total_examples = len(dataset)

        # Create target directory structure
        output_path.mkdir(parents=True, exist_ok=True)
        data_dir = output_path / "data"
        data_dir.mkdir(exist_ok=True)

        # Path for intermediate processed data
        temp_jsonl_file = output_path / "temp_processed_data.jsonl"
        
        # Check current progress
        processed_count = 0
        if temp_jsonl_file.exists():
            with open(temp_jsonl_file, "r", encoding="utf-8") as f:
                processed_count = sum(1 for _ in f)
        
        if processed_count >= total_examples:
            logger.info(f"All {total_examples} examples are already processed in {temp_jsonl_file}")
        else:
            if processed_count > 0:
                logger.info(f"Resuming from example {processed_count}/{total_examples}...")
            
            # Initialize classifier if needed
            classifier = None
            if classify:
                logger.info(f"Initializing classifier with base_url={base_url}, model={model_name}...")
                classifier = TextClassifier(base_url=base_url, model_name=model_name)

            # Open temp file in append mode
            mode = "a" if processed_count > 0 else "w"
            i = processed_count # Initialize i for error logging
            try:
                with open(temp_jsonl_file, mode, encoding="utf-8") as f_out:
                    for i in tqdm(range(processed_count, total_examples), desc="Processing data"):
                        example = dataset[i]
                        
                        # Add ID
                        output_entry = {
                            "id": i + start_id,
                            "text": example.get("text", "")
                        }
                        
                        # Include any other existing fields
                        for key, value in example.items():
                            if key not in ["id", "text"]:
                                output_entry[key] = value

                        # Perform classification
                        if classify and classifier:
                            categories = classifier.classify(output_entry["text"])
                            output_entry["categories"] = categories
                        
                        # Write to temp file
                        f_out.write(json.dumps(output_entry, ensure_ascii=False) + "\n")
                        f_out.flush() # Ensure it's written in case of crash
                        
            except KeyboardInterrupt:
                logger.warning("\nProcessing interrupted by user. Progress saved.")
                logger.info(f"You can resume later by running the same command.")
                sys.exit(0)
            except Exception as e:
                logger.error(f"Error during processing at index {i}: {e}")
                raise

        # Load the intermediate results for final conversion
        logger.info(f"Finalizing Parquet conversion from {temp_jsonl_file}...")
        final_dataset = load_dataset("json", data_files=[str(temp_jsonl_file)], split="train")

        # Save as Parquet (standard for Unsloth and HF Hub)
        parquet_file = data_dir / "train-00000-of-00001.parquet"
        final_dataset.to_parquet(str(parquet_file))
        logger.info(f"Saved Parquet file to {parquet_file}")

        # Generate dataset_info.json (Standard HF Metadata)
        final_dataset.info.write_to_directory(str(output_path))
        logger.info(f"Generated dataset_info.json in {output_path}")

        # Generate metadata.json
        metadata_file = output_path / "metadata.json"
        metadata = {
            "dataset_name": dataset_name,
            "total_examples": len(final_dataset),
            "features": list(final_dataset.features.keys()),
            "format": "parquet",
            "splits": {
                "train": {
                    "file": "data/train-00000-of-00001.parquet",
                    "num_examples": len(final_dataset)
                }
            }
        }
        with open(metadata_file, "w", encoding="utf-8") as f:
            json.dump(metadata, f, indent=4, ensure_ascii=False)
        logger.info(f"Generated {metadata_file}")

        # Optional: cleanup temp file? 
        # Better to keep it for safety or until explicitly deleted.
        # logger.info(f"Temporary file {temp_jsonl_file} preserved.")

        logger.info(f"Successfully converted {len(final_dataset)} examples to HF format in {output_path}")

    except Exception as e:
        logger.error(f"Failed to convert dataset: {e}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Convert JSONL files to a Hugging Face Parquet dataset (Unsloth compatible)."
    )
    parser.add_argument(
        "input_dir",
        type=str,
        help="Path to the directory containing .jsonl files"
    )
    parser.add_argument(
        "--output_dir",
        type=str,
        default=None,
        help="Base path where the dataset will be saved (default: data/<dataset_name>)"
    )
    parser.add_argument(
        "--dataset_name",
        type=str,
        default="dataset",
        help="Name of the dataset (default: dataset)"
    )
    parser.add_argument(
        "--no-recursive",
        action="store_false",
        dest="recursive",
        help="Do not search subdirectories for .jsonl files"
    )
    parser.set_defaults(recursive=True)

    # New classification and ID arguments
    parser.add_argument(
        "--classify",
        action="store_true",
        help="Enable LLM-based text classification during conversion"
    )
    parser.add_argument(
        "--base-url",
        type=str,
        default="http://106.75.68.112:8081/v1",
        help="Base URL for the OpenAI-compatible API"
    )
    parser.add_argument(
        "--model",
        type=str,
        default="qwen",
        help="Name of the model to use for classification"
    )
    parser.add_argument(
        "--start-id",
        type=int,
        default=1,
        help="Starting ID for the dataset (default: 1)"
    )

    args = parser.parse_args()
    args.classify = True
    convert_jsonl_to_hf(
        args.input_dir, 
        args.output_dir, 
        args.dataset_name, 
        args.recursive,
        classify=args.classify,
        base_url=args.base_url,
        model_name=args.model,
        start_id=args.start_id
    )
