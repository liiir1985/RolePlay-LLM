# Roleplay数据集处理流水线设计文档

## 流水线概述

本流水线用于处理轻小说原文，生成适用于Roleplay场景的高质量数据集。流水线采用模块化设计，支持长期迭代维护。

### 核心设计原则

1. **小步骤独立**：每个小步骤的输入是上一个小步骤的输出，便于单独调试和优化
2. **统一工具类**：LLM调用等通用功能通过统一工具类实现，避免重复代码
3. **可追溯性**：每个步骤的输出都保存在独立目录中，便于回溯和调试
4. **可扩展性**：新步骤可以轻松添加到流水线中

---

## 快速开始

### 环境配置

1. 复制 `.env.example` 为 `.env`：
```bash
copy .env.example .env
```

2. 编辑 `.env` 文件，配置LLM相关参数：
```env
# OpenAI / LLM Configuration
OPENAI_API_KEY="your-api-key-here"
OPENAI_BASE_URL="https://api.openai.com/v1"  # 或第三方API地址
OPENAI_MODEL="gpt-3.5-turbo"

# LLM额外请求参数（JSON格式，可选，必须用单引号包裹避免与JSON双引号冲突）
# 例如：禁用思考模式、设置top_k等
# LLM_EXTRA_BODY='{"top_k": 20, "chat_template_kwargs": {"enable_thinking": false}}'

# JSON响应格式模式（可选，默认json_schema）
# json_schema: 使用JSON Schema约束输出（需模型支持structured output）
# json_object: 仅约束输出为JSON对象（兼容性更好）
# LLM_JSON_RESPONSE_FORMAT=json_schema
```

### 使用入口脚本

**入口脚本**：`src/rp-datapipeline/run.py`

列出所有可用步骤：
```bash
python -m src.rp-datapipeline.run --list
```

运行指定步骤（使用默认参数）：
```bash
python -m src.rp-datapipeline.run --step 1_1
```

运行指定步骤，覆盖输入输出路径：
```bash
python -m src.rp-datapipeline.run --step 1_1 --input data/raw --output data/processed/1_1_scene_segmentation
```

运行指定步骤，传递额外参数：
```bash
python -m src.rp-datapipeline.run --step 1_1 -- --chunk-size 3000 --min-scene-chars 200
```

---

## 输入输出目录结构规则

### 目录命名规范

```
data/
├── raw/                    # 原始输入目录（轻小说txt文件）
├── processed/              # 处理过程目录
│   ├── 1_1_scene_segmentation/    # 步骤1_1的输出
│   ├── 1_2_xxx/                    # 步骤1_2的输出（输入来自1_1）
│   ├── 1_3_xxx/                    # 步骤1_3的输出（输入来自1_2）
│   ├── 2_1_xxx/                    # 步骤2_1的输出
│   └── ...
└── final/                  # 最终输出目录
```

### 输入输出关系

每个小步骤的输出目录命名格式：`data/processed/{大步骤序号}_{小步骤序号}_{步骤名称}/`

例如：
- **1_1_scene_segmentation**：输入 `data/raw/`，输出 `data/processed/1_1_scene_segmentation/`
- **1_2_xxx**：输入 `data/processed/1_1_scene_segmentation/`，输出 `data/processed/1_2_xxx/`
- **1_3_xxx**：输入 `data/processed/1_2_xxx/`，输出 `data/processed/1_3_xxx/`
- 以此类推

---

## 步骤1：语料切分和角色建档

### 1.1 场景切换切分

**脚本名称**：`1_1_scene_segmentation.py`

**输入目录**：`data/raw/`
**输出目录**：`data/processed/1_1_scene_segmentation/`

#### 功能描述

使用LLM将轻小说原文按照场景切换进行切分，识别不同的场景边界。

#### 场景定义

- 时空没有大范围变动的一段剧情
- 或者是一段不可分割的连续时间的连续行动的描写

#### 处理流程

1. **文本分块**：将原始文本按照2000字符一个chunk拆分遍历
2. **按行拆分**：每个chunk按换行符拆分为行
3. **添加行号**：给每一行文本加上行号
4. **LLM分析**：将带行号的文本发送给LLM
5. **解析结果**：LLM返回JSON数组，包含发生场景变更的行号
6. **场景切分**：根据LLM返回的行号进行场景切分

#### 场景切换的常见特征

1. **时间变化**：如"第二天"、"三年后"等
2. **地点变化**：如从"教室"切换到"家里"
3. **视角转换**：从一个角色切换到另一个角色
4. **章节分隔符**：如"* * *"、"---"等

#### 输出格式

每个原始文件会生成一个独立的子目录（名称为去除了后缀的原始文件名），切分后的场景保存为独立的txt文件放入该子目录中。

命名格式：`{原文件名（无后缀）}_{splitid}.txt`

例如：
- 输入文件：`data/raw/novel_name.txt`
- 输出目录与文件：
  - `data/processed/1_1_scene_segmentation/novel_name/`
    - `novel_name_000.txt`
    - `novel_name_001.txt`
    - `novel_name_002.txt`
    - ...

#### 使用方法

```bash
python src/rp-datapipeline/step1_corpus_segmentation/1_1_scene_segmentation.py \
  --input data/raw/ \
  --output data/processed/1_1_scene_segmentation/
```

可选参数：
- `--chunk-size`：每个chunk的字符数（默认：2000）
- `--min-scene-chars`：最小场景字符数（默认：100）

---

### 1.2 角色名字和Alias提取

**脚本名称**：`1_2_character_extraction.py`

**输入目录**：`data/processed/1_1_scene_segmentation/`
**输出目录**：`data/processed/1_1_scene_segmentation/`（与输入相同，直接在原目录输出）

#### 功能描述

使用LLM从切分后的场景文本中提取所有角色的名字和Alias，为后续的角色对话分析和数据集生成做准备。

#### 处理流程

1. **遍历书籍目录**：遍历输入目录中的所有子目录（每个子目录代表一本书）
2. **逐段提取角色**：
   - 遍历一本书中的每个分段文本
   - 将当前已知的人名列表和该段文字传递给LLM
   - LLM返回当前段落出现的所有角色称呼（已知角色需附带至少一个已知称呼以便代码合并）
   - 同时判断叙事视角（第一人称/第三人称），如果是第一人称，尝试识别"我"对应的角色名称
3. **分段角色缓存**：将当前分段识别后的名字列表和POV信息缓存下来
4. **POV回填**：如果某段是第一人称但未能识别主角名，会在后续段落确认主角名后回填（仅限同一本书内）
5. **角色名称合并与去重**：
   - 如果角色已存在于已知列表中，通过名称匹配（精确匹配或子串包含关系）进行合并
   - 合并时注意排重，一模一样的称呼不要出现2次
   - 排除人称代词（我、你、他、她等）和模糊形容词（那个家伙、戴绿帽子的等）
6. **正式名字识别**：对每一组名称列表，通过LLM找出该角色的本名（姓+名，不带敬称后缀）
7. **生成输出文件**：
   - 生成 `characters.json`：整本书的角色列表
   - 生成 `{分段文件名}_characters.json`：包含POV信息和出场角色的正式名字列表

#### 输出格式

**整本书角色文件**：`characters.json`

```json
[
  {
    "name": "角色A",
    "alias": ["小A", "A酱"]
  },
  {
    "name": "角色B",
    "alias": ["B哥"]
  }
]
```

**分段角色文件**：`{分段文件名}_characters.json`

```json
{
  "is_pov": true,
  "pov_name": "角色A",
  "characters": ["角色A", "角色B"]
}
```

- `is_pov`：该段文本是否以第一人称视角书写
- `pov_name`：第一人称"我"对应的角色正式名字（非第一人称或无法识别时为空字符串）
- `characters`：该段出场角色的正式名字列表

#### 使用方法

```bash
python src/rp-datapipeline/step1_corpus_segmentation/1_2_character_extraction.py \
  --input data/processed/1_1_scene_segmentation/ \
  --output data/processed/1_1_scene_segmentation/
```

或使用入口脚本：

```bash
python -m src.rp-datapipeline.run --step 1_2
```

---

### 1.3 场景事实与上下文提炼

**脚本名称**：`1_3_scene_context_extraction.py`

**输入目录**：`data/processed/1_1_scene_segmentation/`
**输出目录**：`data/processed/1_1_scene_segmentation/`（与输入相同，直接在原目录输出）

#### 功能描述

根据前两步的输出（按场景切好段的文本和该文本中出现的角色列表），使用LLM提取该段文本中关于客观环境的事实设定，以及每个出场角色在这段文本中的表现。

#### 处理流程

1. **读取数据**：遍历输入目录，读取场景段落 `*.txt` 文件及其对应的 `{分段文件名}_characters.json` 和整本书的 `characters.json`。
2. **组装角色列表**：将出场角色格式化为 `本名（别称：别名A、别名B……）` 的字符串。
3. **构建Prompt**：为了最大化节省Token并利用KV Cache，将静态指令要求放在Prompt最前，动态变化的文本内容和角色列表放在最末尾。
4. **LLM提取**：请求LLM提取以下内容：
   - 提取的环境/世界观设定（人物行为外的客观场景、环境特点、人物行为引起的变化、世界观设定）
   - 提取的角色设定（每个出场角色一条，key为本名，关注关键决定、性格特征、关系变化）
   - 简明扼要的段落总结（记录fact即可，无修辞和感受描述）
5. **保存结果**：将结构化JSON结果写入同目录的 `{分段文件名}_facts.json` 文件中。

#### 输出格式

**场景事实文件**：`{分段文件名}_facts.json`

```json
{
  "environment_facts": [
    "场景发生在教室",
    "因为某人的行为导致课桌发生变化"
  ],
  "character_facts": [
    {
      "name": "角色A",
      "facts": [
        "决定隐瞒秘密",
        "表现出谨慎、沉着的性格",
        "与角色B的关系变得紧张"
      ]
    }
  ],
  "summary": "角色A在教室发生意外后决定隐瞒秘密，导致与角色B关系紧张。"
}
```

#### 使用方法

```bash
python src/rp-datapipeline/step1_corpus_segmentation/1_3_scene_context_extraction.py \
  --input data/processed/1_1_scene_segmentation/ \
  --output data/processed/1_1_scene_segmentation/
```

或使用入口脚本：

```bash
python -m src.rp-datapipeline.run --step 1_3
```

---

### 1.4 世界观设定与角色设定提取

**脚本名称**：`1_4_world_character_profiles.py`

**输入目录**：`data/processed/1_1_scene_segmentation/`
**输出目录**：`data/processed/1_1_scene_segmentation/`（与输入相同，直接在原目录输出）

#### 功能描述

根据前几步的输出（角色列表、分段角色列表、分段事实），提取每本书的世界观设定和每个主要角色的角色设定。

#### 处理流程

1. **加载数据**：遍历输入目录中的书籍子目录，读取 `characters.json`、所有 `*_characters.json` 和 `*_facts.json` 文件。
2. **主要角色筛选**：统计每个角色在各分段 `_characters.json` 中的出现次数，过滤掉出现段落数少于阈值（默认3）的角色。
3. **世界观设定提取**：将所有 `_facts.json` 中的 `summary` 按顺序拼接，发送给LLM提取世界观设定，包括基础简介、特殊概念和专有名词解释、重要地点解释。
4. **角色设定提取**：遍历每个主要角色，从各 `_facts.json` 中按顺序提取该角色出场段落的环境事实、角色行为事实和典型台词，组装后发送给LLM提取角色设定。
5. **输出文件**：生成 `world_settings.md` 和每个主要角色的 `{角色本名}.md`。

#### 角色设定包含内容

- 姓名
- 基础信息：核心身份、视觉印象/年龄
- 性格内核：关键词、设定、行为习惯、道德基准
- 语言习惯：语调、口癖、对他人的称谓
- 人际关系：跟其他主要角色关系
- 人物弧光：角色的成长，关注特质不要写具体事件
- 典型台词：选取5个最能表现角色性格和特点的台词

#### 输出格式

LLM直接输出Markdown格式的设定文档，信息点的标题命名和格式会随机变化，不使用固定模板。

**世界观设定文件**：`world_settings.md`
- 涵盖基础简介、特殊概念/专有名词、重要地点等信息点
- Markdown格式，标题和组织方式由LLM自由生成

**角色设定文件**：`{角色本名}.md`
- 涵盖姓名、基础信息、性格内核、语言习惯、人际关系、人物弧光、典型台词（5句）等信息点
- Markdown格式，标题和组织方式由LLM自由生成

#### 使用方法

```bash
python src/rp-datapipeline/step1_corpus_segmentation/1_4_world_character_profiles.py \
  --input data/processed/1_1_scene_segmentation/ \
  --output data/processed/1_1_scene_segmentation/
```

或使用入口脚本：

```bash
python -m src.rp-datapipeline.run --step 1_4
```

可选参数：
- `--min-appearances`：主要角色最少出场段落数（默认：3）

---

## 步骤2：场景上下文提炼

*（占位符，待后续实现时补充）*

---

## 步骤3：逆向推导和分离重组

*（占位符，待后续实现时补充）*

---

## 步骤4：质量过滤和格式化

*（占位符，待后续实现时补充）*

---

## 工具类

### LLM客户端

**文件位置**：`src/rp-datapipeline/utils/llm_client.py`

#### 功能

提供统一的OpenAI兼容API调用接口，支持：
- 标准chat completion
- 流式输出
- JSON结构化输出（支持Pydantic model自动生成JSON Schema）
- 自动重试机制
- 错误处理

#### 配置方式

通过环境变量配置：
- `OPENAI_API_KEY`：API密钥
- `OPENAI_BASE_URL`：API基础URL（默认：https://api.openai.com/v1）
- `OPENAI_MODEL`：使用的模型（默认：gpt-3.5-turbo）

#### 使用示例

```python
from src.rp-datapipeline.utils.llm_client import LLMClient, ChatMessage
from pydantic import BaseModel

# 创建客户端
client = LLMClient()

# 简单对话
response = client.simple_chat(
    user_message="你好，请介绍一下自己",
    system_message="你是一个 helpful 的助手"
)

# 完整对话
messages = [
    ChatMessage(role="system", content="你是一个 helpful 的助手"),
    ChatMessage(role="user", content="你好")
]
response = client.chat_completion(messages=messages)
print(response.content)

# 结构化JSON输出（使用Pydantic model）
class MyResponse(BaseModel):
    answer: str
    confidence: float

response = client.chat_with_json_response(
    messages=messages,
    response_model=MyResponse  # 自动生成JSON Schema，返回值为MyResponse实例
)
print(response.answer, response.confidence)

# 流式输出
for chunk in client.chat_completion_stream(messages=messages):
    print(chunk, end="")
```

---

## 配置文件

**文件位置**：`src/rp-datapipeline/config.py`

### 配置项

| 配置项 | 环境变量 | 默认值 | 说明 |
|--------|----------|--------|------|
| llm.api_key | OPENAI_API_KEY | "" | API密钥 |
| llm.base_url | OPENAI_BASE_URL | "https://api.openai.com/v1" | API基础URL |
| llm.model | OPENAI_MODEL | "gpt-3.5-turbo" | 使用的模型 |
| llm.temperature | - | 0.7 | 温度参数 |
| llm.max_tokens | - | 4096 | 最大token数 |
| llm.timeout | - | 60 | 超时时间（秒） |
| llm.max_retries | - | 3 | 最大重试次数 |
| raw_data_dir | RAW_DATA_DIR | "data/raw" | 原始数据目录 |
| processed_data_dir | PROCESSED_DATA_DIR | "data/processed" | 处理中数据目录 |
| final_data_dir | FINAL_DATA_DIR | "data/final" | 最终数据目录 |

---

## 版本历史

- v0.1.0 (2026-04-28)：初始版本，实现基础设施和1_1场景切换切分
