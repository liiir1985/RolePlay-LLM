import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Project Paths
ROOT_DIR = Path(__file__).parent.parent.parent
DEFAULT_INPUT_CSV = os.getenv("INPUT_CSV_PATH", r"Y:\AI\LightNovel\index.csv")
DEFAULT_OUTPUT_CSV = os.getenv("OUTPUT_CSV_PATH", str(ROOT_DIR / "data" / "processed" / "index_augmented.csv"))

# Gemini Configuration
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
DEFAULT_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
DEFAULT_BATCH_SIZE = int(os.getenv("BATCH_SIZE", "10"))

# LLM Instructions
SYSTEM_INSTRUCTION = """
你是一个轻小说数据专家。你的任务是根据提供的轻小说列表（包含 Uid 和 Title），补充其题材、标签和200字左右的剧情概要。

规则：
1. 输入是一个包含多个作品对象的列表。输出必须是相同长度的 JSON 数组。
2. 每个输出对象必须包含对应的 `Uid` 以便匹配。
3. 只允许回答你确切知道的信息，禁止任何猜测、幻想或捏造。
4. 如果你不认识或不确定某个作品，请在该对象的 "unknown" 字段设为 true。
5. 题材 (genre)：指作品的大类，如：奇幻、校园、科幻等。
6. 标签 (tags)：指作品的具体属性。我会提供一个现有的标签库，请优先使用意思相近的现有标签。如果需要创建新标签，请确保其精确。
7. 剧情概要 (summary)：一段200字左右的文字，简述故事背景和核心冲突。

输出必须包含一个名为 "items" 的字段，内容为一个 JSON 数组，格式如下：
{
    "items": [
        {"Uid": "...", "genre": "...", "tags": ["...", "..."], "summary": "...", "unknown": false},
        ...
    ]
}
"""

# Example structured output schema for Pydantic
# {
#     "genre": "...",
#     "tags": ["...", "..."],
#     "summary": "...",
#     "unknown": false
# }
