import argparse
import json
import os
import re
from typing import Any, Dict, List, Optional

from datasets import load_dataset
from tqdm import tqdm


class HFDatasetFetcher:
    """Fetcher for Hugging Face datasets with streaming and sharding support."""

    def __init__(self, config_path: str = "configs/dataset_mappings.json"):
        """Initialize the fetcher with mapping configurations.

        Args:
            config_path: Path to the JSON configuration file containing mappings.
        """
        self.config_path = config_path
        self.mappings = self._load_config()

    def _load_config(self) -> Dict[str, Any]:
        """Load mapping configurations from the JSON file."""
        if not os.path.exists(self.config_path):
            raise FileNotFoundError(f"Configuration file not found: {self.config_path}")
        with open(self.config_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def _extract_repo_id(self, url_or_id: str) -> str:
        """Extract the Hugging Face repository ID from a URL or string.

        Args:
            url_or_id: The HF dataset URL or ID (e.g., 'A/B' or 'https://huggingface.co/datasets/A/B').

        Returns:
            The repository ID (e.g., 'A/B').
        """
        # Matches https://huggingface.co/datasets/username/repo or huggingface.co/datasets/username/repo
        match = re.search(r"huggingface\.co/datasets/([^/?#]+/[^/?#]+)", url_or_id)
        if match:
            return match.group(1)
        return url_or_id

    def _map_to_chatml(self, entry: Dict[str, Any], mapping_name: str) -> Optional[Dict[str, Any]]:
        """Map a dataset entry to ChatML format based on the selected mapping.

        Args:
            entry: A single row from the dataset.
            mapping_name: The name of the mapping to use.

        Returns:
            A dictionary containing mapped fields (e.g., 'messages', 'prompt'), or None if mapping fails.
        """
        if mapping_name not in self.mappings:
            mapping_name = "default"

        cfg = self.mappings[mapping_name]
        m = cfg["mapping"]
        m_type = cfg["type"]

        result = {}
        try:
            # 1. Handle direct mapping (no ChatML wrapping)
            if m_type == "direct":
                for key, source_col in m.items():
                    result[key] = entry.get(source_col)
                return result

            # 2. Handle standard conversation mappings (ChatML)
            messages = None
            if m_type == "openai":
                messages = entry.get(m["messages"])
            elif m_type == "alpaca":
                instruction = entry.get(m["instruction"], "")
                user_input = entry.get(m["input"], "")
                output = entry.get(m["output"], "")
                content = f"{instruction}\n\n{user_input}".strip()
                messages = [
                    {"role": "user", "content": content},
                    {"role": "assistant", "content": output}
                ]
            elif m_type == "prompt_completion":
                messages = [
                    {"role": "user", "content": entry.get(m["prompt"], "")},
                    {"role": "assistant", "content": entry.get(m["completion"], "")}
                ]
            elif m_type == "sharegpt":
                convs = entry.get(m["conversations"], [])
                messages = []
                for c in convs:
                    role = "user" if c.get(m["from"]) in ["human", "user"] else "assistant"
                    messages.append({"role": role, "content": c.get(m["value"], "")})
            elif m_type == "reasoning":
                problem = entry.get(m["problem"], "")
                thinking = entry.get(m["thinking"], "")
                solution = entry.get(m["solution"], "")
                combined_content = f"<thought>\n{thinking}\n</thought>\n\n{solution}" if thinking else solution
                messages = [
                    {"role": "user", "content": problem},
                    {"role": "assistant", "content": combined_content}
                ]
            
            if messages is not None:
                result["messages"] = messages

            # 3. Map any additional fields specified in the config
            for key, source_col in m.items():
                if key in result:
                    continue
                result[key] = entry.get(source_col)

        except Exception as e:
            return None
        
        return result if result else None

    def fetch(
        self,
        dataset_url_or_id: str,
        output_dir: str,
        total_limit_mb: float = 100.0,
        shard_limit_mb: float = 10.0,
        mapping_name: str = "default",
        shuffle_buffer: int = 10000,
        split: str = "train",
        subsets: Optional[List[str]] = None,
        trust_remote_code: bool = False,
    ) -> None:
        """Fetch, shuffle, and save the dataset in sharded JSONL files.

        Args:
            dataset_url_or_id: HF dataset URL or ID.
            output_dir: Directory to save the shards.
            total_limit_mb: Global size limit for the fetched data.
            shard_limit_mb: Size limit per JSONL file.
            mapping_name: Mapping configuration to use.
            shuffle_buffer: Buffer size for streaming shuffle.
            split: Dataset split to load (e.g., 'train').
            subsets: List of dataset configurations (subsets) to fetch.
            trust_remote_code: Whether to trust remote code (required for some legacy datasets).
        """
        repo_id = self._extract_repo_id(dataset_url_or_id)
        safe_repo_name = repo_id.replace("/", "_")
        
        # Determine the subsets to iterate over
        subsets_to_fetch = subsets if subsets else [None]

        for subset in subsets_to_fetch:
            # Create a specific subdirectory for this dataset and subset
            subset_label = subset if subset else "default"
            target_dir = os.path.join(output_dir, safe_repo_name, subset_label)
            if not os.path.exists(target_dir):
                os.makedirs(target_dir)

            print(f"\n[{subset_label}] Loading dataset: {repo_id} (subset: {subset_label}, split: {split})")
            print(f"[{subset_label}] Saving to: {target_dir}")

            try:
                # Load in streaming mode
                ds = load_dataset(
                    repo_id, 
                    name=subset, 
                    split=split, 
                    streaming=True, 
                    trust_remote_code=trust_remote_code
                )
                ds = ds.shuffle(buffer_size=shuffle_buffer, seed=3252)

                total_bytes_limit = total_limit_mb * 1024 * 1024
                shard_bytes_limit = shard_limit_mb * 1024 * 1024

                bytes_written_total = 0
                bytes_written_current_shard = 0
                shard_index = 0
                
                pbar = tqdm(total=int(total_limit_mb), unit="MB", desc=f"Downloading {subset_label}")

                current_file = None
                
                try:
                    for entry in ds:
                        if bytes_written_total >= total_bytes_limit:
                            break

                        mapped_entry = self._map_to_chatml(entry, mapping_name)
                        if not mapped_entry:
                            continue

                        line = json.dumps(mapped_entry, ensure_ascii=False) + "\n"
                        line_bytes = len(line.encode("utf-8"))

                        # Check if we need to start a new shard
                        if current_file is None or (bytes_written_current_shard + line_bytes > shard_bytes_limit):
                            if current_file:
                                current_file.close()
                            
                            shard_index += 1
                            file_path = os.path.join(target_dir, f"shard_{shard_index:03d}.jsonl")
                            current_file = open(file_path, "w", encoding="utf-8")
                            bytes_written_current_shard = 0

                        current_file.write(line)
                        bytes_written_current_shard += line_bytes
                        bytes_written_total += line_bytes
                        
                        # Update progress bar
                        current_mb = bytes_written_total / (1024 * 1024)
                        pbar.n = min(int(current_mb), int(total_limit_mb))
                        pbar.refresh()

                finally:
                    if current_file:
                        current_file.close()
                    pbar.close()

                print(f"[{subset_label}] Done! Total written: {bytes_written_total / (1024 * 1024):.2f} MB")
            
            except Exception as e:
                print(f"[{subset_label}] Error loading subset: {e}")

        print(f"\nAll tasks completed for {repo_id}!")


def main():
    parser = argparse.ArgumentParser(description="Hugging Face Dataset Scraper (ChatML format)")
    parser.add_argument("url", type=str, help="HF Dataset URL or repository ID")
    parser.add_argument("--output", type=str, default="data/raw/hf_datasets", help="Output directory")
    parser.add_argument("--total-limit", type=float, default=100.0, help="Total size limit in MB (default 100)")
    parser.add_argument("--shard-limit", type=float, default=10.0, help="Shard size limit in MB (default 10)")
    parser.add_argument("--mapping", type=str, default="default", help="Mapping name from configs/dataset_mappings.json")
    parser.add_argument("--buffer", type=int, default=10000, help="Shuffle buffer size (default 10000)")
    parser.add_argument("--split", type=str, default="train", help="Dataset split to use (default 'train')")
    parser.add_argument("--subset", type=str, nargs="+", default=None, help="Specific subset(s) of the dataset to fetch (list)")
    parser.add_argument("--config", type=str, default="configs/dataset_mappings.json", help="Path to mapping config")
    parser.add_argument("--trust", action="store_true", help="Trust remote code (required for some datasets with custom scripts)")

    args = parser.parse_args()

    fetcher = HFDatasetFetcher(config_path=args.config)
    fetcher.fetch(
        dataset_url_or_id=args.url,
        output_dir=args.output,
        total_limit_mb=args.total_limit,
        shard_limit_mb=args.shard_limit,
        mapping_name=args.mapping,
        shuffle_buffer=args.buffer,
        split=args.split,
        subsets=args.subset,
        trust_remote_code=args.trust
    )


if __name__ == "__main__":
    main()
