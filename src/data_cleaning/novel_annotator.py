import os
import logging
from pathlib import Path
from typing import Optional
from google import genai
from google.genai import types
from src.data_cleaning.config import (
    GEMINI_API_KEY,
    DEFAULT_MODEL,
    ANNOTATION_SYSTEM_INSTRUCTION,
    DEFAULT_ANNOTATION_OUTPUT_DIR
)
from src.data_cleaning.schema import NovelAnnotation, CharacterCard

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class NovelAnnotator:
    def __init__(self, api_key: str, model_name: str = DEFAULT_MODEL):
        self.client = genai.Client(api_key=api_key)
        self.model_name = model_name

    def annotate_novel(self, novel_name: str) -> Optional[NovelAnnotation]:
        """Call Gemini to get worldview and character cards for a novel."""
        prompt = f"请输入该轻小说的名称：{novel_name}\n\n请生成该小说开篇时的世界观介绍（约300字）和主要角色的角色设定卡。"
        
        try:
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=ANNOTATION_SYSTEM_INSTRUCTION,
                    response_mime_type="application/json",
                    # Note: We use the pydantic class directly here if supported by the client,
                    # or model_validate_json on the response text.
                    response_schema=NovelAnnotation,
                ),
            )
            
            if not response.text:
                logger.warning(f"Empty response for novel: {novel_name}")
                return None
            
            annotation = NovelAnnotation.model_validate_json(response.text)
            return annotation
        except Exception as e:
            logger.error(f"Error annotating novel '{novel_name}': {e}")
            return None

    def format_character_md(self, card: CharacterCard) -> str:
        """Format a CharacterCard object into a Markdown string."""
        md = f"""# 角色卡 - {card.profile.name}

## 1. 基础信息 (Profile)
- **角色名**：{card.profile.name}
- **核心身份**：{card.profile.identity}
- **年龄/视觉印象**：{card.profile.impression}

## 2. 性格内核 (Core Personality)
- **三个关键词**：{', '.join(card.personality.keywords)}
- **行为逻辑**：{card.personality.logic}
- **道德基准**：{card.personality.ethics}

## 3. 语言指纹 (Linguistic Fingerprint)
- **语调**：{card.linguistic_fingerprint.tone}
- **口癖/习惯**：{card.linguistic_fingerprint.habit}
- **称谓**：{card.linguistic_fingerprint.address}

## 4. 知识边界 (Knowledge & Bias)
- **已知**：{', '.join(card.knowledge_boundary.known)}
- **未知/偏见**：{card.knowledge_boundary.bias}

## 5. 经典范例 (Sample Dialogue)
"""
        for quote in card.sample_dialogue:
            md += f"- “{quote.replace('\\n', '\n')}”\n"
            
        return md.replace('\\n', '\n')

    def save_annotation(self, novel_name: str, annotation: NovelAnnotation, output_dir: str = DEFAULT_ANNOTATION_OUTPUT_DIR):
        """Save the annotation results into multiple Markdown files and an index.json."""
        if annotation.unknown:
            logger.info(f"Novel '{novel_name}' is unknown to the model. Skipping save.")
            return

        # Create novel-specific directory
        novel_path = Path(output_dir) / novel_name
        novel_path.mkdir(parents=True, exist_ok=True)

        index_data = {
            "world_view": "",
            "characters": {}
        }

        # 1. Save worldview
        worldview_filename = "世界观.md"
        worldview_file = novel_path / worldview_filename
        content = annotation.worldview.replace('\\n', '\n')
        with open(worldview_file, "w", encoding="utf-8") as f:
            f.write(content)
        
        index_data["world_view"] = worldview_filename
        logger.info(f"Saved worldview to {worldview_file}")

        # 2. Save character cards
        for card in annotation.characters:
            char_name = card.profile.name
            # Sanitize character name for filesystem
            safe_char_name = "".join([c for c in char_name if c.isalnum() or c in (' ', '-', '_')]).strip()
            char_filename = f"角色卡-{safe_char_name}.md"
            char_file = novel_path / char_filename
            
            with open(char_file, "w", encoding="utf-8") as f:
                f.write(self.format_character_md(card))
            
            index_data["characters"][char_name] = char_filename
            logger.info(f"Saved character card to {char_file}")

        # 3. Save index.json
        import json
        index_file = novel_path / "index.json"
        with open(index_file, "w", encoding="utf-8") as f:
            json.dump(index_data, f, ensure_ascii=False, indent=4)
        logger.info(f"Saved index to {index_file}")

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Annotate light novel worldview and characters.")
    parser.add_argument("name", help="Name of the light novel")
    parser.add_argument("--output", default=DEFAULT_ANNOTATION_OUTPUT_DIR, help="Output directory")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="Gemini model name")
    
    args = parser.parse_args()
    
    if not GEMINI_API_KEY:
        logger.error("GEMINI_API_KEY not found in environment.")
        return

    annotator = NovelAnnotator(api_key=GEMINI_API_KEY, model_name=args.model)
    logger.info(f"Annotating novel: {args.name}")
    
    result = annotator.annotate_novel(args.name)
    
    if result:
        if result.unknown:
            print(f"提示：作品 '{args.name}' 为未知作品，无法生成标注。")
        else:
            annotator.save_annotation(args.name, result, output_dir=args.output)
            print(f"完成！标注文件已保存至：{Path(args.output) / args.name}")
    else:
        print("标注失败，请检查模型连接或输入。")

if __name__ == "__main__":
    main()
