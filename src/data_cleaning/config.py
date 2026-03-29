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
DEFAULT_ANNOTATION_OUTPUT_DIR = os.getenv("ANNOTATION_OUTPUT_DIR", str(ROOT_DIR / "data" / "annotations"))


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

ANNOTATION_SYSTEM_INSTRUCTION = """
你是一个资深的轻小说研究专家和角色设定分析师。你的任务是为一个给定的轻小说作品，生成其开篇时的世界观介绍及主要角色的详细角色设定卡。

规则：
1. 必须完全基于已公开、已知的作品内容。
2. 世界观介绍：字段为 `worldview`，内容必须直接输出为 Markdown 格式，且必须包含以下三个二级标题：
    - `## 基础简介`：故事开篇时的背景介绍，不超过300字。
    - `## 特殊概念和专有名词解释`：如果有，请按条目列出简介。
    - `## 重要地点解释`：对开篇后剧情发展重要的地点的简介，按条目列出。
3. 角色设定卡：生成开篇时的主要角色卡。必须严格按照提供的 Pydantic 结构返回。
4. **绝对诚实**：如果你不知道这个作品，或者不确定其中的细节，必须在 `unknown` 字段设为 true，并停止生成具体内容。
5. 角色卡的内容必须精炼且富有灵魂，避免空洞的描述。

角色卡内容要求：
- 基础信息：包含名字、核心身份、开篇时的视觉印象/年龄。
- 性格内核：三个关键词、行为逻辑（核心）、道德基准。
- 语言指纹：语调、语癖、对他人的称谓。
- 知识边界：已知的精通领域、偏见或由于背景导致的误解。
- 经典范例：2-3句最能代表灵魂的台词。
"""


# Example structured output schema for Pydantic
# {
#     "genre": "...",
#     "tags": ["...", "..."],
#     "summary": "...",
#     "unknown": false
# }
