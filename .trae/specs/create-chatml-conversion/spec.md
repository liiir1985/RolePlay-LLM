# 步骤2_1：JSONL转ChatML训练集 Spec

## Why
步骤1_5已生成包含对话标注的JSONL数据集文件。现在需要将这些JSONL文件进一步加工成ChatML格式的训练集，包含system提示、角色分配、消息合并以及reasoning_content补全，使其可直接用于Roleplay模型训练。

## What Changes
- 新增脚本 `src/rp-datapipeline/step2_chatml_conversion/2_1_jsonl_to_chatml.py`
- 在 `run.py` 中注册步骤 `2_1`
- 更新 `README.md` 中步骤2.1的文档

## Impact
- Affected code: `run.py`（新增步骤注册）、新增 `step2_chatml_conversion/` 目录、`README.md`
- 依赖: `utils/llm_client.py`（LLM调用）、步骤1_1~1_5的输出文件

## ADDED Requirements

### Requirement: JSONL文件收集与随机抽样
系统 SHALL 遍历输入目录中的所有书籍子目录，收集所有 `*_dialogue.jsonl` 文件，并支持随机抽样功能。

#### Scenario: 默认抽样
- **WHEN** 用户运行步骤2_1，未指定 `--sample-count` 参数
- **THEN** 默认抽样10条，从所有收集到的JSONL文件中随机抽取10个文件进行处理

#### Scenario: 自定义抽样数量
- **WHEN** 用户通过 `--sample-count 5` 指定抽样数量
- **THEN** 随机抽取5个JSONL文件进行处理

#### Scenario: 不抽样（处理所有）
- **WHEN** 用户通过 `--sample-count 0` 指定
- **THEN** 处理所有收集到的JSONL文件，不进行随机抽样

### Requirement: 关联文件加载
系统 SHALL 为每个JSONL文件加载对应的关联文件：
1. 读取对应的 `{stem}_characters.json`，提取出场角色列表、is_pov、pov_name
2. 读取对应的 `{stem}_facts.json`，提取summary用于前情提要构建
3. 读取书籍目录下的 `world_settings.md`（世界观设定）
4. 读取出场角色和POV角色对应的 `{角色本名}.md` 设定文件

#### Scenario: 正常加载
- **WHEN** 所有关联文件存在
- **THEN** 成功加载所有必要信息

#### Scenario: 文件缺失
- **WHEN** 某些关联文件不存在
- **THEN** 跳过该JSONL文件，记录警告日志

### Requirement: 用户角色确定
系统 SHALL 根据以下规则确定用户扮演的角色：
1. 如果 `is_pov` 为 `true` 且 `pov_name` 非空，则用户角色为 `pov_name`
2. 如果不是第一人称，则参考步骤1_4的 `filter_main_characters` 逻辑，统计该书籍中所有 `_characters.json` 文件的角色出场频率，选择出场频率最高的角色作为用户角色

#### Scenario: 第一人称视角
- **WHEN** `is_pov=true` 且 `pov_name="角色A"`
- **THEN** 用户角色为"角色A"

#### Scenario: 第三人称视角
- **WHEN** `is_pov=false`
- **THEN** 统计所有段落的角色出场频率，选择频率最高的角色作为用户角色

### Requirement: ChatML消息转换
系统 SHALL 将JSONL中的每条记录转换为ChatML格式的messages列表：

#### 4-1 System消息构建
系统 SHALL 构建第一条system消息，包含：
- **任务描述**：使用LLM生成随机指令，大意："你是一个专业的角色扮演专家，请根据给定的世界观和角色设定，进行角色扮演。用户扮演的角色为XXXX，你将扮演除了XXX以外的所有角色，并负责剧情的推进。请以第一/三人称进行书写"
- **世界观设定**：来自 `world_settings.md` 的内容
- **出场角色设定**：来自各角色的 `{角色本名}.md` 文件内容
- **前情提要**：构建方式同步骤1_5，累加之前段落的summary，超过700字符时调用LLM总结为不超过500字符

#### Scenario: System消息构建
- **WHEN** 所有必要信息已加载
- **THEN** 生成包含任务描述、世界观、角色设定、前情提要的system消息

#### 4-2 角色分配
系统 SHALL 为JSONL中的每条消息分配role：
- 如果 `speaker` 等于用户角色，则 `role="user"`
- 否则（包括 `speaker` 为空字符串），`role="assistant"`

#### Scenario: 用户角色消息
- **WHEN** `speaker="角色A"` 且用户角色为"角色A"
- **THEN** `role="user"`

#### Scenario: 其他角色消息
- **WHEN** `speaker="角色B"` 且用户角色为"角色A"
- **THEN** `role="assistant"`

#### Scenario: 旁白消息
- **WHEN** `speaker=""`
- **THEN** `role="assistant"`

#### 4-3 相邻消息合并
系统 SHALL 对相邻 `role` 相同的message进行合并：
- 连续相同 `role` 的消息合并为一条
- `content` 合并时添加换行符
- 收集被合并消息中的所有 `speaker`

#### Scenario: 连续相同role合并
- **WHEN** 连续3条消息的 `role` 都是 `"assistant"`
- **THEN** 合并为1条消息，`content` 为3条消息的content用换行符连接，收集所有3条消息的speaker

#### 4-4 首条消息角色调整
系统 SHALL 检查system之后第一条消息的role：
- 如果第一条消息的 `role` 为 `"assistant"`，则改为 `"user"`

#### Scenario: 首条为assistant
- **WHEN** system之后第一条消息的 `role="assistant"`
- **THEN** 将其 `role` 改为 `"user"`

#### Scenario: 首条为user
- **WHEN** system之后第一条消息的 `role="user"`
- **THEN** 保持不变

### Requirement: Reasoning Content补全
系统 SHALL 为每一条 `role="assistant"` 的消息补充 `reasoning_content`，使用LLM进行推导。

#### 思考顺序
LLM的提示词应包含当前message前面所有message的content，按照以下顺序进行思考：

1. **环境状况分析**：
   - 核心动机对齐："根据全局档案，角色的终极目标是什么？在当前的具体场景下，他的短期目的是什么？"
   - 人设约束检查："这个角色绝对不能做什么？绝对不能说什么样的话？"

2. **局势与信息差分析**：
   - "当前对话进展到哪一步了？对方抛出了什么信息？有什么是对方不知道、但角色知道的？"

3. **行动策略制定**：
   - "为了实现上述目标并维持人设，角色接下来应该采取什么战术（转移话题、施压、示弱）？应该用什么语气？"

4. **角色第一视角思考**（对当前message content中的所有speaker角色）：
   - 瞬时情绪反应："面对刚才发生的事情（对方的话语、动作），我心里的第一感觉是什么？"
   - 未说出口的潜台词："我心里真正在盘算什么？有什么真相或抱怨是我现在不能直接说出来的？"
   - 理智与情感的冲突："我本能想怎么做？但为了大局，我不得不怎么做？"

#### 输出格式
- 思考过程不要有固定格式，让LLM自由发挥
- 格式为Markdown

#### Scenario: 补全reasoning_content
- **WHEN** 处理一条 `role="assistant"` 的消息
- **THEN** 调用LLM生成 `reasoning_content`，包含上述思考内容，格式为Markdown

### Requirement: 输出保存
系统 SHALL 将补全了 `reasoning_content` 的ChatML messages保存到2_1的输出目录，在该书所在子目录里。

#### 输出格式
每个处理后的JSONL文件对应一个输出文件，格式为JSON，包含：
```json
{
  "messages": [
    {
      "role": "system",
      "content": "..."
    },
    {
      "role": "user",
      "content": "..."
    },
    {
      "role": "assistant",
      "content": "...",
      "reasoning_content": "..."
    }
  ]
}
```

#### Scenario: 输出目录结构
- **WHEN** 输入含多本书
- **THEN** 输出目录结构为 `data/processed/2_1_chatml_conversion/{book_name}/{stem}_chatml.json`

### Requirement: 入口脚本注册
系统 SHALL 在 `run.py` 中注册步骤 `2_1`：
- 默认输入：`{config.processed_data_dir}/1_1_scene_segmentation`
- 默认输出：`{config.processed_data_dir}/2_1_chatml_conversion`
- 默认参数：`sample_count: 10`

#### Scenario: 通过入口脚本运行
- **WHEN** 用户执行 `python -m src.rp-datapipeline.run --step 2_1`
- **THEN** 使用默认输入输出路径和默认抽样数量运行步骤2_1
