import pandas as pd
import json
import logging
from typing import List, Optional, Set
from pathlib import Path
from pydantic import BaseModel, Field
from google import genai
from google.genai import types
from tqdm import tqdm
from src.data_cleaning.config import (
    GEMINI_API_KEY, 
    DEFAULT_MODEL, 
    SYSTEM_INSTRUCTION, 
    DEFAULT_INPUT_CSV, 
    DEFAULT_OUTPUT_CSV,
    DEFAULT_BATCH_SIZE
)

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class NovelItem(BaseModel):
    """Structured data for a single light novel."""
    Uid: str = Field(..., description="The unique identifier from the input.")
    genre: Optional[str] = Field(None, description="The genre of the novel.")
    tags: List[str] = Field(default_factory=list, description="Specific tags for the novel.")
    summary: Optional[str] = Field(None, description="A ~200 word plot summary.")
    unknown: bool = Field(False, description="True if the model does not know this work.")

class NovelBatchResponse(BaseModel):
    items: List[NovelItem]

class NovelAugmenter:
    def __init__(self, api_key: str, model_name: str = DEFAULT_MODEL):
        self.client = genai.Client(api_key=api_key)
        self.model_name = model_name
        self.existing_tags: Set[str] = set()

    def load_existing_tags(self, df: pd.DataFrame):
        """Initialize the global tag set from existing data in the CSV."""
        if 'tags' in df.columns:
            for tags_str in df['tags'].dropna():
                # Assuming tags are comma-separated or stored as strings
                if isinstance(tags_str, str):
                    tags_list = [t.strip() for t in tags_str.split(',') if t.strip()]
                    self.existing_tags.update(tags_list)
        logger.info(f"Initialized with {len(self.existing_tags)} existing tags.")

    def format_batch_prompt(self, batch_data: List[dict]) -> str:
        """Format a prompt for a batch of novels."""
        tags_hint = ", ".join(sorted(list(self.existing_tags)))
        works_list = json.dumps(batch_data, ensure_ascii=False, indent=2)
        prompt = f"""
现有标签参考：[{tags_hint}]

待处理作品列表：
{works_list}

请按要求返回每个作品的题材、标签和剧情概要。必须返回相同长度的 JSON 数组。
"""
        return prompt

    def augment_batch(self, batch_data: List[dict]) -> List[NovelItem]:
        """Call Gemini to get augmented info for a batch of novels."""
        try:
            prompt = self.format_batch_prompt(batch_data)
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=SYSTEM_INSTRUCTION,
                    response_mime_type="application/json",
                    response_schema=NovelBatchResponse,
                ),
            )
            
            if not response.text:
                logger.warning("Empty response for batch")
                return []
            
            # Parse the wrapper class
            batch_res = NovelBatchResponse.model_validate_json(response.text)
            validated_items = batch_res.items
            
            # Update global tags from known items
            for item in validated_items:
                if not item.unknown and item.tags:
                    self.existing_tags.update(item.tags)
                    
            return validated_items
        except Exception as e:
            logger.error(f"Error augmenting batch: {e}")
            return []

    def process_csv(self, input_path: str, output_path: str, batch_size: int = DEFAULT_BATCH_SIZE, limit: Optional[int] = None):
        """Process the input CSV and save augmented results in batches with resumption."""
        logger.info(f"Reading input CSV from {input_path}")
        df_in = pd.read_csv(input_path)
        
        if limit:
            df_in = df_in.head(limit)

        # 1. Load existing results for resumption
        df_out = pd.DataFrame()
        processed_names = set()
        if Path(output_path).exists():
            logger.info(f"Loading existing results from {output_path} for resumption.")
            df_out = pd.read_csv(output_path)
            # Identify processed items by name (ensure name column exists)
            name_col = 'Title' if 'Title' in df_out.columns else ('name' if 'name' in df_out.columns else ('title' if 'title' in df_out.columns else None))
            if name_col:
                processed_names = set(df_out[name_col].dropna().unique())
                logger.info(f"Found {len(processed_names)} already processed items.")

        self.load_existing_tags(pd.concat([df_in, df_out]) if not df_out.empty else df_in)

        # 2. Filter unprocessed rows
        name_col_in = 'Title' if 'Title' in df_in.columns else ('name' if 'name' in df_in.columns else ('title' if 'title' in df_in.columns else None))
        if not name_col_in:
            logger.error("Could not find 'Title', 'name' or 'title' column in input CSV.")
            return

        df_todo = df_in[~df_in[name_col_in].isin(processed_names)].copy()
        
        if df_todo.empty:
            logger.info("All items are already processed. Nothing to do.")
            return

        logger.info(f"Remaining items to process: {len(df_todo)}")
        
        # 3. Batch processing loop
        try:
            # We'll need the Uid column
            uid_col = 'Uid' if 'Uid' in df_in.columns else None
            
            for i in range(0, len(df_todo), batch_size):
                batch_df = df_todo.iloc[i : i + batch_size]
                
                # Prepare input data for LLM
                batch_input = []
                for _, row in batch_df.iterrows():
                    batch_input.append({
                        "Uid": str(row.get(uid_col)) if uid_col else "unknown",
                        "Title": str(row.get(name_col_in))
                    })
                
                logger.info(f"Processing Batch {i//batch_size + 1}/{(len(df_todo)-1)//batch_size + 1} ({len(batch_input)} items)")
                
                batch_results = self.augment_batch(batch_input)
                
                # Map results back to the original rows using Uid
                # Creating a lookup dict from the LLM results
                results_lookup = {str(item.Uid): item for item in batch_results}
                
                final_batch_rows = []
                for _, row in batch_df.iterrows():
                    uid = str(row.get(uid_col)) if uid_col else "unknown"
                    info = results_lookup.get(uid)
                    
                    if info:
                        res = {
                            "genre": info.genre if not info.unknown else "未知",
                            "tags": ",".join(info.tags) if not info.unknown else "未知",
                            "summary": info.summary if not info.unknown else "未知作品",
                            "unknown": info.unknown
                        }
                    else:
                        # Fallback if Uid mapping failed or item missing from LLM response
                        res = {"genre": "Error", "tags": "Error", "summary": "Mismatch/Error", "unknown": True}
                    
                    combined_row = {**row.to_dict(), **res}
                    final_batch_rows.append(combined_row)

                # Append batch results to df_out and save
                df_out = pd.concat([df_out, pd.DataFrame(final_batch_rows)], ignore_index=True)
                
                # Ensure output directory exists and save
                Path(output_path).parent.mkdir(parents=True, exist_ok=True)
                df_out.to_csv(output_path, index=False, encoding='utf-8-sig')
                logger.info(f"Progress saved after batch {i//batch_size + 1}.")

        except KeyboardInterrupt:
            logger.warning("\nProcess interrupted by user (Ctrl+C). Saving current progress...")
            # Note: Current batch results are already saved if the inner loop completes.
            # If interrupted inside the inner loop, those items are lost unless we handle them.
            # But the batch-wise save is already a good enough checkpoint.
            if 'df_out' in locals():
                df_out.to_csv(output_path, index=False, encoding='utf-8-sig')
            logger.info("Interrupted. Progress remains in " + output_path)
            return

        logger.info(f"Finished. Total augmented data saved to {output_path}")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Augment light novel data using Gemini.")
    parser.add_argument("--input", default=DEFAULT_INPUT_CSV, help="Input CSV path")
    parser.add_argument("--output", default=DEFAULT_OUTPUT_CSV, help="Output CSV path")
    parser.add_argument("--limit", type=int, help="Limit number of items to process")
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE, help="Batch size for processing")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="Gemini model name")
    
    args = parser.parse_args()
    
    if not GEMINI_API_KEY:
        logger.error("GEMINI_API_KEY not found in environment. Please check your .env file.")
        exit(1)
        
    augmenter = NovelAugmenter(api_key=GEMINI_API_KEY, model_name=args.model)
    augmenter.process_csv(args.input, args.output, batch_size=args.batch_size, limit=args.limit)
