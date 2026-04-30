# Tasks

- [x] Task 1: 更新2_1_jsonl_to_chatml.py的命令行参数解析
  - [x] SubTask 1.1: 新增 `--mode` 参数，支持 `normal`、`paraphrase`、`strict-paraphrase` 三种选项，默认值为 `normal`
  - [x] SubTask 1.2: 新增 `--min-chars` 参数，类型为int，默认值为500

- [x] Task 2: 实现消息收集和字数统计功能（必须以assistant结尾）
  - [x] SubTask 2.1: 实现 `collect_messages_batch` 函数，从指定位置开始向后遍历，累加content的字符数
  - [x] SubTask 2.2: 当累加字符数达到或超过 `min_chars` 时，检查最后一条消息的role
  - [x] SubTask 2.3: 如果最后一条消息是assistant，则停止收集
  - [x] SubTask 2.4: 如果最后一条消息是user，则继续向后遍历，直到找到下一条assistant消息为止
  - [x] SubTask 2.5: 如果遍历完所有消息仍未找到assistant，则使用已收集的消息，但记录警告
  - [x] SubTask 2.6: 确保函数返回收集到的消息列表和下一个起始位置

- [x] Task 3: 实现引号去除功能
  - [x] SubTask 3.1: 实现 `remove_quotes` 函数，支持去除多种引号格式：英文双引号 `"..."`、中文双引号 `"..."`、直角引号 `「...」`、`『...』`
  - [x] SubTask 3.2: 确保函数只去除最外层的引号，保留内容中的其他字符

- [x] Task 4: 更新Task Description System Prompt
  - [x] SubTask 4.1: 分析现有 `TASK_DESCRIPTION_SYSTEM_PROMPT` 的结构
  - [x] SubTask 4.2: 更新提示词，使其能够根据模式生成不同的任务描述
  - [x] SubTask 4.3: 对于转述模式，添加以下要求：
    - AI需要生成足够长度的文本内容
    - 用户提供的对话内容需要自然地融入到生成的文本中
  - [x] SubTask 4.4: 对于严格转述模式，除了转述模式的要求外，还添加：
    - 用户角色的发言严格限定在用户提供的内容范围内
    - AI不能为用户角色生成用户没有说过的对话
  - [x] SubTask 4.5: 确保普通模式保持现有行为不变

- [x] Task 5: 检查Reasoning Content提示词
  - [x] SubTask 5.1: 仔细分析现有 `REASONING_CONTENT_SYSTEM_PROMPT` 的内容
  - [x] SubTask 5.2: 评估其是否适用于转述模式和严格转述模式
  - [x] SubTask 5.3: 如果需要调整，进行相应的变更；如果不需要，记录评估结果

- [x] Task 6: 实现转述模式消息转换逻辑
  - [x] SubTask 6.1: 实现 `convert_to_paraphrase_mode` 函数，处理转述模式的消息转换
  - [x] SubTask 6.2: 实现多轮处理逻辑：循环调用 `collect_messages_batch` 函数，直到所有消息处理完毕
  - [x] SubTask 6.3: 对于每一轮收集到的消息：
    - 从收集到的消息中筛选出所有role为user的消息
    - 只选取头1-2条user消息的content（优先选取前2条，如果只有1条则取1条）
    - 使用 `remove_quotes` 函数去掉这些content中的引号，用换行符拼接，作为最终的一条user消息
    - 将收集到的所有消息的完整content按顺序拼接，作为最终的一条assistant消息
  - [x] SubTask 6.4: 确保最终的消息结构为 [system, user, assistant, user, assistant, ...]（可能有多轮）

- [x] Task 7: 实现严格转述模式消息转换逻辑
  - [x] SubTask 7.1: 实现 `convert_to_strict_paraphrase_mode` 函数，处理严格转述模式的消息转换
  - [x] SubTask 7.2: 实现多轮处理逻辑：循环调用 `collect_messages_batch` 函数，直到所有消息处理完毕
  - [x] SubTask 7.3: 对于每一轮收集到的消息：
    - 从收集到的消息中筛选出所有role为user的消息
    - 使用 `remove_quotes` 函数去掉所有这些content中的引号，用换行符拼接，作为最终的一条user消息
    - 将收集到的所有消息的完整content按顺序拼接，作为最终的一条assistant消息
  - [x] SubTask 7.4: 确保最终的消息结构为 [system, user, assistant, user, assistant, ...]（可能有多轮）

- [x] Task 8: 集成新模式到主处理流程
  - [x] SubTask 8.1: 修改 `process_jsonl_file` 函数，根据 `mode` 参数选择不同的转换逻辑
  - [x] SubTask 8.2: 当 `mode` 为 `normal` 时，使用现有的转换逻辑（包括调用 `adjust_first_message_role`）
  - [x] SubTask 8.3: 当 `mode` 为 `paraphrase` 时，使用转述模式的转换逻辑（不调用 `adjust_first_message_role`）
  - [x] SubTask 8.4: 当 `mode` 为 `strict-paraphrase` 时，使用严格转述模式的转换逻辑（不调用 `adjust_first_message_role`）
  - [x] SubTask 8.5: 确保reasoning_content的生成逻辑在新模式下也能正常工作（如果需要）
  - [x] SubTask 8.6: 确保 `generate_task_description` 函数能够根据模式生成不同的任务描述

- [x] Task 9: 更新README文档
  - [x] SubTask 9.1: 在README.md的2-1步骤部分添加新模式的说明
  - [x] SubTask 9.2: 说明 `--mode` 参数的用法和三种模式的区别
  - [x] SubTask 9.3: 说明 `--min-chars` 参数的用法
  - [x] SubTask 9.4: 说明消息收集时必须以assistant结尾的规则
  - [x] SubTask 9.5: 说明转述模式和严格转述模式的System消息构建差异
  - [x] SubTask 9.6: 说明首条消息角色调整规则在不同模式下的差异
  - [x] SubTask 9.7: 说明多轮对话的处理方式
  - [x] SubTask 9.8: 添加使用示例

# Task Dependencies
- [Task 2] depends on [Task 1]
- [Task 3] depends on [Task 1]
- [Task 4] depends on [Task 1]
- [Task 5] depends on [Task 1]
- [Task 6] depends on [Task 2, Task 3, Task 4, Task 5]
- [Task 7] depends on [Task 2, Task 3, Task 4, Task 5]
- [Task 8] depends on [Task 6, Task 7]
- [Task 9] depends on [Task 8]
