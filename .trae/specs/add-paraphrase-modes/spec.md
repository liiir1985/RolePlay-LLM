# 2-1步骤新增转述模式和严格转述模式 Spec

## Why
目前2-1步骤只有普通模式，生成的ChatML训练集中用户角色的对话会分散在多个user消息中。为了满足特定的训练需求，需要新增两种模式：转述模式和严格转述模式，使得用户角色的对话只会出现在一条user消息中，而assistant需要生成包含这些对话的完整文本。

## What Changes
- 新增 `--mode` 参数，支持三种模式：`normal`（默认，普通模式）、`paraphrase`（转述模式）、`strict-paraphrase`（严格转述模式）
- 新增 `--min-chars` 参数，用于转述模式和严格转述模式，指定每一轮assistant需要生成的最少字数（默认500）
- 实现转述模式的核心逻辑：
  - 用户角色的对话只会出现在user role中，并且每一轮只会出现一条
  - 向后遍历消息，收集content直到达到指定字数，且最后一条消息必须是assistant
  - 将收集到的消息中所有user的content去掉引号用换行符拼接作为一条单一的user信息
  - 将满足字数要求的完整content作为一条单独的assistant信息（包括带引号的user信息的content）
  - 根据原数据集的尺寸不同，可能会有多轮对话
- 实现严格转述模式的核心逻辑：
  - 与转述模式类似，但在任务描述中需要强调用户角色的发言严格限定在用户提供的内容范围内
  - 所有拼接时用到的user对话都写在最终的第一条user信息里
  - 根据原数据集的尺寸不同，可能会有多轮对话
- 实现普通转述模式（即转述模式）的核心逻辑：
  - 只选取所有用到了的用户角色的发言当中的头1-2条对话内容
  - 在任务描述中允许AI为用户角色生成额外的对话
- 更新System消息构建逻辑：
  - 对于转述模式和严格转述模式，需要在任务描述中加入对应的要求
  - 转述模式：生成足够长度的文本内容，用户提供的对话内容需要自然地融入到生成的文本中
  - 严格转述模式：除了转述模式的要求外，还需要确保用户角色的发言严格限定在用户提供的内容范围内
- 首条消息角色调整：
  - 普通模式：保持现有行为，如果system之后第一条消息是assistant，改为user
  - 转述模式和严格转述模式：不需要这个调整

## Impact
- Affected specs: 2-1 JSONL转ChatML训练集
- Affected code: 
  - `src/rp-datapipeline/step2_chatml_conversion/2_1_jsonl_to_chatml.py`
  - `src/rp-datapipeline/run.py`（更新默认参数）

## ADDED Requirements

### Requirement: 模式参数支持
系统 SHALL 支持通过 `--mode` 参数选择不同的转换模式，包括：
- `normal`：普通模式（默认值，保持现有行为）
- `paraphrase`：转述模式
- `strict-paraphrase`：严格转述模式

#### Scenario: 使用默认模式
- **WHEN** 用户运行2-1步骤时不指定 `--mode` 参数
- **THEN** 系统使用普通模式（normal）进行转换

#### Scenario: 指定转述模式
- **WHEN** 用户运行2-1步骤时指定 `--mode paraphrase`
- **THEN** 系统使用转述模式进行转换

#### Scenario: 指定严格转述模式
- **WHEN** 用户运行2-1步骤时指定 `--mode strict-paraphrase`
- **THEN** 系统使用严格转述模式进行转换

### Requirement: 最少字数参数支持
系统 SHALL 支持通过 `--min-chars` 参数指定转述模式和严格转述模式中每一轮assistant需要生成的最少字数，默认值为500。

#### Scenario: 使用默认最少字数
- **WHEN** 用户运行转述模式或严格转述模式时不指定 `--min-chars` 参数
- **THEN** 系统使用默认值500作为最少字数

#### Scenario: 指定最少字数
- **WHEN** 用户运行转述模式或严格转述模式时指定 `--min-chars 1000`
- **THEN** 系统使用1000作为最少字数

### Requirement: 消息收集逻辑（必须以assistant结尾）
系统 SHALL 实现消息收集逻辑，确保收集到的消息序列最后一条必须是assistant消息：

1. **初始收集**：从第一条消息开始向后遍历，累加content的字符数
2. **字数检查**：当累加的字符数达到或超过 `--min-chars` 指定的字数时，检查当前最后一条消息的role
3. **assistant结尾确保**：
   - 如果最后一条消息是assistant，则停止收集
   - 如果最后一条消息是user，则继续向后遍历，直到找到下一条assistant消息为止
   - 如果遍历完所有消息仍未找到assistant消息，则使用已收集的消息（即使最后一条是user），但需要记录警告

#### Scenario: 正常情况（达到字数时最后一条是assistant）
- **WHEN** 收集消息时，累加字符数达到 `min_chars`，且最后一条消息是assistant
- **THEN** 停止收集，返回已收集的消息

#### Scenario: 达到字数时最后一条是user
- **WHEN** 收集消息时，累加字符数达到 `min_chars`，但最后一条消息是user
- **THEN** 继续向后遍历，直到找到下一条assistant消息为止，然后停止收集

#### Scenario: 遍历完所有消息仍未找到assistant
- **WHEN** 收集消息时，累加字符数达到 `min_chars`，最后一条消息是user，且后面没有更多消息
- **THEN** 使用已收集的消息，但记录警告信息

### Requirement: 引号去除功能
系统 SHALL 实现引号去除功能，支持去除多种引号格式：

1. **支持的引号格式**：
   - 英文双引号：`"..."`
   - 中文双引号：`"..."`
   - 直角引号：`「...」`、`『...』`
2. **去除规则**：
   - 只去除最外层的引号
   - 保留内容中的其他字符
   - 如果内容中包含嵌套引号，只去除最外层

#### Scenario: 去除英文双引号
- **WHEN** 输入内容为 `"你好，我是张三。"`
- **THEN** 输出内容为 `你好，我是张三。`

#### Scenario: 去除中文双引号
- **WHEN** 输入内容为 `"你好，我是张三。"`
- **THEN** 输出内容为 `你好，我是张三。`

#### Scenario: 去除直角引号
- **WHEN** 输入内容为 `「你好，我是张三。」`
- **THEN** 输出内容为 `你好，我是张三。`

### Requirement: 转述模式核心逻辑
系统 SHALL 实现转述模式的核心逻辑：

1. **消息收集**：按照"必须以assistant结尾"的规则收集消息，形成一轮对话
2. **User消息构建**：
   - 从收集到的消息中筛选出所有role为user的消息
   - 只选取头1-2条user消息的content（优先选取前2条，如果只有1条则取1条）
   - 去掉这些content中的引号（包括英文双引号、中文双引号、直角引号等）
   - 用换行符拼接这些content，作为最终的一条user消息
3. **Assistant消息构建**：
   - 将收集到的所有消息的完整content（包括带引号的user对话）按顺序拼接
   - 作为最终的一条assistant消息
4. **多轮处理**：
   - 如果原始数据集中还有剩余的消息，重复上述步骤，形成多轮对话
   - 每一轮都遵循相同的规则：收集消息（以assistant结尾）→ 构建user消息 → 构建assistant消息
5. **消息结构**：
   - 最终的ChatML消息结构为：[system, user, assistant, user, assistant, ...]
   - 每一轮中，user消息只有一条，包含去掉引号的用户角色对话（头1-2条）
   - 每一轮中，assistant消息只有一条，包含完整的文本内容（包括带引号的user对话）
   - 根据原数据集的尺寸不同，可能会有多轮对话

#### Scenario: 转述模式单轮消息转换
- **WHEN** 用户使用转述模式处理包含以下消息的JSONL文件：
  - 消息1（user）："你好，我是张三。"
  - 消息2（assistant）：你好张三，我是李四。
  - 消息3（user）："很高兴认识你。"
  - 消息4（assistant）：我也很高兴认识你。
- **THEN** 系统生成的ChatML消息结构为：
  - system：包含任务描述、世界观设定、角色设定、前情提要
  - user：包含去掉引号的头1-2条user对话（如："你好，我是张三。\n很高兴认识你。" 或只取第一条）
  - assistant：包含完整的文本内容（包括带引号的user对话）

#### Scenario: 转述模式多轮消息转换
- **WHEN** 用户使用转述模式处理包含大量消息的JSONL文件
- **THEN** 系统会将消息分成多轮处理
  - 每一轮都收集足够的消息（以assistant结尾）
  - 每一轮都构建一条user消息和一条assistant消息
  - 最终的消息结构可能是 [system, user, assistant, user, assistant, ...]

### Requirement: 严格转述模式核心逻辑
系统 SHALL 实现严格转述模式的核心逻辑：

1. **消息收集**：按照"必须以assistant结尾"的规则收集消息，形成一轮对话
2. **User消息构建**：
   - 从收集到的消息中筛选出所有role为user的消息
   - 去掉这些content中的引号（包括英文双引号、中文双引号、直角引号等）
   - 用换行符拼接所有这些content，作为最终的一条user消息
3. **Assistant消息构建**：
   - 将收集到的所有消息的完整content（包括带引号的user对话）按顺序拼接
   - 作为最终的一条assistant消息
4. **多轮处理**：
   - 如果原始数据集中还有剩余的消息，重复上述步骤，形成多轮对话
   - 每一轮都遵循相同的规则：收集消息（以assistant结尾）→ 构建user消息 → 构建assistant消息
5. **消息结构**：
   - 最终的ChatML消息结构为：[system, user, assistant, user, assistant, ...]
   - 每一轮中，user消息只有一条，包含去掉引号的所有用户角色对话
   - 每一轮中，assistant消息只有一条，包含完整的文本内容（包括带引号的user对话）
   - 根据原数据集的尺寸不同，可能会有多轮对话

#### Scenario: 严格转述模式单轮消息转换
- **WHEN** 用户使用严格转述模式处理包含以下消息的JSONL文件：
  - 消息1（user）："你好，我是张三。"
  - 消息2（assistant）：你好张三，我是李四。
  - 消息3（user）："很高兴认识你。"
  - 消息4（assistant）：我也很高兴认识你。
- **THEN** 系统生成的ChatML消息结构为：
  - system：包含任务描述、世界观设定、角色设定、前情提要
  - user：包含去掉引号的所有user对话："你好，我是张三。\n很高兴认识你。"
  - assistant：包含完整的文本内容（包括带引号的user对话）

#### Scenario: 严格转述模式多轮消息转换
- **WHEN** 用户使用严格转述模式处理包含大量消息的JSONL文件
- **THEN** 系统会将消息分成多轮处理
  - 每一轮都收集足够的消息（以assistant结尾）
  - 每一轮都构建一条user消息和一条assistant消息
  - 最终的消息结构可能是 [system, user, assistant, user, assistant, ...]

### Requirement: 转述模式和严格转述模式的System消息构建
系统 SHALL 为转述模式和严格转述模式构建特定的System消息，包含以下要求：

1. **任务描述生成**：
   - 使用LLM生成随机化的任务描述
   - 对于转述模式，需要包含以下核心信息：
     - 用户扮演的角色和AI扮演的角色
     - AI需要生成足够长度的文本内容（不少于指定字数）
     - 用户提供的对话内容需要自然地融入到生成的文本中
   - 对于严格转述模式，除了转述模式的要求外，还需要包含：
     - 用户角色的发言严格限定在用户提供的内容范围内
     - AI不能为用户角色生成用户没有说过的对话

2. **提示词更新**：
   - 更新 `TASK_DESCRIPTION_SYSTEM_PROMPT`，使其能够根据模式生成不同的任务描述
   - 或者创建新的System Prompt专门用于转述模式和严格转述模式

#### Scenario: 转述模式任务描述生成
- **WHEN** 用户使用转述模式处理文件
- **THEN** 生成的任务描述包含：
  - 用户扮演的角色和AI扮演的角色
  - AI需要生成足够长度的文本内容
  - 用户提供的对话内容需要自然地融入到生成的文本中

#### Scenario: 严格转述模式任务描述生成
- **WHEN** 用户使用严格转述模式处理文件
- **THEN** 生成的任务描述包含：
  - 用户扮演的角色和AI扮演的角色
  - AI需要生成足够长度的文本内容
  - 用户提供的对话内容需要自然地融入到生成的文本中
  - 用户角色的发言严格限定在用户提供的内容范围内
  - AI不能为用户角色生成用户没有说过的对话

### Requirement: Reasoning Content提示词检查
系统 SHALL 检查并确认Reasoning Content的提示词是否需要变更：

1. **现有提示词分析**：
   - 检查 `REASONING_CONTENT_SYSTEM_PROMPT` 的内容
   - 确认其是否适用于转述模式和严格转述模式

2. **变更评估**：
   - 如果现有提示词已经能够处理转述模式和严格转述模式的情况，则不需要变更
   - 如果现有提示词需要调整才能更好地处理新模式，则进行相应的变更

#### Scenario: 现有提示词适用
- **WHEN** 检查发现现有Reasoning Content提示词已经能够处理转述模式和严格转述模式
- **THEN** 不需要变更提示词

#### Scenario: 现有提示词需要调整
- **WHEN** 检查发现现有Reasoning Content提示词需要调整才能更好地处理转述模式和严格转述模式
- **THEN** 根据需要调整提示词

### Requirement: 首条消息角色调整规则
系统 SHALL 为不同模式应用不同的首条消息角色调整规则：

1. **普通模式**：
   - 保持现有行为
   - 如果system之后第一条消息的role为 `"assistant"`，则改为 `"user"`

2. **转述模式**：
   - 不应用首条消息角色调整
   - 保持消息的原始role分配

3. **严格转述模式**：
   - 不应用首条消息角色调整
   - 保持消息的原始role分配

#### Scenario: 普通模式首条消息是assistant
- **WHEN** 用户使用普通模式，且system之后第一条消息是assistant
- **THEN** 系统将第一条消息的role改为user

#### Scenario: 转述模式首条消息是assistant
- **WHEN** 用户使用转述模式，且system之后第一条消息是assistant
- **THEN** 系统保持消息的原始role不变

#### Scenario: 严格转述模式首条消息是assistant
- **WHEN** 用户使用严格转述模式，且system之后第一条消息是assistant
- **THEN** 系统保持消息的原始role不变

### Requirement: 普通模式保持不变
系统 SHALL 保持普通模式（normal）的现有行为不变，确保向后兼容性。

#### Scenario: 普通模式消息转换
- **WHEN** 用户使用普通模式处理JSONL文件
- **THEN** 系统的行为与修改前完全一致

## MODIFIED Requirements

### Requirement: 命令行参数更新
2-1步骤的命令行参数 SHALL 新增以下参数：
- `--mode`：选择转换模式，可选值为 `normal`、`paraphrase`、`strict-paraphrase`，默认值为 `normal`
- `--min-chars`：转述模式和严格转述模式中每一轮assistant需要生成的最少字数，默认值为500

### Requirement: 入口脚本参数更新
`run.py` 中2-1步骤的默认参数 SHALL 保持不变，但需要支持传递新增的 `--mode` 和 `--min-chars` 参数。

### Requirement: Task Description System Prompt更新
`TASK_DESCRIPTION_SYSTEM_PROMPT` SHALL 被更新，使其能够根据模式生成不同的任务描述：

1. **普通模式**：保持现有行为
2. **转述模式**：
   - 包含用户扮演的角色和AI扮演的角色
   - 包含AI需要生成足够长度的文本内容的要求
   - 包含用户提供的对话内容需要自然地融入到生成的文本中的要求
3. **严格转述模式**：
   - 包含转述模式的所有要求
   - 包含用户角色的发言严格限定在用户提供的内容范围内的要求
   - 包含AI不能为用户角色生成用户没有说过的对话的要求

### Requirement: 首条消息角色调整逻辑更新
`adjust_first_message_role` 函数 SHALL 被更新，使其只在普通模式下生效：

1. **普通模式**：保持现有行为
2. **转述模式**：不调用 `adjust_first_message_role` 函数
3. **严格转述模式**：不调用 `adjust_first_message_role` 函数

## REMOVED Requirements
无
