"""Module for converting JSONL files into a Hugging Face dataset format for Unsloth.

This tool recursively finds all .jsonl files, combines them, and saves the result
in a Hugging Face compatible directory structure including Parquet files and metadata.
"""

import argparse
import logging
import json
from pathlib import Path
from typing import List, Optional
from datasets import load_dataset

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
    recursive: bool = True
) -> None:
    """Loads all .jsonl files and converts them into a Hugging Face Parquet dataset.

    Args:
        input_dir: Path to directory containing .jsonl files.
        output_dir: Base output directory. If None, defaults to data/<dataset_name>.
        dataset_name: Name of the dataset (used for folder name and metadata).
        recursive: Whether to search for .jsonl files recursively.
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

        # Create target directory structure
        output_path.mkdir(parents=True, exist_ok=True)
        data_dir = output_path / "data"
        data_dir.mkdir(exist_ok=True)

        # Save as Parquet (standard for Unsloth and HF Hub)
        # Using a naming convention similar to HF Hub: train-XXXXX-of-XXXXX.parquet
        parquet_file = data_dir / "train-00000-of-00001.parquet"
        dataset.to_parquet(str(parquet_file))
        logger.info(f"Saved Parquet file to {parquet_file}")

        # Generate dataset_info.json (Standard HF Metadata)
        # Re-using write_to_directory which is available on DatasetInfo
        dataset.info.write_to_directory(str(output_path))
        logger.info(f"Generated dataset_info.json in {output_path}")

        # Generate metadata.json (requested by user for Unsloth compatibility)
        metadata_file = output_path / "metadata.json"
        metadata = {
            "dataset_name": dataset_name,
            "total_examples": len(dataset),
            "features": list(dataset.features.keys()),
            "format": "parquet",
            "splits": {
                "train": {
                    "file": "data/train-00000-of-00001.parquet",
                    "num_examples": len(dataset)
                }
            }
        }
        with open(metadata_file, "w", encoding="utf-8") as f:
            json.dump(metadata, f, indent=4, ensure_ascii=False)
        logger.info(f"Generated {metadata_file}")

        logger.info(f"Successfully converted {len(dataset)} examples to HF format in {output_path}")

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

    args = parser.parse_args()
    convert_jsonl_to_hf(args.input_dir, args.output_dir, args.dataset_name, args.recursive)
