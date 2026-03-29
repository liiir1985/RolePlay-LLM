import pandas as pd
import json
import logging
from typing import List, Optional, Set
from pydantic import BaseModel, Field
from google import genai
from google.genai import types
from tqdm import tqdm
from .config import (
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

class NovelInfo(BaseModel):
    """Structured data for a light novel."""
    genre: Optional[str] = Field(None, description="The genre of the novel (e.g., Fantasy, School, Sci-Fi).")
    tags: List[str] = Field(default_factory=list, description="Specific tags for the novel.")
    summary: Optional[str] = Field(None, description="A ~200 word plot summary.")
    unknown: bool = Field(False, description="True if the model does not know this work.")

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

    def format_prompt(self, novel_name: str) -> str:
        tags_hint = ", ".join(sorted(list(self.existing_tags)))
        prompt = f"""
作品名称：{novel_name}

现有标签参考：[{tags_hint}]

请提供题材(genre)、标签(tags)和200字剧情概要(summary)。
如果该作品不属于知名轻小说或你无法确定，请将 "unknown" 设为 true。
"""
        return prompt

    def augment_novel(self, name: str) -> Optional[NovelInfo]:
        """Call Gemini to get augmented info for a novel."""
        try:
            prompt = self.format_prompt(name)
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=SYSTEM_INSTRUCTION,
                    response_mime_type="application/json",
                    response_schema=NovelInfo,
                ),
            )
            
            if not response.text:
                logger.warning(f"Empty response for {name}")
                return None
            
            data = NovelInfo.model_validate_json(response.text)
            
            # Update global tags if known
            if not data.unknown and data.tags:
                self.existing_tags.update(data.tags)
                
            return data
        except Exception as e:
            logger.error(f"Error augmenting {name}: {e}")
            return None

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
            name_col = 'name' if 'name' in df_out.columns else ('title' if 'title' in df_out.columns else None)
            if name_col:
                processed_names = set(df_out[name_col].dropna().unique())
                logger.info(f"Found {len(processed_names)} already processed items.")

        self.load_existing_tags(pd.concat([df_in, df_out]) if not df_out.empty else df_in)

        # 2. Filter unprocessed rows
        name_col_in = 'name' if 'name' in df_in.columns else ('title' if 'title' in df_in.columns else None)
        if not name_col_in:
            logger.error("Could not find 'name' or 'title' column in input CSV.")
            return

        df_todo = df_in[~df_in[name_col_in].isin(processed_names)].copy()
        
        if df_todo.empty:
            logger.info("All items are already processed. Nothing to do.")
            return

        logger.info(f"Remaining items to process: {len(df_todo)}")
        
        # 3. Batch processing loop
        try:
            for i in range(0, len(df_todo), batch_size):
                batch = df_todo.iloc[i:i+batch_size]
                batch_results = []
                
                desc = f"Batch {i//batch_size + 1}/{(len(df_todo)-1)//batch_size + 1}"
                for _, row in tqdm(batch.iterrows(), total=len(batch), desc=desc):
                    name = row.get(name_col_in)
                    info = self.augment_novel(name)
                    
                    if info:
                        res = {
                            "genre": info.genre if not info.unknown else "未知",
                            "tags": ",".join(info.tags) if not info.unknown else "未知",
                            "summary": info.summary if not info.unknown else "未知作品",
                            "unknown": info.unknown
                        }
                    else:
                        res = {"genre": "Error", "tags": "Error", "summary": "API Error", "unknown": True}
                    
                    # Combine original row with new info
                    combined_row = {**row.to_dict(), **res}
                    batch_results.append(combined_row)

                # Append batch results to df_out and save
                df_out = pd.concat([df_out, pd.DataFrame(batch_results)], ignore_index=True)
                
                # Ensure output directory exists and save
                Path(output_path).parent.mkdir(parents=True, exist_ok=True)
                df_out.to_csv(output_path, index=False, encoding='utf-8-sig')
                logger.info(f"Progress saved to {output_path} after batch.")

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
